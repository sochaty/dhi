"""GitHub OAuth → JWT auth stub.

Fully implemented in Post 9: "Building the Managed Inference Platform:
GitHub OAuth, Redis Queue, and Per-User Token Metering."
"""

from __future__ import annotations


def exchange_github_code(code: str) -> dict:
    """Exchange a GitHub OAuth code for an access token."""
    raise NotImplementedError("Platform auth — coming in Post 9")


def issue_jwt(github_user_id: int, username: str) -> str:
    """Issue a signed JWT for the authenticated user."""
    raise NotImplementedError("Platform auth — coming in Post 9")


def verify_jwt(token: str) -> dict:
    """Verify and decode a Dhi JWT. Returns the claims dict."""
    raise NotImplementedError("Platform auth — coming in Post 9")
