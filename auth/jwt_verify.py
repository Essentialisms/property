"""Verify Supabase-issued JWTs.

Modern Supabase projects sign user JWTs with asymmetric ES256 keys; older
projects use HS256 with a shared JWT_SECRET. This module handles both:
- if the token header has `alg=ES256` (or any RS*), the project's JWKS at
  `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` is fetched (cached for the
  process lifetime), and the kid-matched public key verifies the token;
- otherwise it falls back to HS256 with SUPABASE_JWT_SECRET.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import jwt
import requests
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

logger = logging.getLogger(__name__)

# Module-level JWKS cache. Supabase rotates rarely; refresh on miss.
_JWKS_CACHE: dict = {"fetched_at": 0.0, "keys_by_kid": {}}
_JWKS_TTL_SECONDS = 3600


def _secret() -> str | None:
    return os.environ.get("SUPABASE_JWT_SECRET") or None


def _jwks_url() -> str | None:
    base = os.environ.get("SUPABASE_URL")
    if not base:
        return None
    return base.rstrip("/") + "/auth/v1/.well-known/jwks.json"


def _load_jwks(force: bool = False) -> dict[str, object]:
    now = time.time()
    if not force and _JWKS_CACHE["keys_by_kid"] and (now - _JWKS_CACHE["fetched_at"]) < _JWKS_TTL_SECONDS:
        return _JWKS_CACHE["keys_by_kid"]
    url = _jwks_url()
    if not url:
        return {}
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            logger.warning("JWKS fetch returned %s", resp.status_code)
            return _JWKS_CACHE["keys_by_kid"]
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("JWKS fetch failed: %s", e)
        return _JWKS_CACHE["keys_by_kid"]

    new_keys: dict[str, object] = {}
    for k in data.get("keys", []) or []:
        kid = k.get("kid")
        alg = (k.get("alg") or "").upper()
        if not kid:
            continue
        try:
            if alg.startswith("ES"):
                pubkey = ECAlgorithm.from_jwk(k)
            elif alg.startswith("RS") or alg.startswith("PS"):
                pubkey = RSAAlgorithm.from_jwk(k)
            else:
                continue
            new_keys[kid] = (alg, pubkey)
        except Exception as e:
            logger.warning("Failed to parse JWK %s: %s", kid, e)
    if new_keys:
        _JWKS_CACHE["keys_by_kid"] = new_keys
        _JWKS_CACHE["fetched_at"] = now
    return _JWKS_CACHE["keys_by_kid"]


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

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        logger.info("JWT header parse failed: %s", e)
        return None

    alg = (header.get("alg") or "").upper()
    kid = header.get("kid")

    try:
        if alg == "HS256":
            secret = _secret()
            if not secret:
                logger.warning("SUPABASE_JWT_SECRET not configured for HS256 token")
                return None
            claims = jwt.decode(
                token, secret, algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        elif alg.startswith("ES") or alg.startswith("RS"):
            keys = _load_jwks()
            entry = keys.get(kid) if kid else None
            if not entry:
                # Maybe a rotation — force a refresh once.
                keys = _load_jwks(force=True)
                entry = keys.get(kid) if kid else None
            if not entry:
                logger.warning("No JWKS key for kid=%s", kid)
                return None
            jwk_alg, pubkey = entry
            claims = jwt.decode(
                token, pubkey, algorithms=[alg, jwk_alg],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        else:
            logger.warning("Unsupported JWT alg: %s", alg)
            return None
    except jwt.PyJWTError as e:
        logger.info("JWT decode failed (alg=%s): %s", alg, e)
        return None

    if claims.get("exp", 0) < time.time():
        return None
    return claims


def user_id_from_request(headers) -> Optional[str]:
    claims = verify_bearer(headers.get("Authorization"))
    if not claims:
        return None
    return claims.get("sub")
