"""Berlin Property Finder — Flask application."""

import logging
from flask import Flask, render_template, request, jsonify

from scraper.models import SearchParams, SearchResult
from scraper.immoscout import search_properties, get_demo_properties
from analyzer.scorer import rate_properties, filter_by_budget, filter_by_size, sort_properties
from analyzer.districts import get_districts_summary
from nlp.query_parser import parse_query, is_ai_mode_available

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}

    nl_query = data.get("query", "").strip()
    search_mode = "keyword"

    if nl_query:
        params, search_mode = parse_query(nl_query)
        # Allow structured fields to override NL-parsed values
        if data.get("budget"):
            params.budget = float(data["budget"])
        if data.get("property_type") and data["property_type"] != "all":
            params.property_type = data["property_type"]
    else:
        params = SearchParams(
            budget=float(data["budget"]) if data.get("budget") else None,
            property_type=data.get("property_type", "land"),
            districts=data.get("districts", []),
            min_size=float(data["min_size"]) if data.get("min_size") else None,
            sort_by=data.get("sort_by", "deal_score"),
        )

    # Fetch properties
    properties, is_demo, error = search_properties(
        property_type=params.property_type,
        districts=params.districts if params.districts else None,
        max_pages=params.max_pages,
    )

    # Rate all properties
    rated = rate_properties(properties)
    total_count = len(rated)

    # Apply filters
    rated = filter_by_budget(rated, params.budget)
    rated = filter_by_size(rated, params.min_size)
    filtered_count = len(rated)

    # Sort
    rated = sort_properties(rated, params.sort_by)

    # Serialize
    result = SearchResult(
        properties=[rp.to_dict() for rp in rated],
        total_count=total_count,
        filtered_count=filtered_count,
        is_demo_data=is_demo,
        error=error,
        search_mode=search_mode,
        parsed_params=params.to_dict() if nl_query else None,
    )

    return jsonify(result.to_dict())


@app.route("/api/districts")
def api_districts():
    return jsonify({
        "districts": get_districts_summary(),
        "ai_mode": is_ai_mode_available(),
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
