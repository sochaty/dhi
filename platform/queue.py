"""Redis priority queue stub.

Fully implemented in Post 9: "Building the Managed Inference Platform."

Design (when implemented):
  - Redis Sorted Set with score = priority (0=paid, 1=free)
  - Free tier: max 100 requests/day per user
  - Paid tier ($3/mo): unlimited, higher priority
"""

from __future__ import annotations


def enqueue(user_id: int, request_payload: dict, *, paid: bool = False) -> str:
    """Enqueue a completion request. Returns a request ID."""
    raise NotImplementedError("Platform queue — coming in Post 9")


def dequeue() -> dict | None:
    """Pop the highest-priority pending request. Returns None if queue is empty."""
    raise NotImplementedError("Platform queue — coming in Post 9")
