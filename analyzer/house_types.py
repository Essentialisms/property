"""House subtype classification from listing titles.

German listings spell out the building type in the title (e.g.
"Einfamilienhaus zum Kauf"). This module turns that into a stable enum
the UI can filter on.
"""

from __future__ import annotations

# Order matters — most specific keyword first. The matcher returns the
# label of the first pattern whose keyword is a substring of the title.
HOUSE_SUBTYPE_RULES: list[tuple[str, list[str]]] = [
    ("townhouse", [
        "reihenmittelhaus", "reihenendhaus", "reiheneckhaus",
        "reihenhaus", "reihen-",
    ]),
    ("semi_detached", [
        "doppelhaushälfte", "doppelhaushaelfte", "doppelhaus", "dhh",
    ]),
    ("multi_family", [
        "mehrfamilienhaus", "mfh", "zinshaus", "renditehaus",
    ]),
    ("villa", [
        "villa", "stadtvilla",
    ]),
    ("bungalow", [
        "bungalow",
    ]),
    ("detached", [
        "einfamilienhaus", "efh", "stadthaus", "landhaus", "bauernhaus",
    ]),
]

HOUSE_SUBTYPE_LABELS: dict[str, str] = {
    "detached": "Single-family",
    "semi_detached": "Semi-detached",
    "townhouse": "Townhouse",
    "villa": "Villa",
    "bungalow": "Bungalow",
    "multi_family": "Multi-family",
}


def classify_house(title: str | None) -> str | None:
    if not title:
        return None
    text = title.lower()
    for label, keywords in HOUSE_SUBTYPE_RULES:
        for kw in keywords:
            if kw in text:
                return label
    return None


def label_for(subtype: str | None) -> str | None:
    if not subtype:
        return None
    return HOUSE_SUBTYPE_LABELS.get(subtype)
