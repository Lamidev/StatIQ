import asyncio
import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.ingestion.rate_limiter import HeaderAwareRateLimiter

logger = logging.getLogger("matchiq.client")

class FootballDataClient:
    """
    HTTP Client for Football-Data.org API v4.
    Injects X-Auth-Token header and respects rate limits dynamically via headers.
    """
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.FOOTBALL_DATA_API_KEY
        self.base_url = (base_url or settings.FOOTBALL_DATA_BASE_URL).rstrip("/")
        self.headers = {
            "X-Auth-Token": self.api_key,
            "User-Agent": "MatchIQ-Engine/1.0"
        }
        self.rate_limiter = HeaderAwareRateLimiter(max_requests_per_minute=10)

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(1, retries + 1):
            await self.rate_limiter.acquire()
            logger.info(f"[FootballDataClient] GET {url} (Attempt {attempt}/{retries})")

            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    response = await client.get(url, headers=self.headers, params=params)
                    self.rate_limiter.update_from_headers(response.headers)

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(f"[429 Rate Limit Hit] Retrying in {retry_after} seconds...")
                        await asyncio.sleep(retry_after)
                    elif response.status_code == 403:
                        logger.error(f"[403 Forbidden] Access restricted for endpoint: {endpoint}. Check subscription tier.")
                        return {"error": "403 Forbidden", "status_code": 403, "endpoint": endpoint}
                    elif response.status_code == 404:
                        logger.warning(f"[404 Not Found] Endpoint or resource not found: {endpoint}")
                        return {"error": "404 Not Found", "status_code": 404, "endpoint": endpoint}
                    else:
                        logger.error(f"[{response.status_code} Error] Response: {response.text[:200]}")
                        response.raise_for_status()

                except httpx.HTTPError as exc:
                    logger.error(f"[HTTP Error] {exc} on attempt {attempt}")
                    if attempt == retries:
                        raise exc
                    await asyncio.sleep(2.0 * attempt)

        return {}
