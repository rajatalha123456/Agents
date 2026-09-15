"""Redis-backed fixed-window rate limiting, per tenant and per user
(section 6.4). Stricter limits on upload and LLM endpoints.
"""
from __future__ import annotations

import time

from fastapi import Depends, HTTPException
from redis.asyncio import Redis

from ..auth.dependencies import CurrentUser, get_current_user
from ..jobs.worker import REDIS_URL

_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL)
    return _redis


async def _check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    redis = _get_redis()
    bucket = f"ratelimit:{key}:{int(time.time()) // window_seconds}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window_seconds)
    if count > max_requests:
        ttl = await redis.ttl(bucket)
        raise HTTPException(
            status_code=429, detail="rate limit exceeded",
            headers={"Retry-After": str(max(ttl, 1))},
        )


def rate_limit(max_requests: int, window_seconds: int = 60):
    """Per-tenant AND per-user limits, both enforced, whichever is
    stricter proportionally -- a noisy user cannot exhaust a tenant-wide
    budget for everyone else, and a tenant-wide burst cannot be dodged by
    switching users.
    """
    async def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        await _check_rate_limit(f"tenant:{user.tenant_id}", max_requests * 5, window_seconds)
        await _check_rate_limit(f"user:{user.user_id}", max_requests, window_seconds)
        return user

    return _dependency
