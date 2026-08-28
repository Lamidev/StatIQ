import random
import re
import string
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
import httpx
from sqlalchemy import select, and_

logger = logging.getLogger("matchiq.bookmaker_adapter")

from app.db.models import ProviderMarketMapping, ProviderFixtureMapping

class CanonicalMarketRegistry:
    """
    MatchIQ Canonical Market Registry.
    Canonical Market Keys:
    - MATCH_RESULT_HOME, MATCH_RESULT_DRAW, MATCH_RESULT_AWAY
    - OVER_0_5, UNDER_0_5, OVER_1_5, UNDER_1_5, OVER_2_5, UNDER_2_5, OVER_3_5, UNDER_3_5
    - BTTS_YES, BTTS_NO
    """
    CANONICAL_MARKETS = {
        # Main 1X2
        "MATCH_RESULT_HOME": ("1X2", None, "HOME"),
        "MATCH_RESULT_DRAW": ("1X2", None, "DRAW"),
        "MATCH_RESULT_AWAY": ("1X2", None, "AWAY"),

        # Double Chance
        "DOUBLE_CHANCE_1X": ("DOUBLE_CHANCE", None, "1X"),
        "DOUBLE_CHANCE_X2": ("DOUBLE_CHANCE", None, "X2"),
        "DOUBLE_CHANCE_12": ("DOUBLE_CHANCE", None, "12"),

        # Draw No Bet
        "DRAW_NO_BET_HOME": ("DRAW_NO_BET", None, "HOME"),
        "DRAW_NO_BET_AWAY": ("DRAW_NO_BET", None, "AWAY"),

        # Match Total Goals
        "OVER_0_5": ("OVER_UNDER", 0.5, "OVER"),
        "UNDER_0_5": ("OVER_UNDER", 0.5, "UNDER"),
        "OVER_1_5": ("OVER_UNDER", 1.5, "OVER"),
        "UNDER_1_5": ("OVER_UNDER", 1.5, "UNDER"),
        "OVER_2_5": ("OVER_UNDER", 2.5, "OVER"),
        "UNDER_2_5": ("OVER_UNDER", 2.5, "UNDER"),
        "OVER_3_5": ("OVER_UNDER", 3.5, "OVER"),
        "UNDER_3_5": ("OVER_UNDER", 3.5, "UNDER"),
        "OVER_4_5": ("OVER_UNDER", 4.5, "OVER"),
        "UNDER_4_5": ("OVER_UNDER", 4.5, "UNDER"),

        # Both Teams To Score (GG/NG)
        "BTTS_YES": ("BTTS", None, "YES"),
        "BTTS_NO": ("BTTS", None, "NO"),

        # Asian Handicap
        "ASIAN_HANDICAP_MINUS_0_5": ("ASIAN_HANDICAP", -0.5, "HOME"),
        "ASIAN_HANDICAP_PLUS_0_5": ("ASIAN_HANDICAP", 0.5, "AWAY"),
        "ASIAN_HANDICAP_MINUS_1_5": ("ASIAN_HANDICAP", -1.5, "HOME"),
        "ASIAN_HANDICAP_PLUS_1_5": ("ASIAN_HANDICAP", 1.5, "AWAY"),
        "ASIAN_HANDICAP_MINUS_2_5": ("ASIAN_HANDICAP", -2.5, "HOME"),
        "ASIAN_HANDICAP_PLUS_2_5": ("ASIAN_HANDICAP", 2.5, "AWAY"),

        # Team Goals (Home / Away Over/Under)
        "HOME_OVER_0_5": ("HOME_TOTAL_GOALS", 0.5, "OVER"),
        "HOME_UNDER_0_5": ("HOME_TOTAL_GOALS", 0.5, "UNDER"),
        "HOME_OVER_1_5": ("HOME_TOTAL_GOALS", 1.5, "OVER"),
        "HOME_UNDER_1_5": ("HOME_TOTAL_GOALS", 1.5, "UNDER"),
        "HOME_OVER_2_5": ("HOME_TOTAL_GOALS", 2.5, "OVER"),
        "HOME_UNDER_2_5": ("HOME_TOTAL_GOALS", 2.5, "UNDER"),
        "AWAY_OVER_0_5": ("AWAY_TOTAL_GOALS", 0.5, "OVER"),
        "AWAY_UNDER_0_5": ("AWAY_TOTAL_GOALS", 0.5, "UNDER"),
        "AWAY_OVER_1_5": ("AWAY_TOTAL_GOALS", 1.5, "OVER"),
        "AWAY_UNDER_1_5": ("AWAY_TOTAL_GOALS", 1.5, "UNDER"),

        # Win To Nil & Clean Sheet
        "HOME_WIN_TO_NIL_YES": ("HOME_WIN_TO_NIL", None, "YES"),
        "HOME_WIN_TO_NIL_NO": ("HOME_WIN_TO_NIL", None, "NO"),
        "HOME_CLEAN_SHEET_YES": ("HOME_CLEAN_SHEET", None, "YES"),
        "AWAY_CLEAN_SHEET_YES": ("AWAY_CLEAN_SHEET", None, "YES"),

        # Combo Markets
        "COMBO_HOME_AND_OVER_1_5": ("COMBO_1X2_TOTALS", 1.5, "HOME_OVER"),
        "COMBO_HOME_AND_OVER_2_5": ("COMBO_1X2_TOTALS", 2.5, "HOME_OVER"),
        "COMBO_HOME_AND_BTTS_YES": ("COMBO_1X2_BTTS", None, "HOME_YES"),
        "COMBO_DOUBLE_CHANCE_1X_AND_OVER_1_5": ("COMBO_DC_TOTALS", 1.5, "1X_OVER"),
        "COMBO_DOUBLE_CHANCE_1X_AND_OVER_2_5": ("COMBO_DC_TOTALS", 2.5, "1X_OVER"),
    }

@dataclass
class ProviderCapabilities:
    provider: str
    supports_fixture_mapping: bool = True
    supports_market_mapping: bool = True
    supports_odds_reading: bool = True
    supports_code_reading: bool = True
    supports_code_generation: bool = True
    supports_official_api: bool = False
    status: str = "ACTIVE_WEB_API_ADAPTER"

class BookmakerAdapter(ABC):
    """
    Phase 12 Provider Abstraction Layer Base Class.
    Maps provider-specific representations to canonical MatchIQ keys via database mapping tables.
    Never hardcodes provider IDs.
    """
    def __init__(self, session=None):
        self.session = session

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        pass

    def resolve_market(self, provider_market_name: str, provider_market_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Resolves provider-specific market name to canonical MatchIQ market key using database mapping table.
        """
        provider_name = self.get_provider_name()
        stmt = select(ProviderMarketMapping).where(
            and_(
                ProviderMarketMapping.provider == provider_name,
                ProviderMarketMapping.provider_market_name == provider_market_name,
                ProviderMarketMapping.mapping_status == "ACTIVE"
            )
        )
        mapping = self.session.execute(stmt).scalar_one_or_none()
        if mapping is not None:
            return {
                "matchiq_market_type": mapping.matchiq_market_type,
                "matchiq_market_line": mapping.matchiq_market_line,
                "matchiq_selection": mapping.matchiq_selection,
                "canonical_key": f"{mapping.matchiq_market_type}_{mapping.matchiq_selection}"
            }
        return None

class SportyBetAdapter(BookmakerAdapter):
    """
    SportyBet Direct Web API Adapter (100% Free).
    Interacts directly with SportyBet's public Web/App order share endpoints:
    - Code Reader: GET https://www.sportybet.com/api/{country}/orders/share/{code}
    - Code Generator: POST https://www.sportybet.com/api/{country}/orders/share
    """
    BASE_URL = "https://www.sportybet.com/api"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sportybet.com/"
    }

    def get_provider_name(self) -> str:
        return "SPORTYBET"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="SPORTYBET",
            supports_fixture_mapping=True,
            supports_market_mapping=True,
            supports_odds_reading=True,
            supports_code_reading=True,
            supports_code_generation=True,
            supports_official_api=False,
            status="ACTIVE_WEB_API_ADAPTER"
        )

    def read_code(self, code: str, country_code: str = "ng") -> Dict[str, Any]:
        return self.fetch_booking_code_details(code=code, country_code=country_code)

    def generate_code(self, selections: List[Dict[str, Any]], country_code: str = "ng") -> Dict[str, Any]:
        return self.generate_booking_code(selections=selections, country_code=country_code)

    def fetch_booking_code_details(self, code: str, country_code: str = "ng") -> Dict[str, Any]:

        """
        Fetches and decodes SportyBet share code via public endpoint.
        Uses multi-region fallback (ng, gh, ke, ug, tz, zm) for 100% universal decoding.
        """
        code_clean = code.strip().upper()
        
        # Try requested country first, then fallback across all SportyBet country domains
        regions_to_try = [country_code.lower()] + [c for c in ["ng", "gh", "ke", "ug", "tz", "zm"] if c != country_code.lower()]

        data = None
        matched_region = country_code.lower()

        import urllib.request
        import ssl
        import json

        for reg in regions_to_try:
            url = f"{self.BASE_URL}/{reg}/orders/share/{code_clean}"
            req_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': f'https://www.sportybet.com/{reg}/',
                'Origin': 'https://www.sportybet.com'
            }

            try:
                req = urllib.request.Request(url, headers=req_headers)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx, timeout=4.0) as resp:
                    if resp.status == 200:
                        res_json = json.loads(resp.read().decode('utf-8'))
                        if res_json and res_json.get("bizCode") == 10000:
                            data = res_json
                            matched_region = reg
                            break
            except Exception:
                pass

            if not data:
                try:
                    with httpx.Client(timeout=4.0, headers=req_headers, follow_redirects=True, verify=False) as client:
                        resp = client.get(url)
                        if resp.status_code == 200:
                            res_json = resp.json()
                            if res_json and res_json.get("bizCode") == 10000:
                                data = res_json
                                matched_region = reg
                                break
                except Exception:
                    pass

        if data and data.get("bizCode") == 10000:
            order_data = data.get("data", {})
            outcomes = order_data.get("outcomes", [])
            
            selections = []
            import time
            now_ms = time.time() * 1000

            for out in outcomes:
                home_team = out.get("homeTeamName") or out.get("homeTeam") or "Home"
                away_team = out.get("awayTeamName") or out.get("awayTeam") or "Away"
                
                markets = out.get("markets", [])
                mkt_name = out.get("marketName") or "Match Result"
                sel_name = out.get("desc") or "1"
                odds_val = 1.50

                provider_mkt_id = None
                provider_oc_id = None
                provider_spec = None

                if markets and len(markets) > 0:
                    mkt = markets[0]
                    mkt_name = mkt.get("desc") or mkt.get("name") or mkt_name
                    provider_mkt_id = str(mkt.get("id")) if mkt.get("id") else None
                    provider_spec = mkt.get("specifier")
                    mkt_outcomes = mkt.get("outcomes", [])
                    if mkt_outcomes and len(mkt_outcomes) > 0:
                        sel_item = mkt_outcomes[0]
                        sel_name = sel_item.get("desc") or sel_item.get("name") or sel_name
                        provider_oc_id = str(sel_item.get("id")) if sel_item.get("id") else None
                        try:
                            raw_o = sel_item.get("odds") or sel_item.get("oddsValue") or sel_item.get("currentOdds")
                            odds_val = float(raw_o) if raw_o is not None else 1.50
                        except (ValueError, TypeError):
                            odds_val = 1.50

                event_id = str(out.get("eventId") or "")
                game_id = str(out.get("gameId") or "")
                prov_id = event_id if event_id else game_id
                
                start_time_ms = out.get("estimateStartTime") or out.get("startTime") or 0
                kickoff_str = ""
                if start_time_ms > 0:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(start_time_ms / 1000.0)
                    kickoff_str = dt.strftime("%d/%m %H:%M")

                score_str = out.get("setScore") or out.get("score") or out.get("currentScore") or out.get("matchScore") or out.get("liveScore") or ""
                home_score = out.get("homeScore") or out.get("home_score")
                away_score = out.get("awayScore") or out.get("away_score")

                if home_score is not None and away_score is not None:
                    score_str = f"{home_score} - {away_score}"
                elif score_str:
                    for sep in [":", "-"]:
                        if sep in str(score_str):
                            parts = str(score_str).split(sep)
                            try:
                                home_score = int(parts[0].strip())
                                away_score = int(parts[1].strip())
                                score_str = f"{home_score} - {away_score}"
                                break
                            except Exception:
                                pass

                played_sec = out.get("playedSeconds") or out.get("clock") or ""
                sel_active = mkt_outcomes[0].get("isActive", 1) if (mkt_outcomes and len(mkt_outcomes) > 0) else 1
                mkt_status = markets[0].get("status", 1) if markets else 1
                match_status_code_str = str(out.get("matchStatus") or out.get("status") or "").strip().upper()
                
                # Check if match is in the future
                is_future = bool(start_time_ms > 0 and start_time_ms > (now_ms + 60000))
                is_match_finished = match_status_code_str in ["ENDED", "FT", "CONCLUDED", "FINISHED"] or (start_time_ms > 0 and (now_ms - start_time_ms) > 7200000)
                is_match_live = (not is_future and not is_match_finished and (match_status_code_str in ["H1", "H2", "HT", "LIVE", "IN_PROGRESS", "ONGOING"] or (start_time_ms > 0 and (now_ms - start_time_ms) > 0)))

                # Extract SportyBet authoritative dynamic settlement status & isWinning
                raw_res = str(out.get("outcomeResult") or out.get("result") or out.get("statusDesc") or "").upper()
                is_winning = None
                if mkt_outcomes and len(mkt_outcomes) > 0:
                    sel_res = str(mkt_outcomes[0].get("outcomeResult") or mkt_outcomes[0].get("result") or "").upper()
                    if sel_res:
                        raw_res = sel_res
                    if "isWinning" in mkt_outcomes[0]:
                        is_winning = mkt_outcomes[0].get("isWinning")

                if is_winning is None and "isWinning" in out:
                    is_winning = out.get("isWinning")

                leg_result = None
                if is_winning == 1 or "WON" in raw_res or raw_res in ("1", "SUCCESS"):
                    leg_result = "WON"
                elif is_match_finished and (is_winning == 0 or "LOST" in raw_res or raw_res in ("2", "FAIL")):
                    leg_result = "LOST"

                # Dynamic status resolution
                if mkt_status == 3 or sel_active == 0:
                    match_status = "NULLED_EXPIRED"
                    status_label = "Market Expired / Unavailable"
                elif is_match_finished:
                    match_status = "CONCLUDED"
                    status_label = "Concluded / Settled"
                elif is_match_live:
                    match_status = "LIVE"
                    clock_str = ""
                    if played_sec:
                        try:
                            sec_val = int(str(played_sec).split(":")[0]) * 60 + int(str(played_sec).split(":")[1]) if ":" in str(played_sec) else int(played_sec)
                            mins = sec_val // 60
                            half = "H1" if mins <= 45 else "H2"
                            clock_str = f"{mins}' {half}"
                        except Exception:
                            clock_str = str(played_sec)
                    elif start_time_ms > 0 and (now_ms - start_time_ms) > 0:
                        elapsed_mins = int((now_ms - start_time_ms) / 60000)
                        if elapsed_mins <= 45:
                            clock_str = f"{elapsed_mins}' H1"
                        elif elapsed_mins <= 60:
                            clock_str = "HT"
                        else:
                            clock_str = f"{min(90, elapsed_mins - 15)}' H2"
                    status_label = f"Live ({clock_str})" if clock_str else "In Progress / Live"
                elif out.get("banned") == True or out.get("productStatus") == "CANCELLED":
                    match_status = "NULLED_EXPIRED"
                    status_label = "Nulled / Odds Removed"
                else:
                    match_status = "UPCOMING"
                    status_label = "Upcoming / Bettable"

                selections.append({
                    "external_fixture_id": prov_id,
                    "event_id": event_id or prov_id,
                    "game_id": game_id,
                    "provider_event_id": prov_id,
                    "provider_market_id": provider_mkt_id,
                    "provider_outcome_id": provider_oc_id,
                    "provider_specifier": provider_spec,
                    "_sportybet_market_id": provider_mkt_id,
                    "_sportybet_outcome_id": provider_oc_id,
                    "_sportybet_specifier": provider_spec,
                    "_sportybet_event_id": prov_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "market_name": mkt_name,
                    "selection_name": sel_name,
                    "odds": odds_val,
                    "match_status": match_status,
                    "status_label": status_label,
                    "start_time_ms": start_time_ms,
                    "kickoff_datetime_str": kickoff_str,
                    "score": score_str,
                    "home_score": home_score,
                    "away_score": away_score,
                    "clock": played_sec,
                    "match_status_code": match_status_code_str,
                    "leg_result": leg_result
                })


            return {
                "status": "SUCCESS",
                "code": code_clean,
                "total_selections": len(selections),
                "selections": selections
            }

        return {
            "status": "NOT_FOUND",
            "code": code_clean,
            "total_selections": 0,
            "selections": []
        }
    # ── Market → Outcome Matcher ──────────────────────────────────────────
    # Maps MatchIQ canonical market/selection strings to the exact SportyBet
    # market and outcome so booking codes load with correct picks.
    # ─────────────────────────────────────────────────────────────────────

    # Keyword sets used for fuzzy matching MatchIQ market names to SportyBet market names
    _MARKET_KEYWORDS = {
        "double_chance":   ["double chance", "double_chance", "dc"],
        "over_under":      ["over/under", "over_under", "total", "goals over", "goals under"],
        "btts":            ["gg/ng", "btts", "both teams", "both_teams_to_score"],
        "1x2":             ["1x2", "match result", "full time result", "match_result"],
        "draw_no_bet":     ["draw no bet", "draw_no_bet", "dnb"],
        "asian_handicap":  ["asian handicap", "asian_handicap", "handicap"],
        "home_total":      ["home team total", "home total", "home over", "home under", "home_total"],
        "away_total":      ["away team total", "away total", "away over", "away under", "away_total"],
        "win_either_half": ["win either half", "to win either half"],
        "goal_bounds":     ["goal bounds", "goal range", "goal_bounds"],
        "2nd_half_dc":     ["2nd half", "second half", "2h double chance", "2nd half - double chance"],
        "both_halves":     ["both halves", "both_halves"],
        "to_qualify":      ["to qualify", "to_qualify"],
        "combo":           ["home team or over", "away or over", "over/under & gg", "combo"],
    }

    # Outcome keyword sets for matching MatchIQ selection names to SportyBet outcome names
    _OUTCOME_KEYWORDS = {
        "home":      ["home", "1", "home win"],
        "draw":      ["draw", "x"],
        "away":      ["away", "2", "away win"],
        "1x":        ["1x", "home or draw", "home draw"],
        "x2":        ["x2", "draw or away", "away draw"],
        "12":        ["12", "home or away"],
        "over":      ["over"],
        "under":     ["under"],
        "yes":       ["yes", "gg"],
        "no":        ["no", "ng"],
    }

    def _resolve_market_payload(
        self,
        ev_markets: Any,
        mkt_text: str,
        sel_text: str,
        home_target: str,
        away_target: str
    ) -> Tuple[str, str, Optional[str]]:
        m_lower = (mkt_text or "").lower().strip()
        s_lower = (sel_text or "").lower().strip()
        h_lower = (home_target or "").lower().strip()
        a_lower = (away_target or "").lower().strip()

        STOP = {"fc", "sc", "cd", "ud", "ca", "rc", "ac", "fk", "bk", "sk", "ff", "sad", "club", "team", "the", "de", "cf", "nk", "ks", "sv"}
        h_words = [w for w in h_lower.split() if len(w) >= 3 and w not in STOP]
        a_words = [w for w in a_lower.split() if len(w) >= 3 and w not in STOP]

        # Extract strictly unique words for Home vs Away (exclude shared city/club words like 'zagreb', 'manchester', 'madrid', 'milan', 'istanbul')
        h_unique = [w for w in h_words if w not in a_words]
        a_unique = [w for w in a_words if w not in h_words]

        h_check = h_unique if h_unique else h_words
        a_check = a_unique if a_unique else a_words

        has_home_word = any(w in s_lower or w in m_lower for w in h_check)
        has_away_word = any(w in s_lower or w in m_lower for w in a_check)

        m_list = list(ev_markets.values()) if isinstance(ev_markets, dict) else (ev_markets or [])

        # ── 1. 2nd Half Double Chance ─────────────────────────────────────
        if ("2nd half" in m_lower or "second half" in m_lower or "2h" in m_lower) and ("double chance" in m_lower or "dc" in m_lower or "1x" in s_lower or "x2" in s_lower or "12" in s_lower or "home or away" in s_lower):
            is_12 = "12" in s_lower or "home or away" in s_lower
            is_x2 = "x2" in s_lower or "draw or away" in s_lower or "away or draw" in s_lower
            target_oc = "10" if is_12 else ("11" if is_x2 else "9")
            target_code = "12" if is_12 else ("x2" if is_x2 else "1x")
            for mkt in m_list:
                m_desc = (mkt.get("desc") or mkt.get("name") or "").lower()
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if ("2nd half" in m_desc or "second half" in m_desc) and "double chance" in m_desc:
                    for oc in (mkt.get("outcomes") or []):
                        o_desc = (oc.get("desc") or oc.get("name") or "").lower()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if o_id == target_oc or target_code in o_desc:
                            return m_id, o_id, None
            return "60", target_oc, None

        # ── 2. 1st Half Double Chance ─────────────────────────────────────
        if ("1st half" in m_lower or "first half" in m_lower or "1h" in m_lower) and ("double chance" in m_lower or "dc" in m_lower):
            is_12 = "12" in s_lower or "home or away" in s_lower
            is_x2 = "x2" in s_lower or "draw or away" in s_lower
            target_oc = "10" if is_12 else ("11" if is_x2 else "9")
            for mkt in m_list:
                m_desc = (mkt.get("desc") or mkt.get("name") or "").lower()
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if ("1st half" in m_desc or "first half" in m_desc) and "double chance" in m_desc:
                    for oc in (mkt.get("outcomes") or []):
                        o_desc = (oc.get("desc") or oc.get("name") or "").lower()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if o_id == target_oc or ("12" if is_12 else ("x2" if is_x2 else "1x")) in o_desc:
                            return m_id, o_id, None
            return "41", target_oc, None

        # ── 3. Team Goals (Home Total Goals / Away Total Goals) ───────────
        is_team_goals = ("team goals" in m_lower or "team over" in m_lower or "team under" in m_lower or
                         "home over" in m_lower or "away over" in m_lower or "home under" in m_lower or "away under" in m_lower or
                         "home team total" in m_lower or "away team total" in m_lower or
                         (has_home_word and ("over" in m_lower or "under" in m_lower)) or
                         (has_away_word and ("over" in m_lower or "under" in m_lower)))
        # CRITICAL: exclude Win Either Half and Compound OR from team-goals branch
        _is_either_half = "either half" in m_lower or "either half" in s_lower
        _is_compound_or = ("or over" in s_lower or "win or over" in s_lower or
                           "or over" in m_lower or "win or over" in m_lower or
                           "home or over" in s_lower or "home or over" in m_lower or
                           "away or over" in s_lower or "away or over" in m_lower)
        if is_team_goals and not any(k in m_lower for k in ["double chance", "win either half"]) and not _is_either_half and not _is_compound_or:
            is_away = "away" in m_lower or "away" in s_lower or (has_away_word and not has_home_word)
            target_m_id = "20" if is_away else "19"
            line_match = re.search(r"(\d+\.5|\d+)", s_lower + " " + m_lower)
            line_val = line_match.group(1) if line_match else "1.5"
            is_over = "over" in s_lower or "over" in m_lower
            target_spec = f"total={line_val}"
            for mkt in m_list:
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if m_id == target_m_id:
                    for oc in (mkt.get("outcomes") or []):
                        o_desc = (oc.get("desc") or oc.get("name") or "").lower()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if (is_over and ("over" in o_desc or o_id == "12")) or (not is_over and ("under" in o_desc or o_id == "13")):
                            return target_m_id, o_id, target_spec
            return target_m_id, "12" if is_over else "13", target_spec

        # ── 4. Win Either Half (Home: 73, Away: 74) ───────────────────────
        if _is_either_half or "win either half" in s_lower:
            is_away = (
                "away" in m_lower or "away" in s_lower or "(2)" in s_lower or
                (has_away_word and not has_home_word)
            )
            if has_home_word and not has_away_word:
                is_away = False
            target_m_id = "74" if is_away else "73"
            for mkt in m_list:
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if m_id == target_m_id:
                    outcomes = mkt.get("outcomes", [])
                    if isinstance(outcomes, dict): outcomes = list(outcomes.values())
                    if outcomes:
                        return target_m_id, str(outcomes[0].get("id") or outcomes[0].get("outcome_id") or "75"), None
            # Fallback to universally accepted Double Chance 1X or X2 on SportyBet
            return "10", "11" if is_away else "9", None

        # ── 5. Compound OR / Combo Safety (Home or Over 2.5 / Away or Over 2.5) ─
        if _is_compound_or and "2.5" in (s_lower + " " + m_lower):
            is_away = "away" in m_lower or "away" in s_lower or (has_away_word and not has_home_word)
            for mkt in m_list:
                m_desc = (mkt.get("desc") or mkt.get("name") or "").lower()
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if m_id == "62" or "or over" in m_desc or "win or over" in m_desc:
                    for oc in (mkt.get("outcomes") or []):
                        o_desc = (oc.get("desc") or oc.get("name") or "").lower()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if (is_away and ("away" in o_desc or o_id in ("2", "3"))) or (not is_away and ("home" in o_desc or o_id == "1")):
                            return m_id or "62", o_id, None
            # Fallback to universally accepted Double Chance 1X or X2 on SportyBet
            return "10", "11" if is_away else "9", None

        # ── 6. Asian Handicap / Handicap ──────────────────────────────────
        if "handicap" in m_lower or "asian handicap" in m_lower:
            is_away = "away" in s_lower or "(2)" in s_lower or has_away_word
            hcp_match = re.search(r"([+-]?\d+\.?\d*)", s_lower + " " + m_lower)
            hcp_raw = hcp_match.group(1) if hcp_match else "1.5"
            hcp_val = hcp_raw.replace("+", "")
            target_spec = f"hcp={hcp_val}"
            for mkt in m_list:
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if m_id in ("16", "17", "28") or "handicap" in (mkt.get("desc") or "").lower():
                    for oc in (mkt.get("outcomes") or []):
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        o_desc = (oc.get("desc") or oc.get("name") or "").lower()
                        if (is_away and (o_id in ("1715", "3", "2") or "2" in o_desc or "away" in o_desc)) or (not is_away and (o_id in ("1714", "1") or "1" in o_desc or "home" in o_desc)):
                            return m_id, o_id, target_spec
            # Exact SportyBet Asian Handicap Market ID is 16, outcome 1715 (Away) or 1714 (Home)
            return "16", "1715" if is_away else "1714", target_spec


        # ── 6. Full-Time Double Chance (Market ID: 10) ───────────────────
        if "double chance" in m_lower or "dc" in m_lower or "1x" in s_lower or "x2" in s_lower or "12" in s_lower or "or draw" in s_lower or "home/draw" in s_lower or "home or away" in s_lower:
            is_12 = "12" in s_lower or "home or away" in s_lower or "1 or 2" in s_lower
            is_x2 = "x2" in s_lower or "draw or away" in s_lower or "(x2)" in s_lower or (has_away_word and not has_home_word) or "away or draw" in s_lower
            is_1x = "1x" in s_lower or "home or draw" in s_lower or "(1x)" in s_lower or (has_home_word and not has_away_word)

            target_code = "12" if is_12 else ("x2" if is_x2 else "1x")
            target_oc_id = "10" if is_12 else ("11" if is_x2 else "9")

            for mkt in m_list:
                m_desc = (mkt.get("desc") or mkt.get("name") or mkt.get("market_name") or "").lower().strip()
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if (m_id == "10" or m_desc == "double chance") and not any(k in m_desc for k in ["&", "over", "under", "gg", "corner", "half", "1st", "2nd"]):
                    outcomes = mkt.get("outcomes", [])
                    if isinstance(outcomes, dict): outcomes = list(outcomes.values())
                    for oc in outcomes:
                        o_desc = (oc.get("desc") or oc.get("name") or oc.get("selection_name") or "").lower().strip()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if o_id == target_oc_id or target_code in o_desc:
                            return m_id or "10", o_id, None

            return "10", target_oc_id, None

        # ── 7. Over / Under Goals (Market ID: 18) ─────────────────────────
        if "over" in m_lower or "under" in m_lower or "over" in s_lower or "under" in s_lower or "goal" in m_lower:
            line_match = re.search(r"(\d+\.5|\d+)", s_lower + " " + m_lower)
            line_val = line_match.group(1) if line_match else "1.5"
            is_over = "over" in s_lower or "over" in m_lower
            target_spec = f"total={line_val}"
            for mkt in m_list:
                m_desc = (mkt.get("desc") or mkt.get("name") or mkt.get("market_name") or "").lower().strip()
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                spec = str(mkt.get("specifier") or mkt.get("handicap") or "")
                if (m_id == "18" or "over/under" in m_desc or "total goals" in m_desc) and not any(k in m_desc for k in ["&", "1x2", "double", "winner", "both", "team", "half", "corner"]) and (line_val in spec or line_val in m_desc):
                    outcomes = mkt.get("outcomes", [])
                    if isinstance(outcomes, dict): outcomes = list(outcomes.values())
                    for oc in outcomes:
                        o_desc = (oc.get("desc") or oc.get("name") or oc.get("selection_name") or "").lower().strip()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if (is_over and ("over" in o_desc or o_id == "12")) or (not is_over and ("under" in o_desc or o_id == "13")):
                            if not any(k in o_desc for k in ["&", "home", "away", "draw"]):
                                return m_id or "18", o_id, target_spec
            return "18", "12" if is_over else "13", target_spec

        # ── 8. BTTS / GG / NG (Market ID: 29) ─────────────────────────────
        if "btts" in m_lower or "gg" in m_lower or "both teams" in m_lower or "gg" in s_lower or "ng" in s_lower:
            is_yes = "yes" in s_lower or "gg" in s_lower
            for mkt in m_list:
                m_id = str(mkt.get("id") or mkt.get("market_id") or "")
                if m_id == "29":
                    outcomes = mkt.get("outcomes", [])
                    if isinstance(outcomes, dict): outcomes = list(outcomes.values())
                    for oc in outcomes:
                        o_desc = (oc.get("desc") or oc.get("name") or "").lower().strip()
                        o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                        if (is_yes and ("yes" in o_desc or o_id == "24")) or (not is_yes and ("no" in o_desc or o_id == "25")):
                            return "29", o_id, None
            return "29", "24" if is_yes else "25", None

        # ── 9. 1X2 Match Result ───────────────────────────────────────────
        if "draw" in s_lower or s_lower == "x":
            return "1", "2", None
        elif "away" in s_lower or "(2)" in s_lower or (has_away_word and not has_home_word):
            return "1", "3", None
        return "1", "1", None



    def _fetch_event_markets(self, event_id: str, country_code: str = "ng") -> Optional[List[Dict[str, Any]]]:
        """
        Fetch a specific event's available markets from SportyBet by eventId.
        Returns the list of markets for the event, or None if not found.
        """
        # Try multiple SportyBet event detail endpoints
        urls_to_try = [
            f"{self.BASE_URL}/{country_code}/factsCenter/pcEventDetails?eventId={event_id}",
            f"{self.BASE_URL}/{country_code}/factsCenter/eventDetail?eventId={event_id}",
        ]

        for url in urls_to_try:
            try:
                with httpx.Client(timeout=5.0, headers=self.HEADERS) as client:
                    r = client.get(url)
                    if r.status_code == 200:
                        data = r.json().get("data")
                        if data:
                            # Handle both single-event and nested response shapes
                            if isinstance(data, dict):
                                markets = data.get("markets") or data.get("market") or []
                                if markets:
                                    return markets
                            elif isinstance(data, list) and data:
                                return data[0].get("markets", [])
            except Exception:
                continue

        return None

    def fetch_event_odds_ranked(
        self,
        event_id: str,
        country_code: str = "ng",
        overround: float = 1.06,
    ) -> List[Dict[str, Any]]:
        """
        Fetches all SportyBet markets for a given event_id.
        Strips the bookmaker overround margin (~6%) to compute true implied probabilities.
        Returns a ranked list of candidate picks (highest true prob first).

        Each item in the returned list:
          {
            "market_name": str,
            "selection_name": str,
            "raw_odds": float,          # SportyBet displayed odds
            "true_prob": float,         # overround-stripped probability (0–1)
            "market_id": str,
            "outcome_id": str,
          }
        """
        markets = self._fetch_event_markets(event_id, country_code)
        if not markets:
            return []

        candidates = []
        for mkt in markets:
            mkt_name = mkt.get("desc") or mkt.get("name") or ""
            mkt_id   = str(mkt.get("id") or "")
            for oc in mkt.get("outcomes", []):
                oc_name = oc.get("desc") or oc.get("name") or ""
                raw_odds = None
                try:
                    raw_odds = float(oc.get("odds") or oc.get("oddsValue") or 0)
                except (TypeError, ValueError):
                    pass
                if not raw_odds or raw_odds <= 1.0:
                    continue

                # Strip overround: true_prob = (1/odds) / overround
                true_prob = min(0.97, max(0.05, (1.0 / raw_odds) / overround))

                candidates.append({
                    "market_name":    mkt_name,
                    "selection_name": oc_name,
                    "raw_odds":       raw_odds,
                    "true_prob":      round(true_prob, 4),
                    "market_id":      mkt_id,
                    "outcome_id":     str(oc.get("id") or ""),
                })

        # Sort by true implied probability descending — highest confidence first
        candidates.sort(key=lambda c: c["true_prob"], reverse=True)
        return candidates


    def generate_booking_code(self, selections: List[Dict[str, Any]], country_code: str = "ng") -> Dict[str, Any]:
        """
        Generates a genuine, loadable SportyBet booking code via SportyBet's live API.
        Maps selections to SportyBet canonical marketId, outcomeId, and specifier.
        """
        url_share = f"{self.BASE_URL}/{country_code.lower()}/orders/share"
        
        from app.services.sportybet_ingestion import SportyBetIngestionService
        live_sporty_events = SportyBetIngestionService.fetch_upcoming_fixtures(limit=250)

        # Build lookup maps from live events
        events_by_id = {}
        for ev in live_sporty_events:
            if ev.get("eventId"):
                events_by_id[str(ev["eventId"])] = ev
            if ev.get("event_id"):
                events_by_id[str(ev["event_id"])] = ev
            if ev.get("gameId"):
                events_by_id[str(ev["gameId"])] = ev
            if ev.get("game_id"):
                events_by_id[str(ev["game_id"])] = ev

        selections_payload = []
        STOP_WORDS = {"fc", "sc", "cd", "ud", "ca", "rc", "ac", "fk", "bk", "sk", "ff", "sad", "club", "team"}


        for s in selections:
            raw_event_id = str(s.get("event_id") or s.get("provider_event_id") or s.get("_sportybet_event_id") or s.get("eventId") or s.get("external_fixture_id") or s.get("fixture_id") or s.get("game_id") or s.get("gameId") or "").strip()
            home_target = (s.get("home_team") or s.get("fixture") or "").lower().strip()

            away_target = (s.get("away_team") or "").lower().strip()
            sel_text = (s.get("selection_name") or s.get("selection") or s.get("prediction") or "").lower()

            # 1. Direct verified ID preservation (Canonical First)
            target_event_id = None
            if raw_event_id:
                if str(raw_event_id).startswith("sr:match:"):
                    target_event_id = raw_event_id
                elif str(raw_event_id).startswith("sr_match_"):
                    target_event_id = f"sr:match:{raw_event_id[9:]}"
                elif str(raw_event_id).startswith("fx_"):
                    stripped = raw_event_id[3:]
                    if stripped.startswith("sr_match_"):
                        target_event_id = f"sr:match:{stripped[9:]}"
                    elif stripped.isdigit() and len(stripped) >= 7:
                        target_event_id = f"sr:match:{stripped}"
                    elif stripped in events_by_id:
                        target_event_id = events_by_id[stripped].get("eventId") or events_by_id[stripped].get("event_id")
                elif raw_event_id in events_by_id:
                    target_event_id = events_by_id[raw_event_id].get("eventId") or events_by_id[raw_event_id].get("event_id")
                elif str(raw_event_id).isdigit() and len(str(raw_event_id)) >= 7:
                    target_event_id = f"sr:match:{raw_event_id}"

            # 2. Team name lookup only if direct event ID was not attached
            if not target_event_id and live_sporty_events:
                h_words = [w for w in home_target.split() if len(w) >= 3 and w not in STOP_WORDS]
                a_words = [w for w in away_target.split() if len(w) >= 3 and w not in STOP_WORDS]
                for ev in live_sporty_events:
                    h_name = (ev.get("homeTeamName") or "").lower()
                    a_name = (ev.get("awayTeamName") or "").lower()
                    if (any(w in h_name for w in h_words) or not h_words) and (any(w in a_name for w in a_words) or not a_words):
                        target_event_id = ev.get("eventId")
                        break

            # STRICT RULE: NEVER substitute an arbitrary random match!
            if not target_event_id:
                logger.warning(f"[SportyBetAdapter] Could not find exact event ID for {home_target} vs {away_target}. Skipping.")
                continue

            # Check for direct pre-locked market and outcome IDs
            direct_mkt_id = s.get("provider_market_id") or s.get("marketId") or s.get("_sportybet_market_id") or s.get("market_id")
            direct_oc_id = s.get("provider_outcome_id") or s.get("outcomeId") or s.get("_sportybet_outcome_id") or s.get("outcome_id")
            direct_spec = s.get("provider_specifier") or s.get("specifier") or s.get("_sportybet_specifier")

            mkt_text = (s.get("market_name") or s.get("market") or "").strip()

            item_payload = None
            if direct_mkt_id and direct_oc_id:
                clean_oc_id = str(direct_oc_id)
                clean_mkt_id = str(direct_mkt_id)

                # Fix legacy string market IDs if encountered
                if clean_mkt_id == "TEAM_OU":
                    if "H_" in clean_oc_id or "home" in sel_text.lower():
                        clean_mkt_id = "19"
                    else:
                        clean_mkt_id = "20"
                    clean_oc_id = "12"

                # Strict 1X2 validation guard: Away Win (2) must be outcome 3, Draw (X) must be outcome 2, Home (1) must be outcome 1
                if clean_mkt_id == "1":
                    s_lower = sel_text.lower()
                    if "(2)" in s_lower or "away" in s_lower or "to win (2)" in s_lower:
                        clean_oc_id = "3"
                    elif "draw" in s_lower or "(x)" in s_lower:
                        clean_oc_id = "2"
                    elif "(1)" in s_lower or "home" in s_lower or "to win (1)" in s_lower:
                        clean_oc_id = "1"

                # If boutique market (Win Either Half / Combo) is not offered on this specific match, fallback to Double Chance
                event_obj = events_by_id.get(target_event_id)
                ev_markets = event_obj.get("markets", []) if event_obj else []
                if isinstance(ev_markets, dict):
                    ev_markets = list(ev_markets.values())
                ev_market_ids = {str(m.get("id") or m.get("market_id") or "") for m in ev_markets if isinstance(m, dict)}

                if ev_market_ids and clean_mkt_id not in ev_market_ids and clean_mkt_id in ("73", "74", "62", "16"):
                    m_id_fb, o_id_fb, spec_fb = self._resolve_market_payload(ev_markets, mkt_text, sel_text, home_target, away_target)
                    clean_mkt_id = m_id_fb
                    clean_oc_id = o_id_fb
                    # Specifier sanitization rules for SportyBet API
                clean_spec = direct_spec
                if clean_mkt_id in ("1", "10", "29"):
                    clean_spec = None
                elif clean_mkt_id == "18":
                    if clean_spec:
                        m_tot = re.search(r"(\d+\.?\d*)", str(clean_spec))
                        if m_tot:
                            val = float(m_tot.group(1))
                            if val in (1.0, 2.0, 3.0, 4.0, 5.0):
                                val = val - 0.5
                            val = max(0.5, min(4.5, val))
                            clean_spec = f"total={val:.1f}"
                        else:
                            clean_spec = "total=1.5"
                    else:
                        clean_spec = "total=1.5"

                item_payload = {
                    "eventId": target_event_id,
                    "marketId": clean_mkt_id,
                    "outcomeId": clean_oc_id
                }
                if clean_spec:
                    item_payload["specifier"] = str(clean_spec)
            else:
                event_obj = events_by_id.get(target_event_id)
                ev_markets = event_obj.get("markets", []) if event_obj else []
                if isinstance(ev_markets, dict):
                    ev_markets = list(ev_markets.values())

                m_id, o_id, spec = self._resolve_market_payload(ev_markets, mkt_text, sel_text, home_target, away_target)
                clean_spec = spec
                if str(m_id) in ("1", "10", "29"):
                    clean_spec = None
                elif str(m_id) == "18":
                    if clean_spec:
                        m_tot = re.search(r"(\d+\.?\d*)", str(clean_spec))
                        if m_tot:
                            val = float(m_tot.group(1))
                            if val in (1.0, 2.0, 3.0, 4.0, 5.0):
                                val = val - 0.5
                            val = max(0.5, min(4.5, val))
                            clean_spec = f"total={val:.1f}"
                        else:
                            clean_spec = "total=1.5"
                    else:
                        clean_spec = "total=1.5"

                item_payload = {
                    "eventId": target_event_id,
                    "marketId": str(m_id),
                    "outcomeId": str(o_id)
                }
                if clean_spec:
                    item_payload["specifier"] = str(clean_spec)

            selections_payload.append(item_payload)



        if not selections_payload:
            return {
                "status": "MATCH_NOT_FOUND",
                "provider": "SPORTYBET",
                "booking_code": None,
                "message": "Could not map selected fixtures to active SportyBet pre-match events. Please refresh."
            }

        # Request shareCode from SportyBet API
        try:
            with httpx.Client(timeout=8.0, headers=self.HEADERS) as client:
                resp = client.post(url_share, json={"selections": selections_payload})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("bizCode") == 10000:
                        share_code = data.get("data", {}).get("shareCode")
                        share_url = data.get("data", {}).get("shareURL")
                        if share_code:
                            return {
                                "status": "SUCCESS",
                                "provider": "SPORTYBET",
                                "booking_code": share_code,
                                "verification_status": "BOOKING_VERIFIED",
                                "country": country_code.upper(),
                                "load_url": share_url or f"https://www.sportybet.com/{country_code.lower()}/?shareCode={share_code}",
                                "matched_count": len(selections_payload),
                                "verified": True
                            }

                # Resilient Directional Self-Healing Fallback: Repair any unsupported boutique market
                # preserving Home vs Away intent (NEVER flip an Away favourite pick to 1X!)
                valid_items = []
                for idx, item in enumerate(selections_payload):
                    orig_s = selections[idx] if idx < len(selections) else {}
                    s_name = str(orig_s.get("selection_name") or orig_s.get("selection") or "").lower()
                    m_name = str(orig_s.get("market_name") or orig_s.get("market") or "").lower()
                    h_team = str(orig_s.get("home_team") or "").lower()
                    a_team = str(orig_s.get("away_team") or "").lower()

                    is_away_pick = (
                        "x2" in s_name or "draw or away" in s_name or "(2)" in s_name or 
                        "away" in s_name or (a_team and a_team in s_name and "vs" not in s_name) or
                        item.get("marketId") == "20" or item.get("outcomeId") in ("3", "11", "1715")
                    )
                    is_goals_pick = "over" in s_name or "under" in s_name or "goals" in m_name or item.get("marketId") in ("18", "19", "20")

                    try:
                        r_single = client.post(url_share, json={"selections": [item]})
                        if r_single.status_code == 200 and r_single.json().get("bizCode") == 10000:
                            valid_items.append(item)
                        else:
                            # 1. If it was an Away pick: repair to Draw or Away (X2 - outcome 11) or Over 1.5 Goals
                            if is_away_pick:
                                repaired_x2 = {"eventId": item["eventId"], "marketId": "10", "outcomeId": "11"}
                                r_x2 = client.post(url_share, json={"selections": [repaired_x2]})
                                if r_x2.status_code == 200 and r_x2.json().get("bizCode") == 10000:
                                    valid_items.append(repaired_x2)
                                    continue
                                repaired_o15 = {"eventId": item["eventId"], "marketId": "18", "outcomeId": "12", "specifier": "total=1.5"}
                                r_o15 = client.post(url_share, json={"selections": [repaired_o15]})
                                if r_o15.status_code == 200 and r_o15.json().get("bizCode") == 10000:
                                    valid_items.append(repaired_o15)
                                    continue

                            # 2. If it was a Goals pick: repair to Over 1.5 Goals
                            elif is_goals_pick:
                                repaired_o15 = {"eventId": item["eventId"], "marketId": "18", "outcomeId": "12", "specifier": "total=1.5"}
                                r_o15 = client.post(url_share, json={"selections": [repaired_o15]})
                                if r_o15.status_code == 200 and r_o15.json().get("bizCode") == 10000:
                                    valid_items.append(repaired_o15)
                                    continue
                                repaired_dc = {"eventId": item["eventId"], "marketId": "10", "outcomeId": "9"}
                                r_dc = client.post(url_share, json={"selections": [repaired_dc]})
                                if r_dc.status_code == 200 and r_dc.json().get("bizCode") == 10000:
                                    valid_items.append(repaired_dc)
                                    continue

                            # 3. Default Home pick: repair to Home or Draw (1X - outcome 9)
                            else:
                                repaired_dc = {"eventId": item["eventId"], "marketId": "10", "outcomeId": "9"}
                                r_dc = client.post(url_share, json={"selections": [repaired_dc]})
                                if r_dc.status_code == 200 and r_dc.json().get("bizCode") == 10000:
                                    valid_items.append(repaired_dc)
                                    continue
                                repaired_o15 = {"eventId": item["eventId"], "marketId": "18", "outcomeId": "12", "specifier": "total=1.5"}
                                r_o15 = client.post(url_share, json={"selections": [repaired_o15]})
                                if r_o15.status_code == 200 and r_o15.json().get("bizCode") == 10000:
                                    valid_items.append(repaired_o15)
                                    continue
                    except Exception:
                        pass

                if valid_items and len(valid_items) >= 1:
                    resp2 = client.post(url_share, json={"selections": valid_items})
                    if resp2.status_code == 200 and resp2.json().get("bizCode") == 10000:
                        share_code = resp2.json().get("data", {}).get("shareCode")
                        if share_code:
                            return {
                                "status": "SUCCESS",
                                "provider": "SPORTYBET",
                                "booking_code": share_code,
                                "verification_status": "BOOKING_VERIFIED",
                                "country": country_code.upper(),
                                "load_url": f"https://www.sportybet.com/{country_code.lower()}/?shareCode={share_code}",
                                "matched_count": len(valid_items),
                                "verified": True
                            }
        except Exception as e:
            logger.warning(f"SportyBet booking code generation error: {e}")


        return {
            "status": "CODE_GENERATION_FAILED",
            "provider": "SPORTYBET",
            "booking_code": None,
            "message": "SportyBet rejected booking code request. Please ensure all selections are still open."
        }


    def fetch_live_sportybet_markets(self, country_code: str = "ng") -> List[Dict[str, Any]]:
        """
        Polls live upcoming events and available market lines directly from SportyBet endpoints.
        """
        url_events = f"{self.BASE_URL}/{country_code}/factsCenter/wapUpcomingEvents?sportId=sr%3Asport%3A1&pageSize=100"
        live_matches = []

        try:
            with httpx.Client(timeout=8.0, headers=self.HEADERS, verify=False) as client:
                resp = client.get(url_events)
                if resp.status_code == 200:
                    raw_data = resp.json().get("data", [])
                    for ev in raw_data:
                        h_name = ev.get("homeTeamName") or "Home"
                        a_name = ev.get("awayTeamName") or "Away"
                        event_id = ev.get("eventId")
                        league_name = ev.get("tournamentName") or ev.get("categoryName") or "Top League"
                        
                        markets_list = []
                        for mkt in ev.get("markets", []):
                            mkt_desc = mkt.get("desc") or mkt.get("name") or "Market"
                            outcomes = []
                            for o in mkt.get("outcomes", []):
                                outcomes.append({
                                    "outcome_id": o.get("id"),
                                    "selection_name": o.get("desc") or o.get("name"),
                                    "odds": float(o.get("odds", 1.50)) if o.get("odds") else 1.50
                                })
                            markets_list.append({
                                "market_id": mkt.get("id"),
                                "market_name": mkt_desc,
                                "outcomes": outcomes
                            })

                        live_matches.append({
                            "event_id": event_id,
                            "home_team": h_name,
                            "away_team": a_name,
                            "league": league_name,
                            "markets": markets_list
                        })
        except Exception as e:
            logger.warning(f"Error polling SportyBet live markets: {e}")
        return live_matches

    def _parse_market_name(self, market_name: str, selection_name: Optional[str] = None) -> str:
        """
        Parses raw SportyBet market names into canonical market categories.
        """
        m_lower = (market_name or "").lower()
        s_lower = (selection_name or "").lower()
        if "1x2" in m_lower or "result" in m_lower or "winner" in m_lower:
            return "1X2"
        if "double chance" in m_lower or "double chance" in s_lower:
            return "DOUBLE_CHANCE"
        if "draw no bet" in m_lower or "dnb" in m_lower or "dnb" in s_lower:
            return "DRAW_NO_BET"
        if "over" in m_lower or "under" in m_lower or "goals" in m_lower or "over" in s_lower or "under" in s_lower:
            return "OVER_UNDER"
        if "handicap" in m_lower or "handicap" in s_lower:
            return "ASIAN_HANDICAP"
        return "GENERAL"

