"""Per-ticker news from three independent free sources, each queried
without an API key, plus a sentiment score computed locally rather than
trusting a vendor's figure (no vendor here provides one for free with
clear redistribution terms anyway -- checked directly: Alpha Vantage's
NEWS_SENTIMENT free/demo tier does return one, but its terms around
redisplaying that data in a public-facing app aren't verifiable from the
published docs, so this doesn't depend on it).

Sources:
  - Yahoo Finance's public RSS feed -- recent headlines, no date-range
    query support (same source already used elsewhere in this project).
  - Google News RSS -- supports real historical search via `after:`/
    `before:` query operators, confirmed by fetching a date-bounded query
    and checking the returned pubDates actually fall inside the window.
  - SEC EDGAR -- official, free, no key, and the most precise of the
    three for company-specific material events: resolves a ticker to its
    CIK via SEC's own published mapping (sec.gov/files/company_tickers.json)
    then reads that company's real filing history
    (data.sec.gov/submissions/CIK##########.json), rather than a free-text
    search that could false-positive on an unrelated use of the word.

Each fetcher is independent and wrapped so one source failing doesn't
take down the others -- see combine_news.

Sentiment: VADER (Hutto & Gilbert, 2014), a lexicon/rule-based analyzer
with no training step and no network call, run on each headline's title.
VADER's own lexicon is tuned for general/social-media text, which
measurably misclassifies financial headlines -- checked directly:
"Apple hits record high as iPhone demand surges" scored as *negative*
(-0.128) under plain VADER, because words like "record high" and "surges"
simply aren't in its general-purpose dictionary. FINANCE_LEXICON is a
small, explicit, hand-curated set of common financial terms added to
VADER's lexicon (the library's own documented extension mechanism) to
correct exactly this class of miss -- it is not a peer-reviewed financial
NLP model, just a targeted patch for a demonstrated gap, and should be
read as a rough directional signal, not a trading input.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

USER_AGENT = "portfolio-pipeline/0.1 (personal research use)"
# SEC's fair-access policy (sec.gov/os/webmaster-faq#developers) asks for a
# descriptive User-Agent naming the app and a contact address, specifically
# for its own endpoints -- used only for the two sec.gov calls below, not
# the other sources. Checked directly during development: repeated test
# calls (ticker-map + submissions, several times over a few minutes, from
# more than one IP while verifying this feature) started returning 403
# partway through, consistent with SEC's stated rate limiting rather than
# a one-off bug -- the two calls this module makes per request (one ticker
# lookup, one submissions fetch) are within their documented limits for
# any one real user, but are worth being honest about: this source can
# fail under heavier or clustered load, which is exactly why it's wrapped
# the same as the other two and reported in source_errors rather than
# allowed to take the whole response down.
# Using the project's real public repo as the contact point rather than a
# fabricated email address -- SEC's policy wants something that actually
# identifies the requester, and a made-up "contact@example.com" wouldn't.
SEC_USER_AGENT = "portfolio-pipeline research project (https://github.com/p-doshi/Finance)"

# See module docstring: corrects demonstrated misclassifications in
# VADER's general-purpose lexicon on financial headline phrasing.
# Valences on VADER's own -4..+4 scale.
FINANCE_LEXICON = {
    "surge": 2.5, "surges": 2.5, "surging": 2.5,
    "soar": 2.8, "soars": 2.8, "soaring": 2.8,
    "rally": 2.0, "rallies": 2.0, "rallying": 2.0,
    "record high": 2.5, "all-time high": 2.5,
    "beat": 1.8, "beats": 1.8, "beat estimates": 2.5, "tops estimates": 2.2,
    "upgrade": 2.0, "upgraded": 2.0, "upgrades": 2.0, "outperform": 2.0,
    "raises guidance": 2.3, "raised guidance": 2.3, "raises forecast": 2.3,
    "plunge": -2.8, "plunges": -2.8, "plunging": -2.8,
    "slump": -2.2, "slumps": -2.2, "slumping": -2.2,
    "crash": -3.0, "crashes": -3.0, "crashing": -3.0,
    "downgrade": -2.0, "downgraded": -2.0, "downgrades": -2.0,
    "miss": -1.5, "misses": -1.5, "miss estimates": -2.3, "misses estimates": -2.3,
    "guidance cut": -2.3, "cuts guidance": -2.3, "cuts forecast": -2.3,
    "layoffs": -2.0, "bankruptcy": -3.0, "lawsuit": -1.5,
    "investigation": -1.8, "recall": -1.8, "probe": -1.5,
    "sinks": -2.0, "sinking": -2.0, "tumbles": -2.3, "tumbling": -2.3, "slides": -1.3,
}

_analyzer = SentimentIntensityAnalyzer()
_analyzer.lexicon.update(FINANCE_LEXICON)

SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}"


@dataclass
class NewsItem:
    title: str
    link: str
    source: str  # "yahoo" | "google_news" | "sec_edgar"
    published_at: str | None  # ISO date (YYYY-MM-DD), None if unparseable
    sentiment_compound: float | None
    sentiment_label: str | None  # "positive" | "neutral" | "negative" | None


def score_sentiment(text: str) -> tuple[float, str]:
    """VADER + FINANCE_LEXICON compound score and label. Thresholds are
    VADER's own documented defaults (compound >= 0.05 positive, <= -0.05
    negative, else neutral) -- not tuned by this project."""
    compound = _analyzer.polarity_scores(text)["compound"]
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return compound, label


def _with_sentiment(title: str, link: str, source: str, published_at: str | None) -> NewsItem:
    compound, label = score_sentiment(title)
    return NewsItem(
        title=title, link=link, source=source, published_at=published_at,
        sentiment_compound=round(compound, 4), sentiment_label=label,
    )


# ---- Parsing (pure -- takes already-fetched text/JSON, no network) ----


def _rss_pubdate_to_iso(pubdate: str | None) -> str | None:
    if not pubdate:
        return None
    try:
        return parsedate_to_datetime(pubdate).date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_rss(xml_text: str, source: str) -> list[NewsItem]:
    """Parses a standard RSS 2.0 <item> list (both Yahoo's and Google
    News' feeds use this shape) with the stdlib's XML parser rather than
    hand-rolled regex -- CDATA and entity decoding come for free and
    correctly, unlike a regex-based extraction."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pubdate = item.findtext("pubDate")
        if not title or not link:
            continue
        items.append(_with_sentiment(title, link, source, _rss_pubdate_to_iso(pubdate)))
    return items


def parse_sec_filings(submissions: dict, forms: tuple[str, ...], start_date: str | None, end_date: str | None) -> list[NewsItem]:
    """Pure: takes an already-fetched submissions.json dict (SEC's shape --
    parallel arrays under filings.recent, see module docstring) and the
    company's display name, returns matching filings as NewsItem."""
    recent = submissions.get("filings", {}).get("recent", {})
    company = submissions.get("name", "")
    cik = submissions.get("cik")
    items = []
    forms_list = recent.get("form", [])
    for i, form in enumerate(forms_list):
        if form not in forms:
            continue
        filing_date = recent["filingDate"][i]
        if start_date and filing_date < start_date:
            continue
        if end_date and filing_date > end_date:
            continue
        accession = recent["accessionNumber"][i]
        doc = recent["primaryDocument"][i]
        link = SEC_FILING_URL.format(cik=int(cik), accession_nodash=accession.replace("-", ""), doc=doc)
        title = f"{company}: {form} filed {filing_date}"
        items.append(_with_sentiment(title, link, "sec_edgar", filing_date))
    return items


# ---- Fetching (network + parsing) ----


def _get(url: str, timeout: float, user_agent: str = USER_AGENT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def fetch_yahoo_news(ticker: str, timeout: float = 15.0) -> list[NewsItem]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(ticker)}&region=US&lang=en-US"
    return parse_rss(_get(url, timeout), "yahoo")


def fetch_google_news(query: str, start_date: str | None = None, end_date: str | None = None, timeout: float = 15.0) -> list[NewsItem]:
    """start_date/end_date (YYYY-MM-DD) use Google's own `after:`/`before:`
    search operators -- confirmed working by requesting a bounded range and
    checking every returned pubDate actually falls inside it, not just
    today's news leaking through."""
    q = query
    if start_date:
        q += f" after:{start_date}"
    if end_date:
        q += f" before:{end_date}"
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"
    return parse_rss(_get(url, timeout), "google_news")


def fetch_sec_filings(
    ticker: str,
    forms: tuple[str, ...] = ("8-K",),
    start_date: str | None = None,
    end_date: str | None = None,
    timeout: float = 15.0,
) -> list[NewsItem]:
    ticker_map_raw = _get(SEC_TICKER_MAP_URL, timeout, user_agent=SEC_USER_AGENT)
    ticker_map = json.loads(ticker_map_raw)
    cik = None
    for row in ticker_map.values():
        if row["ticker"].upper() == ticker.upper():
            cik = row["cik_str"]
            break
    if cik is None:
        return []
    submissions = json.loads(_get(SEC_SUBMISSIONS_URL.format(cik=cik), timeout, user_agent=SEC_USER_AGENT))
    return parse_sec_filings(submissions, forms, start_date, end_date)


_TITLE_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_title(title: str) -> str:
    return _TITLE_NORMALIZE_RE.sub(" ", title.lower()).strip()


def filter_by_date_range(items: list[NewsItem], start_date: str | None, end_date: str | None) -> list[NewsItem]:
    """Yahoo's RSS feed has no date-range query of its own (see module
    docstring) -- it always returns its latest ~20 items regardless of what
    range was asked for. Without this filter, a request for a historical
    week got swamped by today's unrelated Yahoo headlines once everything
    was sorted by date and truncated to `limit`, since "today" always
    sorts above a requested date in the past. Applied uniformly to every
    source's output rather than trusting each source to have filtered
    correctly itself. An item with no parseable date is kept rather than
    dropped -- an unknown date isn't evidence it's outside the range."""
    if start_date is None and end_date is None:
        return items
    out = []
    for item in items:
        if item.published_at is None:
            out.append(item)
            continue
        if start_date and item.published_at < start_date:
            continue
        if end_date and item.published_at > end_date:
            continue
        out.append(item)
    return out


def combine_news(items_by_source: dict[str, list[NewsItem]], limit: int = 20) -> list[NewsItem]:
    """Dedupes by normalized title (the same real-world story often runs
    on multiple outlets with near-identical headlines) and sorts by
    published date descending, most recent first; items with an
    unparseable date sort last rather than crowding out dated ones."""
    seen = set()
    combined = []
    for items in items_by_source.values():
        for item in items:
            key = _normalize_title(item.title)
            if key in seen:
                continue
            seen.add(key)
            combined.append(item)
    combined.sort(key=lambda it: it.published_at or "0000-00-00", reverse=True)
    return combined[:limit]


def get_news(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    timeout: float = 15.0,
) -> tuple[list[NewsItem], dict[str, str]]:
    """Queries all three sources, each independently -- one failing
    doesn't take the others down. Defaults to the trailing 30 days when no
    range is given, so a plain "show me the news" call isn't dominated by
    ancient stories. Returns (items, errors_by_source) so a partial
    failure is reported, not silently hidden."""
    if start_date is None and end_date is None:
        end_date = datetime.now(timezone.utc).date().isoformat()
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

    items_by_source: dict[str, list[NewsItem]] = {}
    errors: dict[str, str] = {}

    try:
        items_by_source["yahoo"] = fetch_yahoo_news(ticker, timeout)
    except (urllib.error.URLError, TimeoutError) as e:
        errors["yahoo"] = str(e)

    try:
        items_by_source["google_news"] = fetch_google_news(f"{ticker} stock", start_date, end_date, timeout)
    except (urllib.error.URLError, TimeoutError) as e:
        errors["google_news"] = str(e)

    try:
        items_by_source["sec_edgar"] = fetch_sec_filings(ticker, start_date=start_date, end_date=end_date, timeout=timeout)
    except (urllib.error.URLError, TimeoutError) as e:
        errors["sec_edgar"] = str(e)

    # Google/SEC already filter server-side; re-filtering them here is a
    # harmless no-op. Yahoo doesn't filter at all -- this is the only thing
    # standing between "requested 2024" and getting today's headlines back
    # (see filter_by_date_range's docstring for the bug this fixes).
    items_by_source = {
        source: filter_by_date_range(items, start_date, end_date) for source, items in items_by_source.items()
    }

    return combine_news(items_by_source, limit), errors


def news_item_to_dict(item: NewsItem) -> dict:
    return asdict(item)
