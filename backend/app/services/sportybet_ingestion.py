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
    _cache_ttl = 45  # 45 seconds cache for real-time live match board freshness

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

    _cache_ttl: int = 300  # 5 minutes cache
    _is_refreshing: bool = False
    _shared_client: Optional[httpx.Client] = None

    @classmethod
    def _get_client(cls) -> httpx.Client:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.Client(
                timeout=4.0,
                headers=cls.HEADERS,
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
                follow_redirects=True
            )
        return cls._shared_client

    @classmethod
    def fetch_upcoming_fixtures(cls, limit: int = 0, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches active upcoming football fixtures from SportyBet across all major tournaments.
        Uses stale-while-revalidate to ensure instant sub-second response times.
        """
        import concurrent.futures
        import threading

        cache_key = "master_upcoming_pool"
        now = time.time()

        if cache_key in cls._cache:
            entry = cls._cache[cache_key]
            cached_data = entry.get("data", [])
            is_stale = (now - entry.get("timestamp", 0)) >= cls._cache_ttl

            if cached_data and not force_refresh:
                if is_stale and not cls._is_refreshing:
                    # Trigger non-blocking asynchronous background refresh
                    threading.Thread(target=cls._perform_fetch, daemon=True).start()
                now_ms = time.time() * 1000.0
                active_cached = [
                    ev for ev in cached_data 
                    if (ev.get("start_time_ms") or 0) > (now_ms + 180000)
                    and str(ev.get("status") or "").upper() not in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED"]
                ]
                return active_cached[:limit] if (limit and limit > 0) else active_cached

        return cls._perform_fetch(limit=limit)

    @classmethod
    def _perform_fetch(cls, limit: int = 0) -> List[Dict[str, Any]]:
        import concurrent.futures
        cache_key = "master_upcoming_pool"
        now = time.time()
        cls._is_refreshing = True

        client = cls._get_client()

        def _fetch_url(url: str) -> List[Dict[str, Any]]:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    j = resp.json()
                    if j.get("bizCode") == 10000:
                        data = j.get("data", [])
                        return data if isinstance(data, list) else data.get("events", [])
            except Exception as e:
                logger.debug(f"[SportyBetIngestion] URL fetch error: {e}")
            return []

        # High-density active categories across all major football nations on SportyBet
        core_categories = [
            1, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
            30, 31, 32, 33, 34, 35, 44, 46, 47, 48, 49, 51, 52, 57, 66, 67, 77, 78, 85, 86,
            91, 92, 97, 99, 102, 122, 130, 131, 134, 148, 152, 155, 158, 159, 160, 163, 165,
            201, 252, 257, 270, 274, 278, 280, 281, 289, 291, 296, 297, 299, 305, 310, 322,
            329, 339, 352, 353, 365, 367, 379, 385, 386, 388, 389, 393
        ]
        fetch_urls = [
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&pageNum={p}&pageSize=100" for p in range(1, 16)
        ] + [
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&categoryId=sr:category:{cid}&pageNum=1&pageSize=100"
            for cid in core_categories
        ] + [
            f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:1&tournamentId={t_id}" for t_id in cls.TOP_TOURNAMENTS
        ]

        all_events = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                results = list(executor.map(_fetch_url, fetch_urls))
                for items in results:
                    all_events.extend(items)
        finally:
            cls._is_refreshing = False

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
            # STRICT RULE: Any match that has already started or is within 5 minutes of kickoff must be drafted out
            start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
            if start_ms > 0 and start_ms <= (now_ms + 300000):  # Exclude if within 5 mins or past
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

            # Extract structured double_chance and ou_lines for immediate use by pick engine
            dc_map = {}
            ou_list = []
            import re

            for m in raw_markets:
                m_id = str(m.get("id") or "")
                m_desc = str(m.get("desc") or m.get("name") or "").lower()
                spec = str(m.get("specifier") or "")
                outcomes = m.get("outcomes", [])
                if isinstance(outcomes, dict):
                    outcomes = list(outcomes.values())

                # Double Chance (Market 10)
                if m_id == "10" or ("double chance" in m_desc and not any(k in m_desc for k in ["&", "over", "under", "gg", "corner"])):
                    for o in outcomes:
                        o_id = str(o.get("id") or o.get("outcome_id") or "")
                        o_desc = str(o.get("desc") or o.get("name") or "").upper()
                        try:
                            ov = float(o.get("odds") or o.get("oddsValue") or 0.0)
                            if ov >= 1.02:
                                if o_id == "9" or "1X" in o_desc: dc_map["1X"] = ov
                                elif o_id == "11" or "X2" in o_desc: dc_map["X2"] = ov
                                elif o_id == "10" or "12" in o_desc: dc_map["12"] = ov
                        except Exception:
                            pass

                # Over/Under Goals (Market 18)
                if m_id == "18" or ("over/under" in m_desc and not any(k in m_desc for k in ["&", "1x2", "dc", "corner", "booking"])):
                    line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                    line_str = line_m.group(1) if line_m else "1.5"
                    o_val, u_val = None, None
                    for o in outcomes:
                        o_desc = str(o.get("desc") or o.get("name") or "").lower()
                        o_id = str(o.get("id") or o.get("outcome_id") or "")
                        try:
                            ov = float(o.get("odds") or o.get("oddsValue") or 0.0)
                            if ov >= 1.02:
                                if "over" in o_desc or o_id == "12": o_val = ov
                                elif "under" in o_desc or o_id == "13": u_val = ov
                        except Exception:
                            pass
                    if o_val or u_val:
                        ou_list.append({"line": line_str, "over": o_val, "under": u_val})

            # Accurate overround margin conversion if specific submarket not expanded in list
            if "1X" not in dc_map and odds_home > 1.0 and odds_draw > 1.0:
                dc_map["1X"] = round(1.0 / max(0.01, (1.0 / odds_home + 1.0 / odds_draw) * 1.08), 2)
            if "X2" not in dc_map and odds_away > 1.0 and odds_draw > 1.0:
                dc_map["X2"] = round(1.0 / max(0.01, (1.0 / odds_away + 1.0 / odds_draw) * 1.08), 2)
            if "12" not in dc_map and odds_home > 1.0 and odds_away > 1.0:
                dc_map["12"] = round(1.0 / max(0.01, (1.0 / odds_home + 1.0 / odds_away) * 1.08), 2)

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
                "double_chance": dc_map,
                "ou_lines": ou_list,
                "provider": "SPORTYBET"
            })

        return results
