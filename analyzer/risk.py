"""Heuristic scam / suspicious-listing detection.

Without image analysis or external sources, we rely on signals visible in
the listing data: price vs. district market, area-vs-type sanity, postcode
inside Berlin, title vs. declared type, and known red-flag phrases.

Each flag has a weight; the per-listing risk_score is the (capped) sum of
weights and is exposed on the rating object so the UI can surface a badge.
"""

from __future__ import annotations

from scraper.models import Property

FLAG_WEIGHTS: dict[str, int] = {
    "price_far_below_market": 50,    # < 25% of district avg per m²
    "price_below_market": 20,        # 25-40% of district avg
    "type_mismatch_garage": 60,      # title says garage/stellplatz/parking
    "type_mismatch_apartment": 35,   # title says wohnung but type=house
    "type_mismatch_land": 35,        # title says grundstück but type=house/apt
    "area_too_small_for_house": 30,
    "area_too_small_for_apartment": 25,
    "no_photo": 10,
    "outside_berlin": 70,
    "price_suspiciously_round": 12,
    "urgency_phrase": 18,
    "missing_price_or_area": 8,
}

FLAG_LABELS: dict[str, str] = {
    "price_far_below_market": "Price <25% of district average — likely too good to be true",
    "price_below_market": "Price <40% of district average",
    "type_mismatch_garage": "Title looks like a garage / parking spot, not a house",
    "type_mismatch_apartment": "Title says apartment but listed as house",
    "type_mismatch_land": "Title says plot/Grundstück but listed as building",
    "area_too_small_for_house": "Floor area too small for a house",
    "area_too_small_for_apartment": "Floor area too small for an apartment",
    "no_photo": "No photo",
    "outside_berlin": "Postcode is outside Berlin",
    "price_suspiciously_round": "Suspiciously round price",
    "urgency_phrase": "Urgency / pressure phrase in title",
    "missing_price_or_area": "Missing price or area",
}


def _is_outside_berlin(postcode: str | None) -> bool:
    if not postcode:
        return False
    try:
        pc = int(postcode.strip())
    except ValueError:
        return False
    # Berlin postcodes: 10115–14199 (with gaps), but everything outside this
    # range is definitely not Berlin (e.g. 14532 Kleinmachnow, 16341 Panketal).
    return not (10000 <= pc <= 14999)


def evaluate(prop: Property, district_avg_per_m2: float | None) -> tuple[list[str], int]:
    flags: list[str] = []

    title = (prop.title or "").lower()

    # Price-per-m² vs district market
    if prop.price_per_m2 and district_avg_per_m2 and district_avg_per_m2 > 0:
        ratio = prop.price_per_m2 / district_avg_per_m2
        if ratio < 0.25:
            flags.append("price_far_below_market")
        elif ratio < 0.40:
            flags.append("price_below_market")

    # Title vs declared type. The garage / parking keywords are only a problem
    # when they describe what the listing IS — most legit listings mention a
    # parking spot among amenities, so the flag fires only when no
    # apartment/house indicator is present.
    GARAGE_KEYWORDS = ("garage zu", "stellplatz zu", "tiefgarage zu",
                       "carport zu", "parkplatz zu",
                       "garagenstellplatz", "pkw-stellplatz", "tg-stellplatz")
    HOUSE_INDICATORS = ("haus", "villa", "bungalow", "ehfh", "doppelhaus",
                         "reihen", "stadtvilla", "stadthaus", "mfh")
    APT_INDICATORS = ("wohnung", "zimmer", "apartment", "etagenwohnung",
                       "maisonette", "penthouse", "loft", "altbau",
                       " zi.", " zi ", "wg-", "studio")

    if prop.property_type == "house":
        if any(kw in title for kw in GARAGE_KEYWORDS):
            flags.append("type_mismatch_garage")
        elif any(kw in title for kw in APT_INDICATORS) and not any(kw in title for kw in HOUSE_INDICATORS):
            flags.append("type_mismatch_apartment")
        elif ("grundstück" in title or "baugrund" in title) and not any(kw in title for kw in HOUSE_INDICATORS):
            flags.append("type_mismatch_land")
    elif prop.property_type == "apartment":
        if any(kw in title for kw in GARAGE_KEYWORDS) and not any(kw in title for kw in APT_INDICATORS):
            flags.append("type_mismatch_garage")
        elif ("grundstück" in title or "baugrund" in title) and not any(kw in title for kw in APT_INDICATORS):
            flags.append("type_mismatch_land")

    # Area sanity
    if prop.area_m2:
        if prop.property_type == "house" and prop.area_m2 < 40:
            flags.append("area_too_small_for_house")
        elif prop.property_type == "apartment" and prop.area_m2 < 15:
            flags.append("area_too_small_for_apartment")

    # Image
    if not prop.image_url:
        flags.append("no_photo")

    # Outside Berlin
    if _is_outside_berlin(prop.postcode):
        flags.append("outside_berlin")

    # Suspiciously round price
    if prop.price and prop.property_type in ("house", "apartment"):
        p = int(prop.price)
        if 50_000 <= p <= 600_000 and p % 50_000 == 0:
            flags.append("price_suspiciously_round")

    # Urgency phrases
    if any(phrase in title for phrase in [
        "notverkauf", "schnellverkauf", "must sell", "urgent sale",
        "muss schnell", "schnell verkauft", "absolutely must"
    ]):
        flags.append("urgency_phrase")

    # Missing fundamentals
    if prop.price is None or prop.area_m2 is None:
        flags.append("missing_price_or_area")

    score = min(100, sum(FLAG_WEIGHTS.get(f, 0) for f in flags))
    return flags, score


def labels_for(flags: list[str]) -> list[str]:
    return [FLAG_LABELS[f] for f in flags if f in FLAG_LABELS]
