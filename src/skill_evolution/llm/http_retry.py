"""Bounded retry helpers for OpenAI-compatible / Claude HTTP clients.

Defaults (mirrored on ``LLMConfig``):

* ``timeout_s``: 60.0 — per-request HTTP timeout (SDK client timeout)
* ``max_retries``: 3 — extra attempts after the first (4 attempts total)
* ``retry_backoff_s``: 0.5 — initial delay; doubles each retry
* max sleep per attempt: 8.0s (also caps ``Retry-After``)

Retries only transient failures: timeouts, connection errors, 429, 5xx.
``max_retries`` is hard-capped at 6 so a config typo cannot invent a long loop.
SDK-level retries are disabled on the HTTP clients so loops are not nested.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0
MAX_RETRIES_CAP = 6

_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
_RETRYABLE_NAME_TOKENS = (
    "timeout",
    "ratelimit",
    "apiconnection",
    "internalserver",
    "serviceunavailable",
    "connecterror",
    "remoteprotocol",
    "apitimeout",
)

T = TypeVar("T")


def clamp_max_retries(max_retries: int) -> int:
    """Bound retries to [0, MAX_RETRIES_CAP]. Never unbounded."""
    return max(0, min(int(max_retries), MAX_RETRIES_CAP))


def is_retryable(exc: BaseException) -> bool:
    """True for timeouts, connection failures, 429, and 5xx-class HTTP errors."""
    if isinstance(exc, (TimeoutError, ConnectionError, BrokenPipeError)):
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS or status >= 500
    name = type(exc).__name__.lower()
    return any(token in name for token in _RETRYABLE_NAME_TOKENS)


def retry_after_seconds(exc: BaseException) -> float | None:
    """Parse a Retry-After header if the exception exposes one."""
    headers = None
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(exc, "headers", None)
    if not headers:
        return None
    raw = None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def retry_delay(
    exc: BaseException,
    attempt: int,
    backoff_s: float,
    max_backoff_s: float = MAX_BACKOFF_S,
) -> float:
    """Exponential backoff, honoring Retry-After when present and bounded."""
    after = retry_after_seconds(exc)
    if after is not None:
        return min(max(after, 0.0), max_backoff_s)
    return min(max(backoff_s, 0.0) * (2**attempt), max_backoff_s)


async def call_with_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_s: float = DEFAULT_BACKOFF_S,
    max_backoff_s: float = MAX_BACKOFF_S,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> T:
    """Await ``factory()``, retrying a bounded number of transient failures.

    ``factory`` must create a fresh awaitable each call (coroutines cannot be
    reused). ``max_retries`` is extra attempts after the first, capped at 6.
    """
    sleeper = sleep or asyncio.sleep
    retries = clamp_max_retries(max_retries)
    last_exc: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            return await factory()
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc) or attempt >= retries:
                raise
            delay = retry_delay(exc, attempt, backoff_s, max_backoff_s)
            logger.warning(
                "LLM HTTP transient error (%s: %s); retry %d/%d in %.2fs",
                type(exc).__name__,
                exc,
                attempt + 1,
                retries,
                delay,
            )
            await sleeper(delay)
    assert last_exc is not None
    raise last_exc
