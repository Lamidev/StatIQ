import random
import re
import string
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
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
    def __init__(self, session):
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

                game_id = str(out.get("gameId") or out.get("eventId") or "")
                
                start_time_ms = out.get("estimateStartTime") or out.get("startTime") or 0
                kickoff_str = ""
                if start_time_ms > 0:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(start_time_ms / 1000.0)
                    kickoff_str = dt.strftime("%d/%m %H:%M")

                score_str = out.get("setScore") or out.get("score") or ""
                home_score = None
                away_score = None
                if score_str:
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

                played_sec = out.get("playedSeconds") or ""
                sel_active = mkt_outcomes[0].get("isActive", 1) if (mkt_outcomes and len(mkt_outcomes) > 0) else 1
                mkt_status = markets[0].get("status", 1) if markets else 1
                match_status_code_str = str(out.get("matchStatus") or out.get("status") or "").strip().upper()
                is_match_finished = match_status_code_str in ["ENDED", "FT", "CONCLUDED", "FINISHED", "2"]
                is_match_live = match_status_code_str in ["H1", "H2", "HT", "LIVE", "IN_PROGRESS", "ONGOING", "1"] or (bool(played_sec) and not is_match_finished)

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
                elif is_match_live:
                    match_status = "LIVE"
                    live_clock = f"{played_sec} {match_status_code_str}".strip()
                    status_label = f"Live ({live_clock})" if live_clock else "In Progress / Live"
                elif is_match_finished or (score_str and not is_match_live and start_time_ms > 0 and (now_ms - start_time_ms) > 7200000):
                    match_status = "CONCLUDED"
                    status_label = "Concluded / Settled"
                elif out.get("banned") == True or out.get("productStatus") == "CANCELLED":
                    match_status = "NULLED_EXPIRED"
                    status_label = "Nulled / Odds Removed"
                else:
                    match_status = "UPCOMING"
                    status_label = "Upcoming / Bettable"

                selections.append({
                    "external_fixture_id": game_id,
                    "game_id": game_id,
                    "provider_event_id": game_id,
                    "provider_market_id": provider_mkt_id,
                    "provider_outcome_id": provider_oc_id,
                    "provider_specifier": provider_spec,
                    "_sportybet_market_id": provider_mkt_id,
                    "_sportybet_outcome_id": provider_oc_id,
                    "_sportybet_specifier": provider_spec,
                    "_sportybet_event_id": game_id,
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

    def _find_best_market_outcome(
        self,
        sporty_markets: List[Dict[str, Any]],
        matchiq_market: str,
        matchiq_selection: str,
    ) -> tuple:
        """
        Given a list of SportyBet markets for a matched event, find the market
        and outcome that best corresponds to the MatchIQ market_name and selection_name.

        Returns (market_dict, outcome_dict) or (fallback_market, fallback_outcome).
        """
        mkt_lower = (matchiq_market or "").lower().strip()
        sel_lower = (matchiq_selection or "").lower().strip()

        # Step 1: Score each SportyBet market against the MatchIQ market name
        best_market = None
        best_market_score = 0

        for sm in sporty_markets:
            sm_name = (sm.get("name") or sm.get("desc") or "").lower()
            score = 0

            # Check keyword groups
            for _group, keywords in self._MARKET_KEYWORDS.items():
                mkt_has = any(kw in mkt_lower for kw in keywords)
                sm_has = any(kw in sm_name for kw in keywords)
                if mkt_has and sm_has:
                    score += 10
                    break

            # Exact substring bonus
            if mkt_lower and mkt_lower in sm_name:
                score += 5
            if sm_name and sm_name in mkt_lower:
                score += 5

            # Line/handicap value matching (e.g. "2.5" in both)
            mkt_nums = set(re.findall(r"\d+\.?\d*", mkt_lower))
            sm_nums = set(re.findall(r"\d+\.?\d*", sm_name))
            if mkt_nums and mkt_nums & sm_nums:
                score += 3

            if score > best_market_score:
                best_market_score = score
                best_market = sm

        # Step 2: Within the best market, find the outcome matching the selection
        target_market = best_market if best_market and best_market_score >= 3 else None

        if target_market and target_market.get("outcomes"):
            best_outcome = None
            best_out_score = 0

            for oc in target_market["outcomes"]:
                oc_name = (oc.get("name") or oc.get("desc") or "").lower()
                oscore = 0

                # Keyword group match
                for _group, keywords in self._OUTCOME_KEYWORDS.items():
                    sel_has = any(kw in sel_lower for kw in keywords)
                    oc_has = any(kw in oc_name for kw in keywords)
                    if sel_has and oc_has:
                        oscore += 10
                        break

                # Exact substring
                if sel_lower and sel_lower in oc_name:
                    oscore += 5
                if oc_name and oc_name in sel_lower:
                    oscore += 5

                # Number matching (e.g. "2.5")
                sel_nums = set(re.findall(r"\d+\.?\d*", sel_lower))
                oc_nums = set(re.findall(r"\d+\.?\d*", oc_name))
                if sel_nums and sel_nums & oc_nums:
                    oscore += 3

                if oscore > best_out_score:
                    best_out_score = oscore
                    best_outcome = oc

            if best_outcome and best_out_score >= 3:
                return target_market, best_outcome

            # Fallback: return first outcome of the matched market
            return target_market, target_market["outcomes"][0]

        # Step 3: Ultimate fallback — first market, first outcome
        if sporty_markets and sporty_markets[0].get("outcomes"):
            return sporty_markets[0], sporty_markets[0]["outcomes"][0]

        return None, None

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
        
        Strategy:
        1. For each selection, try to look up the event by its game_id (eventId) directly
        2. Fall back to team name matching in the upcoming events feed
        3. Match the MatchIQ market/selection to the correct SportyBet market/outcome
        """
        url_share = f"{self.BASE_URL}/{country_code}/orders/share"

        # Batch fetch upcoming events (fetching top 100 live events for maximum match coverage)
        url_events = f"{self.BASE_URL}/{country_code}/factsCenter/wapUpcomingEvents?sportId=sr%3Asport%3A1&pageSize=100"
        live_sporty_events = []
        try:
            with httpx.Client(timeout=8.0, headers=self.HEADERS) as client:
                r = client.get(url_events)
                if r.status_code == 200:
                    live_sporty_events = r.json().get("data", [])
        except Exception as e:
            logger.warning(f"Failed to fetch live SportyBet matches: {e}")

        outcomes_payload = []
        import time
        now_sec = time.time()

        for s in selections:
            # Skip matches that have already kicked off or ended (more than 5 mins in the past)
            start_time = s.get("start_time_ms") or s.get("estimateStartTime") or s.get("kickoff_datetime")
            if start_time:
                try:
                    ts_val = float(start_time)
                    ts_sec = (ts_val / 1000.0) if ts_val > 1e11 else ts_val
                    if ts_sec < (now_sec - 300):
                        logger.info(f"SportyBet: Skipping past/kicked-off match for pre-match booking code.")
                        continue
                except (ValueError, TypeError):
                    pass

            game_id = s.get("game_id") or s.get("external_fixture_id") or s.get("fixture_id")
            home_target = (s.get("home_team") or s.get("fixture") or "").lower().strip()
            away_target = (s.get("away_team") or "").lower().strip()
            target_mkt = s.get("market_name") or s.get("market") or ""
            target_sel = s.get("selection_name") or s.get("selection") or s.get("prediction") or ""

            matched = False

            # ── Strategy 1: Direct event lookup by game_id ──────────────────
            if game_id:
                event_markets = self._fetch_event_markets(game_id, country_code)
                if event_markets:
                    mkt, outcome = self._find_best_market_outcome(event_markets, target_mkt, target_sel)
                    if mkt and outcome:
                        outcomes_payload.append({
                            "eventId": game_id,
                            "marketId": mkt["id"],
                            "outcomeId": outcome["id"],
                            "odds": str(outcome.get("odds") or s.get("odds") or "1.50")
                        })
                        matched = True

            # ── Strategy 2: Team name matching in upcoming events feed ──────
            if not matched and live_sporty_events:
                matched_event = None
                best_score = 0

                STOP_WORDS = {"fc", "sc", "cd", "ud", "ca", "rc", "ac", "fk", "bk", "sk", "ff", "sad", "club", "team"}
                h_words = [w for w in home_target.split() if len(w) >= 3 and w not in STOP_WORDS]
                a_words = [w for w in away_target.split() if len(w) >= 3 and w not in STOP_WORDS]

                for ev in live_sporty_events:
                    # Direct game_id / eventId match takes highest priority
                    if game_id and (str(ev.get("eventId")) == str(game_id) or str(ev.get("gameId")) == str(game_id)):
                        matched_event = ev
                        best_score = 100
                        break

                    h_name = (ev.get("homeTeamName") or "").lower()
                    a_name = (ev.get("awayTeamName") or "").lower()

                    h_match = any(kw in h_name for kw in h_words) if h_words else False
                    a_match = any(kw in a_name for kw in a_words) if a_words else False

                    # Require BOTH home AND away teams to match keyword criteria
                    if h_match and a_match:
                        score = 10
                        if score > best_score:
                            best_score = score
                            matched_event = ev

                if matched_event and best_score >= 8 and matched_event.get("markets"):
                    mkt, outcome = self._find_best_market_outcome(
                        matched_event["markets"], target_mkt, target_sel
                    )
                    if mkt and outcome:
                        outcomes_payload.append({
                            "eventId": matched_event["eventId"],
                            "marketId": mkt["id"],
                            "outcomeId": outcome["id"],
                            "odds": str(outcome.get("odds") or s.get("odds") or "1.50")
                        })
                        matched = True

            if not matched:
                logger.warning(
                    f"SportyBet: No event found for '{home_target} vs {away_target}' "
                    f"(gameId={game_id}). Fixture skipped."
                )

        # If no selections could be matched, return a clear error
        if not outcomes_payload:
            return {
                "status": "MATCH_NOT_FOUND",
                "provider": "SPORTYBET",
                "booking_code": None,
                "message": (
                    "None of the MatchIQ fixtures could be matched to currently available SportyBet events. "
                    "The matches may not be listed yet, or team names differ on SportyBet. "
                    "Try again closer to kickoff when the events appear on SportyBet."
                )
            }

        # Generate code on target region and try multi-region generation
        primary_code = None
        regional_codes = {}

        target_reg = country_code.lower()
        regions_to_generate = [target_reg] + [c for c in ["gh", "ke", "ug", "ng"] if c != target_reg]

        try:
            with httpx.Client(timeout=6.0, headers=self.HEADERS) as client:
                for reg in regions_to_generate:
                    reg_url = f"{self.BASE_URL}/{reg}/orders/share"
                    try:
                        resp = client.post(reg_url, json={"selections": outcomes_payload})
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("bizCode") == 10000:
                                c_val = data.get("data", {}).get("shareCode")
                                if c_val:
                                    regional_codes[reg.upper()] = c_val
                                    if reg == target_reg and not primary_code:
                                        primary_code = c_val
                    except Exception:
                        pass

                if not primary_code and regional_codes:
                    primary_code = list(regional_codes.values())[0]

                if primary_code:
                    return {
                        "status": "SUCCESS",
                        "provider": "SPORTYBET",
                        "booking_code": primary_code,
                        "country": country_code.upper(),
                        "load_url": f"https://www.sportybet.com/{country_code.lower()}/?shareCode={primary_code}",
                        "regional_codes": regional_codes
                    }
        except Exception as e:
            logger.warning(f"SportyBet share code generation error: {e}")

        # Return clear error instead of random fake code
        return {
            "status": "CODE_GENERATION_FAILED",
            "provider": "SPORTYBET",
            "booking_code": None,
            "country": country_code.upper(),
            "message": (
                f"Matched {len(outcomes_payload)} fixture(s) but SportyBet rejected the booking code request. "
                "Some markets may not be available for booking. Try adjusting your selections."
            ),
            "matched_count": len(outcomes_payload),
            "total_selections": len(selections)
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

