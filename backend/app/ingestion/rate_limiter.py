import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("matchiq.rate_limiter")

class HeaderAwareRateLimiter:
    """
    Header-aware rate limiter designed for Football-Data.org API.
    Inspects X-Requests-Available-Minute, X-RequestCounter-Reset, and 429 status codes
    to ensure zero rate limit violations.
    """
    def __init__(self, max_requests_per_minute: int = 10):
        self.max_requests = max_requests_per_minute
        self.requests_available: Optional[int] = max_requests_per_minute
        self.counter_reset_seconds: Optional[int] = 60
        self.lock = asyncio.Lock()
        self.last_request_time: float = 0.0
        # Enforce minimum delay between calls (~6.0s for 10 calls/min)
        self.min_delay: float = 60.0 / max_requests_per_minute

    async def acquire(self):
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time

            # If requests available header indicates zero remaining, wait until reset
            if self.requests_available is not None and self.requests_available <= 1:
                wait_time = max(self.counter_reset_seconds or 60, 6.0)
                logger.warning(f"[RateLimiter] Near rate limit ({self.requests_available} left). Throttling for {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                self.requests_available = self.max_requests
            elif elapsed < self.min_delay:
                wait_time = self.min_delay - elapsed
                logger.debug(f"[RateLimiter] Delaying request by {wait_time:.2f}s to respect 10 req/min...")
                await asyncio.sleep(wait_time)

            self.last_request_time = time.time()

    def update_from_headers(self, headers):
        """
        Dynamically updates throttling parameters based on response headers.
        Football-Data.org headers:
        - X-Requests-Available-Minute
        - X-RequestCounter-Reset
        """
        req_avail = headers.get("X-Requests-Available-Minute")
        req_reset = headers.get("X-RequestCounter-Reset")

        if req_avail is not None:
            try:
                self.requests_available = int(req_avail)
            except ValueError:
                pass

        if req_reset is not None:
            try:
                self.counter_reset_seconds = int(req_reset)
            except ValueError:
                pass

        logger.debug(f"[RateLimiter Update] Available: {self.requests_available}, Reset in: {self.counter_reset_seconds}s")
