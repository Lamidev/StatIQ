"""
Basketball Ingestion Service for StatIQ.
Interfaces with SportyBet FactsCenter (sr:sport:2) to discover global basketball fixtures,
parse deep betting markets (120+ lines), and tag session slates (Daytime vs Midnight USA).
"""
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("statiq.basketball.ingestion")

class BasketballIngestionService:
    BASE_URL = "https://www.sportybet.com/api/ng/factsCenter"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sportybet.com/ng/",
        "Origin": "https://www.sportybet.com"
    }

    _client: Optional[httpx.Client] = None
    _markets_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _get_client(cls) -> httpx.Client:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.Client(
                headers=cls.HEADERS,
                timeout=8.0,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=40),
                verify=False
            )
        return cls._client

    @classmethod
    def determine_session_slate(cls, kickoff_dt_wat: datetime) -> str:
        """
        Classifies a game into DAYTIME (Euro/Asia 06:00-22:00 WAT)
        or MIDNIGHT (USA NBA/NCAA 22:00-05:59 WAT).
        """
        hour = kickoff_dt_wat.hour
        if 6 <= hour < 22:
            return "DAYTIME"
        return "MIDNIGHT"

    @classmethod
    def fetch_upcoming_fixtures(
        cls,
        session_filter: str = "ALL",  # "ALL", "DAYTIME", "MIDNIGHT"
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Pulls upcoming basketball matches from SportyBet's configurable orders and upcoming feed.
        Enriches each match with WAT kickoff, tournament metadata, and slate tag.
        """
        client = cls._get_client()
        events_dict = {}
        wat_tz = timezone(timedelta(hours=1))

        # 1. Query wapConfigurableEventsByOrder for comprehensive tournament catalog
        url_order = f"{cls.BASE_URL}/wapConfigurableEventsByOrder"
        for page in (1, 2):
            payload = {
                "sportId": "sr:sport:2",
                "pageNum": page,
                "pageSize": 50,
                "todayGames": True
            }
            try:
                r = client.post(url_order, json=payload, timeout=7.0)
                if r.status_code == 200 and r.json().get("bizCode") == 10000:
                    tournaments = r.json().get("data", {}).get("tournaments", [])
                    for t in tournaments:
                        cat_name = t.get("categoryName") or "Basketball"
                        tourn_name = t.get("name") or "League"
                        for ev in t.get("events", []):
                            eid = ev.get("eventId")
                            if eid and eid not in events_dict:
                                ev["_category_name"] = cat_name
                                ev["_tournament_name"] = tourn_name
                                events_dict[eid] = ev
            except Exception as e:
                logger.warning(f"[BasketballIngestion] Error querying wapConfigurableEventsByOrder page {page}: {e}")

        # 2. Query wapUpcomingEvents fallback/supplementary feed
        url_upcoming = f"{cls.BASE_URL}/wapUpcomingEvents?sportId=sr:sport:2&pageSize=100"
        try:
            r = client.get(url_upcoming, timeout=6.0)
            if r.status_code == 200 and r.json().get("bizCode") == 10000:
                for ev in (r.json().get("data", []) or []):
                    eid = ev.get("eventId")
                    if eid and eid not in events_dict:
                        sport_info = ev.get("sport") or {}
                        cat_info = sport_info.get("category") or {}
                        tourn_info = cat_info.get("tournament") or {}
                        ev["_category_name"] = cat_info.get("name") or ev.get("categoryName") or "Basketball"
                        ev["_tournament_name"] = tourn_info.get("name") or ev.get("tournamentName") or "League"
                        events_dict[eid] = ev
        except Exception as e:
            logger.warning(f"[BasketballIngestion] Error querying wapUpcomingEvents: {e}")

        normalized_list = []
        now_ts = int(time.time())

        for eid, ev in events_dict.items():
            start_ms = ev.get("estimateStartTime")
            if not start_ms:
                continue
            start_ts = int(start_ms) // 1000
            if start_ts < (now_ts - 300):
                continue  # Skip already started matches

            dt_wat = datetime.fromtimestamp(start_ts, tz=wat_tz)
            slate = cls.determine_session_slate(dt_wat)

            if session_filter.upper() != "ALL" and slate != session_filter.upper():
                continue

            h_name = ev.get("homeTeamName") or "Home"
            a_name = ev.get("awayTeamName") or "Away"
            game_id = ev.get("gameId") or ""
            cat_name = ev.get("_category_name") or "Basketball"
            tourn_name = ev.get("_tournament_name") or "League"

            # Parse primary quick markets if available directly on event
            quick_markets = ev.get("markets") or []
            main_total = None
            main_winner = {}
            for m in quick_markets:
                m_desc = m.get("desc") or ""
                if "winner (incl. overtime)" in m_desc.lower():
                    for oc in m.get("outcomes", []):
                        main_winner[oc.get("desc")] = float(oc.get("odds", 1.0))
                elif "over/under" in m_desc.lower() and not main_total:
                    outcomes = m.get("outcomes", [])
                    if len(outcomes) == 2:
                        main_total = {
                            "line": m_desc,
                            "over_odds": float(outcomes[0].get("odds", 1.85)),
                            "under_odds": float(outcomes[1].get("odds", 1.85))
                        }

            normalized_list.append({
                "event_id": eid,
                "game_id": game_id,
                "home_team": h_name,
                "away_team": a_name,
                "category": cat_name,
                "tournament": tourn_name,
                "kickoff_timestamp": start_ts,
                "kickoff_wat_str": dt_wat.strftime("%Y-%m-%d %H:%M WAT"),
                "kickoff_time_str": dt_wat.strftime("%H:%M WAT"),
                "kickoff_date_str": dt_wat.strftime("%Y-%m-%d"),
                "session_slate": slate,
                "is_nba": "nba" in tourn_name.lower() or "usa" in cat_name.lower(),
                "main_winner_odds": main_winner,
                "main_total": main_total,
                "total_market_size": ev.get("totalMarketSize", len(quick_markets))
            })

        # Sort chronologically by kickoff time
        normalized_list.sort(key=lambda x: x["kickoff_timestamp"])
        return normalized_list[:limit]

    @classmethod
    def fetch_deep_match_markets(cls, event_id: str) -> Dict[str, Any]:
        """
        Fetches the complete deep market catalog (120+ markets) for a single basketball event.
        Extracts structured lines for:
        - Full-Time Over/Under Alternative lines (Market 225)
        - Home & Away Team Totals (Markets 227 & 228)
        - 1st Half Over/Under (Market 68)
        - 1st Quarter Over/Under (Market 236)
        - Winner incl. Overtime (Market 219)
        - Alternative Handicaps (Market 220)
        """
        now = time.time()
        if event_id in cls._markets_cache:
            entry = cls._markets_cache[event_id]
            if (now - entry.get("timestamp", 0)) < 120:  # 2-minute cache
                return entry.get("data", {})

        client = cls._get_client()
        url = f"{cls.BASE_URL}/event?eventId={event_id}"

        try:
            r = client.get(url, timeout=5.0)
            if r.status_code != 200 or r.json().get("bizCode") != 10000:
                return {}

            raw_data = r.json().get("data", {})
            markets = raw_data.get("markets", [])

            ft_over_unders = []
            home_totals = []
            away_totals = []
            half1_totals = []
            quarter1_totals = []
            winner_incl_ot = {}
            handicaps = []

            for m in markets:
                m_id = str(m.get("id") or "")
                desc = str(m.get("desc") or "")
                spec = str(m.get("specifier") or "")
                outcomes = m.get("outcomes") or []

                # Market 219: Winner (incl. overtime)
                if m_id == "219" or "winner (incl. overtime)" in desc.lower():
                    for oc in outcomes:
                        desc_name = oc.get("desc") or oc.get("name")
                        winner_incl_ot[desc_name] = {
                            "outcome_id": oc.get("id"),
                            "desc": desc_name,
                            "odds": float(oc.get("odds") or 1.0)
                        }

                # Market 225: Full-Time Over/Under (incl. overtime) OR Team Totals
                elif m_id in ("225", "227", "228") or "over/under (incl. overtime)" in desc.lower():
                    line_val = None
                    if "total=" in spec:
                        try:
                            line_val = float(spec.split("total=")[1].split("|")[0])
                        except Exception:
                            pass
                    if line_val is None:
                        parts = desc.split()
                        try:
                            line_val = float(parts[-1])
                        except Exception:
                            pass

                    over_oc = next((o for o in outcomes if "over" in str(o.get("desc")).lower() or str(o.get("id")) == "12"), None)
                    under_oc = next((o for o in outcomes if "under" in str(o.get("desc")).lower() or str(o.get("id")) == "13"), None)

                    if line_val and over_oc and under_oc:
                        # Full-time game totals are strictly >= 110 points
                        if line_val >= 110.0 and m_id == "225" and not any(k in desc.lower() for k in ["team", "1st", "2nd", "3rd", "4th"]):
                            ft_over_unders.append({
                                "market_id": "225",
                                "specifier": spec or f"total={line_val}",
                                "line": line_val,
                                "over_outcome_id": over_oc.get("id"),
                                "over_desc": f"Over {line_val}",
                                "over_odds": float(over_oc.get("odds") or 1.0),
                                "under_outcome_id": under_oc.get("id"),
                                "under_desc": f"Under {line_val}",
                                "under_odds": float(under_oc.get("odds") or 1.0)
                            })
                        elif line_val < 110.0:
                            # Team total
                            target_list = home_totals if m_id == "227" or "home" in desc.lower() else away_totals
                            target_list.append({
                                "market_id": m_id or "227",
                                "specifier": spec,
                                "line": line_val,
                                "over_odds": float(over_oc.get("odds") or 1.0),
                                "under_odds": float(under_oc.get("odds") or 1.0)
                            })

                # Market 227: Home Team Over/Under (incl. overtime)
                elif m_id == "227":
                    line_val = None
                    if "total=" in spec:
                        try: line_val = float(spec.split("total=")[1].split("|")[0])
                        except Exception: pass
                    over_oc = next((o for o in outcomes if "over" in str(o.get("desc")).lower() or str(o.get("id")) == "12"), None)
                    under_oc = next((o for o in outcomes if "under" in str(o.get("desc")).lower() or str(o.get("id")) == "13"), None)
                    if line_val and over_oc and under_oc:
                        home_totals.append({
                            "market_id": "227",
                            "specifier": spec,
                            "line": line_val,
                            "over_odds": float(over_oc.get("odds") or 1.0),
                            "under_odds": float(under_oc.get("odds") or 1.0)
                        })

                # Market 228: Away Team Over/Under (incl. overtime)
                elif m_id == "228":
                    line_val = None
                    if "total=" in spec:
                        try: line_val = float(spec.split("total=")[1].split("|")[0])
                        except Exception: pass
                    over_oc = next((o for o in outcomes if "over" in str(o.get("desc")).lower() or str(o.get("id")) == "12"), None)
                    under_oc = next((o for o in outcomes if "under" in str(o.get("desc")).lower() or str(o.get("id")) == "13"), None)
                    if line_val and over_oc and under_oc:
                        away_totals.append({
                            "market_id": "228",
                            "specifier": spec,
                            "line": line_val,
                            "over_odds": float(over_oc.get("odds") or 1.0),
                            "under_odds": float(under_oc.get("odds") or 1.0)
                        })

                # Market 68: 1st Half Over/Under
                elif m_id == "68" or "1st half - over/under" in desc.lower():
                    line_val = None
                    if "total=" in spec:
                        try: line_val = float(spec.split("total=")[1].split("|")[0])
                        except Exception: pass
                    over_oc = next((o for o in outcomes if "over" in str(o.get("desc")).lower() or str(o.get("id")) == "12"), None)
                    under_oc = next((o for o in outcomes if "under" in str(o.get("desc")).lower() or str(o.get("id")) == "13"), None)
                    if line_val and over_oc and under_oc:
                        half1_totals.append({
                            "market_id": "68",
                            "specifier": spec,
                            "line": line_val,
                            "over_odds": float(over_oc.get("odds") or 1.0),
                            "under_odds": float(under_oc.get("odds") or 1.0)
                        })

                # Market 236: 1st Quarter Over/Under
                elif m_id == "236" or "1st quarter - over/under" in desc.lower():
                    line_val = None
                    if "total=" in spec:
                        try: line_val = float(spec.split("total=")[1].split("|")[0])
                        except Exception: pass
                    over_oc = next((o for o in outcomes if "over" in str(o.get("desc")).lower() or str(o.get("id")) == "12"), None)
                    under_oc = next((o for o in outcomes if "under" in str(o.get("desc")).lower() or str(o.get("id")) == "13"), None)
                    if line_val and over_oc and under_oc:
                        quarter1_totals.append({
                            "market_id": "236",
                            "specifier": spec,
                            "line": line_val,
                            "over_odds": float(over_oc.get("odds") or 1.0),
                            "under_odds": float(under_oc.get("odds") or 1.0)
                        })

            # Sort lines ascending
            ft_over_unders.sort(key=lambda x: x["line"])
            home_totals.sort(key=lambda x: x["line"])
            away_totals.sort(key=lambda x: x["line"])
            half1_totals.sort(key=lambda x: x["line"])
            quarter1_totals.sort(key=lambda x: x["line"])

            result = {
                "event_id": event_id,
                "winner_incl_ot": winner_incl_ot,
                "fulltime_totals": ft_over_unders,
                "home_team_totals": home_totals,
                "away_team_totals": away_totals,
                "half1_totals": half1_totals,
                "quarter1_totals": quarter1_totals
            }

            cls._markets_cache[event_id] = {"data": result, "timestamp": now}
            return result
        except Exception as e:
            logger.error(f"[BasketballIngestion] Error fetching deep markets for {event_id}: {e}")
            return {}
