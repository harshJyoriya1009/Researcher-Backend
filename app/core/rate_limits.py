from __future__ import annotations

import math
import time
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import RateLimitExceededError
from app.core.redis_client import get_redis_client


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
        if candidate:
            return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@dataclass(slots=True)
class BackoffState:
    attempts: int
    retry_after_seconds: int


class RedisRateLimiter:
    def __init__(self, redis: Redis | None = None):
        self.redis = redis or get_redis_client()

    def _window_key(self, scope: str, identifier: str) -> str:
        return f"rate:window:{scope}:{identifier}"

    def _backoff_count_key(self, scope: str, identifier: str) -> str:
        return f"rate:backoff:count:{scope}:{identifier}"

    def _backoff_block_key(self, scope: str, identifier: str) -> str:
        return f"rate:backoff:block:{scope}:{identifier}"

    async def enforce_fixed_window(
        self,
        *,
        scope: str,
        identifier: str,
        limit: int,
        window_seconds: int,
        message: str,
    ) -> None:
        if limit <= 0:
            return

        key = self._window_key(scope, identifier)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, window_seconds)

        if count > limit:
            ttl = await self.redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else window_seconds
            raise RateLimitExceededError(f"{message} Try again in {retry_after} seconds.")

    async def ensure_backoff_clear(self, *, scope: str, identifier: str) -> None:
        block_key = self._backoff_block_key(scope, identifier)
        blocked_until_raw = await self.redis.get(block_key)
        if not blocked_until_raw:
            return

        try:
            blocked_until = float(blocked_until_raw)
        except (TypeError, ValueError):
            await self.redis.delete(block_key)
            return

        remaining = math.ceil(blocked_until - time.time())
        if remaining <= 0:
            await self.redis.delete(block_key)
            return

        raise RateLimitExceededError(
            f"Too many failed attempts. Please try again in {remaining} seconds."
        )

    async def record_backoff_failure(
        self,
        *,
        scope: str,
        identifier: str,
        window_seconds: int,
        base_delay_seconds: int,
        max_delay_seconds: int,
    ) -> BackoffState:
        count_key = self._backoff_count_key(scope, identifier)
        block_key = self._backoff_block_key(scope, identifier)

        attempts = await self.redis.incr(count_key)
        if attempts == 1:
            await self.redis.expire(count_key, window_seconds)

        if attempts < settings.RATE_LIMIT_AUTH_FAILURE_BACKOFF_THRESHOLD:
            await self.redis.delete(block_key)
            return BackoffState(attempts=attempts, retry_after_seconds=0)

        exponent = attempts - settings.RATE_LIMIT_AUTH_FAILURE_BACKOFF_THRESHOLD
        delay = min(base_delay_seconds * (2**exponent), max_delay_seconds)
        retry_after = max(1, int(delay))
        blocked_until = time.time() + retry_after
        await self.redis.set(block_key, str(blocked_until), ex=retry_after)

        return BackoffState(attempts=attempts, retry_after_seconds=retry_after)

    async def clear_backoff_state(self, *, scope: str, identifier: str) -> None:
        await self.redis.delete(
            self._backoff_count_key(scope, identifier),
            self._backoff_block_key(scope, identifier),
        )
