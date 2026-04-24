"""Thread-safe rate limiter for free LLM API tiers.

OpenRouter free models: 20 RPM, 1000 req/day (with $10 balance)
Groq free tier:         30 RPM, 1000 req/day per model
Together free:          60 RPM

This module provides:
  1. RateLimiter  — token-bucket limiter, shared across threads
  2. retry_on_rate_limit — decorator/context that retries with backoff on 429s
  3. patch_openai_with_rate_limit — wraps openai.chat.completions.create
     with both rate limiting and retry logic in one call

Usage
-----
    from core.rate_limiter import RateLimiter, patch_openai_with_rate_limit

    limiter = RateLimiter(
        requests_per_minute=18,   # stay under OpenRouter's 20 RPM
        daily_limit=900,          # stay under 1000/day
    )
    patch_openai_with_rate_limit(limiter)  # install globally once

    # All subsequent openai.chat.completions.create calls are now rate-limited.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket rate limiter, thread-safe.

    Enforces:
      - requests_per_minute  (short-window cap)
      - daily_limit          (rolling 24h cap; resets at midnight UTC)
    """

    def __init__(
        self,
        requests_per_minute: int = 18,
        daily_limit: int = 900,
        provider: str = "openrouter",
    ) -> None:
        self.rpm = requests_per_minute
        self.daily_limit = daily_limit
        self.provider = provider

        # Token bucket: refills at rpm / 60 tokens per second
        self._bucket_lock = threading.Lock()
        self._tokens: float = float(requests_per_minute)
        self._last_refill: float = time.monotonic()

        # Daily counter: resets at midnight UTC
        self._day_lock = threading.Lock()
        self._day_count: int = 0
        self._day_start: float = self._midnight_utc()

    # --------------------------------------------------------------------- #
    # Public
    # --------------------------------------------------------------------- #

    def acquire(self, block: bool = True) -> bool:
        """Acquire one request slot. Blocks if rate-limited when block=True."""
        if not self._check_daily():
            if not block:
                return False
            # Daily limit hit — sleep until midnight UTC
            sleep_s = self._midnight_utc() + 86400 - time.time()
            logger.warning(
                "Daily limit reached for %s. Sleeping %.0fs until reset.",
                self.provider, sleep_s,
            )
            time.sleep(max(sleep_s, 0))
            self._reset_daily()

        while True:
            wait = self._try_acquire_token()
            if wait == 0:
                self._increment_daily()
                return True
            if not block:
                return False
            time.sleep(wait)

    def wait_if_needed(self) -> None:
        """Block until a request slot is available. Convenience wrapper."""
        self.acquire(block=True)

    def status(self) -> dict:
        with self._bucket_lock:
            tokens = self._tokens
        with self._day_lock:
            day_count = self._day_count
        return {
            "provider": self.provider,
            "rpm_cap": self.rpm,
            "daily_cap": self.daily_limit,
            "tokens_available": round(tokens, 2),
            "day_count": day_count,
            "day_remaining": self.daily_limit - day_count,
        }

    # --------------------------------------------------------------------- #
    # Internal
    # --------------------------------------------------------------------- #

    def _refill(self) -> None:
        """Refill the token bucket based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self.rpm),
            self._tokens + elapsed * (self.rpm / 60.0),
        )
        self._last_refill = now

    def _try_acquire_token(self) -> float:
        """Try to consume one token. Returns 0 on success, wait_seconds on failure."""
        with self._bucket_lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0
            # How long until 1 token is available?
            return (1.0 - self._tokens) / (self.rpm / 60.0)

    def _check_daily(self) -> bool:
        with self._day_lock:
            if time.time() >= self._day_start + 86400:
                self._day_count = 0
                self._day_start = self._midnight_utc()
            return self._day_count < self.daily_limit

    def _increment_daily(self) -> None:
        with self._day_lock:
            self._day_count += 1

    def _reset_daily(self) -> None:
        with self._day_lock:
            self._day_count = 0
            self._day_start = self._midnight_utc()

    @staticmethod
    def _midnight_utc() -> float:
        import datetime
        now = datetime.datetime.utcnow()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp()

    @classmethod
    def from_env(cls) -> "RateLimiter":
        """Build a RateLimiter from environment variables."""
        rpm = int(os.environ.get("OPENROUTER_REQUESTS_PER_MINUTE", "18"))
        daily = int(os.environ.get("OPENROUTER_DAILY_LIMIT", "900"))
        provider = "openrouter"
        base_url = os.environ.get("OPENAI_BASE_URL", "")
        if "groq" in base_url:
            rpm = int(os.environ.get("GROQ_REQUESTS_PER_MINUTE", "28"))
            daily = int(os.environ.get("GROQ_DAILY_LIMIT", "950"))
            provider = "groq"
        elif "together" in base_url:
            rpm = int(os.environ.get("TOGETHER_REQUESTS_PER_MINUTE", "55"))
            daily = int(os.environ.get("TOGETHER_DAILY_LIMIT", "9999"))
            provider = "together"
        elif "localhost" in base_url or "127.0.0.1" in base_url:
            # Local vLLM/Ollama — no rate limiting needed
            rpm = 999
            daily = 999999
            provider = "local"
        return cls(rpm, daily, provider)


# --------------------------------------------------------------------------- #
# Retry logic
# --------------------------------------------------------------------------- #

def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if exc is a 429 / rate-limit response."""
    msg = str(exc).lower()
    return any(kw in msg for kw in (
        "429", "rate limit", "too many requests",
        "rate_limit_exceeded", "quota", "capacity",
    ))


def with_retry(
    fn: Callable,
    *args,
    max_retries: int = 6,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    limiter: RateLimiter | None = None,
    **kwargs,
) -> Any:
    """Call fn(*args, **kwargs) with exponential back-off on rate-limit errors.

    Also calls limiter.wait_if_needed() before each attempt if provided.
    """
    for attempt in range(max_retries + 1):
        if limiter is not None:
            limiter.wait_if_needed()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_rate_limit_error(exc):
                raise
            if attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Rate limited (attempt %d/%d). Retrying in %.0fs. Error: %s",
                attempt + 1, max_retries, delay, exc,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------- #
# Global patch
# --------------------------------------------------------------------------- #

_GLOBAL_LIMITER: RateLimiter | None = None
_PATCH_LOCK = threading.Lock()
_ORIGINAL_CREATE: Any = None


def patch_openai_with_rate_limit(limiter: RateLimiter | None = None) -> RateLimiter:
    """Wrap openai.chat.completions.create with rate limiting + retry.

    Idempotent — calling twice is safe.
    Returns the active limiter.
    """
    global _GLOBAL_LIMITER, _ORIGINAL_CREATE

    with _PATCH_LOCK:
        if _GLOBAL_LIMITER is not None:
            return _GLOBAL_LIMITER

        lim = limiter or RateLimiter.from_env()
        _GLOBAL_LIMITER = lim

        try:
            import openai
        except ImportError:
            return lim

        original = openai.chat.completions.create
        _ORIGINAL_CREATE = original

        def _rate_limited_create(*args, **kwargs):
            return with_retry(
                original, *args,
                limiter=lim,
                max_retries=6,
                base_delay=5.0,
                **kwargs,
            )

        openai.chat.completions.create = _rate_limited_create
        logger.info(
            "Rate limiter installed: %s  rpm=%d  daily=%d",
            lim.provider, lim.rpm, lim.daily_limit,
        )
        return lim


def unpatch_openai() -> None:
    global _GLOBAL_LIMITER, _ORIGINAL_CREATE
    with _PATCH_LOCK:
        if _ORIGINAL_CREATE is not None:
            import openai
            openai.chat.completions.create = _ORIGINAL_CREATE
            _ORIGINAL_CREATE = None
            _GLOBAL_LIMITER = None
