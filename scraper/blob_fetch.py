"""Fetch the cached property dataset from Vercel Blob storage."""

import json
import logging
import os
import time

import requests

from scraper.models import Property

logger = logging.getLogger(__name__)

_CACHE: dict = {"data": None, "fetched_at": 0.0}
_CACHE_TTL_SECONDS = 300


def fetch_from_blob() -> tuple[list[Property] | None, str | None]:
    """Return (properties, error). On success, error is None and properties is non-None."""
    url = os.environ.get("BLOB_DATA_URL")
    if not url:
        return None, None

    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["fetched_at"] < _CACHE_TTL_SECONDS:
        return _CACHE["data"], None

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None, f"Blob returned {resp.status_code}"
        payload = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning(f"Blob fetch failed: {e}")
        return None, str(e)

    raw = payload.get("properties") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return None, "Blob payload missing 'properties' list"

    # Stored payload may carry tracking metadata (first_seen/last_seen) that
    # isn't part of the Property dataclass — strip before reconstituting.
    extra_keys = {"first_seen", "last_seen"}
    properties: list[Property] = []
    for item in raw:
        try:
            clean = {k: v for k, v in item.items() if k not in extra_keys}
            properties.append(Property(**clean))
        except TypeError:
            continue

    _CACHE["data"] = properties
    _CACHE["fetched_at"] = now
    return properties, None
