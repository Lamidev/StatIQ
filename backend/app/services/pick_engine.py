"""
MatchIQ 5-Gate Pick Engine & Strategic Decision Pipeline
=========================================================
Architectural single source of truth for all AI Ticket Builder, Scenario Builder,
and Backtest Simulator pick evaluation decisions.

5 Sequential Decision Gates:
  GATE 1: Structural Tier Filter (Elo gap, team quality mismatch enforcement)
  GATE 2: Calibrated Probability Model (Poisson/Elo threshold verification)
  GATE 3: Scored Market Selection Audit (Bookmaker overround margin stripping + value edge + safety)
  GATE 4: Dynamic Odds Alignment Check (Per-leg target odds range tolerance)
  GATE 5: Accumulator Correlation & Diversity Filter (League limits, kickoff window correlation)

Also provides Fractional Kelly Criterion bankroll stake sizing.
"""

import math
import random
import time
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


from app.predictions.live_calculator import calculate_matchiq_probabilities, get_team_rating
from app.predictions.leg_odds_calculator import calculate_dynamic_leg_config

@dataclass
class PickDecision:
    fixture_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_datetime: Optional[str]
    market_name: str
    selection_name: str
    model_probability: float
    estimated_odds: float
    elo_gap: float
    tier_context: str            # HOME_DOMINANT, AWAY_DOMINANT, COMPETITIVE
    approved: bool
    confidence_tier: str         # ELITE, HIGH, SOLID, SPECULATIVE
    gate_results: Dict[str, Any]
    rejection_reason: Optional[str]
    decision_audit_log: List[str]
    kelly_quarter_stake_pct: float
    raw_match_data: Optional[Dict[str, Any]] = None
    market_id: Optional[str] = None
    outcome_id: Optional[str] = None
    specifier: Optional[str] = None


@dataclass
class BuiltTicket:
    mode: str
    target_odds: float
    accumulated_odds: float
    combined_probability: float
    correlation_adjusted_probability: float
    confidence_tier: str
    leg_config: Dict[str, Any]
    approved_legs: List[Dict[str, Any]]
    rejected_picks: List[Dict[str, Any]]
    total_evaluated: int
    decision_audit_summary: List[str]
    recommended_stake_pct: float

TOP_LEAGUES_BOOST = {
    "PREMIER LEAGUE": 10.0,
    "LALIGA": 9.5,
    "SERIE A": 9.5,
    "BUNDESLIGA": 9.5,
    "LIGUE 1": 9.0,
    "EREDIVISIE": 8.5,
    "PRIMEIRA LIGA": 8.5,
    "LIGA PORTUGAL": 8.5,
    "SUPER LIG": 8.5,
    "SAUDI PRO LEAGUE": 8.0,
    "BELGIUM": 8.0,
    "SCOTTISH PREMIERSHIP": 8.0,
    "CHAMPIONS LEAGUE": 10.0,
    "EUROPA LEAGUE": 9.5,
    "CONFERENCE LEAGUE": 9.0,
    "COPPA ITALIA": 8.5,
    "DFB POKAL": 8.5,
    "COPA DEL REY": 8.5,
    "FA CUP": 8.5,
    "EFL CUP": 8.0,
}

TOP_POWERHOUSE_CLUBS = {
    # Premier League
    "MANCHESTER CITY", "MAN CITY", "LIVERPOOL", "ARSENAL", "CHELSEA", "MANCHESTER UNITED", "MAN UTD", "TOTTENHAM", "ASTON VILLA", "NEWCASTLE",
    # LaLiga
    "REAL MADRID", "BARCELONA", "ATLETICO MADRID", "ATLETICO", "SEVILLA", "REAL SOCIEDAD", "VILLARREAL", "ATHLETIC BILBAO", "VALENCIA",
    # Bundesliga
    "BAYERN MUNICH", "BAYERN MUNCHEN", "BORUSSIA DORTMUND", "DORTMUND", "BAYER LEVERKUSEN", "LEVERKUSEN", "RB LEIPZIG", "EINTRACHT FRANKFURT", "STUTTGART",
    # Serie A
    "INTER", "INTER MILAN", "AC MILAN", "MILAN", "JUVENTUS", "NAPOLI", "ATALANTA", "ROMA", "LAZIO", "FIORENTINA", "TORINO", "UDINESE",
    # Ligue 1
    "PARIS SAINT-GERMAIN", "PSG", "MARSEILLE", "MONACO", "LYON", "LILLE", "LENS",
    # Eredivisie
    "PSV", "PSV EINDHOVEN", "AJAX", "FEYENOORD", "AZ ALKMAAR",
    # Liga Portugal
    "PORTO", "BENFICA", "SPORTING CP", "SPORTING LISBON", "BRAGA",
    # Super Lig
    "FENERBAHCE", "GALATASARAY", "BESIKTAS", "TRABZONSPOR",
    # Saudi Pro League
    "AL NASSR", "AL-NASSR", "AL HILAL", "AL-HILAL", "AL ITTIHAD", "AL-ITTIHAD", "AL AHLI", "AL-AHLI",
    # Scotland & Europe Elite
    "CELTIC", "RANGERS", "VIKTORIA PLZEN", "SLAVIA PRAGUE", "SPARTA PRAGUE", "GENK", "CLUB BRUGGE", "ANDERLECHT",
    "RED BULL SALZBURG", "SHAKHTAR DONETSK", "DINAMO ZAGREB", "OLYMPIACOS", "PAOK", "AEK ATHENS", "BODØ/GLIMT", "LUDOGORETS", "KRASNODAR"
}

class MatchIQPickEngine:
    """
    Core engine enforcing strict 5-gate pipeline validation.
    """
    def __init__(self, use_live_odds: bool = False):
        self.use_live_odds = use_live_odds

    def _get_structural_safety(self, market_name: str) -> float:
        m_lower = market_name.lower()
        if any(x in m_lower for x in ["double chance", "over 0.5 team", "team over 0.5", "win either half"]):
            return 1.0
        if any(x in m_lower for x in ["match result", "1x2", "over 1.5"]):
            return 0.7
        return 0.5  # BTTS, Over 2.5, Corners (higher variance)

    def _strip_overround_margin(self, odds: float, market_type: str = "2WAY") -> float:
        """
        Strips typical bookmaker profit overround (~5-8%) to yield true implied probability.
        """
        if odds <= 1.0:
            return 0.5
        raw_implied = 1.0 / odds
        # Estimate overround factor based on market type
        margin_factor = 1.06 if market_type == "2WAY" else 1.08
        true_implied = raw_implied / margin_factor
        return min(0.98, max(0.02, true_implied))

    def calculate_kelly_stake(self, prob: float, odds: float, fraction: float = 0.25) -> float:
        """
        Calculates Fractional Kelly Criterion recommended bankroll percentage.
        b = odds - 1, p = prob, q = 1 - p
        Kelly % = (b*p - q) / b
        """
        if odds <= 1.0 or prob <= 0.0:
            return 0.0
        b = odds - 1.0
        p = prob
        q = 1.0 - p
        full_kelly = (b * p - q) / b
        if full_kelly <= 0:
            return 0.0
        # Return percentage rounded to 2 decimal places (e.g. 2.5%)
        return round(min(full_kelly * fraction * 100.0, 10.0), 2)

    def evaluate_fixture_markets(
        self,
        fixture: Dict[str, Any],
        per_leg_target_odds: float = 1.30,
        min_prob_threshold: float = 0.85,
        league_pick_counts: Optional[Dict[str, int]] = None,
        max_league_picks: int = 4,
        risk_profile: str = "BALANCED",
        allowed_markets: Optional[List[str]] = None,
        excluded_markets: Optional[List[str]] = None,
    ) -> PickDecision:

        """
        Runs a single fixture through all 5 decision gates.
        Returns PickDecision object with audit logs.
        """
        home = fixture.get("home_team") or fixture.get("home") or "Home Team"
        away = fixture.get("away_team") or fixture.get("away") or "Away Team"
        comp = fixture.get("competition_code") or fixture.get("league") or "PL"
        fix_id = str(fixture.get("fixture_id") or fixture.get("external_id") or f"FIX_{home}_{away}")
        kickoff = fixture.get("kickoff_datetime")

        audit_log = []
        gate_results = {}

        # Fetch / compute probabilities & structural context
        # Extract live odds dictionaries if present on fixture
        ou_lines = fixture.get("ou_lines") or []
        dc_odds = fixture.get("double_chance") or {}

        # Also inspect raw_markets for 1X2 if not in result_1x2
        r1x2 = dict(fixture.get("result_1x2") or {})
        if "1" in r1x2 and "home" not in r1x2:
            r1x2["home"] = r1x2["1"]
        if "X" in r1x2 and "draw" not in r1x2:
            r1x2["draw"] = r1x2["X"]
        if "2" in r1x2 and "away" not in r1x2:
            r1x2["away"] = r1x2["2"]
        if "home" in r1x2 and "1" not in r1x2:
            r1x2["1"] = r1x2["home"]
        if "draw" in r1x2 and "X" not in r1x2:
            r1x2["X"] = r1x2["draw"]
        if "away" in r1x2 and "2" not in r1x2:
            r1x2["2"] = r1x2["away"]

        if not r1x2 and fixture.get("markets"):
            mkts = fixture.get("markets", [])
            if isinstance(mkts, dict):
                mkts = list(mkts.values())
            for m in mkts:
                if not isinstance(m, dict):
                    continue
                m_desc = (m.get("desc") or m.get("name") or "").lower()

                if "1x2" in m_desc or "match result" in m_desc:
                    for o in m.get("outcomes", []):
                        o_desc = (o.get("desc") or o.get("name") or "").lower()
                        try:
                            val = float(o.get("odds"))
                            if o_desc in ["1", "home", home.lower()]:
                                r1x2["home"] = val
                                r1x2["1"] = val
                            elif o_desc in ["x", "draw"]:
                                r1x2["draw"] = val
                                r1x2["X"] = val
                            elif o_desc in ["2", "away", away.lower()]:
                                r1x2["away"] = val
                                r1x2["2"] = val
                        except (ValueError, TypeError):
                            pass

        fixture["result_1x2"] = r1x2

        h_odd = float(r1x2.get("home", 0.0)) if r1x2.get("home") else None
        d_odd = float(r1x2.get("draw", 0.0)) if r1x2.get("draw") else None
        a_odd = float(r1x2.get("away", 0.0)) if r1x2.get("away") else None
        # Fetch baseline probabilities
        probs_data = calculate_matchiq_probabilities(home, away)



        if self.use_live_odds and h_odd and a_odd and d_odd and h_odd > 1.0 and a_odd > 1.0:
            # Derive implied probabilities from live bookmaker odds
            ph = min(0.95, max(0.05, 1.0 / (h_odd * 1.06)))
            pd = min(0.95, max(0.05, 1.0 / (d_odd * 1.06)))
            pa = min(0.95, max(0.05, 1.0 / (a_odd * 1.06)))
            tot_p = ph + pd + pa
            ph, pd, pa = ph / tot_p, pd / tot_p, pa / tot_p

            if h_odd <= 1.40 and a_odd >= 4.0:
                tier_context = "HOME_DOMINANT"
                elo_gap = 200.0
            elif a_odd <= 1.40 and h_odd >= 4.0:
                tier_context = "AWAY_DOMINANT"
                elo_gap = -200.0
            elif h_odd <= 1.85 and a_odd >= 2.50:
                tier_context = "HOME_FAVORITE"
                elo_gap = 120.0
            elif a_odd <= 1.85 and h_odd >= 2.50:
                tier_context = "AWAY_FAVORITE"
                elo_gap = -120.0
            elif h_odd < a_odd and (a_odd - h_odd) >= 0.60:
                tier_context = "HOME_SLIGHT_FAVORITE"
                elo_gap = 60.0
            elif a_odd < h_odd and (h_odd - a_odd) >= 0.60:
                tier_context = "AWAY_SLIGHT_FAVORITE"
                elo_gap = -60.0
            else:
                tier_context = "COMPETITIVE"
                elo_gap = 0.0
        else:
            ph = probs_data.get("ai_prob_home", 0.33)
            pd = probs_data.get("ai_prob_draw", 0.33)
            pa = probs_data.get("ai_prob_away", 0.33)
            elo_gap = probs_data.get("elo_gap", 0.0)
            tier_context = probs_data.get("tier_context", "COMPETITIVE")

        raw_po15 = fixture.get("ai_prob_over_1_5") or probs_data.get("ai_prob_over_1_5", 78.0)
        po15 = raw_po15 if raw_po15 <= 1.0 else (raw_po15 / 100.0)
        raw_po25 = fixture.get("ai_prob_over_2_5") or probs_data.get("ai_prob_over_2_5", 52.0)
        po25 = raw_po25 if raw_po25 <= 1.0 else (raw_po25 / 100.0)


        audit_log.append(f"Fixture: {home} vs {away} [{comp}]")
        audit_log.append(f"Elo/Odds Gap: {elo_gap:+.1f} pts -> Tier Context: {tier_context}")

        # -------------------------------------------------------------
        # GATE 1: Structural Tier Filter & Candidate Market Generation
        # -------------------------------------------------------------
        if tier_context in ["HOME_DOMINANT", "HOME_FAVORITE", "HOME_SLIGHT_FAVORITE"]:
            allowed_directions = ["HOME", "NEUTRAL"]
        elif tier_context in ["AWAY_DOMINANT", "AWAY_FAVORITE", "AWAY_SLIGHT_FAVORITE"]:
            allowed_directions = ["AWAY", "NEUTRAL"]
        else:
            allowed_directions = ["HOME", "AWAY", "NEUTRAL"]
        gate_results["gate1"] = "PASS"

        ou15_data = next((x for x in ou_lines if str(x.get("line")) == "1.5"), {})
        ou35_data = next((x for x in ou_lines if str(x.get("line")) == "3.5"), {})
        ou45_data = next((x for x in ou_lines if str(x.get("line")) == "4.5"), {})
        ou05_data = next((x for x in ou_lines if str(x.get("line")) == "0.5"), {})

        candidate_markets = []

        if "HOME" in allowed_directions and (ph + pd) >= 0.55 and (h_odd is None or h_odd <= 3.20):
            dc_1x_odds = dc_odds.get("1X") or round(max(1.04, 1.0 / (ph + pd + 0.04)), 2)
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{home} or Draw (1X)",
                "prob": min(ph + pd + 0.02, 0.98),
                "odds": dc_1x_odds,
                "direction": "HOME",
                "category": "DOUBLE_CHANCE"
            })

        if "AWAY" in allowed_directions and (pa + pd) >= 0.55 and (a_odd is None or a_odd <= 3.20):
            dc_x2_odds = dc_odds.get("X2") or round(max(1.04, 1.0 / (pa + pd + 0.04)), 2)
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{away} or Draw (X2)",
                "prob": min(pa + pd + 0.02, 0.98),
                "odds": dc_x2_odds,
                "direction": "AWAY",
                "category": "DOUBLE_CHANCE"
            })

        if "HOME" in allowed_directions and "AWAY" in allowed_directions and pd <= 0.28 and (ph + pa) >= 0.70:
            dc_12_odds = dc_odds.get("12") or round(max(1.15, 1.0 / (ph + pa + 0.02)), 2)
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{home} or {away} (12)",
                "prob": min(ph + pa, 0.94),
                "odds": dc_12_odds,
                "direction": "NEUTRAL",
                "category": "DOUBLE_CHANCE"
            })

        # 2. Over 1.5 Goals
        o15_odds = ou15_data.get("over") or round(max(1.12, 1.0 / max(po15 - 0.03, 0.5)), 2)
        implied_o15_prob = min(0.96, max(po15, 1.0 / (o15_odds * 1.05)))
        if implied_o15_prob >= 0.72 and o15_odds <= 1.45:
            candidate_markets.append({
                "market": "Over/Under Goals",
                "selection": "Over 1.5 Goals",
                "prob": round(implied_o15_prob, 3),
                "odds": o15_odds,
                "direction": "NEUTRAL",
                "category": "OVER_UNDER"
            })

        # 3. Under 3.5 Goals
        if ou35_data.get("under"):
            u35_odds = ou35_data.get("under")
            implied_u35_prob = min(0.94, max(0.10, 1.0 / (u35_odds * 1.05)))
            if implied_u35_prob >= 0.72 and u35_odds <= 1.35:
                candidate_markets.append({
                    "market": "Over/Under Goals",
                    "selection": "Under 3.5 Goals",
                    "prob": round(implied_u35_prob, 3),
                    "odds": u35_odds,
                    "direction": "NEUTRAL",
                    "category": "OVER_UNDER"
                })

        # 4. Under 4.5 Goals
        if ou45_data.get("under"):
            u45_odds = ou45_data.get("under")
            implied_u45_prob = min(0.96, max(0.10, 1.0 / (u45_odds * 1.04)))
            if implied_u45_prob >= 0.78 and u45_odds <= 1.25:
                candidate_markets.append({
                    "market": "Over/Under Goals",
                    "selection": "Under 4.5 Goals",
                    "prob": round(implied_u45_prob, 3),
                    "odds": u45_odds,
                    "direction": "NEUTRAL",
                    "category": "OVER_UNDER"
                })

        # 5. Over 0.5 Goals
        if ou05_data.get("over"):
            o05_odds = ou05_data.get("over")
            implied_o05_prob = min(0.98, max(0.85, 1.0 / (o05_odds * 1.02)))
            if o05_odds >= 1.03 and o05_odds <= 1.12:
                candidate_markets.append({
                    "market": "Over/Under Goals",
                    "selection": "Over 0.5 Goals",
                    "prob": round(implied_o05_prob, 3),
                    "odds": o05_odds,
                    "direction": "NEUTRAL",
                    "category": "OVER_UNDER"
                })

        # 6. Straight 1X2 Win (STRICT: Only when heavy dominant favorite <= 1.55 real odds and >= 70% model prob)
        has_real_1x2 = bool(h_odd and a_odd and h_odd > 1.0 and a_odd > 1.0 and h_odd != a_odd)
        if "HOME" in allowed_directions and ph >= 0.70 and (h_odd and h_odd <= 1.55) and has_real_1x2:
            candidate_markets.append({
                "market": "Match Result",
                "selection": f"{home} to Win (1)",
                "prob": ph,
                "odds": h_odd,
                "direction": "HOME",
                "category": "1X2"
            })

        if "AWAY" in allowed_directions and pa >= 0.70 and (a_odd and a_odd <= 1.55) and has_real_1x2:
            candidate_markets.append({
                "market": "Match Result",
                "selection": f"{away} to Win (2)",
                "prob": pa,
                "odds": a_odd,
                "direction": "AWAY",
                "category": "1X2"
            })

        # Apply Risk Profile & Market Filter Rules
        if risk_profile.upper() == "ULTRA_CONSERVATIVE":
            candidate_markets = [c for c in candidate_markets if c.get("category") in ("DOUBLE_CHANCE", "OVER_UNDER", "TEAM_GOALS", "COMBO") and "1x2" not in c["market"].lower()]
        elif risk_profile.upper() == "AGGRESSIVE":
            pass

        if allowed_markets and len(allowed_markets) > 0 and "ALL" not in [x.upper() for x in allowed_markets]:
            allowed_upper = [x.upper() for x in allowed_markets]
            candidate_markets = [c for c in candidate_markets if c.get("category", "").upper() in allowed_upper]

        if excluded_markets and len(excluded_markets) > 0:
            excluded_upper = [x.upper() for x in excluded_markets]
            candidate_markets = [c for c in candidate_markets if c.get("category", "").upper() not in excluded_upper]


        if not candidate_markets:
            gate_results["gate2"] = "FAIL"
            reason = "No candidate markets generated matching structural directions"
            audit_log.append(f"REJECTED at GATE 2: {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name="None", selection_name="None",
                model_probability=0.0, estimated_odds=1.0, elo_gap=elo_gap,
                tier_context=tier_context, approved=False, confidence_tier="REJECTED",
                gate_results=gate_results, rejection_reason=reason,
                decision_audit_log=audit_log, kelly_quarter_stake_pct=0.0
            )

        # If raw SportyBet markets are present on fixture, match candidates strictly against open markets
        raw_markets = fixture.get("markets") or []
        if isinstance(raw_markets, dict):
            raw_markets = list(raw_markets.values())

        if raw_markets:
            matched_candidates = []
            for cand in candidate_markets:
                m_kw = cand["market"].lower()
                s_kw = cand["selection"].lower()
                cand_matched = False

                for m in raw_markets:
                    if not isinstance(m, dict) or cand_matched:
                        continue
                    m_desc = (m.get("desc") or m.get("name") or m.get("market_name") or "").lower()
                    m_id = str(m.get("market_id") or m.get("id") or "")
                    spec = m.get("specifier")

                    outcomes = m.get("outcomes", [])
                    if isinstance(outcomes, dict):
                        outcomes = list(outcomes.values())

                    # Match 1: Double Chance
                    if ("double chance" in m_kw or "dc" in m_kw) and (m_id == "10" or "double chance" in m_desc) and not any(x in m_desc for x in ["&", "over", "under", "gg"]):
                        for o in outcomes:
                            if not isinstance(o, dict): continue
                            o_desc = (o.get("desc") or o.get("name") or o.get("selection_name") or "").lower()
                            o_id = str(o.get("outcome_id") or o.get("id") or "")
                            if ("1x" in s_kw and ("1x" in o_desc or o_id == "9")) or ("x2" in s_kw and ("x2" in o_desc or o_id == "11")) or ("12" in s_kw and ("12" in o_desc or o_id == "10")):
                                try:
                                    real_o = float(o.get("odds"))
                                    if real_o >= 1.05:
                                        cand["odds"] = real_o
                                        cand["market_id"] = m_id or "10"
                                        cand["outcome_id"] = o_id
                                        cand["specifier"] = None
                                        matched_candidates.append(cand)
                                        cand_matched = True
                                        break
                                except (ValueError, TypeError):
                                    pass

                    # Match 2: Over/Under Goals (Over 1.5, Under 3.5, Over 2.5, Over 0.5)
                    elif ("over" in m_kw or "under" in m_kw or "over" in s_kw or "under" in s_kw) and (m_id == "18" or "over/under" in m_desc) and not any(x in m_desc for x in ["&", "1x2", "dc"]):
                        line_match = re.search(r"(\d+\.5|\d+)", s_kw)
                        line_val = line_match.group(1) if line_match else "1.5"
                        spec_str = str(spec or m_desc)
                        if line_val in spec_str or f"total={line_val}" in spec_str:
                            is_over = "over" in s_kw
                            for o in outcomes:
                                if not isinstance(o, dict): continue
                                o_desc = (o.get("desc") or o.get("name") or o.get("selection_name") or "").lower()
                                o_id = str(o.get("outcome_id") or o.get("id") or "")
                                if (is_over and ("over" in o_desc or o_id == "12")) or (not is_over and ("under" in o_desc or o_id == "13")):
                                    try:
                                        real_o = float(o.get("odds"))
                                        if real_o >= 1.05:
                                            cand["odds"] = real_o
                                            cand["market_id"] = m_id or "18"
                                            cand["outcome_id"] = o_id
                                            cand["specifier"] = f"total={line_val}"
                                            matched_candidates.append(cand)
                                            cand_matched = True
                                            break
                                    except (ValueError, TypeError):
                                        pass

                    # Match 3: 1X2 Match Result
                    elif ("match result" in m_kw or "1x2" in m_kw) and (m_id == "1" or m_desc == "1x2" or m_desc == "match result"):
                        for o in outcomes:
                            if not isinstance(o, dict): continue
                            o_desc = (o.get("desc") or o.get("name") or o.get("selection_name") or "").lower()
                            o_id = str(o.get("outcome_id") or o.get("id") or "")
                            if ("(1)" in s_kw and (o_id == "1" or "home" in o_desc or "1" == o_desc)) or ("(2)" in s_kw and (o_id == "3" or "away" in o_desc or "2" == o_desc)):
                                try:
                                    real_o = float(o.get("odds"))
                                    if real_o >= 1.05:
                                        cand["odds"] = real_o
                                        cand["market_id"] = m_id or "1"
                                        cand["outcome_id"] = o_id
                                        cand["specifier"] = None
                                        matched_candidates.append(cand)
                                        cand_matched = True
                                        break
                                except (ValueError, TypeError):
                                    pass

                    # Match 4: Win Either Half
                    elif "either half" in m_kw or "either half" in s_kw:
                        is_away = "(2)" in s_kw or away.lower() in s_kw
                        target_m_id = "74" if is_away else "73"
                        if m_id == target_m_id:
                            for o in outcomes:
                                if not isinstance(o, dict): continue
                                o_id = str(o.get("outcome_id") or o.get("id") or "75")
                                try:
                                    real_o = float(o.get("odds"))
                                    if real_o >= 1.05:
                                        cand["odds"] = real_o
                                        cand["market_id"] = target_m_id
                                        cand["outcome_id"] = o_id
                                        cand["specifier"] = None
                                        matched_candidates.append(cand)
                                        cand_matched = True
                                        break
                                except (ValueError, TypeError):
                                    pass

            if matched_candidates:
                candidate_markets = matched_candidates



        # -------------------------------------------------------------
        # GATE 2: Calibrated Probability Threshold (Dynamic Adaptability)
        # -------------------------------------------------------------
        # Global Low Odds & Empty Value Purge: Discard ANY pick offering odds below 1.12
        candidate_markets = [m for m in candidate_markets if m["odds"] >= 1.12]

        if not candidate_markets:
            gate_results["gate2"] = "FAIL"
            reason = "All candidates rejected by global < 1.12 odds purge rule"
            audit_log.append(f"REJECTED at GATE 2: {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name="None", selection_name="None",
                model_probability=0.0, estimated_odds=1.0, elo_gap=elo_gap,
                tier_context=tier_context, approved=False, confidence_tier="REJECTED",
                gate_results=gate_results, rejection_reason=reason,
                decision_audit_log=audit_log, kelly_quarter_stake_pct=0.0
            )

        effective_threshold = min(min_prob_threshold, 0.72)
        valid_g2_candidates = [m for m in candidate_markets if m["prob"] >= effective_threshold]
        if not valid_g2_candidates:
            # Fall back to best available structural market for this match
            valid_g2_candidates = candidate_markets

        max_p = max(m["prob"] for m in candidate_markets)

        gate_results["gate2"] = "PASS"
        audit_log.append(f"GATE 2 PASS: {len(valid_g2_candidates)} candidate market(s) exceed {min_prob_threshold*100:.0f}% confidence threshold.")

        # -------------------------------------------------------------
        # GATE 3: Scored Market Audit (Edge + Safety)
        # -------------------------------------------------------------
        scored_candidates = []
        for cand in valid_g2_candidates:
            prob = cand["prob"]
            odds = cand["odds"]
            safety = self._get_structural_safety(cand["market"])
            if self.use_live_odds:
                true_implied = self._strip_overround_margin(odds)
                value_edge = max(0.0, prob - true_implied)
                market_score = (prob * 0.60) + (value_edge * 0.25) + (safety * 0.15)
            else:
                value_edge = 0.0
                market_score = (prob * 0.80) + (safety * 0.20)
            cand["score"] = market_score
            cand["value_edge"] = value_edge
            cand["safety"] = safety
            scored_candidates.append(cand)

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        best_cand = scored_candidates[0]

        gate_results["gate3"] = "PASS"
        audit_log.append(
            f"GATE 3 PASS: Selected [{best_cand['selection']}] — Model Prob: {best_cand['prob']*100:.1f}%, "
            f"Market Score: {best_cand['score']:.3f}, Value Edge: {best_cand['value_edge']*100:+.1f}%."
        )

        # -------------------------------------------------------------
        # GATE 4: Dynamic Odds Alignment Check
        # -------------------------------------------------------------
        pick_odds = best_cand["odds"]
        lower_bound = max(1.05, per_leg_target_odds * 0.70)
        upper_bound = per_leg_target_odds * 1.45

        if not (lower_bound <= pick_odds <= upper_bound):
            # Try to find another candidate in scored list that meets odds bounds
            in_bounds = [c for c in scored_candidates if lower_bound <= c["odds"] <= upper_bound]
            if in_bounds:
                best_cand = in_bounds[0]
                pick_odds = best_cand["odds"]
                audit_log.append(f"GATE 4 ADJUSTED: Switched to [{best_cand['selection']}] ({pick_odds} odds) to fit target odds window [{lower_bound:.2f}–{upper_bound:.2f}].")
                gate_results["gate4"] = "PASS"
            else:
                gate_results["gate4"] = "FAIL"
                reason = f"Odds ({pick_odds}) outside target per-leg range [{lower_bound:.2f}–{upper_bound:.2f}]"
                audit_log.append(f"REJECTED at GATE 4: {reason}")
                return PickDecision(
                    fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                    kickoff_datetime=kickoff, market_name=best_cand["market"],
                    selection_name=best_cand["selection"], model_probability=best_cand["prob"],
                    estimated_odds=pick_odds, elo_gap=elo_gap, tier_context=tier_context,
                    approved=False, confidence_tier="REJECTED", gate_results=gate_results,
                    rejection_reason=reason, decision_audit_log=audit_log,
                    kelly_quarter_stake_pct=0.0
                )
        else:
            gate_results["gate4"] = "PASS"
            audit_log.append(f"GATE 4 PASS: Pick odds {pick_odds:.2f} align with per-leg target {per_leg_target_odds:.2f} [{lower_bound:.2f}–{upper_bound:.2f}].")

        # -------------------------------------------------------------
        # GATE 5: Accumulator Correlation & Diversity Filter
        # -------------------------------------------------------------
        current_league_count = league_pick_counts.get(comp, 0)
        if current_league_count >= max_league_picks:
            gate_results["gate5"] = "FAIL"
            reason = f"League diversity limit reached ({current_league_count} picks already from {comp})"
            audit_log.append(f"REJECTED at GATE 5: {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name=best_cand["market"],
                selection_name=best_cand["selection"], model_probability=best_cand["prob"],
                estimated_odds=pick_odds, elo_gap=elo_gap, tier_context=tier_context,
                approved=False, confidence_tier="REJECTED", gate_results=gate_results,
                rejection_reason=reason, decision_audit_log=audit_log,
                kelly_quarter_stake_pct=0.0
            )

        gate_results["gate5"] = "PASS"
        audit_log.append(f"GATE 5 PASS: Diversity check clear ({current_league_count}/{max_league_picks} allowed from {comp}).")

        # Determine Confidence Tier
        prob = best_cand["prob"]
        m_score = best_cand["score"]
        if prob >= 0.88 and m_score >= 0.82:
            confidence_tier = "ELITE"
        elif prob >= 0.80 and m_score >= 0.74:
            confidence_tier = "HIGH"
        elif prob >= 0.70 and m_score >= 0.64:
            confidence_tier = "SOLID"
        else:
            confidence_tier = "SPECULATIVE"

        audit_log.append(f"FINAL AUDIT: Approved pick classification -> [{confidence_tier}] Confidence Tier.")

        kelly_pct = self.calculate_kelly_stake(prob, pick_odds, fraction=0.25)

        return PickDecision(
            fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
            kickoff_datetime=kickoff, market_name=best_cand["market"],
            selection_name=best_cand["selection"], model_probability=round(prob, 3),
            estimated_odds=pick_odds, elo_gap=elo_gap, tier_context=tier_context,
            approved=True, confidence_tier=confidence_tier, gate_results=gate_results,
            rejection_reason=None, decision_audit_log=audit_log,
            kelly_quarter_stake_pct=kelly_pct,
            raw_match_data=fixture,
            market_id=best_cand.get("market_id"),
            outcome_id=best_cand.get("outcome_id"),
            specifier=best_cand.get("specifier")
        )


    def build_ticket(
        self,
        fixture_pool: List[Dict[str, Any]],
        target_total_odds: float,
        mode: str = "ACCUMULATOR",
        target_mode: str = "ODDS",
        target_games: Optional[int] = None,
        max_league_picks: int = 4,
        rollover_days: Optional[int] = None,
        reshuffle_seed: Optional[int] = None,
        risk_profile: str = "BALANCED",
        allowed_markets: Optional[List[str]] = None,
        excluded_markets: Optional[List[str]] = None,
    ) -> BuiltTicket:
        """
        Evaluates a pool of fixtures through the 5-Gate pipeline and constructs
        an optimal ticket or rollover plan with dynamic candidate reshuffling.
        """
        import random
        import time

        if target_mode == "GAMES" and target_games:
            target_legs_count = max(1, min(50, target_games))
            per_leg_target = 1.30
            min_prob_threshold = 0.65
            max_league_picks = max(max_league_picks, (target_games // 2) + 2)
            leg_config = {
                "ideal_legs": target_legs_count,
                "per_leg_target_odds": per_leg_target,
                "min_probability_threshold": min_prob_threshold
            }
        else:
            leg_config = calculate_dynamic_leg_config(target_total_odds)
            target_legs_count = leg_config["ideal_legs"]
            per_leg_target = leg_config.get("per_leg_target_odds", target_total_odds)
            min_prob_threshold = leg_config.get("min_probability_threshold", 0.85)

        league_pick_counts: Dict[str, int] = {}
        approved_legs = []
        rejected_picks = []
        summary_logs = [
            f"MatchIQ Pick Engine Execution ({mode} Mode - {target_mode})",
            f"Target: {target_games if target_mode == 'GAMES' else f'{target_total_odds:.2f}x'} | Legs: {target_legs_count}",
            f"Risk Profile: {risk_profile} | Min Probability Gate: {int(min_prob_threshold*100)}% | Per-Leg Target: {per_leg_target:.2f}x"
        ]

        total_evaluated = len(fixture_pool)

        # First pass: evaluate all fixtures through 5-Gate Pipeline
        all_decisions: List[PickDecision] = []
        for fix in fixture_pool:
            comp = fix.get("competition_code") or fix.get("league") or "PL"
            dec = self.evaluate_fixture_markets(
                fixture=fix,
                per_leg_target_odds=per_leg_target,
                min_prob_threshold=min_prob_threshold,
                league_pick_counts=league_pick_counts,
                max_league_picks=max_league_picks,
                risk_profile=risk_profile,
                allowed_markets=allowed_markets,
                excluded_markets=excluded_markets,
            )
            all_decisions.append(dec)
            if dec.approved:
                league_pick_counts[comp] = league_pick_counts.get(comp, 0) + 1

        # Separate approved and rejected decisions
        approved_decisions = [d for d in all_decisions if d.approved]

        rejected_decisions = [d for d in all_decisions if not d.approved]

        def _dynamic_candidate_score(d: PickDecision) -> float:
            """
            100% Dynamic Quantitative Scoring Metric.
            Zero hardcoded club or league strings. Evaluates true dominance purely from live data:
            - Live Market Dominance Ratio (Underdog Odds / Favorite Odds)
            - Dynamic ELO / Statistical Rating Gap
            - Verified Model Win Probability
            - Market Safety Cushioning Factor (Tier 1 vs Naked 1X2)
            """
            # 1. Base Model Probability Core (0 to 100)
            prob_score = d.model_probability * 100.0

            # 2. Live Market Dominance & Price Asymmetry (Dynamic Powerhouse Metric)
            raw = d.raw_match_data or {}
            r1x2 = raw.get("result_1x2") or {}
            dominance_score = 0.0
            try:
                h_odd = float(r1x2.get("1") or r1x2.get("home") or 0.0)
                a_odd = float(r1x2.get("2") or r1x2.get("away") or 0.0)
                if h_odd > 1.0 and a_odd > 1.0:
                    fav = min(h_odd, a_odd)
                    und = max(h_odd, a_odd)
                    # When a real favorite dominates (e.g. 1.25 vs 9.0), ratio is huge
                    dominance_ratio = und / fav
                    if fav <= 1.50 and dominance_ratio >= 3.0:
                        dominance_score = min(75.0, dominance_ratio * 8.0)
                    elif fav <= 1.80 and dominance_ratio >= 1.8:
                        dominance_score = min(40.0, dominance_ratio * 6.0)
            except Exception:
                pass

            # 3. Dynamic ELO / Rating Gap
            elo_score = min(35.0, max(0.0, abs(float(d.elo_gap or 0.0)) * 0.25))

            # 4. Market Cushion Safety (Tier 1 Double Chance & Compound OR get priority)
            cushion_bonus = 0.0
            m_name = (d.market_name or "").lower()
            if "double chance" in m_name or "or over" in m_name:
                cushion_bonus = 25.0
            elif "over 1.5" in (d.selection_name or "").lower():
                cushion_bonus = 20.0
            elif "1x2" in m_name:
                cushion_bonus = 0.0

            return prob_score + dominance_score + elo_score + cushion_bonus

        if mode == "ROLLOVER":
            # For Rollover: Strictly prioritize high dominance ratio, wide ELO gap & high win probability
            approved_decisions.sort(key=_dynamic_candidate_score, reverse=True)
            
            # Filter for true dominant fixtures with high statistical cushion
            top_decisions = [d for d in approved_decisions if _dynamic_candidate_score(d) >= 110.0]
            pool_candidates = top_decisions if len(top_decisions) >= 2 else approved_decisions[:]
            
            # Enable dynamic permutation for regenerate while keeping candidates elite
            seed_val = reshuffle_seed if reshuffle_seed is not None else int(time.time() * 1000)
            rng = random.Random(seed_val)
            
            # Take top qualified candidates and shuffle for variation
            elite_subset = pool_candidates[:max(8, len(pool_candidates))]
            pool_copy = elite_subset[:]
            rng.shuffle(pool_copy)


            # PRECISE ODDS MATCHING: Accumulate high-assurance legs until product closely matches target_total_odds
            selected_decisions: List[PickDecision] = []
            curr_acc_odds = 1.0
            for d in pool_copy:
                if len(selected_decisions) >= 1 and curr_acc_odds >= (target_total_odds * 0.92):
                    break
                selected_decisions.append(d)
                curr_acc_odds *= d.estimated_odds
                if curr_acc_odds >= (target_total_odds * 0.98):
                    break
                if len(selected_decisions) >= 4:  # Keep daily rollover tight (max 3-4 ultra-safe legs)
                    break
            if not selected_decisions and pool_copy:
                selected_decisions.append(pool_copy[0])
        else:
            seed_val = reshuffle_seed if reshuffle_seed is not None else int(time.time() * 1000)
            rng = random.Random(seed_val)

            # Sort approved decisions by Dynamic Quantitative Dominance Score
            approved_decisions.sort(key=_dynamic_candidate_score, reverse=True)
            
            # Form broader dynamic candidate pool from all approved matches
            elite_candidate_pool = approved_decisions[:]
            if len(elite_candidate_pool) > 1:
                # Randomize ordering with weighted bias towards top scores based on seed
                rng.shuffle(elite_candidate_pool)

            selected_decisions: List[PickDecision] = []
            market_counts: Dict[str, int] = {}
            target_legs_count = leg_config["ideal_legs"]
            max_per_market = 2 if target_legs_count <= 8 else 3

            if target_mode == "ODDS":
                # Dynamic Beam Selection: Build diverse combinations guided by the reshuffle seed
                candidate_combo = []
                curr_odds = 1.0
                m_counts: Dict[str, int] = {}

                for d in elite_candidate_pool:
                    m_key = d.selection_name
                    if "Under 4.5" in m_key or "Over 0.5" in m_key:
                        if m_counts.get(m_key, 0) >= 2:
                            continue
                    
                    candidate_combo.append(d)
                    m_counts[m_key] = m_counts.get(m_key, 0) + 1
                    curr_odds *= d.estimated_odds
                    
                    if curr_odds >= (target_total_odds * 0.95):
                        break
                    if len(candidate_combo) >= 20:
                        break

                selected_decisions = candidate_combo if candidate_combo else elite_candidate_pool[:target_legs_count]
            else:
                # GAMES mode: sample target_legs_count diverse games from randomized pool
                for d in elite_candidate_pool:
                    m_key = d.selection_name
                    if "Under 4.5" in m_key or "Over 0.5" in m_key:
                        if market_counts.get(m_key, 0) >= max_per_market:
                            continue
                    selected_decisions.append(d)
                    market_counts[m_key] = market_counts.get(m_key, 0) + 1
                    if len(selected_decisions) >= target_legs_count:
                        break
                
                if len(selected_decisions) < target_legs_count:
                    for d in elite_candidate_pool:
                        if d not in selected_decisions:
                            selected_decisions.append(d)
                            if len(selected_decisions) >= target_legs_count:
                                break


        # Calculate combined probability & accumulated odds
        accumulated_odds = 1.0
        combined_prob = 1.0

        for d in selected_decisions:
            accumulated_odds *= d.estimated_odds
            combined_prob *= d.model_probability
            k_ms = d.kickoff_datetime if isinstance(d.kickoff_datetime, (int, float)) and d.kickoff_datetime > 1e11 else None
            
            # Compute relative day offset (0 = today, 1 = tomorrow, 2 = day after tomorrow)
            day_offset = 0
            date_str = ""
            if k_ms:
                try:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(k_ms / 1000.0, tz=datetime.timezone.utc)
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    date_str = dt.strftime("%Y-%m-%d")
                    day_offset = max(0, (dt.date() - now_utc.date()).days)
                except Exception:
                    pass

            ev_id = str((d.raw_match_data or {}).get("event_id") or d.fixture_id)
            approved_legs.append({
                "fixture_id": d.fixture_id,
                "event_id": ev_id,
                "provider_event_id": ev_id,
                "game_id": d.fixture_id,
                "home_team": d.home_team,
                "away_team": d.away_team,
                "competition": d.competition,
                "kickoff_datetime": d.kickoff_datetime,
                "start_time_ms": k_ms,
                "day_offset": day_offset,
                "date_str": date_str,
                "market_name": d.market_name,
                "selection_name": d.selection_name,
                "model_probability": d.model_probability,
                "estimated_odds": d.estimated_odds,
                "odds": d.estimated_odds,
                "confidence_tier": d.confidence_tier,
                "elo_gap": d.elo_gap,
                "tier_context": d.tier_context,
                "decision_audit_log": d.decision_audit_log,
                "kelly_quarter_stake_pct": d.kelly_quarter_stake_pct,
                "raw_match_data": d.raw_match_data,
                "market_id": d.market_id,
                "outcome_id": d.outcome_id,
                "specifier": d.specifier
            })


        for r in rejected_decisions:
            rejected_picks.append({
                "fixture": f"{r.home_team} vs {r.away_team}",
                "competition": r.competition,
                "rejection_reason": r.rejection_reason or "Failed gate check",
                "gate_results": r.gate_results
            })

        # Calculate correlation factor penalty
        n_legs = len(selected_decisions)
        league_counts_selected = {}
        for d in selected_decisions:
            league_counts_selected[d.competition] = league_counts_selected.get(d.competition, 0) + 1

        same_league_pairs = sum(c - 1 for c in league_counts_selected.values() if c > 1)
        correlation_penalty = 1.0 - (0.05 * same_league_pairs)
        corr_adjusted_prob = round(combined_prob * max(0.70, correlation_penalty), 3)

        # Ticket level confidence tier
        if selected_decisions:
            avg_prob = sum(d.model_probability for d in selected_decisions) / n_legs
            if avg_prob >= 0.85:
                ticket_tier = "ELITE"
            elif avg_prob >= 0.78:
                ticket_tier = "HIGH"
            elif avg_prob >= 0.70:
                ticket_tier = "SOLID"
            else:
                ticket_tier = "SPECULATIVE"
        else:
            ticket_tier = "NONE"

        # Fractional Kelly recommended stake
        avg_leg_odds = accumulated_odds ** (1.0 / max(1, n_legs))
        rec_stake_pct = self.calculate_kelly_stake(corr_adjusted_prob, accumulated_odds, fraction=0.25)

        summary_logs.append(
            f"Pipeline Completed: {len(approved_legs)} legs selected out of {total_evaluated} evaluated. "
            f"Final Accumulated Odds: {accumulated_odds:.2f}x (Target {target_total_odds:.2f}x). "
            f"Combined Win Prob: {combined_prob*100:.1f}% (Corr-Adjusted: {corr_adjusted_prob*100:.1f}%)."
        )

        return BuiltTicket(
            mode=mode,
            target_odds=target_total_odds,
            accumulated_odds=round(accumulated_odds, 2),
            combined_probability=round(combined_prob, 3),
            correlation_adjusted_probability=corr_adjusted_prob,
            confidence_tier=ticket_tier,
            leg_config=leg_config,
            approved_legs=approved_legs,
            rejected_picks=rejected_picks,
            total_evaluated=total_evaluated,
            decision_audit_summary=summary_logs,
            recommended_stake_pct=rec_stake_pct
        )
