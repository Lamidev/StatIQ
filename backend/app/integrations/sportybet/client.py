import logging
import time
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("matchiq.integrations.sportybet.client")

class SportyBetClient:
    """
    Dedicated HTTP Client for communicating directly with SportyBet FactsCenter APIs.
    Handles connection pooling, request throttling, and raw response extraction.
    """
    BASE_URL = "https://www.sportybet.com/api"
    DEFAULT_REGION = "ng"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.sportybet.com",
        "Referer": "https://www.sportybet.com/ng/"
    }

    def __init__(self, region: str = "ng", timeout: float = 8.0, max_connections: int = 50):
        self.region = region.lower()
        self.timeout = timeout
        self.max_connections = max_connections
        self._client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None

    async def get_async_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.HEADERS,
                limits=httpx.Limits(max_keepalive_connections=self.max_connections, max_connections=100),
                follow_redirects=True,
                verify=False
            )
        return self._client

    def get_sync_client(self) -> httpx.Client:
        if self._sync_client is None or self._sync_client.is_closed:
            self._sync_client = httpx.Client(
                timeout=self.timeout,
                headers=self.HEADERS,
                limits=httpx.Limits(max_keepalive_connections=self.max_connections, max_connections=100),
                follow_redirects=True,
                verify=False
            )
        return self._sync_client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()

    async def fetch_configurable_events(
        self,
        sport_id: str = "sr:sport:1",
        page_num: int = 1,
        page_size: int = 50,
        today_games: bool = True,
        timeline: Optional[int] = None,
        tournament_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Queries wapConfigurableEventsByOrder endpoint with exact filters and pagination.
        """
        url = f"{self.BASE_URL}/{self.region}/factsCenter/wapConfigurableEventsByOrder"
        payload = {
            "sportId": sport_id,
            "pageNum": page_num,
            "pageSize": page_size,
            "withTwoUpMarket": True,
            "withOneUpMarket": True
        }
        if today_games:
            payload["todayGames"] = True
        elif timeline is not None:
            payload["timeline"] = timeline
        if tournament_id:
            payload["tournamentId"] = tournament_id

        client = await self.get_async_client()
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("bizCode") == 10000:
                    return data.get("data", {})
            else:
                logger.warning(f"[SportyBetClient] HTTP {resp.status_code} on {url}")
        except Exception as e:
            logger.error(f"[SportyBetClient] fetch_configurable_events error: {e}")
        return {}

    async def fetch_upcoming_events_flat(
        self,
        sport_id: str = "sr:sport:1",
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Queries wapUpcomingEvents endpoint.
        """
        url = f"{self.BASE_URL}/{self.region}/factsCenter/wapUpcomingEvents?sportId={sport_id}&pageSize={page_size}"
        client = await self.get_async_client()
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("bizCode") == 10000:
                    raw_data = data.get("data", [])
                    if isinstance(raw_data, list):
                        return raw_data
                    elif isinstance(raw_data, dict):
                        return raw_data.get("events", [])
        except Exception as e:
            logger.error(f"[SportyBetClient] fetch_upcoming_events_flat error: {e}")
        return []

    async def fetch_event_details(self, event_id: str) -> Dict[str, Any]:
        """
        Fetches full detailed event payload with all deep markets from pcEventDetails or eventDetail.
        """
        urls = [
            f"{self.BASE_URL}/{self.region}/factsCenter/pcEventDetails?eventId={event_id}",
            f"{self.BASE_URL}/{self.region}/factsCenter/eventDetail?eventId={event_id}",
        ]
        client = await self.get_async_client()
        for url in urls:
            try:
                resp = await client.get(url, timeout=4.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("bizCode") == 10000:
                        payload = data.get("data")
                        if isinstance(payload, dict):
                            return payload
                        elif isinstance(payload, list) and payload:
                            return payload[0]
            except Exception as e:
                logger.debug(f"[SportyBetClient] fetch_event_details failed on {url}: {e}")
        return {}

    async def fetch_h2h_stats(self, event_id: str) -> Dict[str, Any]:
        """
        Fetches internal head-to-head match stats.
        """
        url = f"{self.BASE_URL}/{self.region}/factsCenter/h2h/{event_id}"
        client = await self.get_async_client()
        try:
            resp = await client.get(url, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("bizCode") == 10000:
                    return data.get("data") or {}
        except Exception as e:
            logger.debug(f"[SportyBetClient] fetch_h2h_stats error for {event_id}: {e}")
        return {}
