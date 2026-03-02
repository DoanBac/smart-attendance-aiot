import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self._cache: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # WebSocket upgrade — skip rate limiting (BaseHTTPMiddleware không handle WS)
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        client_ip = request.client.host
        now = time.time()
        window_start = now - self.period

        # Clean old entries
        self._cache[client_ip] = [t for t in self._cache[client_ip] if t > window_start]

        if len(self._cache[client_ip]) >= self.calls:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."}
            )

        self._cache[client_ip].append(now)
        return await call_next(request)