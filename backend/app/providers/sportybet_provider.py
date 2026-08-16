import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.providers.base import BaseProvider, NormalizedFixtureState

class SportyBetProvider(BaseProvider):
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.sportybet.com/ng/',
            'Origin': 'https://www.sportybet.com'
        }

    def get_provider_name(self) -> str:
        return "SPORTYBET"

    def fetch_fixture_state(self, provider_event_id: Optional[str] = None, provider_game_id: Optional[str] = None) -> Optional[NormalizedFixtureState]:
        # Try fetching from SportyBet live events feed
        target_id = provider_event_id or provider_game_id
        if not target_id:
            return None

        live_url = "https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&pageSize=150"
        try:
            with httpx.Client(timeout=6.0, headers=self.headers, verify=False) as client:
                resp = client.get(live_url)
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("data", []) or []
                    for ev in events:
                        ev_gid = str(ev.get("gameId") or ev.get("eventId") or "")
                        ev_sr = str(ev.get("eventId") or "")
                        if target_id in (ev_gid, ev_sr):
                            return self._parse_sporty_event(ev, target_id)
        except Exception as e:
            print(f"[SportyBetProvider] Fetch error for {target_id}:", e)
        return None

    def search_fixtures(self, date_str: str, competition: Optional[str] = None) -> List[Dict[str, Any]]:
        live_url = "https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&pageSize=150"
        try:
            with httpx.Client(timeout=6.0, headers=self.headers, verify=False) as client:
                resp = client.get(live_url)
                if resp.status_code == 200:
                    return resp.json().get("data", []) or []
        except Exception as e:
            print(f"[SportyBetProvider] Search error:", e)
        return []

    def _parse_sporty_event(self, ev: Dict[str, Any], fix_id: str) -> NormalizedFixtureState:
        ev_score = ev.get("setScore") or ev.get("score") or ev.get("currentScore") or ""
        h_score = ev.get("homeScore") or ev.get("home_score")
        a_score = ev.get("awayScore") or ev.get("away_score")
        ev_clock = ev.get("playedSeconds") or ev.get("clock") or ""
        ev_status = str(ev.get("matchStatus") or "LIVE").upper()
        
        is_finished = ev_status in ("ENDED", "FT", "CONCLUDED", "FINISHED")
        is_live = ev_status in ("IN_PROGRESS", "LIVE", "H1", "H2", "HT") or (not is_finished and bool(ev_clock))
        
        mins = None
        clock_str = "--"
        if ev_clock:
            try:
                if isinstance(ev_clock, (int, float)):
                    mins = int(ev_clock) // 60
                    half = "H1" if mins <= 45 else "H2"
                    clock_str = f"{mins}' {half}"
                elif ":" in str(ev_clock):
                    mins = int(str(ev_clock).split(":")[0])
                    half = "H1" if mins <= 45 else "H2"
                    clock_str = f"{mins}' {half}"
            except Exception:
                clock_str = str(ev_clock)

        if is_finished:
            clock_str = "FT"
            canonical_status = "FINISHED"
        elif is_live:
            canonical_status = "LIVE"
        else:
            canonical_status = "SCHEDULED"

        if h_score is None and ev_score and "-" in ev_score:
            parts = ev_score.split("-")
            try:
                h_score = int(parts[0].strip())
                a_score = int(parts[1].strip())
            except Exception:
                pass

        return NormalizedFixtureState(
            fixture_id=fix_id,
            provider="SPORTYBET",
            status=canonical_status,
            is_live=is_live,
            is_finished=is_finished,
            minute=mins,
            match_clock=clock_str,
            home_score=int(h_score) if h_score is not None else None,
            away_score=int(a_score) if a_score is not None else None,
            updated_at=datetime.now(timezone.utc),
            raw_payload=ev
        )
