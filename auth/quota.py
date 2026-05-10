"""Search quota policy.

- Anonymous: 2 free searches per browser. Tracked via signed cookie so we
  don't need a DB write for unauthenticated traffic.
- Authenticated, no active subscription: 1 free search per UTC day.
  Searches are recorded in Supabase.
- Authenticated subscriber: unlimited.

The check_and_consume() function is the single point of policy: it returns
either an "ok" result or a structured "blocked" result with the reason
the caller should send back to the client (signup vs. subscribe).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from itsdangerous import BadSignature, URLSafeTimedSerializer

from auth import supabase_client as supa

logger = logging.getLogger(__name__)

ANON_FREE_SEARCHES = 2
AUTHED_FREE_PER_DAY = 1
COOKIE_NAME = "anon_quota"
COOKIE_MAX_AGE = 86400  # 24h


@dataclass
class QuotaResult:
    allowed: bool
    reason: str | None = None  # 'signup_required' | 'subscribe_required' | None
    remaining_anon: int | None = None  # remaining free anon searches
    cookie_value: str | None = None  # set by caller as updated cookie if non-None


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("APP_SECRET_KEY") or "dev-only-not-for-production"
    return URLSafeTimedSerializer(secret, salt="anon-quota")


def _read_anon_cookie(value: str | None) -> int:
    if not value:
        return 0
    try:
        data = _serializer().loads(value, max_age=COOKIE_MAX_AGE)
    except BadSignature:
        return 0
    except Exception:
        return 0
    return int(data.get("c", 0)) if isinstance(data, dict) else 0


def _write_anon_cookie(count: int) -> str:
    return _serializer().dumps({"c": count})


def has_active_subscription(user_id: str) -> bool:
    if not supa.is_configured():
        return False
    sub = supa.get_subscription(user_id)
    if not sub:
        return False
    status = (sub.get("status") or "").lower()
    return status in ("active", "trialing")


def check_and_consume(user_id: str | None, anon_cookie: str | None) -> QuotaResult:
    """Run the quota policy and (when allowed) consume one search."""
    if user_id:
        if has_active_subscription(user_id):
            supa.record_search(user_id)
            return QuotaResult(allowed=True)
        used_today = supa.count_searches_today_utc(user_id)
        if used_today >= AUTHED_FREE_PER_DAY:
            return QuotaResult(allowed=False, reason="subscribe_required")
        supa.record_search(user_id)
        return QuotaResult(allowed=True)

    # Anonymous
    used = _read_anon_cookie(anon_cookie)
    if used >= ANON_FREE_SEARCHES:
        return QuotaResult(allowed=False, reason="signup_required")
    used += 1
    return QuotaResult(
        allowed=True,
        remaining_anon=max(0, ANON_FREE_SEARCHES - used),
        cookie_value=_write_anon_cookie(used),
    )
