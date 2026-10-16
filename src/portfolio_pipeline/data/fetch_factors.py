"""Kenneth French's published Fama-French factor returns — Dartmouth's
Tuck data library (mba.tuck.dartmouth.edu/pages/faculty/ken.french/),
fetched directly rather than reconstructed from fundamentals this project
doesn't have (book-to-market for HML, profitability for RMW, investment
for CMA all need balance-sheet data no source here provides). This is
standard practice, not a workaround: real factor-model use regresses
asset returns against these published series rather than re-deriving them.

Confirmed live (not assumed from memory): both the 3-factor and 5-factor
daily CSVs download as real zip files with data through the most recent
CRSP update (the file's own header states which month), date format
YYYYMMDD, values in percent (divided by 100 here before anything else
touches them).
"""
from __future__ import annotations

import io
import re
import urllib.request
import zipfile

import pandas as pd

from .fetch import USER_AGENT, DataQualityError

FF3_DAILY_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
FF5_DAILY_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"


def _fetch_zip_csv_text(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as e:  # noqa: BLE001 — network/zip errors both become a DataQualityError
        raise DataQualityError(f"Fama-French fetch failed for {url}: {e}") from e
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise DataQualityError(f"no CSV found inside zip from {url}")
        return zf.read(names[0]).decode("utf-8", errors="replace")


def parse_factor_csv(csv_text: str) -> pd.DataFrame:
    """Parses Ken French's daily-factor CSV layout: a few header text
    lines, then `,col1,col2,...` and `YYYYMMDD, v1, v2, ...` data rows,
    ending with a blank line and a copyright line. Only lines that are
    purely `YYYYMMDD` followed by numeric fields are kept — this is
    deliberately permissive about header/footer text changing slightly
    between releases, strict about what counts as a data row."""
    lines = csv_text.splitlines()
    header_idx = next((i for i, line in enumerate(lines) if re.match(r"^,\s*\S", line)), None)
    if header_idx is None:
        raise DataQualityError("could not find the column-header row in Fama-French CSV")
    columns = [c.strip() for c in lines[header_idx].split(",")][1:]

    rows = []
    for line in lines[header_idx + 1:]:
        parts = line.split(",")
        if len(parts) != len(columns) + 1:
            continue
        date_str = parts[0].strip()
        if not re.match(r"^\d{8}$", date_str):
            continue
        try:
            values = [float(p.strip()) for p in parts[1:]]
        except ValueError:
            continue
        rows.append((date_str, values))

    if len(rows) < 100:
        raise DataQualityError(f"only {len(rows)} data rows parsed — layout may have changed")

    dates = pd.to_datetime([r[0] for r in rows], format="%Y%m%d")
    data = pd.DataFrame([r[1] for r in rows], index=dates, columns=columns)
    return data / 100.0  # the source reports percent, e.g. 0.09 means 0.09%


def fetch_ff3_daily() -> pd.DataFrame:
    return parse_factor_csv(_fetch_zip_csv_text(FF3_DAILY_URL))


def fetch_ff5_daily() -> pd.DataFrame:
    return parse_factor_csv(_fetch_zip_csv_text(FF5_DAILY_URL))
