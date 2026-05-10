"""Thin wrapper around Supabase's PostgREST API for the tables we own.

Avoids a heavy SDK — just signed HTTP calls with the service role key for
backend-only operations (writing subscription rows, counting daily searches).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _base() -> str | None:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        return None
    return url.rstrip("/") + "/rest/v1"


def _service_key() -> str | None:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None


def _headers() -> dict[str, str]:
    key = _service_key() or ""
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def is_configured() -> bool:
    return bool(_base() and _service_key())


def get_subscription(user_id: str) -> dict | None:
    base = _base()
    if not base:
        return None
    try:
        r = requests.get(
            f"{base}/subscriptions",
            params={"user_id": f"eq.{user_id}", "select": "*", "limit": "1"},
            headers=_headers(),
            timeout=5,
        )
        if r.status_code != 200:
            logger.warning("subscriptions select returned %s: %s", r.status_code, r.text[:200])
            return None
        rows = r.json()
        return rows[0] if rows else None
    except requests.RequestException as e:
        logger.warning("subscriptions select failed: %s", e)
        return None


def upsert_subscription(row: dict[str, Any]) -> bool:
    base = _base()
    if not base:
        return False
    try:
        r = requests.post(
            f"{base}/subscriptions",
            json=row,
            headers={**_headers(), "Prefer": "return=minimal,resolution=merge-duplicates"},
            timeout=8,
        )
        if r.status_code >= 400:
            logger.warning("upsert_subscription %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except requests.RequestException as e:
        logger.warning("upsert_subscription failed: %s", e)
        return False


def record_search(user_id: str) -> bool:
    base = _base()
    if not base:
        return False
    payload = {"user_id": user_id, "searched_at": datetime.now(timezone.utc).isoformat()}
    try:
        r = requests.post(f"{base}/searches", json=payload, headers=_headers(), timeout=5)
        return r.status_code < 400
    except requests.RequestException as e:
        logger.warning("record_search failed: %s", e)
        return False


def count_searches_today_utc(user_id: str) -> int:
    base = _base()
    if not base:
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        r = requests.get(
            f"{base}/searches",
            params={
                "user_id": f"eq.{user_id}",
                "searched_at": f"gte.{today}T00:00:00Z",
                "select": "id",
            },
            headers={**_headers(), "Prefer": "count=exact"},
            timeout=5,
        )
        if r.status_code != 200:
            return 0
        # Supabase returns total in Content-Range header when count=exact
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:
            try:
                return int(cr.split("/", 1)[1])
            except ValueError:
                pass
        return len(r.json())
    except requests.RequestException as e:
        logger.warning("count_searches_today failed: %s", e)
        return 0
