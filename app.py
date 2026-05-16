"""Berlin Property Finder — Flask application."""

import os
import logging
from flask import Flask, render_template, request, jsonify, make_response

from scraper.models import SearchParams, SearchResult
from scraper.immoscout import search_properties, get_demo_properties
from analyzer.scorer import rate_properties, filter_by_budget, filter_by_size, sort_properties
from analyzer.districts import get_districts_summary
from nlp.query_parser import parse_query, is_ai_mode_available

from auth import quota, stripe_handler
from auth.jwt_verify import user_id_from_request
from auth import supabase_client as supa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    # Quota gate before doing any work — anonymous get 2 free / browser,
    # authenticated get 1 / day, subscribers unlimited.
    user_id = user_id_from_request(request.headers)
    anon_cookie = request.cookies.get(quota.COOKIE_NAME)
    q = quota.check_and_consume(user_id, anon_cookie)
    if not q.allowed:
        status = 401 if q.reason == "signup_required" else 402
        return jsonify({
            "error": q.reason,
            "message": (
                "Create a free account to keep searching."
                if q.reason == "signup_required"
                else "An active subscription is required to search."
            ),
        }), status

    data = request.get_json(silent=True) or {}

    nl_query = data.get("query", "").strip()
    search_mode = "keyword"

    if nl_query:
        params, search_mode = parse_query(nl_query)
        # Allow structured fields to override NL-parsed values
        if data.get("budget"):
            params.budget = float(data["budget"])
        if data.get("property_types"):
            params.property_types = [t for t in data["property_types"] if t]
        elif data.get("property_type") and data["property_type"] != "all":
            params.property_type = data["property_type"]
    else:
        params = SearchParams(
            budget=float(data["budget"]) if data.get("budget") else None,
            property_type=data.get("property_type", "all"),
            property_types=[t for t in (data.get("property_types") or []) if t],
            districts=data.get("districts", []),
            min_size=float(data["min_size"]) if data.get("min_size") else None,
            sort_by=data.get("sort_by", "deal_score"),
        )

    # House subtype filter (single-family, semi-detached, townhouse, etc.).
    raw_sub = data.get("subtypes") or ([] if not data.get("subtype") else [data["subtype"]])
    subtypes = [s for s in raw_sub if s]

    # Structured fields can override / extend NL-parsed include + exclude lists.
    # An explicit district pick from the dropdown is authoritative — it
    # overrides any NL-parsed districts AND clears any 'near' proximity
    # expansion so the user's strict UI choice isn't silently widened.
    if data.get("districts"):
        params.districts = data["districts"]
        params.near = None
    if data.get("excluded_districts"):
        params.excluded_districts = data["excluded_districts"]
    if data.get("near"):
        params.near = data["near"]
    if data.get("residence_type") in ("permanent", "weekend"):
        params.residence_type = data["residence_type"]
    if data.get("construction_status") in ("existing", "new_build", "to_build"):
        params.construction_status = data["construction_status"]
    include_no_price = bool(data.get("include_no_price", False))

    # Cap pages in serverless environments (Vercel has 10s timeout on free tier)
    max_pages = min(params.max_pages, 2) if os.environ.get("VERCEL") else params.max_pages

    # Fetch properties
    properties, is_demo, error = search_properties(
        property_type=params.property_type,
        property_types=params.property_types or None,
        districts=params.districts if params.districts else None,
        max_pages=max_pages,
        subtypes=subtypes or None,
        excluded_districts=params.excluded_districts or None,
        near=params.near,
        residence_type=params.residence_type,
        construction_status=params.construction_status,
        include_no_price=include_no_price,
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

    payload = result.to_dict()
    payload["quota"] = {
        "anonymous": user_id is None,
        "remaining_anon": q.remaining_anon,
    }
    response = make_response(jsonify(payload))
    if q.cookie_value:
        response.set_cookie(
            quota.COOKIE_NAME, q.cookie_value,
            max_age=quota.COOKIE_MAX_AGE, httponly=True, samesite="Lax",
            secure=not app.debug,
        )
    return response


@app.route("/api/me")
def api_me():
    """Return the current user's auth + subscription state."""
    user_id = user_id_from_request(request.headers)
    if not user_id:
        return jsonify({"authenticated": False})
    sub = supa.get_subscription(user_id) if supa.is_configured() else None
    return jsonify({
        "authenticated": True,
        "user_id": user_id,
        "subscription": {
            "active": bool(sub and (sub.get("status") or "").lower() in ("active", "trialing")),
            "plan": sub.get("plan") if sub else None,
            "status": sub.get("status") if sub else None,
            "current_period_end": sub.get("current_period_end") if sub else None,
        },
    })


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    user_id = user_id_from_request(request.headers)
    if not user_id:
        return jsonify({"error": "auth_required"}), 401
    if not stripe_handler.is_configured():
        return jsonify({"error": "stripe_not_configured"}), 503
    body = request.get_json(silent=True) or {}
    plan = body.get("plan")
    if plan not in stripe_handler.PLAN_TO_PRICE_ENV:
        return jsonify({"error": "invalid_plan"}), 400
    origin = request.headers.get("Origin") or request.host_url.rstrip("/")
    url = stripe_handler.create_checkout_session(
        plan=plan,
        user_id=user_id,
        user_email=body.get("email"),
        success_url=f"{origin}/?subscribed=1",
        cancel_url=f"{origin}/?canceled=1",
    )
    if not url:
        return jsonify({"error": "checkout_failed"}), 500
    return jsonify({"url": url})


@app.route("/api/portal", methods=["POST"])
def api_portal():
    user_id = user_id_from_request(request.headers)
    if not user_id:
        return jsonify({"error": "auth_required"}), 401
    sub = supa.get_subscription(user_id) if supa.is_configured() else None
    customer_id = sub.get("stripe_customer_id") if sub else None
    if not customer_id:
        return jsonify({"error": "no_customer"}), 400
    origin = request.headers.get("Origin") or request.host_url.rstrip("/")
    url = stripe_handler.create_portal_session(customer_id, return_url=f"{origin}/")
    if not url:
        return jsonify({"error": "portal_failed"}), 500
    return jsonify({"url": url})


@app.route("/api/stripe-webhook", methods=["POST"])
def api_stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature")
    code, msg = stripe_handler.handle_webhook(payload, sig)
    return jsonify({"message": msg}), code


@app.route("/api/districts")
def api_districts():
    return jsonify({
        "districts": get_districts_summary(),
        "ai_mode": is_ai_mode_available(),
    })


@app.route("/api/config")
def api_config():
    """Public Supabase keys + Stripe plan presence so the frontend can render."""
    return jsonify({
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
        "stripe_enabled": stripe_handler.is_configured(),
        "plans": [
            {"id": "weekly", "label": "Weekly", "price": "€1.50/week", "available": bool(stripe_handler.price_id_for("weekly"))},
            {"id": "monthly", "label": "Monthly", "price": "€5/month", "available": bool(stripe_handler.price_id_for("monthly"))},
            {"id": "yearly", "label": "Yearly", "price": "€60/year", "available": bool(stripe_handler.price_id_for("yearly"))},
        ],
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
