"""Natural language query parser with Claude API + keyword fallback."""

import json
import os
import logging

from scraper.models import SearchParams
from nlp.keyword_parser import parse_query as keyword_parse
from analyzer.districts import get_all_district_names

logger = logging.getLogger(__name__)

_ANTHROPIC_KEY = None


def _get_api_key() -> str | None:
    global _ANTHROPIC_KEY
    if _ANTHROPIC_KEY is None:
        _ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    return _ANTHROPIC_KEY if _ANTHROPIC_KEY else None


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
            params = _parse_with_claude(query, api_key)
            if params:
                return params, "ai"
        except Exception as e:
            logger.warning(f"Claude API parsing failed, falling back to keyword: {e}")

    return keyword_parse(query), "keyword"


def _parse_with_claude(query: str, api_key: str) -> SearchParams | None:
    """Use Claude API to extract structured search params from natural language."""
    import anthropic

    districts = get_all_district_names()
    district_list = ", ".join(districts)

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=f"""You extract structured property search parameters from natural language queries about Berlin real estate.

Available Berlin districts: {district_list}

Return ONLY a JSON object with these fields (omit fields that aren't mentioned):
- budget: number (max price in EUR)
- property_type: "land" | "apartment" | "house" | "all"
- districts: array of district name strings (from the available list above)
- min_size: number (minimum area in m2)
- max_size: number (maximum area in m2)
- sort_by: "deal_score" | "growth_score" | "price" | "size"

For sort_by, use "deal_score" if the user wants cheap/affordable/bargain/undervalued properties, "growth_score" if they want investment potential/up-and-coming areas, "price" for cheapest first, "size" for largest first.

If the user mentions "east" or "eastern" Berlin, map to eastern districts like Lichtenberg, Treptow-Koepenick, Marzahn-Hellersdorf, Friedrichshain.
If they say "west" or "western", map to Charlottenburg, Spandau, Steglitz-Zehlendorf, Reinickendorf.

Return ONLY the JSON, no other text.""",
        messages=[
            {"role": "user", "content": query}
        ],
    )

    response_text = message.content[0].text.strip()

    # Extract JSON from response
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    data = json.loads(response_text)

    return SearchParams(
        budget=data.get("budget"),
        property_type=data.get("property_type", "land"),
        districts=data.get("districts", []),
        min_size=data.get("min_size"),
        max_size=data.get("max_size"),
        sort_by=data.get("sort_by", "deal_score"),
    )
