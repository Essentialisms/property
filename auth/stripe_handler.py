"""Stripe Checkout + Webhook helpers."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import stripe

from auth import supabase_client as supa

logger = logging.getLogger(__name__)

PLAN_TO_PRICE_ENV = {
    "weekly": "STRIPE_PRICE_WEEKLY",
    "monthly": "STRIPE_PRICE_MONTHLY",
    "yearly": "STRIPE_PRICE_YEARLY",
}


def _configure() -> None:
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def is_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def price_id_for(plan: str) -> str | None:
    env_name = PLAN_TO_PRICE_ENV.get(plan)
    if not env_name:
        return None
    return os.environ.get(env_name) or None


def create_checkout_session(plan: str, user_id: str, user_email: str | None,
                             success_url: str, cancel_url: str) -> str | None:
    _configure()
    price_id = price_id_for(plan)
    if not price_id:
        logger.warning("No Stripe price configured for plan=%s", plan)
        return None
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=user_id,
            customer_email=user_email,
            metadata={"user_id": user_id, "plan": plan},
            subscription_data={"metadata": {"user_id": user_id, "plan": plan}},
            allow_promotion_codes=True,
        )
        return session.url
    except stripe.error.StripeError as e:
        logger.exception("create_checkout_session failed: %s", e)
        return None


def create_portal_session(stripe_customer_id: str, return_url: str) -> str | None:
    _configure()
    try:
        portal = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return portal.url
    except stripe.error.StripeError as e:
        logger.exception("create_portal_session failed: %s", e)
        return None


def handle_webhook(payload: bytes, sig_header: str | None) -> tuple[int, str]:
    _configure()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return 500, "webhook secret not configured"
    if not sig_header:
        return 400, "missing signature"
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning("Stripe webhook verification failed: %s", e)
        return 400, "signature verification failed"

    etype = event["type"]
    raw_obj = event["data"]["object"]
    # Normalise to a plain dict — Stripe SDK objects look dict-ish but nested
    # 'metadata' is a StripeObject without a working .get method.
    try:
        obj = raw_obj.to_dict_recursive() if hasattr(raw_obj, "to_dict_recursive") else dict(raw_obj)
    except Exception:
        obj = dict(raw_obj) if raw_obj else {}
    md = obj.get("metadata") or {}
    if not isinstance(md, dict):
        try:
            md = dict(md)
        except Exception:
            md = {}

    if etype == "checkout.session.completed":
        user_id = obj.get("client_reference_id") or md.get("user_id")
        plan = md.get("plan")
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        if user_id and customer_id:
            supa.upsert_subscription({
                "user_id": user_id,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "plan": plan,
                "status": "active",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        return 200, "checkout recorded"

    if etype in ("customer.subscription.updated", "customer.subscription.created"):
        user_id = md.get("user_id")
        if not user_id:
            return 200, "no user_id in metadata"
        plan = md.get("plan")
        period_end = obj.get("current_period_end")
        period_end_iso = (
            datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
            if period_end else None
        )
        supa.upsert_subscription({
            "user_id": user_id,
            "stripe_customer_id": obj.get("customer"),
            "stripe_subscription_id": obj.get("id"),
            "plan": plan,
            "status": obj.get("status"),
            "current_period_end": period_end_iso,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return 200, "subscription synced"

    if etype == "customer.subscription.deleted":
        user_id = md.get("user_id")
        if user_id:
            supa.upsert_subscription({
                "user_id": user_id,
                "stripe_subscription_id": obj.get("id"),
                "status": "canceled",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        return 200, "subscription canceled"

    return 200, f"ignored event {etype}"
