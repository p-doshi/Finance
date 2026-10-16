import io
import zipfile
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from portfolio_pipeline.data.fetch import DataQualityError
from portfolio_pipeline.data.fetch_factors import _fetch_zip_csv_text, parse_factor_csv


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _zip_bytes(filename: str, content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()

HEADER = (
    "This file was created by using the 202608 CRSP database.\n"
    "The Tbill return is the simple daily rate that, over the number of trading days\n"
    "compounds to 1-month TBill rate.\n"
    "\n"
    ",Mkt-RF,SMB,HML,RF\n"
)
FOOTER = "\nCopyright 2026 Eugene F. Fama and Kenneth R. French\n"


def _make_csv(n_rows=120):
    d = date(1926, 7, 1)
    rows = []
    for _ in range(n_rows):
        rows.append(f"{d.strftime('%Y%m%d')},    0.09,   -0.23,   -0.28,    0.01")
        d += timedelta(days=1)
    return HEADER + "\n".join(rows) + FOOTER


def test_parse_factor_csv_known_values():
    csv_text = HEADER + "19260701,    0.09,   -0.23,   -0.28,    0.01\n" * 120 + FOOTER
    df = parse_factor_csv(csv_text)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    # 0.09 (percent) -> 0.0009 (decimal)
    assert df["Mkt-RF"].iloc[0] == pytest.approx(0.0009)
    assert df["SMB"].iloc[0] == pytest.approx(-0.0023)
    assert len(df) == 120


def test_parse_factor_csv_ignores_header_and_footer_text():
    csv_text = _make_csv(110)
    df = parse_factor_csv(csv_text)
    assert len(df) == 110
    # nothing from the header/footer text leaked in as a spurious row
    assert all(df.index.year >= 1900)


def test_parse_factor_csv_rejects_too_few_rows():
    csv_text = HEADER + "19260701,    0.09,   -0.23,   -0.28,    0.01\n" * 5 + FOOTER
    with pytest.raises(DataQualityError, match="only 5 data rows"):
        parse_factor_csv(csv_text)


def test_parse_factor_csv_rejects_missing_header():
    csv_text = "garbage\nmore garbage\n" + "19260701,0.09,-0.23,-0.28,0.01\n" * 120
    with pytest.raises(DataQualityError, match="column-header"):
        parse_factor_csv(csv_text)


def test_parse_factor_csv_skips_rows_with_malformed_date():
    rows = _make_csv(110).splitlines()
    rows.insert(5, "not-a-date,0.09,-0.23,-0.28,0.01")  # 10 real header/data rows precede this
    csv_text = "\n".join(rows)
    df = parse_factor_csv(csv_text)
    assert len(df) == 110  # the malformed row was skipped, not counted or crashed on


def test_parse_factor_csv_skips_rows_with_non_numeric_values():
    rows = _make_csv(110).splitlines()
    rows.insert(5, "19270101,oops,-0.23,-0.28,0.01")
    csv_text = "\n".join(rows)
    df = parse_factor_csv(csv_text)
    assert len(df) == 110


def test_fetch_zip_csv_text_extracts_csv_from_a_real_zip():
    body = _zip_bytes("factors.csv", "hello,world\n1,2\n")
    with patch("portfolio_pipeline.data.fetch_factors.urllib.request.urlopen",
               return_value=_FakeResponse(body)):
        text = _fetch_zip_csv_text("https://example.com/fake.zip")
    assert text == "hello,world\n1,2\n"


def test_fetch_zip_csv_text_raises_if_zip_has_no_csv():
    body = _zip_bytes("readme.txt", "not a csv")
    with patch("portfolio_pipeline.data.fetch_factors.urllib.request.urlopen",
               return_value=_FakeResponse(body)), \
            pytest.raises(DataQualityError, match="no CSV found"):
        _fetch_zip_csv_text("https://example.com/fake.zip")


def test_fetch_zip_csv_text_wraps_network_error():
    with patch("portfolio_pipeline.data.fetch_factors.urllib.request.urlopen",
               side_effect=OSError("connection refused")), \
            pytest.raises(DataQualityError, match="fetch failed"):
        _fetch_zip_csv_text("https://example.com/fake.zip")


def test_parse_factor_csv_handles_5factor_layout():
    header5 = ",Mkt-RF,SMB,HML,RMW,CMA,RF\n"
    csv_text = HEADER.rsplit(",", 1)[0].rsplit("\n", 1)[0] + "\n" + header5
    csv_text += ("19630701,   -0.67,    0.00,   -0.33,   -0.01,    0.16,    0.01\n") * 110
    csv_text += FOOTER
    df = parse_factor_csv(csv_text)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    assert df["RMW"].iloc[0] == pytest.approx(-0.0001)
