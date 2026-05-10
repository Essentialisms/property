"""Verify Supabase-issued JWTs.

Supabase signs user JWTs with a project-specific HS256 secret available in
the dashboard as the `JWT_SECRET`. This module verifies the bearer token
and returns the user_id (sub claim) when the token is valid.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import jwt

logger = logging.getLogger(__name__)


def _secret() -> str | None:
    return os.environ.get("SUPABASE_JWT_SECRET") or None


def verify_bearer(authorization_header: str | None) -> Optional[dict]:
    """Validate a 'Bearer <jwt>' header. Returns the decoded claims dict or
    None if the header is missing/invalid.
    """
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    secret = _secret()
    if not secret:
        logger.warning("SUPABASE_JWT_SECRET not configured — rejecting token")
        return None
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as e:
        logger.info("JWT decode failed: %s", e)
        return None
    if claims.get("exp", 0) < time.time():
        return None
    return claims


def user_id_from_request(headers) -> Optional[str]:
    claims = verify_bearer(headers.get("Authorization"))
    if not claims:
        return None
    return claims.get("sub")
