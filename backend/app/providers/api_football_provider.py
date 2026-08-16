import os
import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.providers.base import BaseProvider, NormalizedFixtureState
from app.core.config import settings

class ApiFootballProvider(BaseProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY") or getattr(settings, "API_FOOTBALL_KEY", "") or "0b0325d43261d8c75e97266397bbb3cc"
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            "x-apisports-key": self.api_key,
            "User-Agent": "StatIQ-Engine/2.0"
        }

    def get_provider_name(self) -> str:
        return "API_FOOTBALL"

    def fetch_fixture_state(self, provider_event_id: Optional[str] = None, provider_game_id: Optional[str] = None) -> Optional[NormalizedFixtureState]:
        fix_id = provider_event_id or provider_game_id
        if not fix_id:
            return None
        
        url = f"{self.base_url}/fixtures?id={fix_id}"
        try:
            with httpx.Client(timeout=8.0, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    arr = data.get("response", [])
                    if arr:
                        return self._parse_fixture_object(arr[0])
        except Exception as e:
            print(f"[ApiFootballProvider] Fetch error for {fix_id}:", e)
        return None

    def search_fixtures(self, date_str: str, competition: Optional[str] = None) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/fixtures?date={date_str}"
        try:
            with httpx.Client(timeout=10.0, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return resp.json().get("response", []) or []
        except Exception as e:
            print(f"[ApiFootballProvider] Search error for {date_str}:", e)
        return []

    def _parse_fixture_object(self, fix: Dict[str, Any]) -> NormalizedFixtureState:
        fixture_data = fix.get("fixture", {})
        status_data = fixture_data.get("status", {})
        short_status = str(status_data.get("short") or "").upper()
        elapsed = status_data.get("elapsed")
        
        goals = fix.get("goals", {})
        score = fix.get("score", {})
        halftime = score.get("halftime", {})
        
        h_score = goals.get("home")
        a_score = goals.get("away")
        ht_h = halftime.get("home")
        ht_a = halftime.get("away")
        
        is_finished = short_status in ("FT", "AET", "PEN", "FINISHED", "ENDED")
        is_live = short_status in ("1H", "HT", "2H", "ET", "P", "LIVE", "IN_PLAY")
        
        canonical_status = "SCHEDULED"
        if is_finished:
            canonical_status = "FINISHED"
        elif short_status == "HT":
            canonical_status = "HALFTIME"
        elif short_status == "2H":
            canonical_status = "SECOND_HALF"
        elif is_live:
            canonical_status = "LIVE"
        elif short_status in ("PST", "POSTPONED"):
            canonical_status = "POSTPONED"
        elif short_status in ("CANC", "CANCELLED"):
            canonical_status = "CANCELLED"
            
        clock_str = f"{elapsed}'" if elapsed else (short_status if short_status else "--")
        if is_finished:
            clock_str = "FT"
        elif short_status == "HT":
            clock_str = "HT"

        return NormalizedFixtureState(
            fixture_id=str(fixture_data.get("id")),
            provider="API_FOOTBALL",
            status=canonical_status,
            is_live=is_live,
            is_finished=is_finished,
            minute=int(elapsed) if elapsed is not None else None,
            match_clock=clock_str,
            home_score=int(h_score) if h_score is not None else None,
            away_score=int(a_score) if a_score is not None else None,
            half_time_home_score=int(ht_h) if ht_h is not None else None,
            half_time_away_score=int(ht_a) if ht_a is not None else None,
            updated_at=datetime.now(timezone.utc),
            raw_payload=fix
        )
