"""Permanent vs. weekend / vacation residence classification.

Some Berlin / Brandenburg listings are not legally usable as a primary
residence (Hauptwohnsitz) — they sit in a Wochenendhausgebiet or
Erholungsgrundstück zone. This module spots those from the listing title.

The signal is sparse (most listings don't shout about it in the title)
so a 'permanent' classification is presumptive: it just means we found
no weekend marker, not that we proved the listing is a permanent home.
"""

from __future__ import annotations

WEEKEND_MARKERS = (
    "wochenend",            # Wochenendhaus, Wochenendgrundstück, etc.
    "ferienhaus",
    "ferienwohnung",
    "ferienimmobilie",
    "feriendomizil",
    "datsche",
    "datscha",
    "kleingarten",
    "kleingärten",
    "erholungsgrundstück",
    "erholungsgrundstueck",
    "erholungsgebiet",
    "ohne wohnstatus",
    "kein hauptwohnsitz",
    "kein dauerwohnen",
    "wochenendsiedlung",
    "freizeitgrundstück",
    "freizeitgrundstueck",
    # NOTE: 'Gartenhaus' is intentionally NOT here. In Berlin building lingo
    # it means a back-courtyard apartment building, not a weekend cabin —
    # including it produced too many false positives on Altbau listings.
)


def classify_residence(title: str | None, description: str | None = None) -> str:
    """Return 'weekend' if a weekend/vacation marker is present in title or
    description, else 'permanent'.
    """
    haystack = " ".join(part.lower() for part in (title, description) if part)
    if not haystack:
        return "permanent"
    for marker in WEEKEND_MARKERS:
        if marker in haystack:
            return "weekend"
    return "permanent"
