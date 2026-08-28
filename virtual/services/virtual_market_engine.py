"""
Multi-Market Selection & Dynamic Calibration Engine for SportyBet Virtual Football.
Implements:
1. Dynamic multi-market discovery (1X2, Double Chance, Over/Under 0.5/1.5/2.5/3.5, BTTS).
2. Probabilistic feature weighting and edge calculation.
3. Fail-Closed Target Odds Builder (Returns NO_BET if no qualified ticket exists).
"""
import logging
from typing import Dict, Any, List, Optional
from itertools import combinations
from sqlalchemy.orm import Session

from virtual.services.virtual_stats_enricher import VirtualStatsEnricher

logger = logging.getLogger("statiq.virtual.market_engine")

class VirtualMarketEngine:
    
    MIN_LEG_ODDS = 1.12
    MAX_LEG_ODDS = 1.55
    
    @classmethod
    def extract_all_markets(cls, event: Dict[str, Any], safety_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Dynamically extracts all available betting markets for a single vFootball match.
        """
        candidates = []
        sport = event.get("sport", {})
        cat = sport.get("category", {}) if isinstance(sport, dict) else {}
        league = f"{cat.get('name', 'Virtual')} Virtual"
        home = event.get("homeTeamName", "?")
        away = event.get("awayTeamName", "?")
        game_id = str(event.get("gameId", ""))
        event_id = str(event.get("eventId") or f"sr:match:{game_id}")
        markets = event.get("markets", [])
        
        # 1. Double Chance (1X, X2, 12)
        for m in markets:
            desc = str(m.get("desc") or "").upper()
            m_id = str(m.get("id") or "10")
            if "DOUBLE CHANCE" in desc or m_id == "10":
                for o in m.get("outcomes", []):
                    o_desc = str(o.get("desc") or "").upper()
                    odds = float(o.get("odds") or 0.0)
                    oid = str(o.get("id") or "")
                    
                    if not (cls.MIN_LEG_ODDS <= odds <= cls.MAX_LEG_ODDS):
                        continue
                    
                    pick_label = None
                    pick_code = None
                    safety_factor = 0.75
                    
                    if "1X" in o_desc or "HOME OR DRAW" in o_desc or oid == "9":
                        pick_label = f"{home} or Draw (1X)"
                        pick_code = "1x"
                        safety_factor = safety_meta.get("dc_1x_safety", 0.78)
                    elif "X2" in o_desc or "DRAW OR AWAY" in o_desc or oid == "11":
                        pick_label = f"Draw or {away} (X2)"
                        pick_code = "x2"
                        safety_factor = safety_meta.get("dc_x2_safety", 0.75)
                    elif "12" in o_desc or "HOME OR AWAY" in o_desc or oid == "10":
                        pick_label = f"{home} or {away} (12)"
                        pick_code = "12"
                        safety_factor = 0.72

                    if pick_label:
                        implied_prob = 1.0 / odds
                        edge = max(0.0, safety_factor - implied_prob)
                        candidates.append({
                            "game_id": game_id,
                            "event_id": event_id,
                            "league": league,
                            "match": f"{home} vs {away}",
                            "pick": pick_label,
                            "pick_code": pick_code,
                            "market_type": "DC",
                            "market_id": m_id,
                            "outcome_id": oid,
                            "specifier": None,
                            "odds": odds,
                            "implied_prob": implied_prob,
                            "model_prob": safety_factor,
                            "edge": edge,
                            "safety_score": implied_prob * (1.0 + edge),
                        })

        # 2. Over / Under Goals (Over 0.5, Over 1.5, Under 3.5, Under 4.5)
        for m in markets:
            desc = str(m.get("desc") or "").upper()
            m_id = str(m.get("id") or "18")
            specifier = str(m.get("specifier") or "")
            if ("O/U" in desc or "OVER" in desc or m_id == "18") and "total=" in specifier:
                line = specifier.replace("total=", "")
                for o in m.get("outcomes", []):
                    o_desc = str(o.get("desc") or "").upper()
                    odds = float(o.get("odds") or 0.0)
                    oid = str(o.get("id") or "")
                    
                    if not (cls.MIN_LEG_ODDS <= odds <= cls.MAX_LEG_ODDS):
                        continue
                    
                    is_over = "OVER" in o_desc or oid == "12"
                    is_under = "UNDER" in o_desc or oid == "13"
                    
                    pick_label = None
                    pick_code = None
                    model_p = 0.75
                    
                    if is_over and line == "1.5":
                        pick_label = "Over 1.5 Goals"
                        pick_code = "over_1.5"
                        model_p = safety_meta.get("over_15_prob", 0.80)
                    elif is_over and line == "0.5":
                        pick_label = "Over 0.5 Goals"
                        pick_code = "over_0.5"
                        model_p = 0.92
                    elif is_under and line in ("3.5", "4.5"):
                        pick_label = f"Under {line} Goals"
                        pick_code = f"under_{line}"
                        model_p = 0.82
                    
                    if pick_label:
                        implied_prob = 1.0 / odds
                        edge = max(0.0, model_p - implied_prob)
                        candidates.append({
                            "game_id": game_id,
                            "event_id": event_id,
                            "league": league,
                            "match": f"{home} vs {away}",
                            "pick": pick_label,
                            "pick_code": pick_code,
                            "market_type": "OU",
                            "market_id": m_id,
                            "outcome_id": oid,
                            "specifier": specifier,
                            "odds": odds,
                            "implied_prob": implied_prob,
                            "model_prob": model_p,
                            "edge": edge,
                            "safety_score": implied_prob * (1.0 + edge),
                        })

        # 3. Both Teams to Score (BTTS)
        for m in markets:
            desc = str(m.get("desc") or "").upper()
            m_id = str(m.get("id") or "29")
            if "BOTH TEAMS" in desc or "GG/NG" in desc or m_id == "29":
                for o in m.get("outcomes", []):
                    o_desc = str(o.get("desc") or "").upper()
                    odds = float(o.get("odds") or 0.0)
                    oid = str(o.get("id") or "")
                    
                    if not (cls.MIN_LEG_ODDS <= odds <= cls.MAX_LEG_ODDS):
                        continue
                    
                    if "YES" in o_desc or "GG" in o_desc:
                        implied_prob = 1.0 / odds
                        model_p = safety_meta.get("btts_prob", 0.65)
                        edge = max(0.0, model_p - implied_prob)
                        candidates.append({
                            "game_id": game_id,
                            "event_id": event_id,
                            "league": league,
                            "match": f"{home} vs {away}",
                            "pick": "Both Teams to Score (Yes)",
                            "pick_code": "btts_yes",
                            "market_type": "BTTS",
                            "market_id": m_id,
                            "outcome_id": oid,
                            "specifier": None,
                            "odds": odds,
                            "implied_prob": implied_prob,
                            "model_prob": model_p,
                            "edge": edge,
                            "safety_score": implied_prob * (1.0 + edge),
                        })

        # 4. Straight Match Winner (Heavy Favorites only: 1.15 - 1.45)
        for m in markets:
            desc = str(m.get("desc") or "").upper()
            m_id = str(m.get("id") or "1")
            if desc == "1X2" or m_id == "1":
                for o in m.get("outcomes", []):
                    o_desc = str(o.get("desc") or "").upper()
                    odds = float(o.get("odds") or 0.0)
                    oid = str(o.get("id") or "")
                    
                    if not (cls.MIN_LEG_ODDS <= odds <= 1.45):
                        continue
                    
                    if "HOME" in o_desc or oid == "1":
                        implied_prob = 1.0 / odds
                        model_p = safety_meta.get("home_win_prob", 0.72)
                        edge = max(0.0, model_p - implied_prob)
                        candidates.append({
                            "game_id": game_id,
                            "event_id": event_id,
                            "league": league,
                            "match": f"{home} vs {away}",
                            "pick": f"{home} to Win",
                            "pick_code": "1",
                            "market_type": "1X2",
                            "market_id": m_id,
                            "outcome_id": oid,
                            "specifier": None,
                            "odds": odds,
                            "implied_prob": implied_prob,
                            "model_prob": model_p,
                            "edge": edge,
                            "safety_score": implied_prob * (1.0 + edge),
                        })
                    elif "AWAY" in o_desc or oid == "3":
                        implied_prob = 1.0 / odds
                        model_p = safety_meta.get("away_win_prob", 0.70)
                        edge = max(0.0, model_p - implied_prob)
                        candidates.append({
                            "game_id": game_id,
                            "event_id": event_id,
                            "league": league,
                            "match": f"{home} vs {away}",
                            "pick": f"{away} to Win",
                            "pick_code": "2",
                            "market_type": "1X2",
                            "market_id": m_id,
                            "outcome_id": oid,
                            "specifier": None,
                            "odds": odds,
                            "implied_prob": implied_prob,
                            "model_prob": model_p,
                            "edge": edge,
                            "safety_score": implied_prob * (1.0 + edge),
                        })

        return candidates

    @classmethod
    def build_ticket_from_events(
        cls,
        events: List[Dict[str, Any]],
        target_odds: float = 2.0,
        preferred_market: str = "ALL",
        selected_leagues: Optional[List[str]] = None,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Builds a safe 2-to-3 leg ticket satisfying target odds with strict Fail-Closed behavior.
        If no combination falls within target tolerance, returns empty list [] (NO_BET).
        """
        all_candidates = []

        for ev in events:
            sport = ev.get("sport", {})
            cat = sport.get("category", {}) if isinstance(sport, dict) else {}
            league = f"{cat.get('name', 'Virtual')} Virtual"
            
            # Filter by selected leagues if provided
            if selected_leagues and league not in selected_leagues:
                continue

            home = ev.get("homeTeamName", "?")
            away = ev.get("awayTeamName", "?")
            
            safety_meta = {}
            if db:
                safety_meta = VirtualStatsEnricher.evaluate_fixture_safety(db, home, away, league)
                if safety_meta.get("is_cold_trap"):
                    continue

            ev_candidates = cls.extract_all_markets(ev, safety_meta)
            
            # Apply preferred market filter
            if preferred_market != "ALL":
                if preferred_market in ("DC", "DOUBLE_CHANCE"):
                    ev_candidates = [c for c in ev_candidates if c["market_type"] == "DC"]
                elif preferred_market in ("OU", "OVER_UNDER", "OVER_1.5"):
                    ev_candidates = [c for c in ev_candidates if c["market_type"] == "OU"]
                elif preferred_market in ("BTTS", "BOTH_TEAMS_TO_SCORE"):
                    ev_candidates = [c for c in ev_candidates if c["market_type"] == "BTTS"]
                elif preferred_market in ("1X2", "MATCH_WINNER"):
                    ev_candidates = [c for c in ev_candidates if c["market_type"] == "1X2"]

            all_candidates.extend(ev_candidates)

        if not all_candidates:
            logger.info("[MarketEngine] No qualified market candidates discovered. Returning NO_BET.")
            return []

        # Sort candidates by safety_score descending
        all_candidates.sort(key=lambda x: x["safety_score"], reverse=True)
        pool = all_candidates[:12]

        target = float(target_odds or 2.0)
        min_bracket = target * 0.88  # e.g., 1.76 for 2.0 target
        max_bracket = target * 1.18  # e.g., 2.36 for 2.0 target

        best_combo = []
        best_score = float("inf")

        # Search 2-leg combos
        for combo in combinations(pool, 2):
            if combo[0]["game_id"] == combo[1]["game_id"]:
                continue
            tot_odds = round(combo[0]["odds"] * combo[1]["odds"], 2)
            if min_bracket <= tot_odds <= max_bracket:
                dist = abs(tot_odds - target)
                avg_safety = (combo[0]["safety_score"] + combo[1]["safety_score"]) / 2.0
                score = (dist * 1.5) - (avg_safety * 0.5)
                if score < best_score:
                    best_score = score
                    best_combo = list(combo)

        # Search 3-leg combos
        for combo in combinations(pool, 3):
            gids = {c["game_id"] for c in combo}
            if len(gids) < 3:
                continue
            tot_odds = round(combo[0]["odds"] * combo[1]["odds"] * combo[2]["odds"], 2)
            if min_bracket <= tot_odds <= max_bracket:
                dist = abs(tot_odds - target)
                avg_safety = (combo[0]["safety_score"] + combo[1]["safety_score"] + combo[2]["safety_score"]) / 3.0
                score = (dist * 1.5) - (avg_safety * 0.5)
                if score < best_score:
                    best_score = score
                    best_combo = list(combo)

        if not best_combo:
            logger.info(f"[MarketEngine] No combination within bracket [{min_bracket:.2f}x - {max_bracket:.2f}x]. FAIL-CLOSED NO_BET returned.")
            return []

        return best_combo
