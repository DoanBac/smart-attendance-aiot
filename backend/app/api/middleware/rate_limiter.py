"""
Redis-backed rate limiter — fixed window counter.

Key:    rate_limit:{ip}:{window}      (window = unix_epoch // period)
Value:  integer request count
TTL:    2 × period (retain after window rolls over, auto-expire)

Fail-open: if Redis is unavailable the request is allowed through and a
warning is logged. This avoids denying legitimate traffic due to Redis hiccup.
"""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period

    async def dispatch(self, request: Request, call_next):
        # WebSocket upgrade path — BaseHTTPMiddleware cannot handle WS upgrades,
        # skip rate limiting entirely for them.
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        window = int(time.time()) // self.period
        key = f"rate_limit:{client_ip}:{window}"

        try:
            from app.core.redis_client import get_redis   # lazy import — avoids circular dep
            redis = await get_redis()

            # Atomic pipeline: INCR counter then set TTL in one round-trip
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.period * 2)   # keep 2 windows for safety
            results = await pipe.execute()
            count: int = results[0]

            if count > self.calls:
                retry_after = self.period - (int(time.time()) % self.period)
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "detail": (
                            f"Rate limit exceeded: {self.calls} requests per "
                            f"{self.period}s. Retry after {retry_after}s."
                        )
                    },
                )
        except Exception as exc:
            # Fail open — never block good traffic because of a Redis issue
            logger.warning("Rate limiter Redis error (fail-open): %s", exc)

        return await call_next(request)
