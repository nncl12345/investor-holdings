"""
Parser unit tests against real, checked-in EDGAR fixtures.

The fixtures were sampled from live EDGAR filings, so these tests exercise
namespace handling, malformed-XML recovery, SGML header quirks, and the
edge cases we've actually seen in production (e.g. missing TRADING-SYMBOL).
"""

from app.services.edgar import (
    _accession_to_index_url,
    _parse_13dg_xml,
    _parse_13f_xml,
    _parse_date,
    _parse_sgml_header,
    _safe_int,
)


class TestParse13FXml:
    def test_extracts_all_positions(self, fixture_13f_xml: bytes):
        positions = _parse_13f_xml(fixture_13f_xml)
        # The sampled filing (Icahn 13F 2025-Q1) has 21 positions
        assert len(positions) == 21

    def test_first_position_shape(self, fixture_13f_xml: bytes):
        positions = _parse_13f_xml(fixture_13f_xml)
        first = positions[0]
        assert set(first.keys()) == {
            "issuer_name",
            "cusip",
            "ticker",
            "shares",
            "market_value_usd",
            "pct_of_class",
        }

    def test_cusips_are_9_chars(self, fixture_13f_xml: bytes):
        positions = _parse_13f_xml(fixture_13f_xml)
        for p in positions:
            if p["cusip"]:
                assert len(p["cusip"]) == 9

    def test_market_values_are_positive_ints(self, fixture_13f_xml: bytes):
        positions = _parse_13f_xml(fixture_13f_xml)
        for p in positions:
            if p["market_value_usd"] is not None:
                assert isinstance(p["market_value_usd"], int)
                assert p["market_value_usd"] > 0

    def test_handles_empty_input(self):
        assert _parse_13f_xml(b"") == []

    def test_handles_invalid_xml(self):
        # recover=True should gracefully return [] rather than raising
        result = _parse_13f_xml(b"<not valid xml")
        assert result == []


class TestParseSgmlHeader:
    def test_extracts_subject_name(self, fixture_sgml_header: str):
        result = _parse_sgml_header(fixture_sgml_header)
        assert result["subject_company_name"] == "Southwest Gas Holdings, Inc."

    def test_extracts_subject_cik(self, fixture_sgml_header: str):
        # CIK should be stripped of leading zeros (matches data.sec.gov URL format)
        result = _parse_sgml_header(fixture_sgml_header)
        assert result["subject_company_cik"] == "1692115"

    def test_ticker_absent_when_sgml_omits_it(self, fixture_sgml_header: str):
        # Southwest Gas fixture has no <TRADING-SYMBOL> — this is the case the
        # subject-CIK fallback in fetch_filing_index is designed to handle.
        result = _parse_sgml_header(fixture_sgml_header)
        assert result.get("subject_company_ticker") is None

    def test_only_captures_first_cik_in_subject_block(self):
        # Regression: the SGML has multiple <CIK> tags; we must pick the one
        # inside <SUBJECT-COMPANY> and not later <FILED-BY> CIKs.
        sgml = (
            "<SUBJECT-COMPANY>\n"
            "<COMPANY-DATA>\n"
            "<CONFORMED-NAME>Acme Corp\n"
            "<CIK>0000123456\n"
            "<TRADING-SYMBOL>ACME\n"
            "</COMPANY-DATA>\n"
            "</SUBJECT-COMPANY>\n"
            "<FILED-BY>\n"
            "<COMPANY-DATA>\n"
            "<CONFORMED-NAME>The Filer\n"
            "<CIK>0000999999\n"
        )
        result = _parse_sgml_header(sgml)
        assert result["subject_company_cik"] == "123456"
        assert result["subject_company_name"] == "Acme Corp"
        assert result["subject_company_ticker"] == "ACME"

    def test_empty_input_returns_empty_dict(self):
        assert _parse_sgml_header("") == {}


class TestParse13DgXml:
    def test_extracts_shares_and_pct(self, fixture_13d_primary_doc: str):
        result = _parse_13dg_xml(fixture_13d_primary_doc)
        # The sampled Icahn SCHEDULE 13D/A filing reports 48,260,832 shares / 3.63%
        assert result["shares_owned"] == 48260832
        assert result["pct_owned"] == 3.63

    def test_handles_invalid_xml(self):
        assert _parse_13dg_xml("<broken") == {}


class TestUtilities:
    def test_accession_to_index_url_roundtrip(self):
        # 0001234567-24-000001 → index URL
        url = _accession_to_index_url("0001234567-24-000001")
        assert "0001234567-24-000001-index.htm" in url
        assert "Archives/edgar/data/1234567/" in url

    def test_safe_int_strips_commas(self):
        assert _safe_int("1,234,567") == 1234567
        assert _safe_int(None) is None
        assert _safe_int("not a number") is None

    def test_parse_date_iso_prefix(self):
        from datetime import date

        assert _parse_date("2024-03-15") == date(2024, 3, 15)
        assert _parse_date("2024-03-15T12:00:00") == date(2024, 3, 15)
        assert _parse_date(None) is None
        assert _parse_date("garbage") is None
