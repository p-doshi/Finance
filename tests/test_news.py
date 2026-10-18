from portfolio_pipeline.data.news import (
    NewsItem,
    combine_news,
    filter_by_date_range,
    parse_rss,
    parse_sec_filings,
    score_sentiment,
)

YAHOO_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title><![CDATA[Apple hits record high as iPhone demand surges]]></title>
<link>https://finance.yahoo.com/a1?.tsrc=rss</link>
<pubDate>Fri, 17 Oct 2026 15:00:00 +0000</pubDate>
</item>
<item>
<title>Plain title with &amp; entity</title>
<link>https://finance.yahoo.com/a2</link>
<pubDate>Thu, 16 Oct 2026 09:00:00 +0000</pubDate>
</item>
</channel></rss>"""


def test_parse_rss_extracts_title_link_date():
    items = parse_rss(YAHOO_RSS_SAMPLE, "yahoo")
    assert len(items) == 2
    assert items[0].title == "Apple hits record high as iPhone demand surges"
    assert items[0].link == "https://finance.yahoo.com/a1?.tsrc=rss"
    assert items[0].published_at == "2026-10-17"
    assert items[0].source == "yahoo"


def test_parse_rss_decodes_html_entities():
    items = parse_rss(YAHOO_RSS_SAMPLE, "yahoo")
    assert items[1].title == "Plain title with & entity"


def test_parse_rss_skips_items_missing_title_or_link():
    xml = """<rss><channel><item><title>No link here</title></item></channel></rss>"""
    assert parse_rss(xml, "yahoo") == []


def test_parse_rss_tolerates_malformed_xml():
    assert parse_rss("not xml at all <<<", "yahoo") == []


def test_parse_rss_attaches_sentiment():
    items = parse_rss(YAHOO_RSS_SAMPLE, "yahoo")
    assert items[0].sentiment_label == "positive"
    assert items[0].sentiment_compound > 0


def test_score_sentiment_positive_financial_headline():
    # the exact case plain VADER misclassified as negative before the
    # finance-lexicon patch (checked directly, see news.py's module
    # docstring) -- this test pins that fix in place
    compound, label = score_sentiment("Apple hits record high as iPhone demand surges")
    assert label == "positive"
    assert compound > 0


def test_score_sentiment_negative_financial_headline():
    compound, label = score_sentiment("Company plunges after guidance cut and lawsuit")
    assert label == "negative"
    assert compound < 0


def test_score_sentiment_neutral_headline():
    compound, label = score_sentiment("Company reports quarterly earnings in line with expectations")
    assert label == "neutral"
    assert compound == 0


def test_score_sentiment_thresholds_match_vader_defaults():
    # labels must be a pure function of VADER's own documented cutoffs,
    # not a project-specific tuning
    for text in ["ok", "fine", "the stock exists"]:
        compound, label = score_sentiment(text)
        if compound >= 0.05:
            assert label == "positive"
        elif compound <= -0.05:
            assert label == "negative"
        else:
            assert label == "neutral"


SEC_SUBMISSIONS_SAMPLE = {
    "cik": 320193,
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "8-K", "4"],
            "filingDate": ["2026-07-30", "2026-07-01", "2024-01-03", "2026-06-01"],
            "accessionNumber": ["0000320193-26-000018", "0000320193-26-000010", "0001140361-24-000001", "0000320193-26-000005"],
            "primaryDocument": ["aapl-20260730.htm", "aapl-10q.htm", "ef2024_8k.htm", "form4.htm"],
        }
    },
}


def test_parse_sec_filings_filters_by_form():
    items = parse_sec_filings(SEC_SUBMISSIONS_SAMPLE, ("8-K",), None, None)
    assert len(items) == 2
    assert all("8-K" in item.title for item in items)


def test_parse_sec_filings_filters_by_date_range():
    items = parse_sec_filings(SEC_SUBMISSIONS_SAMPLE, ("8-K",), "2026-01-01", "2026-12-31")
    assert len(items) == 1
    assert items[0].published_at == "2026-07-30"


def test_parse_sec_filings_builds_correct_filing_url():
    items = parse_sec_filings(SEC_SUBMISSIONS_SAMPLE, ("8-K",), "2024-01-01", "2024-01-31")
    assert items[0].link == "https://www.sec.gov/Archives/edgar/data/320193/000114036124000001/ef2024_8k.htm"


def test_parse_sec_filings_empty_when_no_match():
    assert parse_sec_filings(SEC_SUBMISSIONS_SAMPLE, ("10-K",), None, None) == []


def _item(title, source, date, link=None):
    return NewsItem(title=title, link=link or f"https://x/{title}", source=source, published_at=date,
                     sentiment_compound=0.0, sentiment_label="neutral")


def test_combine_news_dedupes_by_normalized_title_across_sources():
    by_source = {
        "yahoo": [_item("Apple Hits Record High!", "yahoo", "2026-10-17")],
        "google_news": [_item("apple hits record high", "google_news", "2026-10-17", link="https://other")],
    }
    combined = combine_news(by_source)
    assert len(combined) == 1


def test_combine_news_sorts_by_date_descending():
    by_source = {
        "yahoo": [_item("Old story", "yahoo", "2026-01-01"), _item("New story", "yahoo", "2026-10-17")],
    }
    combined = combine_news(by_source)
    assert [i.title for i in combined] == ["New story", "Old story"]


def test_combine_news_respects_limit():
    by_source = {"yahoo": [_item(f"story {i}", "yahoo", "2026-01-01") for i in range(30)]}
    assert len(combine_news(by_source, limit=5)) == 5


def test_combine_news_undated_items_sort_last():
    by_source = {
        "sec_edgar": [_item("Dated", "sec_edgar", "2026-01-01"), _item("Undated", "sec_edgar", None)],
    }
    combined = combine_news(by_source)
    assert [i.title for i in combined] == ["Dated", "Undated"]


def test_filter_by_date_range_drops_items_outside_range():
    # the exact bug this exists to fix: Yahoo returns today's headlines
    # regardless of the requested range, which swamped real historical
    # results after date-descending sort + limit truncation (checked
    # directly against the live API before this filter was added)
    items = [
        _item("Today's unrelated story", "yahoo", "2026-10-17"),
        _item("The actually-requested story", "yahoo", "2024-01-05"),
    ]
    filtered = filter_by_date_range(items, "2024-01-01", "2024-01-10")
    assert [i.title for i in filtered] == ["The actually-requested story"]


def test_filter_by_date_range_keeps_undated_items():
    items = [_item("No date", "yahoo", None)]
    assert filter_by_date_range(items, "2024-01-01", "2024-01-10") == items


def test_filter_by_date_range_noop_when_no_range_given():
    items = [_item("Anything", "yahoo", "2026-01-01")]
    assert filter_by_date_range(items, None, None) == items
