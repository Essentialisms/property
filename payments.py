"""Stripe subscriptions for the agentic real estate search.

Plans:
  - weekly:  €2 / week
  - monthly: €5 / month
  - yearly:  €50 / year

Required environment variables:
  STRIPE_SECRET_KEY        — sk_test_… or sk_live_…
  STRIPE_WEBHOOK_SECRET    — whsec_… (set after creating the webhook endpoint)
  STRIPE_PRICE_WEEKLY      — Stripe Price ID for the €2/week plan
  STRIPE_PRICE_MONTHLY     — Stripe Price ID for the €5/month plan
  STRIPE_PRICE_YEARLY      — Stripe Price ID for the €50/year plan
"""

import os
import logging

import stripe
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    abort,
    flash,
)
from flask_login import login_required, current_user

import auth

logger = logging.getLogger(__name__)

bp = Blueprint("payments", __name__)


# ===== Plan catalogue (display side) =====

PLANS = [
    {
        "key": "weekly",
        "name": "Weekly",
        "price_label": "€2",
        "interval_label": "per week",
        "price_env": "STRIPE_PRICE_WEEKLY",
        "blurb": "Try agentic search for a week.",
    },
    {
        "key": "monthly",
        "name": "Monthly",
        "price_label": "€5",
        "interval_label": "per month",
        "price_env": "STRIPE_PRICE_MONTHLY",
        "blurb": "Best for ongoing property hunts.",
    },
    {
        "key": "yearly",
        "name": "Yearly",
        "price_label": "€50",
        "interval_label": "per year",
        "price_env": "STRIPE_PRICE_YEARLY",
        "blurb": "Save ~17% vs. monthly.",
    },
]

PLAN_BY_KEY = {p["key"]: p for p in PLANS}
_PRICE_TO_PLAN: dict[str, str] = {}


# ===== Init =====

def init_app(app) -> None:
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if api_key:
        stripe.api_key = api_key
    else:
        logger.warning("STRIPE_SECRET_KEY not set — Stripe checkout will fail at runtime.")

    # Build reverse lookup: stripe price id -> plan key
    for plan in PLANS:
        price_id = os.environ.get(plan["price_env"])
        if price_id:
            _PRICE_TO_PLAN[price_id] = plan["key"]

    app.register_blueprint(bp)


def _price_id_for(plan_key: str) -> str | None:
    plan = PLAN_BY_KEY.get(plan_key)
    if not plan:
        return None
    return os.environ.get(plan["price_env"])


def _ensure_stripe_customer(user) -> str:
    """Create a Stripe Customer for this user if one doesn't exist yet."""
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": str(user.id)},
    )
    auth.set_stripe_customer(user.id, customer.id)
    user.stripe_customer_id = customer.id
    return customer.id


# ===== Routes =====

@bp.route("/pricing")
def pricing():
    return render_template("pricing.html", plans=PLANS, user=current_user)


@bp.route("/api/checkout", methods=["POST"])
@login_required
def create_checkout_session():
    plan_key = request.form.get("plan") or ""
    if not plan_key and request.is_json:
        plan_key = (request.get_json(silent=True) or {}).get("plan", "")
    price_id = _price_id_for(plan_key)
    if not price_id:
        flash(f"Plan '{plan_key}' is not configured. Set {PLAN_BY_KEY.get(plan_key, {}).get('price_env', '???')} in your environment.", "error")
        return redirect(url_for("payments.pricing"))

    try:
        customer_id = _ensure_stripe_customer(current_user)
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=url_for("payments.checkout_success", _external=True)
            + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("payments.pricing", _external=True),
            allow_promotion_codes=True,
            metadata={"user_id": str(current_user.id), "plan": plan_key},
        )
    except stripe.error.StripeError as e:
        logger.exception("Stripe checkout creation failed")
        flash(f"Could not start checkout: {e.user_message or str(e)}", "error")
        return redirect(url_for("payments.pricing"))

    return redirect(session.url, code=303)


@bp.route("/checkout/success")
@login_required
def checkout_success():
    return render_template("checkout_success.html")


@bp.route("/api/billing-portal", methods=["POST"])
@login_required
def billing_portal():
    if not current_user.stripe_customer_id:
        flash("No billing account on file.", "error")
        return redirect(url_for("auth.account"))
    try:
        portal = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for("auth.account", _external=True),
        )
    except stripe.error.StripeError as e:
        logger.exception("Billing portal creation failed")
        flash(f"Could not open billing portal: {e.user_message or str(e)}", "error")
        return redirect(url_for("auth.account"))
    return redirect(portal.url, code=303)


@bp.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=False)
    sig = request.headers.get("Stripe-Signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET not set; refusing to process webhook.")
        abort(500)

    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        logger.warning("Invalid Stripe webhook signature")
        abort(400)

    etype = event["type"]
    obj = event["data"]["object"]

    if etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        sub = obj
        customer_id = sub.get("customer")
        status = sub.get("status")
        sub_id = sub.get("id")
        period_end = sub.get("current_period_end")
        plan_key = None
        items = (sub.get("items") or {}).get("data") or []
        if items:
            price_id = items[0].get("price", {}).get("id")
            if price_id:
                plan_key = _PRICE_TO_PLAN.get(price_id)
        if etype == "customer.subscription.deleted":
            status = "canceled"
        auth.update_subscription(customer_id, sub_id, status, plan_key, period_end)
        logger.info(f"Subscription {etype}: customer={customer_id} status={status} plan={plan_key}")

    return jsonify({"received": True})
