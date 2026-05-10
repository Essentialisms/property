"""Kleinanzeigen.de scraper.

No bot protection — plain `requests` works. Pagination is `/seite:N/`
between the city slug and the category code.
"""

from __future__ import annotations

import logging
import random
import re
import time

import requests
from bs4 import BeautifulSoup, Tag

from analyzer.districts import identify_district
from scraper.models import Property

logger = logging.getLogger(__name__)

BASE = "https://www.kleinanzeigen.de"
# /s-<slug>/<city>/<category-code>
CATEGORY_PATHS = {
    "land": "/s-grundstuecke/berlin/c233l3331",
    "apartment": "/s-eigentumswohnung/berlin/c196l3331",
    "house": "/s-haus-kaufen/berlin/c208l3331",
}
PROPERTY_TYPES = tuple(CATEGORY_PATHS.keys())

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def url_for(property_type: str, page: int = 1) -> str:
    cat = CATEGORY_PATHS[property_type]
    if page <= 1:
        return BASE + cat
    # Insert seite:N before the c<id>l<id> tail segment
    head, tail = cat.rsplit("/", 1)
    return f"{BASE}{head}/seite:{page}/{tail}"


def fetch_pages(urls: list[str], delay: tuple[float, float] = (0.4, 1.2)) -> dict[str, str]:
    """Fetch with plain requests + User-Agent. Random small delay between hits."""
    out: dict[str, str] = {}
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    })
    for i, url in enumerate(urls):
        if i:
            time.sleep(random.uniform(*delay))
        logger.info("Fetching %s", url)
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning("  %s returned %s", url, resp.status_code)
                out[url] = ""
            else:
                out[url] = resp.text
        except requests.RequestException as e:
            logger.warning("  %s failed: %s", url, e)
            out[url] = ""
    return out


def parse_listings(html: str, property_type: str) -> list[Property]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.aditem")
    properties: list[Property] = []
    for card in cards:
        prop = _card_to_property(card, property_type)
        if prop:
            properties.append(prop)
    return properties


def parse_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = set()
    for a in soup.select("a[href*='/seite:']"):
        href = a.get("href", "")
        m = re.search(r"/seite:(\d+)/", href)
        if m:
            pages.add(int(m.group(1)))
    return max(pages) if pages else 1


def _card_to_property(card: Tag, property_type: str) -> Property | None:
    try:
        ad_id = card.get("data-adid")
        if not ad_id:
            return None

        title_el = card.select_one("a.ellipsis, h2 a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        url = BASE + href if href.startswith("/") else href

        addr_el = card.select_one(".aditem-main--top--left")
        address = addr_el.get_text(strip=True) if addr_el else ""
        postcode_m = re.search(r"\b(\d{5})\b", address)
        postcode = postcode_m.group(1) if postcode_m else None

        price_el = card.select_one(".aditem-main--middle--price-shipping--price")
        price = None
        if price_el:
            text = price_el.get_text(strip=True)
            m = re.search(r"([\d.]+)\s*€", text)
            if m:
                price = _parse_de_number(m.group(1))

        tags_el = card.select_one(".aditem-main--middle--tags")
        area = None
        rooms = None
        if tags_el:
            text = tags_el.get_text(" ", strip=True)
            ma = re.search(r"([\d.,]+)\s*m²", text)
            if ma:
                area = _parse_de_number(ma.group(1))
            mr = re.search(r"([\d.,]+)\s*Zi", text)
            if mr:
                rooms = _parse_de_number(mr.group(1))

        desc_el = card.select_one(".aditem-main--middle--description")
        description = None
        if desc_el:
            text = desc_el.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                description = text[:600]

        img_el = card.select_one("img[src]")
        image_url = img_el.get("src") if img_el else None
        if image_url and image_url.startswith("data:"):
            image_url = None

        price_per_m2 = round(price / area, 2) if price and area else None
        district = identify_district(address, postcode)

        return Property(
            id=f"ka-{ad_id}",
            title=title,
            address=address,
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
        logger.debug("ka card parse failed: %s", e)
        return None


def _parse_de_number(s: str) -> float | None:
    if not s:
        return None
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None
