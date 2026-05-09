"""Berlin Property Finder — Flask application."""

import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user, login_required

from scraper.models import SearchParams, SearchResult
from scraper.immoscout import search_properties, get_demo_properties
from analyzer.scorer import rate_properties, filter_by_budget, filter_by_size, sort_properties
from analyzer.districts import get_districts_summary
from nlp.query_parser import parse_query, is_ai_mode_available

import auth
import payments

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")

auth.init_app(app)
payments.init_app(app)


def _run_search(data: dict) -> dict:
    """Shared search pipeline used by both free and agentic endpoints."""
    nl_query = data.get("query", "").strip()
    search_mode = "keyword"

    if nl_query:
        params, search_mode = parse_query(nl_query)
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

    max_pages = min(params.max_pages, 2) if os.environ.get("VERCEL") else params.max_pages

    properties, is_demo, error = search_properties(
        property_type=params.property_type,
        districts=params.districts if params.districts else None,
        max_pages=max_pages,
    )

    rated = rate_properties(properties)
    total_count = len(rated)

    rated = filter_by_budget(rated, params.budget)
    rated = filter_by_size(rated, params.min_size)
    filtered_count = len(rated)

    rated = sort_properties(rated, params.sort_by)

    result = SearchResult(
        properties=[rp.to_dict() for rp in rated],
        total_count=total_count,
        filtered_count=filtered_count,
        is_demo_data=is_demo,
        error=error,
        search_mode=search_mode,
        parsed_params=params.to_dict() if nl_query else None,
    )
    return result.to_dict()


@app.route("/")
def index():
    return render_template("index.html", user=current_user)


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    return jsonify(_run_search(data))


@app.route("/api/agent-search", methods=["POST"])
@login_required
def api_agent_search():
    """Agentic real estate search — gated by an active Stripe subscription."""
    if not current_user.has_active_subscription():
        return jsonify({
            "error": "subscription_required",
            "message": "An active subscription is required for agentic search.",
            "pricing_url": url_for("payments.pricing"),
        }), 402

    data = request.get_json(silent=True) or {}
    # Force AI/NL parsing on agent endpoint — natural language is the point.
    if not data.get("query"):
        return jsonify({"error": "query_required", "message": "Provide a natural-language `query`."}), 400

    payload = _run_search(data)
    payload["agentic"] = True
    return jsonify(payload)


@app.route("/api/districts")
def api_districts():
    return jsonify({
        "districts": get_districts_summary(),
        "ai_mode": is_ai_mode_available(),
        "authenticated": current_user.is_authenticated,
        "subscribed": current_user.is_authenticated and current_user.has_active_subscription(),
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
