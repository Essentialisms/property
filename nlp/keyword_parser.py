"""Keyword-based natural language parser for search queries.

Extracts structured search parameters from free text without any AI API.
"""

import re
from scraper.models import SearchParams
from analyzer.districts import BERLIN_DISTRICTS


# District names sorted longest-first for greedy matching
_DISTRICT_NAMES = sorted(BERLIN_DISTRICTS.keys(), key=len, reverse=True)

# Property type keywords
_PROPERTY_TYPES = {
    "land": [
        "land", "plot", "grundstück", "grundstueck", "bauland",
        "baugrundstück", "baugrundstuck", "grundstuck",
    ],
    "apartment": [
        "apartment", "wohnung", "flat", "condo", "eigentumswohnung", "etw",
    ],
    "house": [
        "house", "haus", "einfamilienhaus", "reihenhaus", "doppelhaus",
        "villa", "bungalow",
    ],
}

# Sort preference keywords
_SORT_KEYWORDS = {
    "deal_score": [
        "cheap", "affordable", "deal", "bargain", "günstig", "guenstig",
        "billig", "preiswert", "schnäppchen", "schnaeppchen", "value",
        "undervalued", "below market",
    ],
    "growth_score": [
        "growing", "growth", "potential", "up-and-coming", "emerging",
        "aufstrebend", "zukunft", "future", "investment", "invest",
        "trending", "hot",
    ],
    "price": [
        "cheapest", "lowest price", "price low", "preis",
    ],
    "size": [
        "biggest", "largest", "spacious", "groß", "gross", "große", "large",
        "big", "geräumig", "geraeumig",
    ],
}


def parse_query(query: str) -> SearchParams:
    """Extract structured search parameters from a natural language query."""
    if not query or not query.strip():
        return SearchParams()

    q = query.strip()
    q_lower = q.lower()

    budget = _extract_budget(q)
    property_type = _extract_property_type(q_lower)
    districts = _extract_districts(q_lower)
    min_size = _extract_min_size(q)
    sort_by = _extract_sort_preference(q_lower)

    return SearchParams(
        budget=budget,
        property_type=property_type,
        districts=districts,
        min_size=min_size,
        sort_by=sort_by,
    )


def _extract_budget(text: str) -> float | None:
    """Extract budget from text. Handles: 200k, €300,000, 500000 EUR, under 250k, etc."""
    patterns = [
        # "under/below/max/up to 200k" or "unter 200k"
        r'(?:under|below|max|up\s*to|unter|bis|maximal)\s*[€$]?\s*([\d.,]+)\s*[kK]',
        r'(?:under|below|max|up\s*to|unter|bis|maximal)\s*[€$]?\s*([\d.,]+)\s*(?:thousand|tausend)',
        r'(?:under|below|max|up\s*to|unter|bis|maximal)\s*[€$]?\s*([\d.,]+)\s*(?:EUR|€|euro)',
        r'(?:under|below|max|up\s*to|unter|bis|maximal)\s*[€$]?\s*([\d.,]+)',
        # "200k budget" or "budget 200k" or "€200k"
        r'[€$]?\s*([\d.,]+)\s*[kK]\b',
        # "200,000 EUR" or "€200,000" or "200.000€"
        r'[€$]\s*([\d.,]+)\s*(?:EUR|€|euro)?',
        r'([\d.,]+)\s*[€$]\s*',
        r'([\d.,]+)\s*(?:EUR|euro)\b',
        # Plain large number (6+ digits likely a price)
        r'\b(\d{6,})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num_str = match.group(1).replace(",", "").replace(".", "")
            try:
                value = float(num_str)
            except ValueError:
                continue

            # Check if it was in thousands (k suffix)
            full_match = match.group(0).lower()
            if "k" in full_match and value < 10000:
                value *= 1000
            elif "thousand" in full_match or "tausend" in full_match:
                value *= 1000

            if value >= 1000:  # reasonable minimum price
                return value

    return None


def _extract_property_type(text_lower: str) -> str:
    """Detect property type from keywords."""
    for ptype, keywords in _PROPERTY_TYPES.items():
        for kw in keywords:
            if kw in text_lower:
                return ptype
    return "land"  # default


def _extract_districts(text_lower: str) -> list[str]:
    """Find mentioned Berlin district names."""
    found = []
    remaining = text_lower

    for name in _DISTRICT_NAMES:
        if name.lower() in remaining:
            found.append(name)
            # Remove matched text to avoid double-matching
            remaining = remaining.replace(name.lower(), " ")

    # Deduplicate: if we matched both "Treptow" and "Treptow-Koepenick", keep the longer
    deduped = []
    for name in found:
        is_subset = any(
            name != other and name.lower() in other.lower()
            for other in found
        )
        if not is_subset:
            deduped.append(name)

    return deduped


def _extract_min_size(text: str) -> float | None:
    """Extract minimum size in m2."""
    patterns = [
        r'(?:min|minimum|at\s*least|mindestens|ab)\s*(\d+)\s*(?:m2|m²|sqm|qm)',
        r'(\d+)\s*(?:m2|m²|sqm|qm)\s*(?:or\s*more|minimum|\+|plus)',
        r'(\d+)\s*(?:m2|m²|sqm|qm)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if val >= 10:  # reasonable min
                return val
    return None


def _extract_sort_preference(text_lower: str) -> str:
    """Detect sorting preference from sentiment keywords."""
    scores = {key: 0 for key in _SORT_KEYWORDS}
    for sort_key, keywords in _SORT_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[sort_key] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "deal_score"
