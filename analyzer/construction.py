"""Built-vs-to-be-built classification.

German listings advertise still-to-build properties with phrases like
"Neubauprojekt", "Bauträger", "schlüsselfertig", "wird errichtet",
"Fertigstellung 2026", "geplante Eigentumswohnung", "Projektiert" — vs.
existing inventory described as "Bestand", "Baujahr 1995", "Altbau",
"Erstbezug nach Sanierung".

Returns one of:
- 'to_build'  — project that doesn't physically exist yet
- 'new_build' — finished but never occupied (Erstbezug Neubau)
- 'existing'  — standing structure, possibly old or renovated

Used both as a filter and as a small badge on the card.
"""

from __future__ import annotations

import re

# Phrases that are *unambiguous* signals the property doesn't physically exist
# yet. Order doesn't matter — first match wins.
TO_BUILD_MARKERS = (
    "neubauprojekt",
    "bauprojekt",
    "bauträger",
    "bautraeger",
    "schlüsselfertig",
    "schluesselfertig",
    "wird errichtet",
    "wird gebaut",
    "noch zu errichten",
    "im bau",
    "in bau",
    "in planung",
    "geplant",
    "projektiert",
    "fertigstellung",
    "bauphase",
    "rohbau",
    "vorvermarktung",
    "off-plan",
    "off plan",
)

# Already-built but never lived in. Ranks lower than TO_BUILD.
NEW_BUILD_MARKERS = (
    "erstbezug",
    "neubau",  # without "projekt" / "in planung" — those are caught above
    "neubauwohnung",
    "neubau-wohnung",
)

# Strong "this exists already" signals (used to override an ambiguous "neubau"
# that's actually finished).
EXISTING_MARKERS = (
    "altbau",
    "bestand",
    "bj. ",
    "saniert",
    "renoviert",
    "kernsaniert",
    "modernisiert",
)

_BAUJAHR_PAST = re.compile(r"baujahr\s*(\d{4})")


def classify_construction(title: str | None, description: str | None = None,
                          current_year: int = 2026) -> str:
    haystack = " ".join(part.lower() for part in (title, description) if part)
    if not haystack:
        return "existing"

    if any(m in haystack for m in TO_BUILD_MARKERS):
        return "to_build"

    # Baujahr in the past locks the listing as existing, even if "Neubau"
    # appears (used loosely for any modern build).
    bj = _BAUJAHR_PAST.search(haystack)
    if bj:
        try:
            year = int(bj.group(1))
            if year <= current_year:
                return "existing"
        except ValueError:
            pass

    if any(m in haystack for m in NEW_BUILD_MARKERS):
        return "new_build"

    if any(m in haystack for m in EXISTING_MARKERS):
        return "existing"

    return "existing"
