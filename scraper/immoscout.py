"""ImmoScout24 scraper with demo data fallback."""

import random
import time
import logging

import requests
from scraper.models import Property
from scraper.parser import parse_search_results, parse_total_pages
from scraper.blob_fetch import fetch_from_blob
from analyzer.districts import identify_district, resolve_bezirk, near_bezirke
from analyzer.house_types import classify_house
from analyzer.residence import classify_residence

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

PROPERTY_TYPE_SLUGS = {
    "land": "grundstueck-kaufen",
    "apartment": "wohnung-kaufen",
    "house": "haus-kaufen",
    "all": "immobilien-kaufen",
}

BASE_URL = "https://www.immobilienscout24.de/Suche/de/berlin/berlin"


def _district_matches(prop: Property, filter_districts: list[str]) -> bool:
    """Match a property to a filter using Bezirk geography.

    A property's Bezirk is resolved from its postcode (preferred) or district
    string. The filter is normalised the same way. The match is a Bezirk-set
    intersection — so 'Zehlendorf' (Ortsteil) and 'Steglitz-Zehlendorf'
    (Bezirk) both resolve to Steglitz-Zehlendorf and match each other,
    regardless of how the listing's `district` field happens to be spelled.
    """
    prop_bezirk = resolve_bezirk(prop.postcode, prop.district)
    if not prop_bezirk:
        return False
    accepted = set()
    for fd in filter_districts:
        bz = resolve_bezirk(None, fd)
        if bz:
            accepted.add(bz)
    return prop_bezirk in accepted


def search_properties(
    property_type: str = "land",
    districts: list[str] | None = None,
    max_pages: int = 5,
    subtypes: list[str] | None = None,
    excluded_districts: list[str] | None = None,
    near: str | None = None,
    residence_type: str | None = None,
) -> tuple[list[Property], bool, str | None]:
    """Scrape ImmoScout24 for Berlin property listings.

    Returns:
        (properties, is_demo_data, error_message)
    """
    # Try the blob-cached dataset first (refreshed daily by scripts/refresh.py).
    blob_props, blob_err = fetch_from_blob()
    if blob_props is not None:
        all_properties = blob_props
        # Enrich each property with its house subtype + residence type.
        for p in all_properties:
            if p.property_type == "house" and not p.subtype:
                p.subtype = classify_house(p.title)
            # Always recompute residence — the classifier reads description too
            # now and we want late-arriving descriptions to be picked up.
            p.residence_type = classify_residence(p.title, p.description)
        if property_type and property_type != "all":
            all_properties = [p for p in all_properties if p.property_type == property_type]

        # "Near X" expands to X's Bezirk + its physical neighbors and is unioned
        # with any explicit district filter.
        include_filters = list(districts or [])
        if near:
            include_filters.extend(near_bezirke(near))
        if include_filters:
            all_properties = [
                p for p in all_properties if _district_matches(p, include_filters)
            ]
        if excluded_districts:
            all_properties = [
                p for p in all_properties if not _district_matches(p, excluded_districts)
            ]
        if subtypes:
            wanted = set(subtypes)
            all_properties = [p for p in all_properties if p.subtype in wanted]
        if residence_type in ("permanent", "weekend"):
            all_properties = [p for p in all_properties if p.residence_type == residence_type]
        return all_properties, False, None

    slug = PROPERTY_TYPE_SLUGS.get(property_type, PROPERTY_TYPE_SLUGS["land"])
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    all_properties = []
    error = None

    is_demo = False

    try:
        # Page 1: no pagenumber param
        url = f"{BASE_URL}/{slug}"
        logger.info(f"Fetching {url}")
        resp = session.get(url, timeout=15)

        if resp.status_code in (401, 403):
            logger.warning(f"Got {resp.status_code} from ImmoScout24 — blocked")
            all_properties = get_demo_properties(property_type)
            is_demo = True
            error = "ImmoScout24 blocked the request (likely datacenter IP). Showing demo data."
        elif resp.status_code != 200:
            logger.warning(f"Got {resp.status_code} from ImmoScout24")
            all_properties = get_demo_properties(property_type)
            is_demo = True
            error = f"ImmoScout24 returned {resp.status_code}. Showing demo data."
        else:
            props = parse_search_results(resp.text)
            all_properties.extend(props)

            total_pages = min(parse_total_pages(resp.text), max_pages)

            # Subsequent pages
            for page in range(2, total_pages + 1):
                time.sleep(random.uniform(2.0, 4.0))
                page_url = f"{url}?pagenumber={page}"
                logger.info(f"Fetching {page_url}")

                try:
                    resp = session.get(page_url, timeout=15)
                    if resp.status_code == 200:
                        props = parse_search_results(resp.text)
                        all_properties.extend(props)
                    else:
                        logger.warning(f"Page {page} returned {resp.status_code}, stopping")
                        break
                except requests.RequestException as e:
                    logger.warning(f"Page {page} failed: {e}")
                    break

    except requests.RequestException as e:
        logger.warning(f"Scraping failed: {e}")
        all_properties = get_demo_properties(property_type)
        is_demo = True
        error = f"Connection failed: {e}. Showing demo data."

    if not all_properties:
        logger.info("No properties found via scraping, using demo data")
        all_properties = get_demo_properties(property_type)
        is_demo = True
        error = "No listings found. Showing demo data."

    # Filter by districts if specified — empty result means empty result.
    if districts:
        all_properties = [p for p in all_properties if _district_matches(p, districts)]

    return all_properties, is_demo, error


def get_demo_properties(property_type: str = "land") -> list[Property]:
    """Return realistic sample Berlin property listings."""
    demo_data = [
        # Land / Grundstück
        Property(
            id="demo-1", title="Baugrundstück in Treptow-Köpenick",
            address="Baumschulenweg, 12437 Berlin",
            district="Treptow", postcode="12437",
            price=185000, area_m2=520, price_per_m2=355.77,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-2", title="Grundstück in Spandau – ruhige Lage",
            address="Gatower Str., 13595 Berlin",
            district="Spandau", postcode="13595",
            price=210000, area_m2=680, price_per_m2=308.82,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-3", title="Erschlossenes Bauland in Marzahn",
            address="Landsberger Allee, 12679 Berlin",
            district="Marzahn", postcode="12679",
            price=95000, area_m2=420, price_per_m2=226.19,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-4", title="Grundstück in Reinickendorf mit Altbestand",
            address="Residenzstr., 13409 Berlin",
            district="Reinickendorf", postcode="13409",
            price=320000, area_m2=850, price_per_m2=376.47,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-5", title="Baugrundstück in Pankow – Stadtrandlage",
            address="Blankenburger Str., 13156 Berlin",
            district="Pankow", postcode="13156",
            price=275000, area_m2=600, price_per_m2=458.33,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-6", title="Grundstück Lichtenberg – gute Anbindung",
            address="Frankfurter Allee, 10365 Berlin",
            district="Lichtenberg", postcode="10365",
            price=350000, area_m2=480, price_per_m2=729.17,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-7", title="Grundstück in Köpenick am Wasser",
            address="Wendenschlossstr., 12559 Berlin",
            district="Koepenick", postcode="12559",
            price=420000, area_m2=750, price_per_m2=560.0,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        Property(
            id="demo-8", title="Kleines Baugrundstück Neukölln",
            address="Karl-Marx-Str., 12043 Berlin",
            district="Neukoelln", postcode="12043",
            price=195000, area_m2=280, price_per_m2=696.43,
            property_type="land",
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen",
        ),
        # Apartments
        Property(
            id="demo-9", title="2-Zimmer Wohnung in Friedrichshain",
            address="Boxhagener Str., 10245 Berlin",
            district="Friedrichshain", postcode="10245",
            price=245000, area_m2=55, price_per_m2=4454.55,
            property_type="apartment", rooms=2,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        Property(
            id="demo-10", title="Altbau in Prenzlauer Berg – saniert",
            address="Kastanienallee, 10435 Berlin",
            district="Prenzlauer Berg", postcode="10435",
            price=389000, area_m2=72, price_per_m2=5402.78,
            property_type="apartment", rooms=3,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        Property(
            id="demo-11", title="Kapitalanlage Wohnung Wedding",
            address="Müllerstr., 13349 Berlin",
            district="Wedding", postcode="13349",
            price=165000, area_m2=48, price_per_m2=3437.50,
            property_type="apartment", rooms=2,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        Property(
            id="demo-12", title="Moderne 3-Zi in Schöneberg",
            address="Hauptstr., 10827 Berlin",
            district="Schoeneberg", postcode="10827",
            price=410000, area_m2=85, price_per_m2=4823.53,
            property_type="apartment", rooms=3,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        Property(
            id="demo-13", title="1-Zimmer Apartment Mitte – zentral",
            address="Rosenthaler Str., 10119 Berlin",
            district="Mitte", postcode="10119",
            price=220000, area_m2=32, price_per_m2=6875.0,
            property_type="apartment", rooms=1,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        Property(
            id="demo-14", title="Große Wohnung Charlottenburg",
            address="Kantstr., 10623 Berlin",
            district="Charlottenburg", postcode="10623",
            price=520000, area_m2=95, price_per_m2=5473.68,
            property_type="apartment", rooms=4,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        Property(
            id="demo-15", title="Schnäppchen in Marzahn-Hellersdorf",
            address="Allee der Kosmonauten, 12681 Berlin",
            district="Marzahn", postcode="12681",
            price=115000, area_m2=58, price_per_m2=1982.76,
            property_type="apartment", rooms=2,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-kaufen",
        ),
        # Houses
        Property(
            id="demo-16", title="Einfamilienhaus Steglitz",
            address="Schloßstr., 12163 Berlin",
            district="Steglitz", postcode="12163",
            price=680000, area_m2=140, price_per_m2=4857.14,
            property_type="house", rooms=5,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/haus-kaufen",
        ),
        Property(
            id="demo-17", title="Doppelhaushälfte Reinickendorf",
            address="Alt-Reinickendorf, 13407 Berlin",
            district="Reinickendorf", postcode="13407",
            price=450000, area_m2=120, price_per_m2=3750.0,
            property_type="house", rooms=4,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/haus-kaufen",
        ),
        Property(
            id="demo-18", title="Reihenhaus Spandau – Garten",
            address="Heerstr., 13591 Berlin",
            district="Spandau", postcode="13591",
            price=395000, area_m2=110, price_per_m2=3590.91,
            property_type="house", rooms=4,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/haus-kaufen",
        ),
        Property(
            id="demo-19", title="Villa in Zehlendorf – Toplage",
            address="Clayallee, 14169 Berlin",
            district="Zehlendorf", postcode="14169",
            price=1250000, area_m2=220, price_per_m2=5681.82,
            property_type="house", rooms=7,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/haus-kaufen",
        ),
        Property(
            id="demo-20", title="Sanierungsbedürftiges Haus Lichtenberg",
            address="Rummelsburger Str., 10317 Berlin",
            district="Lichtenberg", postcode="10317",
            price=310000, area_m2=105, price_per_m2=2952.38,
            property_type="house", rooms=4,
            url="https://www.immobilienscout24.de/Suche/de/berlin/berlin/haus-kaufen",
        ),
    ]

    if property_type and property_type != "all":
        demo_data = [p for p in demo_data if p.property_type == property_type]

    return demo_data
