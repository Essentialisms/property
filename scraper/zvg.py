"""Scrape Berlin foreclosure auctions from zvg-portal.de.

Each Bundesland's auction list is one POST request away — the search
results page has all the data we need (case number, court, type+address,
Verkehrswert, auction date) inline. No detail-page navigation required.

Listings are tagged `sale_type='auction'` so the UI can flag them.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from analyzer.districts import identify_district
from scraper.models import Property

logger = logging.getLogger(__name__)

BASE = "https://www.zvg-portal.de"
SEARCH_URL = f"{BASE}/index.php?button=Suchen&all=1"  # all=1 returns every case on one page
FORM_URL = f"{BASE}/index.php?button=Termine+suchen&land_abk=be"
LAND_ABK = "be"  # Berlin
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

MONTHS_DE = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
}

# Map the German object type words to our existing property_type enum.
TYPE_KEYWORDS = (
    ("apartment", ("eigentumswohnung", "wohnungseigentum", "wohnung")),
    ("house", ("einfamilienhaus", "zweifamilienhaus", "mehrfamilienhaus",
                "doppelhaus", "reihenhaus", "haus", "villa", "bungalow")),
    ("land", ("grundstück", "grundstueck", "bauplatz", "unbebautes")),
)


def _classify_type(text: str) -> str:
    t = text.lower()
    for prop_type, keywords in TYPE_KEYWORDS:
        for kw in keywords:
            if kw in t:
                return prop_type
    return "land"


def _parse_de_money(text: str) -> float | None:
    """'730.000,00' or '730.000,00 €' → 730000.0. Falls back to first
    plausible number when the cell is a complex summary (joint shares etc.).
    """
    matches = re.findall(r"([\d.]+,\d{2})", text)
    if not matches:
        matches = re.findall(r"\b(\d{1,3}(?:\.\d{3})+)\b", text)
    if not matches:
        return None
    s = matches[0].replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_termin(text: str) -> str | None:
    """'Dienstag, 02. Juni 2026, 11:00 Uhr' → '2026-06-02'."""
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s*(\d{4})", text)
    if not m:
        return None
    day, month_name, year = m.group(1), m.group(2), m.group(3)
    month = MONTHS_DE.get(month_name)
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day)).date().isoformat()
    except ValueError:
        return None


def fetch_results(session: requests.Session | None = None) -> str:
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", USER_AGENT)
    # Warm the form first so the session cookie is set
    s.get(FORM_URL, timeout=15)
    resp = s.post(
        SEARCH_URL,
        data={"land_abk": LAND_ABK, "order_by": "", "art": ""},
        timeout=20,
    )
    resp.encoding = "iso-8859-1"
    if resp.status_code != 200:
        logger.warning("ZVG search returned %s", resp.status_code)
        return ""
    return resp.text


def parse_results(html: str) -> list[Property]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    properties: list[Property] = []
    # The main results table is the one with many TRs. Iterate rows and
    # collect 7-row blocks per case.
    rows: list[BeautifulSoup] = []
    for t in soup.find_all("table"):
        candidate = t.find_all("tr")
        if len(candidate) > len(rows):
            rows = candidate

    for case in _iter_cases(rows):
        prop = _case_to_property(case)
        if prop:
            properties.append(prop)
    return properties


def _iter_cases(rows: list) -> Iterable[dict[str, str]]:
    """Walk rows and yield one dict per case keyed by the German label."""
    current: dict[str, str] = {}
    for tr in rows:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(" ", strip=True)
        value = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""
        if label == "Aktenzeichen" and current:
            yield current
            current = {}
        if label:
            current[label] = value
        # Capture the Detailansicht link for the zvg_id
        link = tr.find("a", href=True)
        if link and "zvg_id=" in link["href"] and "zvg_id" not in current:
            m = re.search(r"zvg_id=(\d+)", link["href"])
            if m:
                current["zvg_id"] = m.group(1)
    if current.get("Aktenzeichen"):
        yield current


def _case_to_property(case: dict[str, str]) -> Property | None:
    aktenzeichen = case.get("Aktenzeichen", "")
    if not aktenzeichen:
        return None
    # Strip the "(Detailansicht)" suffix and the update timestamp
    aktenzeichen = re.sub(r"\s*\(Detailansicht\).*$", "", aktenzeichen).strip()
    aktenzeichen = re.sub(r"\(letzte Aktualisierung.*?\)", "", aktenzeichen).strip()

    objekt_lage = case.get("Objekt/Lage", "")
    # Format: "<Typ> : <Address>" or "<Typ> (notes) : <Address>"
    parts = objekt_lage.split(":", 1)
    type_part = parts[0].strip() if parts else ""
    address = parts[1].strip() if len(parts) > 1 else objekt_lage
    property_type = _classify_type(type_part or objekt_lage)

    postcode_m = re.search(r"\b(\d{5})\b", address)
    postcode = postcode_m.group(1) if postcode_m else None
    if postcode and not (10000 <= int(postcode) <= 14999):
        return None  # outside Berlin — skip

    price = _parse_de_money(case.get("Verkehrswert in €", ""))
    auction_date = _parse_termin(case.get("Termin", ""))

    zvg_id = case.get("zvg_id") or aktenzeichen.replace(" ", "_").replace("/", "-")
    listing_id = f"zvg-{zvg_id}"
    url = f"{BASE}/index.php?button=showZvg&zvg_id={zvg_id}&land_abk={LAND_ABK}"

    district = identify_district(address, postcode)

    title_bits = [t for t in (type_part, "Zwangsversteigerung") if t]
    title = " — ".join(title_bits) if title_bits else "Zwangsversteigerung"

    description_parts = []
    if aktenzeichen:
        description_parts.append(f"Az. {aktenzeichen}")
    if case.get("Amtsgericht"):
        description_parts.append(case["Amtsgericht"])
    if case.get("Termin"):
        description_parts.append(f"Termin: {case['Termin']}")
    if case.get("Verkehrswert in €"):
        description_parts.append(f"Verkehrswert: {case['Verkehrswert in €']}")
    description = " · ".join(description_parts)[:600] or None

    return Property(
        id=listing_id,
        title=title,
        address=address,
        district=district,
        postcode=postcode,
        price=price,
        area_m2=None,
        price_per_m2=None,
        property_type=property_type,
        url=url,
        image_url=None,
        rooms=None,
        description=description,
        sale_type="auction",
        auction_date=auction_date,
        case_number=aktenzeichen,
    )


def scrape_berlin() -> list[Property]:
    html = fetch_results()
    return parse_results(html)
