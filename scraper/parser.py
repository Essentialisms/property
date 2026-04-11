"""Parse ImmoScout24 search result pages into Property objects."""

import json
import re
from bs4 import BeautifulSoup
from scraper.models import Property
from analyzer.districts import identify_district


def parse_search_results(html: str) -> list[Property]:
    """Extract property listings from an ImmoScout24 search results page."""
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: Extract from embedded JSON in <script> tags
    properties = _parse_from_json(soup)
    if properties:
        return properties

    # Strategy 2: Parse HTML structure directly
    return _parse_from_html(soup)


def parse_total_pages(html: str) -> int:
    """Extract total number of search result pages."""
    soup = BeautifulSoup(html, "html.parser")

    # Try JSON first
    data = _extract_search_json(soup)
    if data:
        try:
            paging = data.get("searchResponseModel", data)
            paging = _deep_get(paging, "resultlist.resultlist.paging")
            if paging:
                return paging.get("numberOfPages", 1)
        except (KeyError, TypeError, AttributeError):
            pass

    # Fallback: look for pagination elements
    paging = soup.select("select.select-pageNumber option")
    if paging:
        return len(paging)

    nav_links = soup.select("[data-nav-page]")
    if nav_links:
        pages = [int(a.get("data-nav-page", 1)) for a in nav_links if a.get("data-nav-page", "").isdigit()]
        return max(pages) if pages else 1

    return 1


def _extract_search_json(soup: BeautifulSoup) -> dict | None:
    """Find and parse the embedded JSON search data from script tags."""
    for script in soup.find_all("script"):
        text = script.string or ""
        # Look for the search response model
        if "searchResponseModel" in text or "resultlistEntries" in text:
            # Try to extract JSON object
            for pattern in [
                r'keyValues\s*=\s*(\{.*?\});',
                r'resultList\.resultListModel\s*=\s*(\{.*?\});',
                r'IS24\.resultList\s*=\s*(\{.*?\});',
            ]:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        continue

            # Try to find any large JSON blob
            json_matches = re.findall(r'(\{["\']searchResponseModel["\'].*?\})\s*;', text, re.DOTALL)
            for m in json_matches:
                try:
                    return json.loads(m)
                except json.JSONDecodeError:
                    continue

        # Also try __NEXT_DATA__ for newer page versions
        if "__NEXT_DATA__" in text or "props" in text:
            match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', str(script), re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

    return None


def _parse_from_json(soup: BeautifulSoup) -> list[Property]:
    """Parse listings from embedded JSON data."""
    data = _extract_search_json(soup)
    if not data:
        return []

    entries = []
    # Navigate the JSON structure to find result entries
    search_model = data.get("searchResponseModel", data)
    result_list = _deep_get(search_model, "resultlist.resultlist.resultlistEntries")

    if not result_list:
        result_list = _deep_get(data, "props.pageProps.searchResult.results")

    if not result_list:
        return []

    if isinstance(result_list, list) and result_list:
        # Sometimes it's a list of entry groups
        for group in result_list:
            if isinstance(group, dict) and "resultlistEntry" in group:
                items = group["resultlistEntry"]
                if isinstance(items, list):
                    entries.extend(items)
                else:
                    entries.append(items)
            elif isinstance(group, dict):
                entries.append(group)

    properties = []
    for entry in entries:
        prop = _entry_to_property(entry)
        if prop:
            properties.append(prop)

    return properties


def _entry_to_property(entry: dict) -> Property | None:
    """Convert a JSON result entry to a Property object."""
    try:
        attrs = entry.get("resultlist.realEstate", entry.get("realEstate", entry))
        if not isinstance(attrs, dict):
            return None

        listing_id = str(entry.get("@id", attrs.get("@id", attrs.get("id", ""))))
        title = attrs.get("title", "")

        # Address
        address_obj = attrs.get("address", {})
        street = address_obj.get("street", "")
        house_number = address_obj.get("houseNumber", "")
        postcode = str(address_obj.get("postcode", ""))
        city = address_obj.get("city", "Berlin")
        quarter = address_obj.get("quarter", "")

        address_parts = [f"{street} {house_number}".strip(), quarter, f"{postcode} {city}"]
        address = ", ".join(p for p in address_parts if p)

        # Price
        price_obj = attrs.get("price", {})
        price = price_obj.get("value") if isinstance(price_obj, dict) else None
        if price is None:
            price = attrs.get("buyingPrice") or attrs.get("price")
            if isinstance(price, dict):
                price = price.get("value")

        # Area
        area = attrs.get("livingSpace") or attrs.get("plotArea") or attrs.get("netFloorSpace")
        if isinstance(area, str):
            area = float(re.sub(r"[^\d.]", "", area)) if re.search(r"\d", area) else None

        # Price per m2
        price_per_m2 = None
        if price and area and area > 0:
            price_per_m2 = round(price / area, 2)

        # Property type
        obj_type = str(attrs.get("@xsi.type", attrs.get("realEstateType", "")))
        if "Grundstueck" in obj_type or "plot" in obj_type.lower():
            prop_type = "land"
        elif "Haus" in obj_type or "house" in obj_type.lower():
            prop_type = "house"
        else:
            prop_type = "apartment"

        # URL
        expose_id = listing_id
        url = f"https://www.immobilienscout24.de/expose/{expose_id}"

        # Image
        title_picture = attrs.get("titlePicture", {})
        image_url = None
        if isinstance(title_picture, dict):
            urls = title_picture.get("urls", [])
            if isinstance(urls, list):
                for u in urls:
                    if isinstance(u, dict) and u.get("url"):
                        image_url = u["url"][0].get("@href", "") if isinstance(u["url"], list) else str(u.get("url", ""))
                        break
            image_url = image_url or title_picture.get("@href", "")

        # Rooms
        rooms = attrs.get("numberOfRooms")

        # District
        district = identify_district(address, postcode)

        if price is not None:
            price = float(price)
        if area is not None:
            area = float(area)
        if rooms is not None:
            rooms = float(rooms)

        return Property(
            id=listing_id,
            title=title,
            address=address,
            district=district,
            postcode=postcode if postcode else None,
            price=price,
            area_m2=area,
            price_per_m2=price_per_m2,
            property_type=prop_type,
            url=url,
            image_url=image_url if image_url else None,
            rooms=rooms,
        )
    except Exception:
        return None


def _parse_from_html(soup: BeautifulSoup) -> list[Property]:
    """Fallback: parse listings from HTML elements."""
    properties = []

    # Try various CSS selectors that ImmoScout24 uses
    selectors = [
        "li.result-list__listing",
        "article[data-item]",
        "div.result-list-entry__data",
        "[data-go-to-expose-id]",
    ]

    entries = []
    for sel in selectors:
        entries = soup.select(sel)
        if entries:
            break

    for entry in entries:
        prop = _html_entry_to_property(entry)
        if prop:
            properties.append(prop)

    return properties


def _html_entry_to_property(el) -> Property | None:
    """Convert an HTML listing element to a Property."""
    try:
        # ID
        listing_id = (
            el.get("data-go-to-expose-id")
            or el.get("data-item")
            or el.get("data-id")
            or ""
        )

        # Title
        title_el = el.select_one("h2, h5, .result-list-entry__brand-title, [class*='title']")
        title = title_el.get_text(strip=True) if title_el else ""

        # Address
        addr_el = el.select_one(".result-list-entry__address, [class*='address'], .result-list-entry__map-link")
        address = addr_el.get_text(strip=True) if addr_el else ""

        # Extract postcode from address
        postcode = None
        pc_match = re.search(r"\b(\d{5})\b", address)
        if pc_match:
            postcode = pc_match.group(1)

        # Price and area from criteria list
        criteria = el.select(".result-list-entry__criteria dd, [class*='criteria'] dd, [class*='attribute'] span")
        price = None
        area = None
        rooms = None

        for dd in criteria:
            text = dd.get_text(strip=True)
            if "€" in text or "EUR" in text:
                num = re.sub(r"[^\d]", "", text)
                if num:
                    price = float(num)
            elif "m²" in text or "m2" in text:
                num = re.sub(r"[^\d,.]", "", text).replace(",", ".")
                if num:
                    area = float(num)
            elif "Zi." in text or "Zimmer" in text:
                num = re.sub(r"[^\d,.]", "", text).replace(",", ".")
                if num:
                    rooms = float(num)

        price_per_m2 = round(price / area, 2) if price and area and area > 0 else None

        # URL
        link = el.select_one("a[href*='/expose/']")
        url = ""
        if link:
            href = link.get("href", "")
            if href.startswith("/"):
                url = f"https://www.immobilienscout24.de{href}"
            else:
                url = href
        elif listing_id:
            url = f"https://www.immobilienscout24.de/expose/{listing_id}"

        # Image
        img = el.select_one("img[src], img[data-src]")
        image_url = None
        if img:
            image_url = img.get("data-src") or img.get("src")

        district = identify_district(address, postcode)

        return Property(
            id=str(listing_id),
            title=title,
            address=address,
            district=district,
            postcode=postcode,
            price=price,
            area_m2=area,
            price_per_m2=price_per_m2,
            property_type="apartment",  # default, HTML doesn't always indicate type
            url=url,
            image_url=image_url,
            rooms=rooms,
        )
    except Exception:
        return None


def _deep_get(d: dict, path: str):
    """Navigate nested dict with dot-separated path."""
    keys = path.split(".")
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return None
    return d
