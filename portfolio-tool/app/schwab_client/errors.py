"""Schwab adapter error types."""

from __future__ import annotations


class SchwabError(Exception):
    """Base for all adapter errors."""


class SchwabAuthError(SchwabError):
    """OAuth load/refresh failed."""


class SchwabAPIError(SchwabError):
    """A read-only API call failed."""


class RateLimitError(SchwabError):
    """Rate limit exceeded."""


class StaleCacheError(SchwabError):
    """API failed and the only cache available is stale."""


class OrderExecutionDisabledError(SchwabError):
    """Raised if any execution path is reached while order_execution_enabled is false.

    v1 is read-only and ships NO execution endpoints; this exists so that, if order
    code is ever added, it is gated behind config and fails loudly by default.
    """
