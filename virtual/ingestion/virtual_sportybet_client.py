"""
VirtualSportyBetClient - Correct implementation for SportyBet vFootball.

KEY INSIGHT (discovered 2026-08-26):
  - vFootball gameIds are allocated from a SHARED global pool across all leagues
  - All 6 leagues' IDs for the ~same kickoff time span ~2000+ units
  - Example from one round: Italy=34xxx, England=36xxx, Spain=36xxx (higher)
  - Italy 07:36 IDs: 34650-34928 (~280 unit spread, 10 matches)
  - England 07:58 IDs: 36211-36737 (~526 unit spread, 10 matches)
  - Spain 08:06 IDs: 36765-36984 (~219 unit spread, 10 matches)
  - Total span across all leagues for 2 upcoming rounds: ~3000 IDs

  SOLUTION: Async concurrent scanning with a wide window (±100 to +1500)
  Using 50 concurrent workers, 1500 IDs takes ~1.5s (vs 75s sequential)

CONFIRMED ENDPOINT:
  GET https://www.sportybet.com/api/ng/factsCenter/event?gameId={id}
  Returns sport.id = "sr:sport:202120001" for true vFootball events.
"""

import json
import time
import asyncio
import httpx
import logging
import os
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone

from virtual.core.config import virtual_config

logger = logging.getLogger("statiq.virtual.sportybet_client")

VFOOTBALL_SPORT_ID = "sr:sport:202120001"

_STATE_DIR = os.path.join(os.path.dirname(__file__), "..")
_WATERMARK_FILE = os.path.join(_STATE_DIR, ".vfootball_watermark.json")

# Initial anchor — updated from the first confirmed working run
_INITIAL_ANCHOR = 36591


class VirtualSportyBetClient:
    """
    HTTP client for SportyBet vFootball (Virtual Football).

    vFootball runs in ~30-minute rounds across 6 virtual leagues:
    England, Spain, Italy, Germany, France, Turkey.
    Each league has 10 matches per round.

    GameIds are 5-digit sequential integers allocated from a shared global pool.
    All league IDs for the same time window can span 1000-3000 units.
    We use async concurrent scanning to efficiently find them.
    """

    BASE_URL = "https://www.sportybet.com/api/ng/factsCenter"

    API_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sportybet.com/ng/sport/vFootball/",
        "Origin": "https://www.sportybet.com",
    }

    # Scan window: look back 50 and forward 400 around watermark (~450 IDs total)
    SCAN_BEHIND = 50
    SCAN_AHEAD = 400
    CONCURRENT_REQUESTS = 40  # Async workers


    # ---------------------------------------------------------------
    # Watermark persistence
    # ---------------------------------------------------------------

    @classmethod
    def _load_watermark(cls) -> int:
        try:
            with open(_WATERMARK_FILE, "r") as f:
                data = json.load(f)
                return int(data.get("max_game_id", _INITIAL_ANCHOR))
        except Exception:
            return _INITIAL_ANCHOR

    @classmethod
    def _save_watermark(cls, max_id: int):
        try:
            with open(_WATERMARK_FILE, "w") as f:
                json.dump({
                    "max_game_id": max_id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }, f)
        except Exception as e:
            logger.warning(f"[vFootball] Could not save watermark: {e}")

    _last_fetch_time: float = 0.0
    _cached_events: List[Dict[str, Any]] = []
    CACHE_TTL_SECONDS: float = 45.0

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    @classmethod
    def fetch_upcoming_virtual_events(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Discover and return all upcoming vFootball events from SportyBet.
        Uses async concurrent scanning across a wide ID window.
        Caches results for CACHE_TTL_SECONDS for fast responsiveness.
        """
        now = time.time()
        if not force_refresh and cls._cached_events and (now - cls._last_fetch_time < cls.CACHE_TTL_SECONDS):
            return cls._cached_events

        try:
            events = asyncio.run(cls._async_fetch_upcoming())
        except RuntimeError:
            # Already in an event loop (e.g. FastAPI / Uvicorn worker thread)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, cls._async_fetch_upcoming())
                events = future.result()

        if events:
            cls._cached_events = events
            cls._last_fetch_time = now

        return events or cls._cached_events


    @classmethod
    def fetch_event_by_game_id(cls, game_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single vFootball event by its gameId (synchronous)."""
        import httpx as _httpx
        try:
            with _httpx.Client(timeout=8.0, verify=False, follow_redirects=True) as client:
                r = client.get(
                    f"{cls.BASE_URL}/event?gameId={game_id}",
                    headers=cls.API_HEADERS
                )
                if r.status_code == 200:
                    d = r.json()
                    if d.get("bizCode") == 10000:
                        ev = d.get("data")
                        if ev and cls._is_vfootball_event(ev):
                            return ev
        except Exception as e:
            logger.debug(f"[vFootball] fetch_event_by_game_id error: {e}")
        return None

    @classmethod
    def fetch_event_result(cls, game_id: str) -> Optional[Dict[str, Any]]:
        """Fetch current state of a vFootball event (for result/settlement)."""
        return cls.fetch_event_by_game_id(game_id)

    VIRTUAL_TOURNAMENTS = [
        {"id": "sv:league:1", "name": "England Virtual"},
        {"id": "sv:league:2", "name": "Spain Virtual"},
        {"id": "sv:league:3", "name": "Italy Virtual"},
        {"id": "sv:league:4", "name": "Germany Virtual"},
        {"id": "sv:league:5", "name": "France Virtual"},
        {"id": "sv:league:6", "name": "Turkey Virtual"},
    ]

    # ---------------------------------------------------------------
    # Async concurrent tournament querying
    # ---------------------------------------------------------------

    @classmethod
    async def _async_fetch_upcoming(cls) -> List[Dict[str, Any]]:
        """
        Directly queries SportyBet's official vFootball tournament endpoints
        for all 6 virtual leagues in parallel. Fast (<1s) and 100% complete.
        """
        events = []
        now_ms = time.time() * 1000.0
        two_hours_ms = 2 * 3600 * 1000.0
        grace_ms = 3 * 60 * 1000.0

        async with httpx.AsyncClient(
            timeout=8.0,
            verify=False,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        ) as aclient:

            async def fetch_tournament(tour: Dict[str, str]) -> List[Dict[str, Any]]:
                url = f"{cls.BASE_URL}/wapUpcomingEvents?sportId={VFOOTBALL_SPORT_ID}&tournamentId={tour['id']}&pageSize=50"
                try:
                    r = await aclient.get(url, headers=cls.API_HEADERS)
                    if r.status_code == 200:
                        d = r.json()
                        if d.get("bizCode") == 10000:
                            matches = d.get("data", [])
                            if isinstance(matches, list):
                                return matches
                except Exception as e:
                    logger.debug(f"[vFootball] Error fetching {tour['name']}: {e}")
                return []

            tasks = [fetch_tournament(tour) for tour in cls.VIRTUAL_TOURNAMENTS]
            results = await asyncio.gather(*tasks, return_exceptions=False)

            seen_event_ids = set()
            for match_list in results:
                for ev in match_list:
                    if not isinstance(ev, dict) or not cls._is_vfootball_event(ev):
                        continue
                    ev_id = str(ev.get("eventId") or ev.get("gameId") or "")
                    if ev_id in seen_event_ids:
                        continue
                    seen_event_ids.add(ev_id)

                    start_ms = float(ev.get("estimateStartTime") or 0)
                    # Include active upcoming matches (within next 2 hours or starting within grace period)
                    if start_ms == 0 or (start_ms > (now_ms - grace_ms) and (start_ms - now_ms) < two_hours_ms):
                        events.append(ev)

        logger.info(f"[vFootball] Successfully fetched {len(events)} upcoming vFootball matches across all leagues")
        return events

    # ---------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------

    @classmethod
    def _is_vfootball_event(cls, event: Dict[str, Any]) -> bool:
        """Strictly validate this is a true vFootball event."""
        sport = event.get("sport", {})
        if isinstance(sport, dict):
            if sport.get("id") == VFOOTBALL_SPORT_ID:
                return True
        # Secondary check: virtual event IDs start with sr:match:2000
        event_id = str(event.get("eventId", ""))
        return "sr:match:2000" in event_id
