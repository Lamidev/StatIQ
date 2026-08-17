import time
import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("matchiq.sportybet_ingestion")

class SportyBetIngestionService:
    """
    StatIQ V2.0 Native SportyBet Fixture & Odds Ingestion Service.
    Pulls live upcoming matches, tournament metadata, and decimal odds directly from SportyBet API.
    """
    BASE_URL = "https://www.sportybet.com/api/ng/factsCenter"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sportybet.com/ng/",
        "Origin": "https://www.sportybet.com"
    }

    _cache: Dict[str, Any] = {}
    _cache_ttl = 120  # 2 minutes cache for live odds freshness

    TOP_TOURNAMENTS = [
        "sr:tournament:17",   # Premier League
        "sr:tournament:8",    # LaLiga
        "sr:tournament:23",   # Serie A
        "sr:tournament:35",   # Bundesliga
        "sr:tournament:34",   # Ligue 1
        "sr:tournament:37",   # Eredivisie
        "sr:tournament:18",   # Championship
        "sr:tournament:40",   # Allsvenskan
        "sr:tournament:41",   # Eliteserien
        "sr:tournament:39",   # Superliga (Denmark)
        "sr:tournament:7",    # Champions League
        "sr:tournament:679",  # Europa League
        "sr:tournament:325",  # UEFA Conference League
        "sr:tournament:52",   # Super Lig (Turkey)
        "sr:tournament:242",  # MLS
        "sr:tournament:384",  # Saudi Pro League
        "sr:tournament:329",  # Brazil Serie A
        "sr:tournament:155",  # Argentina Liga Profesional
        "sr:tournament:45",   # Scottish Premiership
        "sr:tournament:38",   # Belgian Pro League
        "sr:tournament:44",   # Austrian Bundesliga
        "sr:tournament:238",  # Portugal Primeira Liga
    ]

    @classmethod
    def fetch_upcoming_fixtures(cls, limit: int = 250, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches active upcoming football fixtures from SportyBet across all major tournaments.
        """
        import concurrent.futures

        cache_key = "master_upcoming_pool"
        now = time.time()

        if not force_refresh and cache_key in cls._cache:
            entry = cls._cache[cache_key]
            if (now - entry["timestamp"]) < cls._cache_ttl and len(entry.get("data", [])) > 0:
                cached_data = entry["data"]
                return cached_data[:limit] if limit else cached_data

        def _fetch_url(url: str) -> List[Dict[str, Any]]:
            try:
                with httpx.Client(timeout=6.0, headers=cls.HEADERS) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        j = resp.json()
                        if j.get("bizCode") == 10000:
                            data = j.get("data", [])
                            return data if isinstance(data, list) else data.get("events", [])
            except Exception as e:
                logger.debug(f"[SportyBetIngestion] URL fetch error: {e}")
            return []

        fetch_urls = [
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&pageNum=1&pageSize=100",
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&pageNum=2&pageSize=100",
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&timeline=today&pageSize=100",
        ] + [
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&tournamentId={t_id}" for t_id in cls.TOP_TOURNAMENTS
        ]

        all_events = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(fetch_urls))) as executor:
            results = list(executor.map(_fetch_url, fetch_urls))
            for items in results:
                all_events.extend(items)

        # Deduplicate events by eventId
        unique_events = []
        seen_ids = set()
        for ev in all_events:
            ev_id = str(ev.get("eventId") or ev.get("gameId") or "")
            if ev_id and ev_id not in seen_ids:
                seen_ids.add(ev_id)
                unique_events.append(ev)

        normalized = cls._normalize_events(unique_events)
        if normalized:
            cls._cache[cache_key] = {"data": normalized, "timestamp": now}

        return normalized[:limit] if limit else normalized





    @classmethod
    def _normalize_events(cls, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transforms raw SportyBet events into canonical StatIQ fixtures with structured odds.
        """
        results = []
        now_ms = time.time() * 1000.0

        for ev in events:
            # STRICT RULE: Any match that has already started or is in-play must be drafted out
            start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
            if start_ms > 0 and start_ms <= (now_ms + 30000):  # Exclude if within 30s or past
                continue

            status_str = str(ev.get("status") or ev.get("match_status") or "").upper()
            if status_str in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED"]:
                continue

            event_id = ev.get("eventId")
            game_id = str(ev.get("gameId") or "")
            home_team = ev.get("homeTeamName") or "Home"
            away_team = ev.get("awayTeamName") or "Away"
            
            kickoff_str = ""
            if start_ms > 0:
                dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
                kickoff_str = dt.strftime("%Y-%m-%d %H:%M:%S")


            sport_info = ev.get("sport", {})
            category_info = sport_info.get("category", {}) if isinstance(sport_info, dict) else {}
            tournament_info = category_info.get("tournament", {}) if isinstance(category_info, dict) else {}
            
            country = category_info.get("name") if isinstance(category_info, dict) else ""
            competition = tournament_info.get("name") if isinstance(tournament_info, dict) else (ev.get("tournamentName") or "Football")

            # Extract structured markets and odds
            markets_dict = {}
            raw_markets = ev.get("markets", [])

            for m in raw_markets:
                m_id = str(m.get("id"))
                m_desc = (m.get("desc") or m.get("name") or "").strip()
                specifier = m.get("specifier")
                outcomes_list = []

                for out in m.get("outcomes", []):
                    o_id = str(out.get("id"))
                    o_desc = (out.get("desc") or out.get("name") or "").strip()
                    try:
                        odds_val = float(out.get("odds") or out.get("oddsValue") or 1.0)
                    except (ValueError, TypeError):
                        odds_val = 1.0
                    
                    prob = out.get("probability")
                    try:
                        prob_val = float(prob) if prob else (1.0 / odds_val if odds_val > 0 else 0.0)
                    except (ValueError, TypeError):
                        prob_val = 0.0

                    outcomes_list.append({
                        "outcome_id": o_id,
                        "selection_name": o_desc,
                        "odds": odds_val,
                        "implied_probability": round(prob_val, 4)
                    })

                market_key = m_desc.upper() if m_desc else f"MARKET_{m_id}"
                markets_dict[market_key] = {
                    "market_id": m_id,
                    "market_name": m_desc,
                    "specifier": specifier,
                    "outcomes": outcomes_list
                }

            # Extract 1X2 main odds for quick calculation
            m1 = next((m for m in raw_markets if str(m.get("id")) == "1"), None)
            prob_home, prob_draw, prob_away = 0.33, 0.33, 0.33
            odds_home, odds_draw, odds_away = 2.50, 3.00, 2.50

            if m1:
                outs = m1.get("outcomes", [])
                for o in outs:
                    desc = (o.get("desc") or "").upper()
                    try:
                        ov = float(o.get("odds") or 2.50)
                    except:
                        ov = 2.50
                    if desc in ("HOME", "1"):
                        odds_home = ov
                    elif desc in ("DRAW", "X"):
                        odds_draw = ov
                    elif desc in ("AWAY", "2"):
                        odds_away = ov

            results.append({
                "id": f"fx_{game_id}" if game_id else f"fx_{event_id.replace(':', '_')}",
                "event_id": event_id,
                "game_id": game_id,
                "home_team": home_team,
                "away_team": away_team,
                "country": country,
                "competition": competition,
                "kickoff_time": kickoff_str,
                "start_time_ms": start_ms,
                "odds_home": odds_home,
                "odds_draw": odds_draw,
                "odds_away": odds_away,
                "markets": markets_dict,
                "provider": "SPORTYBET"
            })

        return results
