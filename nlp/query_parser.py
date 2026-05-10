"""Natural language query parser with OpenAI API + keyword fallback."""

import json
import os
import logging

from scraper.models import SearchParams
from nlp.keyword_parser import parse_query as keyword_parse
from analyzer.districts import get_all_district_names

logger = logging.getLogger(__name__)

_OPENAI_KEY = None


def _get_api_key() -> str | None:
    global _OPENAI_KEY
    if _OPENAI_KEY is None:
        _OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
    return _OPENAI_KEY if _OPENAI_KEY else None


def is_ai_mode_available() -> bool:
    return _get_api_key() is not None


def parse_query(query: str) -> tuple[SearchParams, str]:
    """Parse a natural language query into structured search parameters.

    Returns:
        (SearchParams, mode) where mode is "ai" or "keyword"
    """
    if not query or not query.strip():
        return SearchParams(), "keyword"

    api_key = _get_api_key()
    if api_key:
        try:
            params = _parse_with_openai(query, api_key)
            if params:
                return params, "ai"
        except Exception as e:
            logger.warning(f"OpenAI API parsing failed, falling back to keyword: {e}")

    return keyword_parse(query), "keyword"


def _parse_with_openai(query: str, api_key: str) -> SearchParams | None:
    """Use OpenAI API to extract structured search params from natural language."""
    from openai import OpenAI

    districts = get_all_district_names()
    district_list = ", ".join(districts)

    client = OpenAI(api_key=api_key)

    system_prompt = f"""You extract structured property search parameters from natural language queries about Berlin real estate.

Available Berlin districts: {district_list}

Return ONLY a JSON object with these fields (omit fields that aren't mentioned):
- budget: number (max price in EUR)
- property_type: "land" | "apartment" | "house" | "all"
- districts: array of district name strings (from the available list above)
- excluded_districts: array of district names the user explicitly does NOT want
- near: a single Ortsteil or Bezirk name when the user says "near X" / "around X" / "close to X" (e.g. "near Wannsee" → "Wannsee"). Set this INSTEAD OF districts when phrased as proximity, never both for the same location.
- min_size: number (minimum area in m2)
- max_size: number (maximum area in m2)
- residence_type: "permanent" if user wants somewhere they can register as Hauptwohnsitz / live year-round / not a vacation home; "weekend" if they explicitly want a weekend / vacation / Datsche / Ferienhaus / Erholungsgrundstück; omit if no preference.
- sort_by: "deal_score" | "growth_score" | "price" | "size"

For sort_by, use "deal_score" if the user wants cheap/affordable/bargain/undervalued properties, "growth_score" if they want investment potential/up-and-coming areas, "price" for cheapest first, "size" for largest first.

For excluded_districts: phrases like "not in Mitte", "anywhere except Spandau", "no Marzahn", "avoid Lichtenberg" should populate this list.

If the user mentions "east" or "eastern" Berlin, map to eastern districts like Lichtenberg, Treptow-Koepenick, Marzahn-Hellersdorf, Friedrichshain.
If they say "west" or "western", map to Charlottenburg, Spandau, Steglitz-Zehlendorf, Reinickendorf.

Return ONLY the JSON, no other text."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=500,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
    )

    response_text = response.choices[0].message.content.strip()
    data = json.loads(response_text)

    rt = data.get("residence_type")
    if rt not in ("permanent", "weekend"):
        rt = None
    return SearchParams(
        budget=data.get("budget"),
        property_type=data.get("property_type", "land"),
        districts=data.get("districts", []),
        excluded_districts=data.get("excluded_districts", []),
        near=data.get("near"),
        min_size=data.get("min_size"),
        max_size=data.get("max_size"),
        sort_by=data.get("sort_by", "deal_score"),
        residence_type=rt,
    )
