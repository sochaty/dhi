"""Per-user token metering stub.

Fully implemented in Post 9: "Building the Managed Inference Platform."

Design (when implemented):
  - Redis INCR counter keyed by user_id + date bucket
  - Free tier: 100 completions/day — returns 429 when exceeded
  - Paid tier: unlimited, tracked for billing via Stripe usage records
"""

from __future__ import annotations

FREE_TIER_DAILY_LIMIT = 100


def record_completion(user_id: int, tokens_used: int) -> None:
    """Record a completion for metering/billing."""
    raise NotImplementedError("Platform metering — coming in Post 9")


def check_quota(user_id: int) -> bool:
    """Return True if the user is within their daily quota."""
    raise NotImplementedError("Platform metering — coming in Post 9")


def daily_usage(user_id: int) -> int:
    """Return the number of completions the user has made today."""
    raise NotImplementedError("Platform metering — coming in Post 9")
