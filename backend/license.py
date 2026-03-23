"""
System Link — Gumroad License Validator
========================================
Validates Gumroad purchase license keys against the Gumroad Licenses API.

How it works
------------
1. User purchases a subscription at the Gumroad product page.
2. Gumroad e-mails a unique license key to the buyer.
3. User enters the key in the System Link Settings panel.
4. The frontend sends ``POST /license/validate`` with the key.
5. This module calls ``https://api.gumroad.com/v2/licenses/verify``
   using the ``GUMROAD_PRODUCT_PERMALINK`` from the server environment.
6. A successful (non-refunded, non-cancelled) purchase is cached in Redis
   for 24 hours so subsequent API calls are instant.

Environment variables
---------------------
GUMROAD_PRODUCT_PERMALINK
    The slug portion of the product URL, e.g. the part after
    ``usayeed.gumroad.com/l/``.  This is the *product* identifier used
    when calling the Gumroad verification API.  Not a user secret.

CLOUD_OPENAI_API_KEY
    The owner's OpenAI API key used exclusively for validated Pro
    subscribers.  This key is **never** exposed to the client.

Security notes
--------------
• The raw license key is never cached or logged.  Only a SHA-256 hash is
  stored in Redis and log messages.
• If ``GUMROAD_PRODUCT_PERMALINK`` is absent (e.g. self-hosted free
  distribution), all keys are treated as invalid and the app falls back
  to the user-supplied ``OPENAI_API_KEY``.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"
GUMROAD_MANAGE_URL = "https://app.gumroad.com/subscriptions"
GUMROAD_PRODUCT_PERMALINK = os.environ.get("GUMROAD_PRODUCT_PERMALINK", "")
GUMROAD_PURCHASE_URL = (
    f"https://usayeed.gumroad.com/l/{GUMROAD_PRODUCT_PERMALINK}"
    if GUMROAD_PRODUCT_PERMALINK
    else "https://usayeed.gumroad.com"
)

_CACHE_TTL_S = 86_400  # 24 hours


def _cache_key(license_key: str) -> str:
    """Return the Redis key used to cache a validation result."""
    h = hashlib.sha256(license_key.encode()).hexdigest()
    return f"sl:license:{h}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def validate_license(
    license_key: str,
    redis_client: Optional[object] = None,  # aioredis.Redis
) -> bool:
    """
    Return ``True`` if *license_key* corresponds to a valid, active Gumroad
    subscription; ``False`` otherwise.

    Results are cached in Redis under ``sl:license:<sha256(key)>`` with a
    24-hour TTL to avoid hitting the Gumroad API on every request.  If Redis
    is unavailable the check is performed live.

    The function never raises; errors are logged and ``False`` is returned.
    """
    if not GUMROAD_PRODUCT_PERMALINK:
        log.debug(
            "GUMROAD_PRODUCT_PERMALINK not configured; "
            "treating all license keys as invalid (self-hosted free mode)."
        )
        return False

    if not license_key or not license_key.strip():
        return False

    key = license_key.strip()
    cache_key = _cache_key(key)

    # ── Redis cache check ────────────────────────────────────────────────────
    if redis_client is not None:
        try:
            cached = await redis_client.get(cache_key)  # type: ignore[union-attr]
            if cached is not None:
                log.debug("License cache hit for key hash %s…", cache_key[-8:])
                return cached == "1"
        except Exception as exc:
            log.warning("Redis license cache read failed: %s", exc)

    # ── Gumroad API call ─────────────────────────────────────────────────────
    valid = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GUMROAD_VERIFY_URL,
                data={
                    "product_permalink": GUMROAD_PRODUCT_PERMALINK,
                    "license_key": key,
                    "increment_uses_count": "false",
                },
            )
            data = resp.json()

        if not data.get("success", False):
            log.info(
                "License validation failed (Gumroad returned success=false): %s",
                data.get("message", "no message"),
            )
            valid = False
        else:
            purchase = data.get("purchase", {})
            refunded = purchase.get("refunded", False)
            chargebacked = purchase.get("chargebacked", False)
            cancelled = (
                purchase.get("subscription_cancelled_at") is not None
                and purchase.get("subscription_ended_at") is not None
            )
            if refunded or chargebacked or cancelled:
                log.info(
                    "License key invalid: refunded=%s chargebacked=%s cancelled=%s",
                    refunded,
                    chargebacked,
                    cancelled,
                )
                valid = False
            else:
                valid = True
                log.info("License key validated successfully.")

    except Exception as exc:
        log.error("Gumroad API call failed: %s", exc)
        valid = False

    # ── Store result in Redis ────────────────────────────────────────────────
    if redis_client is not None:
        try:
            await redis_client.set(  # type: ignore[union-attr]
                cache_key, "1" if valid else "0", ex=_CACHE_TTL_S
            )
        except Exception as exc:
            log.warning("Redis license cache write failed: %s", exc)

    return valid


def cloud_openai_key() -> Optional[str]:
    """Return the owner's cloud OpenAI API key, or None if not configured."""
    return os.environ.get("CLOUD_OPENAI_API_KEY") or None
