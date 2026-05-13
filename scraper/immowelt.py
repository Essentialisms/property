"""Immowelt scraper. Uses the same browser fetcher as ImmoScout24."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from analyzer.districts import identify_district
from scraper.models import Property

logger = logging.getLogger(__name__)

BERLIN_LOCATION_CODE = "AD08DE8634"
ESTATE_TYPE_PARAM = {
    "land": "Plot",
    "apartment": "Apartment",
    "house": "House",
}
BASE_URL = "https://www.immowelt.de/classified-search"
PROPERTY_TYPES = ("land", "apartment", "house")


def url_for(
    property_type: str,
    page: int = 1,
    price_min: int | None = None,
    price_max: int | None = None,
) -> str:
    estate_type = ESTATE_TYPE_PARAM[property_type]
    qs = f"distributionTypes=Buy&estateTypes={estate_type}&locations={BERLIN_LOCATION_CODE}"
    if price_min is not None:
        qs += f"&priceMin={price_min}"
    if price_max is not None:
        qs += f"&priceMax={price_max}"
    if page > 1:
        qs += f"&page={page}"
    return f"{BASE_URL}?{qs}"


def parse_listings(html: str, property_type: str) -> list[Property]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('div[data-testid="serp-core-classified-card-testid"]')
    properties: list[Property] = []
    for card in cards:
        prop = _card_to_property(card, property_type)
        if prop:
            properties.append(prop)
    return properties


def parse_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    btns = soup.select('button[aria-label^="zu seite "]')
    nums = []
    for b in btns:
        label = b.get("aria-label", "")
        last = label.split()[-1]
        if last.isdigit():
            nums.append(int(last))
    return max(nums) if nums else 1


def _card_to_property(card: Tag, property_type: str) -> Property | None:
    try:
        anchor = card.select_one("a[href*='/expose/']")
        if not anchor:
            return None
        href = anchor.get("href", "")
        title_attr = anchor.get("title", "") or ""

        # Listing UUID lives in /expose/<uuid>
        m = re.search(r"/expose/([a-f0-9-]+)", href)
        if not m:
            return None
        listing_id = m.group(1)
        url = f"https://www.immowelt.de/expose/{listing_id}"

        # Title — strip the "<type> zum Kauf - <city> - <price> - <facts>" suffix.
        title = title_attr.split(" - ")[0].strip() if title_attr else ""

        # Address
        addr_el = card.select_one('[data-testid="cardmfe-description-box-address"]')
        address = addr_el.get_text(strip=True) if addr_el else ""
        postcode_match = re.search(r"\((\d{5})\)", address)
        postcode = postcode_match.group(1) if postcode_match else None
        # Strip "(12345)" suffix from address for cleaner display
        address_clean = re.sub(r"\s*\(\d{5}\)\s*$", "", address)

        # Price text: "799.985 €9.570 €/m²"
        price_el = card.select_one('[data-testid="cardmfe-price-testid"]')
        price = None
        price_per_m2 = None
        if price_el:
            text = price_el.get_text(" ", strip=True)
            price_matches = re.findall(r"([\d.]+)\s*€", text)
            if price_matches:
                price = _parse_de_number(price_matches[0])
            ppm_match = re.search(r"([\d.,]+)\s*€/m²", text)
            if ppm_match:
                price_per_m2 = _parse_de_number(ppm_match.group(1))

        # Keyfacts: "6 Zimmer · 83,6 m² · 266 m² Grundstück"
        kf_el = card.select_one('[data-testid="cardmfe-keyfacts-testid"]')
        rooms = None
        area = None
        plot = None
        if kf_el:
            kf_text = kf_el.get_text("·", strip=True)
            for part in kf_text.split("·"):
                part = part.strip()
                if "Zimmer" in part:
                    n = re.search(r"([\d,.]+)", part)
                    if n:
                        rooms = _parse_de_number(n.group(1))
                elif "Grundstück" in part:
                    n = re.search(r"([\d.,]+)\s*m²", part)
                    if n:
                        plot = _parse_de_number(n.group(1))
                elif "m²" in part:
                    n = re.search(r"([\d.,]+)\s*m²", part)
                    if n:
                        area = _parse_de_number(n.group(1))

        # For land, "area" is the plot area
        if property_type == "land":
            area = area or plot

        if price and area and not price_per_m2:
            try:
                price_per_m2 = round(price / area, 2)
            except ZeroDivisionError:
                price_per_m2 = None

        # Image
        img_el = card.select_one("img[src]")
        image_url = img_el.get("src") if img_el else None
        if image_url and image_url.startswith("data:"):
            image_url = None

        # Description (snippet visible on the card). Trim to a reasonable length.
        desc_el = card.select_one('[data-testid="cardmfe-description-text-test-id"]')
        description = None
        if desc_el:
            text = desc_el.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                description = text[:600]

        # District inference from address
        district = identify_district(address_clean, postcode)

        return Property(
            id=f"iw-{listing_id}",
            title=title,
            address=address_clean,
            district=district,
            postcode=postcode,
            price=price,
            area_m2=area,
            price_per_m2=price_per_m2,
            property_type=property_type,
            url=url,
            image_url=image_url,
            rooms=rooms,
            description=description,
        )
    except Exception as e:
        logger.debug("card parse failed: %s", e)
        return None


def _parse_de_number(s: str) -> float | None:
    """Parse a German-formatted number like '1.234.567,89' or '799.985'."""
    if not s:
        return None
    s = s.strip()
    # If it has a comma, comma is the decimal separator
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None
