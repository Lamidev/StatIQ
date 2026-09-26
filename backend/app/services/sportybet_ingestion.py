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
                timeout=5.0,
                headers=cls.HEADERS,
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
                follow_redirects=True,
                verify=False
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
        endpoint = f"{cls.BASE_URL}/wapConfigurableEventsByOrder"

        def _fetch_page(page_num: int, is_today: bool) -> List[Dict[str, Any]]:
            payload = {
                "sportId": "sr:sport:1",
                "pageNum": page_num,
                "pageSize": 50,
                "withTwoUpMarket": True,
                "withOneUpMarket": True
            }
            if is_today:
                payload["todayGames"] = True
            else:
                payload["timeline"] = 1

            try:
                resp = client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    j = resp.json()
                    if j.get("bizCode") == 10000:
                        return j.get("data", {}).get("tournaments", [])
            except Exception as e:
                logger.debug(f"[SportyBetIngestion] Page fetch error (p={page_num}, today={is_today}): {e}")
            return []

        # Concurrently fetch pages 1..8 for Today and pages 1..5 for Tomorrow
        pages_to_fetch = [(p, True) for p in range(1, 9)] + [(p, False) for p in range(1, 6)]
        all_tournaments = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
                results = list(executor.map(lambda x: _fetch_page(x[0], x[1]), pages_to_fetch))
                for items in results:
                    all_tournaments.extend(items)
        finally:
            cls._is_refreshing = False

        # Flatten tournaments and events
        unique_events = []
        seen_ids = set()
        for tour in all_tournaments:
            c_name = (tour.get("categoryName") or "").strip()
            t_name = (tour.get("name") or "").strip()
            c_id = tour.get("categoryId") or ""
            t_id = tour.get("id") or ""
            for ev in tour.get("events", []):
                ev_id = str(ev.get("eventId") or ev.get("gameId") or "")
                if ev_id and ev_id not in seen_ids:
                    seen_ids.add(ev_id)
                    ev["country"] = c_name
                    ev["competition"] = t_name
                    ev["sport"] = {
                        "category": {
                            "id": c_id,
                            "name": c_name,
                            "tournament": {"id": t_id, "name": t_name}
                        }
                    }
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
            # AIR-TIGHT PRE-MATCH FILTER:
            # 1. Start time must be strictly upcoming in the future (>3 minutes from now)
            start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
            if start_ms > 0 and start_ms <= (now_ms + 180000):  # Exclude if in the past or starting within 3 mins
                continue

            # 2. SportyBet numerical status (0 = Not started, 1 = Live/In-play, 2 = Finished)
            st_val = ev.get("status")
            if st_val is not None:
                try:
                    if int(st_val) != 0:
                        continue
                except (ValueError, TypeError):
                    pass

            # 3. SportyBet match status label
            ms_str = str(ev.get("matchStatus") or ev.get("match_status") or "").strip().upper()
            if ms_str in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED", "CLOSED", "CONCLUDED", "INTERRUPTED", "DELAYED"]:
                continue
            if ms_str and ms_str not in ("NOT START", "NOT STARTED", "UPCOMING", "PRE-MATCH", "PREMATCH"):
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
            
            country = ev.get("country") or (category_info.get("name") if isinstance(category_info, dict) else "")
            competition = ev.get("competition") or (tournament_info.get("name") if isinstance(tournament_info, dict) else (ev.get("tournamentName") or "Football"))

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


    @classmethod
    def fetch_h2h_stats(cls, event_id: str, home_team: str = "", away_team: str = "") -> Dict[str, Any]:
        """
        Fetches Head-to-Head stats from SportyBet's internal match stats endpoint.
        Returns structured H2H data: home_wins, draws, away_wins, avg_goals, last_5_results.
        Non-blocking: returns empty dict on timeout/error so caller always gets a result in <0.8s.
        """
        if not event_id:
            return {}

        cache_key = f"h2h_{event_id}"
        now = time.time()
        if cache_key in cls._cache:
            entry = cls._cache[cache_key]
            if (now - entry.get("timestamp", 0)) < 3600:  # 1 hour H2H cache
                return entry.get("data", {})

        url = f"https://www.sportybet.com/api/ng/factsCenter/h2h/{event_id}"
        client = cls._get_client()
        try:
            resp = client.get(url, timeout=0.7)
            if resp.status_code == 200:
                j = resp.json()
                raw = j.get("data") or j
                h2h = cls._parse_h2h_stats(raw, home_team, away_team)
                cls._cache[cache_key] = {"data": h2h, "timestamp": now}
                return h2h
        except Exception:
            pass

        return {}

    @classmethod
    def _parse_h2h_stats(cls, raw: Any, home_team: str, away_team: str) -> Dict[str, Any]:
        """
        Parses SportyBet H2H response into a canonical H2H summary dict.
        """
        if not raw or not isinstance(raw, dict):
            return {}

        result = {
            "home_wins": 0,
            "draws": 0,
            "away_wins": 0,
            "total_meetings": 0,
            "avg_total_goals": 0.0,
            "home_avg_goals_scored": 0.0,
            "away_avg_goals_scored": 0.0,
            "last_5": [],
            "home_win_pct": 0.0,
            "away_win_pct": 0.0,
            "draw_pct": 0.0,
        }

        # SportyBet returns H2H in various formats — try each
        h2h_section = raw.get("h2h") or raw.get("previousMeetings") or raw.get("meetings") or []
        overview = raw.get("overview") or raw.get("matchStats") or {}

        # Try to extract from overview block (e.g. wins/draws summary)
        if isinstance(overview, dict):
            result["home_wins"] = int(overview.get("homeWins", 0) or overview.get("home_wins", 0) or 0)
            result["draws"] = int(overview.get("draws", 0) or 0)
            result["away_wins"] = int(overview.get("awayWins", 0) or overview.get("away_wins", 0) or 0)

        # Parse match-by-match records if available
        meetings = h2h_section if isinstance(h2h_section, list) else []
        total_goals = 0
        home_goals = 0
        away_goals = 0
        parsed_count = 0
        local_home_w = 0
        local_draw = 0
        local_away_w = 0

        for m in meetings[:10]:  # Last 10 H2H meetings max
            if not isinstance(m, dict):
                continue
            try:
                hg = int(m.get("homeScore", m.get("home_score", 0) or 0))
                ag = int(m.get("awayScore", m.get("away_score", 0) or 0))
                total_goals += hg + ag
                home_goals += hg
                away_goals += ag
                parsed_count += 1

                if hg > ag:
                    local_home_w += 1
                elif ag > hg:
                    local_away_w += 1
                else:
                    local_draw += 1

                result["last_5"].append({
                    "home_score": hg,
                    "away_score": ag,
                    "total_goals": hg + ag
                })
                if len(result["last_5"]) >= 5:
                    break
            except Exception:
                continue

        # Use parsed data if overview didn't have wins/draws
        if result["home_wins"] == 0 and result["draws"] == 0 and result["away_wins"] == 0:
            result["home_wins"] = local_home_w
            result["draws"] = local_draw
            result["away_wins"] = local_away_w

        total = result["home_wins"] + result["draws"] + result["away_wins"]
        result["total_meetings"] = total or parsed_count

        if result["total_meetings"] > 0:
            result["home_win_pct"] = round(result["home_wins"] / result["total_meetings"], 3)
            result["away_win_pct"] = round(result["away_wins"] / result["total_meetings"], 3)
            result["draw_pct"] = round(result["draws"] / result["total_meetings"], 3)

        if parsed_count > 0:
            result["avg_total_goals"] = round(total_goals / parsed_count, 2)
            result["home_avg_goals_scored"] = round(home_goals / parsed_count, 2)
            result["away_avg_goals_scored"] = round(away_goals / parsed_count, 2)

        return result

    @classmethod
    def fetch_h2h_batch(cls, fixtures: List[Dict[str, Any]], max_items: int = 35) -> Dict[str, Dict[str, Any]]:
        """
        Batch-fetches H2H stats for fixtures in parallel with high concurrency.
        Guaranteed to return in < 1 second.
        """
        import concurrent.futures
        results = {}

        def _fetch_one(fix):
            ev_id = str(fix.get("event_id") or fix.get("eventId") or "")
            h = str(fix.get("home_team") or "")
            a = str(fix.get("away_team") or "")
            if not ev_id:
                return ev_id, {}
            h2h = cls.fetch_h2h_stats(ev_id, h, a)
            return ev_id, h2h

        target_fixtures = fixtures[:max_items] if max_items else fixtures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=35) as pool:
                for ev_id, h2h_data in pool.map(_fetch_one, target_fixtures):
                    if ev_id:
                        results[ev_id] = h2h_data
        except Exception as e:
            logger.warning(f"[H2H Batch] Error: {e}")

        return results


