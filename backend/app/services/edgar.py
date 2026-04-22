"""
EDGAR ingestion service.

Two pipelines:
  1. 13D/G watcher  — polls EDGAR full-text search for activist/passive disclosures
  2. 13F ingester   — fetches quarterly holdings reports for tracked investors

SEC EDGAR rate limit: 10 requests/second. We stay well under that.
User-Agent header is required by SEC policy (https://www.sec.gov/developer).
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

import httpx
from lxml import etree
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.filing import Filing, FilingType
from app.models.holding import ChangeType, Holding
from app.models.investor import Investor

logger = logging.getLogger(__name__)

# EDGAR API endpoints
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

# 13D/G form types we care about
ACTIVIST_FORMS = [
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
    # EDGAR also uses full "SCHEDULE" prefix in submissions JSON
    "SCHEDULE 13D",
    "SCHEDULE 13D/A",
    "SCHEDULE 13G",
    "SCHEDULE 13G/A",
]
QUARTERLY_FORMS = ["13F-HR"]


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


# ---------------------------------------------------------------------------
# EDGAR search API
# ---------------------------------------------------------------------------


async def fetch_recent_activist_filings_for_investor(
    cik: str,
    since: date | None = None,
) -> list[dict]:
    """
    Fetch recent 13D/G filings for a specific investor from their submissions JSON.

    Returns normalised filing dicts ready for parse_activist_hit().
    Uses data.sec.gov/submissions which is reliable and always up to date.
    """
    if since is None:
        since = date.today() - timedelta(days=7)

    submissions = await fetch_investor_submissions(cik)
    filings = submissions.get("filings", {}).get("recent", {})

    form_types = filings.get("form", [])
    acc_numbers = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])
    report_dates = filings.get("reportDate", [])
    entity_name = submissions.get("name", "")

    results = []
    for i, form in enumerate(form_types):
        if form not in ACTIVIST_FORMS:
            continue
        filing_date = _parse_date(filing_dates[i] if i < len(filing_dates) else None)
        if filing_date and filing_date < since:
            # Submissions are newest-first; once we go past `since` we can stop
            break
        raw_acc = acc_numbers[i] if i < len(acc_numbers) else ""
        clean_acc = raw_acc.replace("-", "")
        results.append(
            {
                "accession_number": clean_acc,
                "filing_type": form,
                "filing_date": filing_date,
                "period_of_report": _parse_date(report_dates[i] if i < len(report_dates) else None),
                "filer_name": entity_name,
                "filer_cik": cik,
                "subject_company_name": None,
                "subject_company_ticker": None,
                "subject_company_cusip": None,
                "raw_url": _accession_to_index_url(raw_acc) if raw_acc else None,
            }
        )

    logger.info("Submissions scan for CIK %s returned %d 13D/G filings since %s", cik, len(results), since)
    return results


async def fetch_investor_submissions(cik: str) -> dict:
    """
    Fetch the full submission history for a filer by CIK.
    Returns the raw JSON from https://data.sec.gov/submissions/CIK{cik}.json
    """
    padded_cik = cik.zfill(10)
    url = f"{EDGAR_SUBMISSIONS_URL}/CIK{padded_cik}.json"
    async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 13D/G parsing
# ---------------------------------------------------------------------------


def parse_activist_hit(hit: dict) -> dict:
    """
    Extract structured fields from a raw EDGAR search hit for a 13D/G filing.
    Returns a normalised dict ready to be inserted as a Filing + Holding row.
    """
    source = hit.get("_source", {})
    return {
        "accession_number": hit.get("_id", "").replace("-", ""),
        "filing_type": source.get("form_type"),
        "filing_date": _parse_date(source.get("file_date")),
        "period_of_report": _parse_date(source.get("period_of_report")),
        # The filer is the investor; the subject company is the target
        "filer_name": source.get("entity_name"),
        "filer_cik": source.get("file_num"),  # not CIK but we resolve below
        # Subject company info lives in the filing index — fetched separately
        "subject_company_name": None,
        "subject_company_ticker": None,
        "subject_company_cusip": None,
        "raw_url": _accession_to_index_url(hit.get("_id", "")),
    }


async def fetch_13dg_details(index_url: str) -> dict:
    """
    Fetch position details from a 13D/G filing's primary_doc.xml.

    Newer EDGAR SCHEDULE 13D/G filings include a structured XML cover page with:
      - aggregateAmountOwned (shares)
      - percentOfClass
      - transactionPurpose (Item 4 narrative)
      - issuerCusips

    Falls back to empty dict if not available (older SC 13D/A HTML-only filings).
    """
    await asyncio.sleep(0.15)
    async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
        # Fetch the filing index HTML to find primary_doc.xml link
        resp = await client.get(index_url)
        if resp.status_code != 200:
            return {}
        html = resp.text

        # Find the primary_doc.xml URL from the index links
        xml_url = None
        from html.parser import HTMLParser

        class _LinkParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.xml_url: str | None = None

            def handle_starttag(self, tag, attrs):
                if tag == "a" and self.xml_url is None:
                    for k, v in attrs:
                        if k == "href" and "primary_doc.xml" in v and "xsl" not in v.lower():
                            self.xml_url = v

        parser = _LinkParser()
        parser.feed(html)
        xml_url = parser.xml_url
        if not xml_url:
            return {}

        if xml_url.startswith("/"):
            xml_url = f"https://www.sec.gov{xml_url}"

        await asyncio.sleep(0.15)
        resp = await client.get(xml_url)
        if resp.status_code != 200:
            return {}

    return _parse_13dg_xml(resp.text)


def _parse_13dg_xml(xml_text: str) -> dict:
    """
    Parse the primary_doc.xml cover page for a SCHEDULE 13D/G filing.
    Returns a dict with shares_owned, pct_owned, transaction_purpose, cusip.
    """
    import re

    # Strip namespace declarations for simpler parsing
    xml_text = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_text)
    xml_text = re.sub(r"<(/?)[\w]+:([\w]+)", r"<\1\2", xml_text)

    try:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_text.encode(), parser)
    except Exception:
        logger.exception("Failed to parse 13D/G primary_doc.xml")
        return {}

    def _text(tag: str) -> str | None:
        el = root.find(f".//{tag}")
        return el.text.strip() if el is not None and el.text else None

    # Aggregate position across all reporting persons
    total_shares = 0.0
    pct = None
    for person in root.findall(".//reportingPersonInfo"):
        amt_el = person.find("aggregateAmountOwned")
        if amt_el is not None and amt_el.text:
            try:
                total_shares += float(amt_el.text.strip())
            except ValueError:
                pass
        if pct is None:
            pct_el = person.find("percentOfClass")
            if pct_el is not None and pct_el.text:
                try:
                    pct = float(pct_el.text.strip())
                except ValueError:
                    pass

    result: dict = {}
    if total_shares:
        result["shares_owned"] = int(total_shares)
    if pct is not None:
        result["pct_owned"] = pct

    # CUSIP from issuerCusipNumber
    cusip_el = root.find(".//issuerCusipNumber")
    if cusip_el is not None and cusip_el.text:
        result["cusip"] = cusip_el.text.strip()

    # Transaction purpose (Item 4)
    purpose_el = root.find(".//transactionPurpose")
    if purpose_el is not None and purpose_el.text:
        result["transaction_purpose"] = purpose_el.text.strip()

    return result


async def fetch_filing_index(accession_number: str, cik: str) -> dict:
    """
    Fetch the SGML header file for a filing to extract subject company metadata.

    The .hdr.sgml file is a reliable, machine-readable source for:
      - CONFORMED-NAME (subject company name)
      - TRADING-SYMBOL (ticker)
      - CIK of the subject company

    Falls back to empty dict if unavailable.
    """
    clean_acc = accession_number.replace("-", "")
    formatted_acc = f"{clean_acc[:10]}-{clean_acc[10:12]}-{clean_acc[12:]}"
    cik_stripped = cik.lstrip("0")
    url = f"{EDGAR_ARCHIVES_URL}/{cik_stripped}/{clean_acc}/{formatted_acc}.hdr.sgml"

    await asyncio.sleep(0.15)
    async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning("SGML header not found: %s (%s)", url, resp.status_code)
            return {}

    parsed = _parse_sgml_header(resp.text)

    # Fallback: many older filings' SGML headers omit TRADING-SYMBOL even though
    # the issuer clearly has one. Look it up by the subject's CIK from the
    # per-filer submissions endpoint (which carries a `tickers` array).
    if not parsed.get("subject_company_ticker") and parsed.get("subject_company_cik"):
        ticker = await _lookup_ticker_by_cik(parsed["subject_company_cik"])
        if ticker:
            parsed["subject_company_ticker"] = ticker

    return parsed


def _parse_sgml_header(sgml: str) -> dict:
    """
    Parse the EDGAR SGML header file to extract subject company fields.

    Structure looks like:
      <SUBJECT-COMPANY>
      <COMPANY-DATA>
      <CONFORMED-NAME>Howard Hughes Holdings Inc.
      <CIK>0001981792
      <TRADING-SYMBOL>HHH
      ...
    """
    result: dict = {}
    in_subject = False

    for line in sgml.splitlines():
        line = line.strip()
        if line == "<SUBJECT-COMPANY>":
            in_subject = True
            continue
        # Stop parsing subject block when we hit the next top-level section
        if (
            in_subject
            and line.startswith("<")
            and not line.startswith("<COMPANY")
            and line in ("<FILED-BY>", "<FILER>", "</SEC-HEADER>")
        ):
            break
        if not in_subject:
            continue

        if line.startswith("<CONFORMED-NAME>"):
            result["subject_company_name"] = line[len("<CONFORMED-NAME>") :].strip()
        elif line.startswith("<TRADING-SYMBOL>"):
            result["subject_company_ticker"] = line[len("<TRADING-SYMBOL>") :].strip().upper()
        elif line.startswith("<CIK>"):
            # Keep the first CIK we see inside the SUBJECT-COMPANY block.
            # Used as a fallback key for ticker lookup when TRADING-SYMBOL is missing.
            if "subject_company_cik" not in result:
                result["subject_company_cik"] = line[len("<CIK>") :].strip().lstrip("0")

    return result


async def _lookup_ticker_by_cik(cik: str) -> str | None:
    """
    Secondary lookup: when the SGML header doesn't carry a TRADING-SYMBOL, fall
    back to data.sec.gov/submissions/CIK{cik}.json which almost always has a
    `tickers` array for the entity. Returns the first ticker or None.
    """
    if not cik:
        return None
    try:
        submissions = await fetch_investor_submissions(cik)
    except Exception:
        logger.warning("Ticker fallback lookup failed for CIK %s", cik)
        return None
    tickers = submissions.get("tickers") or []
    if tickers:
        return str(tickers[0]).upper()
    return None


# ---------------------------------------------------------------------------
# 13F parsing
# ---------------------------------------------------------------------------


async def fetch_13f_xml(accession_number: str, cik: str) -> list[dict]:
    """
    Download and parse the XML holdings report from a 13F-HR filing.
    Returns a list of position dicts, one per reported issuer.
    """
    clean_acc = accession_number.replace("-", "")
    cik_stripped = cik.lstrip("0")
    base_url = f"{EDGAR_ARCHIVES_URL}/{cik_stripped}/{clean_acc}"

    # Format accession with dashes: 000119312525282901 → 0001193125-25-282901
    formatted_acc = f"{clean_acc[:10]}-{clean_acc[10:12]}-{clean_acc[12:]}"

    async with httpx.AsyncClient(headers=_headers(), timeout=60) as client:
        # Try known filenames first before falling back to index scan
        for candidate in ("infotable.xml", "form13fInfoTable.xml"):
            url = f"{base_url}/{candidate}"
            resp = await client.get(url)
            await asyncio.sleep(0.15)
            if resp.status_code == 200:
                positions = _parse_13f_xml(resp.content)
                if positions:
                    return positions

        # Fall back: scan the filing index for any raw XML
        xml_url = await _find_13f_xml_url(base_url, formatted_acc, client)
        if not xml_url:
            logger.warning("Could not locate 13F XML for %s", accession_number)
            return []
        await asyncio.sleep(0.15)
        resp = await client.get(xml_url)
        resp.raise_for_status()

    return _parse_13f_xml(resp.content)


async def _find_13f_xml_url(base_url: str, formatted_acc: str, client: httpx.AsyncClient) -> str | None:
    """Scan the filing index page to find the raw infotable XML document URL.

    EDGAR index URLs use the dash-formatted accession number, e.g.:
      .../000119312525282901/0001193125-25-282901-index.htm

    We skip xslForm13F_X02/* links — those are XSLT-transformed HTML views,
    not the raw XML we need.
    """
    index_url = f"{base_url}/{formatted_acc}-index.htm"
    try:
        resp = await client.get(index_url)
        await asyncio.sleep(0.15)
        resp.raise_for_status()
        tree = etree.fromstring(resp.content, etree.HTMLParser())
        links = tree.xpath("//a/@href")

        # Priority 1: any XML with "infotable" in the name, not in an xsl subdirectory
        for link in links:
            if link.endswith(".xml") and "infotable" in link.lower() and "xslform" not in link.lower():
                return f"https://www.sec.gov{link}" if link.startswith("/") else link

        # Priority 2: any XML not inside an xsl subdirectory
        for link in links:
            if link.endswith(".xml") and "xslform" not in link.lower() and "primary_doc" not in link.lower():
                return f"https://www.sec.gov{link}" if link.startswith("/") else link

    except Exception:
        logger.exception("Failed to find 13F XML URL at %s", index_url)
    return None


def _parse_13f_xml(xml_bytes: bytes) -> list[dict]:
    """
    Parse an EDGAR 13F infotable XML into a list of position dicts.

    The 13F XML schema uses namespaces; we strip them for simpler XPath.
    Uses lxml recover mode to handle minor malformations.
    """
    positions = []
    try:
        import re

        xml_str = xml_bytes.decode(errors="replace")
        # Strip all XML namespace declarations so element names are bare
        xml_str = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_str)
        # Also strip namespace prefixes from tag names (e.g. ns1:infoTable → infoTable)
        xml_str = re.sub(r"<(/?)[\w]+:([\w]+)", r"<\1\2", xml_str)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_str.encode(), parser)

        for info in root.iter("infoTable"):

            def txt(tag: str) -> str | None:
                el = info.find(tag)
                return el.text.strip() if el is not None and el.text else None

            positions.append(
                {
                    "issuer_name": txt("nameOfIssuer"),
                    "cusip": txt("cusip"),
                    "ticker": None,  # 13F doesn't include ticker — enrich later
                    "shares": _safe_int(txt("sshPrnamt")),
                    "market_value_usd": _safe_int(txt("value")),
                    "pct_of_class": None,
                }
            )
    except Exception:
        logger.exception("Failed to parse 13F XML")

    logger.info("Parsed %d positions from 13F XML", len(positions))
    return positions


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------


async def upsert_investor(db: AsyncSession, cik: str, name: str) -> Investor:
    """Get or create an Investor row by CIK."""
    from sqlalchemy import select

    result = await db.execute(select(Investor).where(Investor.cik == cik))
    investor = result.scalar_one_or_none()
    if investor is None:
        investor = Investor(cik=cik, name=name)
        db.add(investor)
        await db.flush()
    return investor


async def filing_exists(db: AsyncSession, accession_number: str) -> bool:
    """Return True if we've already ingested this filing."""
    from sqlalchemy import select

    result = await db.execute(select(Filing.id).where(Filing.accession_number == accession_number))
    return result.scalar_one_or_none() is not None


async def persist_activist_filing(
    db: AsyncSession,
    investor: Investor,
    parsed: dict,
    index_meta: dict,
) -> Filing:
    """Insert a 13D/G filing and its single holding row."""
    # Fetch structured position details from primary_doc.xml if available
    xml_details: dict = {}
    raw_url = parsed.get("raw_url")
    if raw_url:
        try:
            xml_details = await fetch_13dg_details(raw_url)
        except Exception:
            logger.warning("Could not fetch 13D/G XML details for %s", parsed.get("accession_number"))

    # CUSIP: prefer XML (issuerCusipNumber) over SGML (often missing)
    cusip = xml_details.get("cusip") or index_meta.get("subject_company_cusip")

    # Generate a clean investment thesis from Item 4 text via Claude
    transaction_summary: str | None = None
    transaction_purpose = xml_details.get("transaction_purpose")
    if transaction_purpose:
        try:
            from app.services.llm import summarize_transaction_purpose

            transaction_summary = await summarize_transaction_purpose(transaction_purpose)
        except Exception:
            logger.warning("Failed to summarize transaction purpose for %s", parsed.get("accession_number"))

    filing = Filing(
        investor_id=investor.id,
        filing_type=FilingType(parsed["filing_type"]),
        accession_number=parsed["accession_number"],
        filing_date=parsed["filing_date"],
        period_of_report=parsed.get("period_of_report"),
        subject_company_name=index_meta.get("subject_company_name"),
        subject_company_ticker=index_meta.get("subject_company_ticker"),
        subject_company_cusip=cusip,
        raw_url=raw_url,
        shares_owned=xml_details.get("shares_owned"),
        pct_owned=xml_details.get("pct_owned"),
        transaction_purpose=transaction_purpose,
        transaction_summary=transaction_summary,
    )
    db.add(filing)
    await db.flush()

    if filing.subject_company_name:
        holding = Holding(
            filing_id=filing.id,
            issuer_name=filing.subject_company_name,
            ticker=filing.subject_company_ticker,
            cusip=cusip,
            shares=xml_details.get("shares_owned"),
            pct_of_class=xml_details.get("pct_owned"),
            change_type=ChangeType.NEW,
        )
        db.add(holding)

    await db.commit()
    return filing


async def persist_13f_holdings(
    db: AsyncSession,
    filing: Filing,
    positions: list[dict],
) -> None:
    """Bulk-insert 13F position rows for a filing."""
    for pos in positions:
        holding = Holding(
            filing_id=filing.id,
            issuer_name=pos["issuer_name"] or "Unknown",
            ticker=pos.get("ticker"),
            cusip=pos.get("cusip"),
            shares=pos.get("shares"),
            market_value_usd=pos.get("market_value_usd"),
            pct_of_class=pos.get("pct_of_class"),
        )
        db.add(holding)
    await db.commit()
    logger.info("Persisted %d holdings for filing %s", len(positions), filing.accession_number)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def _accession_to_index_url(accession_id: str) -> str:
    """Convert EDGAR accession ID (e.g. 0001234567-24-000001) to its index URL."""
    clean = accession_id.replace("-", "")
    cik_part = clean[:10].lstrip("0")
    formatted = f"{clean[:10]}-{clean[10:12]}-{clean[12:]}"
    return f"{EDGAR_ARCHIVES_URL}/{cik_part}/{clean}/{formatted}-index.htm"
