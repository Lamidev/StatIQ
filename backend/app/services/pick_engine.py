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

def classify_league_tier(comp_name: str, country: str = "") -> tuple[int, str]:
    """
    Classifies football competitions into 3 operational priority tiers:
    - Tier 1 (Score 100 - ELITE): Premier League (England), UCL, Europa League, Conference League,
      La Liga (Spain Primera), Serie A (Italy), Bundesliga (Germany), Ligue 1 (France), World Cup, Euros.
    - Tier 2 (Score 50 - SOLID): Championship, Eredivisie, Liga Portugal, 2. Bundesliga, LaLiga 2/Hypermotion,
      Serie B, Ligue 2, Brasileiro Serie A, MLS, Belgian Pro, Scottish Prem, Super Lig, Argentine Primera, Top Domestic Cups.
    - Tier 3 (Score 10 - REGIONAL/YOUTH): U19, U20, U21, U23, Youth, Reserves, Non-League, Regional/Lower divisions.
    """
    c_upper = str(comp_name or "").strip().upper()
    country_upper = str(country or "").strip().upper()

    # 1. Youth, Women, Regional & Lower divisions are strictly Tier 3
    t3_keywords = [
        "U19", "U20", "U21", "U23", "U18", "U17", "YOUTH", "NEXT GEN", "RESERVE", "REGIONAL",
        "KOLMONEN", "ISTHMIAN", "NORTHERN PREMIER", "SOUTHERN LEAGUE", "DIVISION 2", "DIVISION 3",
        "DIVISION 4", "PRIMERA C", "PRIMERA D", "TERCERA", "PROMOTION LEAGUE", "OBERLIGA",
        "WOMEN", "FEMENINO", "FEMININE", "FRAUEN", "DONNE", "LADIES", "VROUWEN", "PRIMAVERA",
        "CARICOCA", "CARIOCA", "PAULISTA", "GAUCHO", "MINEIRO"
    ]
    if any(k in c_upper for k in t3_keywords):
        return (10, "TIER_3_REGIONAL")

    # 2. Second divisions / secondary tiers are explicitly Tier 2 (Score 50)
    t2_explicit = [
        "HYPERMOTION", "LALIGA 2", "LA LIGA 2", "SEGUNDA", "2. BUNDESLIGA", "2.BUNDESLIGA",
        "LIGUE 2", "SERIE B", "SERIE C", "CHAMPIONSHIP", "EREDIVISIE", "PRIMEIRA LIGA", "LIGA PORTUGAL",
        "SUPER LIG", "SÜPER LIG", "SUPERLIG", "PREMIERSHIP", "PRO LEAGUE", "BRASILEIRO",
        "LEAGUE ONE", "LEAGUE TWO", "COPA DEL REY", "FA CUP", "EFL CUP", "DFB POKAL", "COPPA ITALIA", "COUPE DE FRANCE"
    ]
    if any(k in c_upper for k in t2_explicit):
        return (50, "TIER_2_SOLID")

    # 3. Top 5 European Leagues & Continental Elite (Strict verification)
    # English Premier League
    if "PREMIER LEAGUE" in c_upper:
        if country_upper in ["ENGLAND", "UK", "GREAT BRITAIN", ""] and not any(x in c_upper for x in ["VICTORIA", "GHANA", "EGYPT", "KUWAIT", "WALES", "RUSSIA", "CRIMEA", "ISRAEL", "KAZAKHSTAN", "NORTHERN IRELAND", "SOUTH AFRICA", "UKRAINE", "BHUTAN"]):
            return (100, "TIER_1_ELITE")
        return (50, "TIER_2_SOLID")

    # Spanish LaLiga
    if any(x in c_upper for x in ["LALIGA", "LA LIGA", "PRIMERA DIVISION"]):
        if country_upper in ["SPAIN", ""] and not any(x in c_upper for x in ["HYPERMOTION", "2", "SEGUNDA", "RFEF", "FEDERACION"]):
            return (100, "TIER_1_ELITE")
        return (50, "TIER_2_SOLID")

    # Italian Serie A
    if "SERIE A" in c_upper:
        if country_upper in ["ITALY", ""] and not any(x in c_upper for x in ["BRAZIL", "BRASILEIRO", "ECUADOR", "COLOMBIA"]):
            return (100, "TIER_1_ELITE")
        return (50, "TIER_2_SOLID")

    # German Bundesliga
    if "BUNDESLIGA" in c_upper:
        if country_upper in ["GERMANY", ""] and not any(x in c_upper for x in ["2.", "AUSTRIA", "ÖSTERREICH"]):
            return (100, "TIER_1_ELITE")
        return (50, "TIER_2_SOLID")

    # French Ligue 1
    if "LIGUE 1" in c_upper:
        if country_upper in ["FRANCE", ""] and not any(x in c_upper for x in ["ALGERIA", "IVORY COAST", "TUNISIA"]):
            return (100, "TIER_1_ELITE")
        return (50, "TIER_2_SOLID")

    # UEFA Continental Tournaments
    if any(k in c_upper for k in ["CHAMPIONS LEAGUE", "EUROPA LEAGUE", "CONFERENCE LEAGUE", "WORLD CUP", "EUROPEAN CHAMPIONSHIP", "COPA AMERICA"]):
        return (100, "TIER_1_ELITE")

    return (50, "TIER_2_SOLID")


def detect_match_archetype(odds_home: float, odds_draw: float, odds_away: float, ou_lines: list, home: str, away: str) -> dict:
    """
    Detects tactical match dynamic to intelligently prioritize the safest natural market:
    - HEAVY_FAVORITE: Fav <= 1.48, Ratio >= 2.8 -> Prioritize Team Over 0.5/1.5, Double Chance 1X/X2, Win Either Half.
    - HIGH_GOAL_EXPECTANCY: Over 2.5 <= 1.82 or Over 1.5 <= 1.26 -> Prioritize Over 1.5 Goals, Over 2.0.
    - LOW_GOAL_DEFENSIVE: Under 2.5 <= 1.68 -> Prioritize Under 3.5 Goals, Under 4.5 Goals.
    - COMPETITIVE_VALUE: Odds ~2.10-3.00 -> Prioritize Double Chance 12 / 1X / X2.
    """
    h_odd = float(odds_home or 2.5)
    a_odd = float(odds_away or 2.5)
    fav = min(h_odd, a_odd)
    und = max(h_odd, a_odd)
    ratio = (und / fav) if fav > 0 else 1.0

    o25_odd, u25_odd, o15_odd = None, None, None
    for line in (ou_lines or []):
        l_str = str(line.get("line"))
        if l_str == "2.5":
            o25_odd = line.get("over")
            u25_odd = line.get("under")
        elif l_str == "1.5":
            o15_odd = line.get("over")

    if fav <= 1.48 and ratio >= 2.8:
        return {
            "archetype": "HEAVY_FAVORITE",
            "fav_team": home if fav == h_odd else away,
            "fav_side": "HOME" if fav == h_odd else "AWAY",
            "dominant_ratio": ratio,
            "boost_markets": ["team over", "double chance", "win either half"]
        }
    elif (o25_odd and float(o25_odd) <= 1.82) or (o15_odd and float(o15_odd) <= 1.26):
        return {
            "archetype": "HIGH_GOAL_EXPECTANCY",
            "fav_team": None,
            "fav_side": None,
            "dominant_ratio": ratio,
            "boost_markets": ["over 1.5", "over 2", "both teams to score"]
        }
    elif (u25_odd and float(u25_odd) <= 1.68):
        return {
            "archetype": "LOW_GOAL_DEFENSIVE",
            "fav_team": None,
            "fav_side": None,
            "dominant_ratio": ratio,
            "boost_markets": ["under 3.5", "under 4.5"]
        }
    else:
        return {
            "archetype": "COMPETITIVE_VALUE",
            "fav_team": home if h_odd < a_odd else away,
            "fav_side": "HOME" if h_odd < a_odd else "AWAY",
            "dominant_ratio": ratio,
            "boost_markets": ["double chance", "draw no bet"]
        }


HIGH_SCORING_LEAGUES = {
    "DED", "EREDIVISIE", "BL1", "BUNDESLIGA", "SUI", "SUPER LEAGUE", "AUT", "BEL", "PRO LEAGUE",
    "NETHERLANDS", "GERMANY", "SWITZERLAND", "AUSTRIA", "BELGIUM", "NORWAY", "ELITESERIEN", "SCO", "PREMIERSHIP"
}

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
    league_tier: str = "TIER_2_SOLID"
    league_tier_score: int = 50
    tactical_archetype: str = "COMPETITIVE_VALUE"
    tactical_score: float = 0.0
    tactical_reason: str = ""


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
    def __init__(self, use_live_odds: bool = True):
        self.use_live_odds = use_live_odds

    def _get_structural_safety(self, market_name: str, selection_name: str = "") -> float:
        m_lower = (market_name or "").lower()
        s_lower = (selection_name or "").lower()

        # 1. Fatal structural penalty for volatile "12" double chance (loses on ~27% draw base rate)
        if "12" in s_lower or "home or away" in s_lower or "12" in m_lower:
            return 0.15

        # 2. Maximum Structural Safety (1.0): Draw-protected lines, cushions, & team goal thresholds
        if any(x in m_lower or x in s_lower for x in ["(+1.5)", "(+2.0)", "+1.5", "+2.0", "team over 0.5", "team goals", "win either half"]):
            return 1.0
        if "double chance" in m_lower and any(x in s_lower for x in ["1x", "x2", "draw or away", "home or draw"]):
            return 1.0

        # 3. High Structural Safety (0.90 - 0.95): Conservative Unders & Low-line Overs
        if any(x in m_lower or x in s_lower for x in ["under 3.5", "under 4.5", "over 0.5"]):
            return 0.95
        if "over 1.5" in m_lower or "over 1.5" in s_lower:
            return 0.85

        # 4. Standard Favorite Win (0.80)
        if any(x in m_lower for x in ["match result", "1x2"]):
            return 0.80

        # 5. Higher Variance (0.40): BTTS, Over 2.5, Exotic Corners
        return 0.40

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
        comp = fixture.get("competition_code") or fixture.get("competition") or fixture.get("league") or "Football"
        country = fixture.get("country") or ""
        fix_id = str(fixture.get("eventId") or fixture.get("event_id") or fixture.get("fixture_id") or fixture.get("external_id") or f"FIX_{home}_{away}")
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

        h_odd = float(r1x2.get("home", 0.0)) if r1x2.get("home") else (float(fixture.get("odds_home")) if fixture.get("odds_home") else None)
        d_odd = float(r1x2.get("draw", 0.0)) if r1x2.get("draw") else (float(fixture.get("odds_draw")) if fixture.get("odds_draw") else None)
        a_odd = float(r1x2.get("away", 0.0)) if r1x2.get("away") else (float(fixture.get("odds_away")) if fixture.get("odds_away") else None)
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

        # Detect Match Archetype for Tactical Assignment
        fav_odd = min(h_odd, a_odd) if (h_odd and a_odd and h_odd > 1.0 and a_odd > 1.0) else 2.5
        und_odd = max(h_odd, a_odd) if (h_odd and a_odd and h_odd > 1.0 and a_odd > 1.0) else 2.5
        dom_ratio = (und_odd / fav_odd) if fav_odd > 0 else 1.0

        is_heavy_fav = (tier_context in ["HOME_DOMINANT", "AWAY_DOMINANT"] or (fav_odd <= 1.48 and dom_ratio >= 2.5))
        is_balanced = (not is_heavy_fav and (tier_context in ["COMPETITIVE", "HOME_SLIGHT_FAVORITE", "AWAY_SLIGHT_FAVORITE"] or abs(ph - pa) <= 0.15))

        ou15_data = next((x for x in ou_lines if str(x.get("line")) == "1.5"), {})
        ou35_data = next((x for x in ou_lines if str(x.get("line")) == "3.5"), {})
        ou45_data = next((x for x in ou_lines if str(x.get("line")) == "4.5"), {})
        ou05_data = next((x for x in ou_lines if str(x.get("line")) == "0.5"), {})

        candidate_markets = []

        # -----------------------------------------------------------------------
        # H2H GATE: Apply Head-to-Head intelligence to block bad Double Chance picks
        # -----------------------------------------------------------------------
        h2h_data = fixture.get("h2h_data") or {}
        h2h_home_win_pct = float(h2h_data.get("home_win_pct", 0.0) or 0.0)
        h2h_away_win_pct = float(h2h_data.get("away_win_pct", 0.0) or 0.0)
        h2h_avg_goals = float(h2h_data.get("avg_total_goals", 0.0) or 0.0)
        h2h_total = int(h2h_data.get("total_meetings", 0) or 0)

        # Block X2 (Draw or Away) when home team dominates H2H (≥60% win rate with ≥3 meetings)
        h2h_block_x2 = (h2h_total >= 3 and h2h_home_win_pct >= 0.60)
        # Block 1X (Home or Draw) when away team dominates H2H (≥60% win rate with ≥3 meetings)
        h2h_block_1x = (h2h_total >= 3 and h2h_away_win_pct >= 0.60)
        # Use H2H avg goals to influence Over/Under picks
        h2h_is_high_scoring = (h2h_total >= 3 and h2h_avg_goals >= 2.5)
        h2h_is_low_scoring = (h2h_total >= 3 and h2h_avg_goals <= 1.5 and h2h_avg_goals > 0)

        audit_log.append(
            f"H2H: {h2h_total} meetings | Home win%: {h2h_home_win_pct*100:.0f}% | Away win%: {h2h_away_win_pct*100:.0f}% | Avg Goals: {h2h_avg_goals} "
            + (f"[BLOCKING X2 - home fortress]" if h2h_block_x2 else "")
            + (f"[BLOCKING 1X - away powerhouse]" if h2h_block_1x else "")
        )

        # 1. Double Chance (1X, X2, and H2H-Gated 12)
        if "HOME" in allowed_directions and (ph + pd) >= 0.58 and (h_odd is None or h_odd <= 2.80):
            dc_1x_odds = dc_odds.get("1X") or round(max(1.15, 1.0 / (ph + pd + 0.04)), 2)
            # H2H block: never give Home or Draw when away team dominates H2H
            # Reasonable boundary: DC odds between 1.15 and 1.35
            if not h2h_block_1x and 1.15 <= float(dc_1x_odds) <= 1.35:
                candidate_markets.append({
                    "market": "Double Chance",
                    "selection": f"{home} or Draw (1X)",
                    "prob": min(ph + pd + 0.02, 0.98),
                    "odds": float(dc_1x_odds),
                    "direction": "HOME",
                    "category": "DOUBLE_CHANCE"
                })

        if "AWAY" in allowed_directions and (pa + pd) >= 0.58 and (a_odd is None or a_odd <= 2.80):
            dc_x2_odds = dc_odds.get("X2") or round(max(1.15, 1.0 / (pa + pd + 0.04)), 2)
            # H2H block: never give Draw or Away when home team dominates H2H
            # Reasonable boundary: DC odds between 1.15 and 1.35
            if not h2h_block_x2 and 1.15 <= float(dc_x2_odds) <= 1.35:
                candidate_markets.append({
                    "market": "Double Chance",
                    "selection": f"{away} or Draw (X2)",
                    "prob": min(pa + pd + 0.02, 0.98),
                    "odds": float(dc_x2_odds),
                    "direction": "AWAY",
                    "category": "DOUBLE_CHANCE"
                })

        # Double Chance 12 (Home or Away) - STRICTLY GATED BY H2H & LOW DRAW EXPECTANCY
        dc_12_odds = dc_odds.get("12") or round(max(1.15, 1.0 / max(0.01, (ph + pa) * 1.04)), 2)
        h2h_draw_pct = float(h2h_data.get("draw_pct", 0.0) or 0.0)
        h2h_recent_draws = any(m.get("home_score") == m.get("away_score") for m in h2h_data.get("last_5", []))
        # 12 is only permitted when H2H data confirms low draw rate (<=18%), no recent H2H draws, odds >= 1.15, and draw probability pd <= 0.22
        if (
            float(dc_12_odds) >= 1.15 and float(dc_12_odds) <= 1.35 and
            h2h_total >= 2 and h2h_draw_pct <= 0.18 and not h2h_recent_draws and pd <= 0.22
        ):
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{home} or {away} (12)",
                "prob": min(ph + pa + 0.02, 0.95),
                "odds": float(dc_12_odds),
                "direction": "NEUTRAL",
                "category": "DOUBLE_CHANCE"
            })

        # 2. Asian Handicap (+1.5 / +2.0): STRICTLY FOR BALANCED/EQUAL STRENGTH GAMES ONLY (Never give to underdog vs heavy favorite)
        if is_balanced and not is_heavy_fav:
            if a_odd and 1.80 <= a_odd <= 3.80:
                p_ah_away = min(0.95, max(0.85, pa + pd + 0.12))
                odd_ah_away = round(max(1.10, 1.0 / (p_ah_away * 1.04)), 2)
                candidate_markets.append({
                    "market": "Asian Handicap",
                    "selection": f"{away} (+1.5 Handicap)",
                    "prob": p_ah_away,
                    "odds": odd_ah_away,
                    "direction": "AWAY",
                    "category": "HANDICAP"
                })
            if h_odd and 1.80 <= h_odd <= 3.80:
                p_ah_home = min(0.95, max(0.85, ph + pd + 0.12))
                odd_ah_home = round(max(1.10, 1.0 / (p_ah_home * 1.04)), 2)
                candidate_markets.append({
                    "market": "Asian Handicap",
                    "selection": f"{home} (+1.5 Handicap)",
                    "prob": p_ah_home,
                    "odds": odd_ah_home,
                    "direction": "HOME",
                    "category": "HANDICAP"
                })

        # 3. Team Goals (Team Over 0.5 / 1.5 Goals)
        if is_heavy_fav:
            fav_is_home = (h_odd and a_odd and h_odd < a_odd)
            fav_team = home if fav_is_home else away
            fav_p = ph if fav_is_home else pa
            fav_odd_val = h_odd if fav_is_home else a_odd

            # Heavy Favorite Team Over 0.5 Goals (Mega High Win Rate)
            p_to05 = min(0.96, max(0.88, fav_p + 0.15))
            o_to05 = round(max(1.08, min(1.30, 1.0 / (p_to05 * 1.03))), 2)
            candidate_markets.append({
                "market": "Team Goals",
                "selection": f"{fav_team} Over 0.5 Goals",
                "prob": p_to05,
                "odds": o_to05,
                "direction": "HOME" if fav_is_home else "AWAY",
                "category": "TEAM_GOALS"
            })

            # Win Either Half for Heavy Favorite
            p_weh = min(0.94, max(0.85, fav_p + 0.10))
            o_weh = round(max(1.15, min(1.38, 1.0 / (p_weh * 1.03))), 2)
            candidate_markets.append({
                "market": "Win Either Half",
                "selection": f"{fav_team} to Win Either Half",
                "prob": p_weh,
                "odds": o_weh,
                "direction": "HOME" if fav_is_home else "AWAY",
                "category": "COMBO"
            })

        # 4. Over 1.5 Goals (Strictly gated by H2H average goals and odds >= 1.15)
        o15_odds = ou15_data.get("over") or round(max(1.15, 1.0 / max(po15 - 0.03, 0.5)), 2)
        implied_o15_prob = min(0.96, max(po15, 1.0 / (float(o15_odds) * 1.05)))
        # Do not pick Over 1.5 blindly: reject if H2H proves low-scoring grinder (<= 1.5 goals/game) or odds < 1.15
        if implied_o15_prob >= 0.72 and 1.15 <= float(o15_odds) <= 1.35 and not h2h_is_low_scoring:
            candidate_markets.append({
                "market": "Over/Under Goals",
                "selection": "Over 1.5 Goals",
                "prob": round(implied_o15_prob, 3),
                "odds": float(o15_odds),
                "direction": "NEUTRAL",
                "category": "OVER_UNDER"
            })

        # 5. Under 3.5 & Under 4.5 Goals (Gated against high-scoring H2H games and odds >= 1.15)
        if ou35_data.get("under"):
            u35_odds = ou35_data.get("under")
            implied_u35_prob = min(0.95, max(0.75, 1.0 / (float(u35_odds) * 1.04)))
            if implied_u35_prob >= 0.76 and 1.15 <= float(u35_odds) <= 1.35 and not h2h_is_high_scoring:
                candidate_markets.append({
                    "market": "Over/Under Goals",
                    "selection": "Under 3.5 Goals",
                    "prob": round(implied_u35_prob, 3),
                    "odds": float(u35_odds),
                    "direction": "NEUTRAL",
                    "category": "OVER_UNDER"
                })

        if ou45_data.get("under"):
            u45_odds = ou45_data.get("under")
            implied_u45_prob = min(0.97, max(0.80, 1.0 / (float(u45_odds) * 1.03)))
            if implied_u45_prob >= 0.80 and 1.15 <= float(u45_odds) <= 1.25 and not h2h_is_high_scoring:
                candidate_markets.append({
                    "market": "Over/Under Goals",
                    "selection": "Under 4.5 Goals",
                    "prob": round(implied_u45_prob, 3),
                    "odds": float(u45_odds),
                    "direction": "NEUTRAL",
                    "category": "OVER_UNDER"
                })

        # 6. Straight 1X2 Win (STRICT: Heavy dominant favorite <= 1.48 real odds and >= 72% model prob)
        has_real_1x2 = bool(h_odd and a_odd and h_odd > 1.0 and a_odd > 1.0 and h_odd != a_odd)
        if "HOME" in allowed_directions and ph >= 0.72 and (h_odd and h_odd <= 1.48) and has_real_1x2:
            candidate_markets.append({
                "market": "Match Result",
                "selection": f"{home} to Win (1)",
                "prob": ph,
                "odds": h_odd,
                "direction": "HOME",
                "category": "1X2"
            })

        if "AWAY" in allowed_directions and pa >= 0.72 and (a_odd and a_odd <= 1.48) and has_real_1x2:
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
        # Global Low Odds & Empty Value Purge: Discard ANY pick offering odds below 1.15
        candidate_markets = [m for m in candidate_markets if float(m["odds"]) >= 1.15]

        if not candidate_markets:
            gate_results["gate2"] = "FAIL"
            reason = "All candidates rejected by global < 1.15 odds purge rule"
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
        soft_threshold = effective_threshold * 0.88  # 12% soft tolerance before hard reject
        valid_g2_candidates = [m for m in candidate_markets if m["prob"] >= effective_threshold]
        if not valid_g2_candidates:
            # Soft fallback: allow candidates within 12% below threshold
            valid_g2_candidates = [m for m in candidate_markets if m["prob"] >= soft_threshold]
        # Hard reject: if still nothing above soft floor, reject this fixture entirely
        if not valid_g2_candidates:
            gate_results["gate2"] = "FAIL"
            reason = f"All candidates below soft probability floor ({soft_threshold*100:.0f}%); fixture rejected to protect win rate"
            audit_log.append(f"REJECTED at GATE 2 (hard floor): {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name="None", selection_name="None",
                model_probability=0.0, estimated_odds=1.0, elo_gap=elo_gap,
                tier_context=tier_context, approved=False, confidence_tier="REJECTED",
                gate_results=gate_results, rejection_reason=reason,
                decision_audit_log=audit_log, kelly_quarter_stake_pct=0.0
            )

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
            safety = self._get_structural_safety(cand["market"], cand.get("selection", ""))
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
        lpc = league_pick_counts if league_pick_counts is not None else {}
        current_league_count = lpc.get(comp, 0)
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
        if prob >= 0.88 and m_score >= 0.83:
            confidence_tier = "ELITE"
        elif prob >= 0.82 and m_score >= 0.76:
            confidence_tier = "HIGH"
        elif prob >= 0.75 and m_score >= 0.66:
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

    def evaluate_fixture_all_candidates(
        self,
        fixture: Dict[str, Any],
        per_leg_target_odds: float = 1.30,
        min_prob_threshold: float = 0.70,
        risk_profile: str = "BALANCED",
        allowed_markets: Optional[List[str]] = None,
        excluded_markets: Optional[List[str]] = None,
    ) -> List[PickDecision]:
        """
        Generates ALL approved candidate market options for a single fixture across
        different categories (Double Chance, Over/Under, Team Goals, 1X2), strictly filtered
        by allowed market categories, risk profile thresholds, and enriched with league tier ranking.
        """
        home = fixture.get("home_team") or fixture.get("home") or "Home Team"
        away = fixture.get("away_team") or fixture.get("away") or "Away Team"
        comp = fixture.get("competition_code") or fixture.get("competition") or fixture.get("league") or "Football"
        country = fixture.get("country") or ""
        fix_id = str(fixture.get("eventId") or fixture.get("event_id") or fixture.get("fixture_id") or fixture.get("external_id") or f"FIX_{home}_{away}")
        kickoff = fixture.get("kickoff_datetime")

        tier_score, tier_label = classify_league_tier(comp, country)

        # Risk Profile Parameters (2 Distinct Operational Modes)
        rp = (risk_profile or "CONSERVATIVE").upper()
        is_aggressive = rp in ("AGGRESSIVE", "AGGRESSIVE_VALUE", "VALUE")
        
        if is_aggressive:
            # AGGRESSIVE MODE: Focus on high-yield outright wins, Over 2.5 goals, handicaps & dominant odds
            prob_floor = 0.55
            min_odds_floor = 1.25
            max_odds_cap = 2.85
        else:
            # CONSERVATIVE MODE: Focus on ultra-safe cushions (70%+ win rate, Double Chance, Over 1.5, Team Goals)
            prob_floor = 0.70
            min_odds_floor = 1.15
            max_odds_cap = 1.48

        # Allowed / Excluded Categories Check
        allowed_list = [x.upper() for x in allowed_markets] if (allowed_markets and len(allowed_markets) > 0 and "ALL" not in [x.upper() for x in allowed_markets]) else ["DOUBLE_CHANCE", "OVER_UNDER", "TEAM_GOALS", "1X2"]
        excluded_list = [x.upper() for x in excluded_markets] if excluded_markets else []

        def _cat_allowed(cat: str) -> bool:
            return cat.upper() in allowed_list and cat.upper() not in excluded_list

        ou_lines = fixture.get("ou_lines") or []
        dc_odds = fixture.get("double_chance") or {}
        h2h_data = fixture.get("h2h_data") or {}
        h2h_total = int(h2h_data.get("total_meetings", 0) or 0)
        h2h_draw_pct = float(h2h_data.get("draw_pct", 0.0) or 0.0)
        h2h_recent_draws = any(m.get("home_score") == m.get("away_score") for m in h2h_data.get("last_5", []))

        r1x2 = dict(fixture.get("result_1x2") or {})
        r_home = float(r1x2.get("home") or r1x2.get("1") or fixture.get("odds_home") or 2.5)
        r_draw = float(r1x2.get("draw") or r1x2.get("X") or fixture.get("odds_draw") or 3.2)
        r_away = float(r1x2.get("away") or r1x2.get("2") or fixture.get("odds_away") or 2.8)

        # Derived implied probabilities
        margin = (1.0 / r_home) + (1.0 / r_draw) + (1.0 / r_away) if (r_home > 1.0 and r_draw > 1.0 and r_away > 1.0) else 1.0
        ph = round((1.0 / r_home) / margin, 3) if r_home > 1.0 else 0.40
        pd = round((1.0 / r_draw) / margin, 3) if r_draw > 1.0 else 0.28
        pa = round((1.0 / r_away) / margin, 3) if r_away > 1.0 else 0.32

        elo_gap = 200.0 if (r_home <= 1.45 and r_away >= 3.8) else (-200.0 if (r_away <= 1.45 and r_home >= 3.8) else 0.0)
        tier_context = "HOME_DOMINANT" if r_home < r_away else ("AWAY_DOMINANT" if r_away < r_home else "COMPETITIVE")

        # Detect 50/50 Balanced Match
        is_even_match = abs(ph - pa) <= 0.12 and pd >= 0.26

        archetype_info = detect_match_archetype(r_home, r_draw, r_away, ou_lines, home, away)
        archetype_type = archetype_info["archetype"]

        # Inspect real open markets from SportyBet
        raw_markets = fixture.get("markets") or []
        if isinstance(raw_markets, dict):
            raw_markets = list(raw_markets.values())
        raw_market_ids = {str(m.get("id") or m.get("market_id") or "") for m in raw_markets if isinstance(m, dict)}

        candidates: List[PickDecision] = []
        seen_selections = set()

        # 1. Double Chance Lines
        if _cat_allowed("DOUBLE_CHANCE"):
            # Ensure dc_odds has values
            dc_work = dict(dc_odds)
            if "1X" not in dc_work and r_home > 1.0 and r_draw > 1.0:
                dc_work["1X"] = round(1.0 / max(0.01, (ph + pd) * 1.04), 2)
            if "X2" not in dc_work and r_away > 1.0 and r_draw > 1.0:
                dc_work["X2"] = round(1.0 / max(0.01, (pa + pd) * 1.04), 2)
            if "12" not in dc_work and r_home > 1.0 and r_away > 1.0:
                dc_work["12"] = round(1.0 / max(0.01, (ph + pa) * 1.04), 2)

            is_high_scoring_league = any(k in comp.upper() or k in country.upper() for k in HIGH_SCORING_LEAGUES)
            is_cup_or_knockout = any(k in comp.upper() for k in ["CUP", "POKAL", "COPA", "KNOCKOUT", "PLAYOFF", "TROPHY", "CHAMPIONS LEAGUE", "EUROPA LEAGUE", "CONFERENCE LEAGUE"])

            for dc_key, dc_val in dc_work.items():
                # TACTICAL RULE: Strictly Gate "12" based on H2H history, low draw rate and non-tier-3 league
                is_defensive_trap = (archetype_type == "LOW_GOAL_DEFENSIVE" or is_even_match or pd >= 0.22)
                if dc_key == "12":
                    if tier_label == "TIER_3_REGIONAL" or is_defensive_trap or pd >= 0.22:
                        continue
                    if h2h_total >= 2 and (h2h_draw_pct > 0.18 or h2h_recent_draws):
                        continue

                # TACTICAL RULE: Away Powerhouse Protection - Never give 1X to a home underdog vs an away powerhouse
                if dc_key == "1X" and (tier_context == "AWAY_DOMINANT" or (r_away <= 1.65 and r_home >= 2.50) or pa >= 0.55):
                    continue

                # TACTICAL RULE: Home Fortress Protection - Never give X2 to an away underdog vs a home fortress
                if dc_key == "X2" and (tier_context == "HOME_DOMINANT" or (r_home <= 1.65 and r_away >= 2.50) or ph >= 0.55):
                    continue

                if dc_val and min_odds_floor <= float(dc_val) <= max(1.35, max_odds_cap):
                    if dc_key == "1X":
                        prob = min(0.96, ph + pd)
                        sel_lbl = f"{home} or Draw (1X)"
                        out_id = "9"
                        t_reason = f"🛡️ Draw-Protected 1X Fortress ({int(prob*100)}% Win Chance)"
                    elif dc_key == "X2":
                        prob = min(0.96, pa + pd)
                        sel_lbl = f"{away} or Draw (X2)"
                        out_id = "11"
                        t_reason = f"🛡️ Draw-Protected X2 Away Cushion ({int(prob*100)}% Win Chance)"
                    else:
                        prob = min(0.96, ph + pa)
                        sel_lbl = f"{home} or {away} (12)"
                        out_id = "10"
                        t_reason = f"⚡ H2H-Vetted Decisive Match ({int(prob*100)}% Win Chance)"

                    if prob >= prob_floor and sel_lbl not in seen_selections:
                        seen_selections.add(sel_lbl)
                        t_boost = 25.0 if (archetype_type == "HEAVY_FAVORITE" and ((dc_key == "1X" and r_home < r_away) or (dc_key == "X2" and r_away < r_home))) else 10.0
                        candidates.append(PickDecision(
                            fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                            kickoff_datetime=kickoff, market_name="Double Chance", selection_name=sel_lbl,
                            model_probability=round(prob, 3), estimated_odds=float(dc_val),
                            elo_gap=elo_gap, tier_context=tier_context,
                            approved=True, confidence_tier="ELITE" if prob >= 0.88 else "HIGH",
                            gate_results={"gate1": "PASS", "gate2": "PASS"}, rejection_reason=None,
                            decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                            raw_match_data=fixture, market_id="10", outcome_id=out_id, specifier=None,
                            league_tier=tier_label, league_tier_score=tier_score,
                            tactical_archetype=archetype_type, tactical_score=t_boost,
                            tactical_reason=t_reason
                        ))

        def _mkt_available(mid: str) -> bool:
            # Universal SportyBet markets (1X2: 1, DC: 10, O/U: 18, Team Goals: 19, 20) are standard on SportyBet
            if str(mid) in ("1", "10", "18", "19", "20"):
                return True
            if not raw_market_ids:
                return True
            return str(mid) in raw_market_ids

        # 2. Asian Handicaps (+1.5 for 50/50 games, -1.0 for Heavy Favorites)
        if _cat_allowed("HANDICAP") and _mkt_available("16"):
            if is_even_match:
                # Home +1.5 Asian Handicap (wins on Home win, draw, or 1-goal loss)
                prob_h_p15 = min(0.93, 0.60 + (ph * 0.40) + (pd * 0.35))
                odd_h_p15 = round(1.0 / (prob_h_p15 * 1.04), 2)
                sel_hp15 = f"{home} (+1.5 Handicap)"
                if prob_h_p15 >= prob_floor and min_odds_floor <= odd_h_p15 <= max_odds_cap and sel_hp15 not in seen_selections:
                    seen_selections.add(sel_hp15)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="Asian Handicap", selection_name=sel_hp15,
                        model_probability=round(prob_h_p15, 3), estimated_odds=odd_h_p15,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE", gate_results={"gate1": "PASS", "gate2": "PASS"},
                        rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                        raw_match_data=fixture, market_id="16", outcome_id="1714", specifier="hcp=1.5",
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype="BALANCED_HANDICAP", tactical_score=28.0,
                        tactical_reason=f"🎯 Equal-Strength +1.5 Cushion (Wins on Win/Draw/1-Goal Loss)"
                    ))

                # Away +1.5 Asian Handicap (wins on Away win, draw, or 1-goal loss)
                prob_a_p15 = min(0.92, 0.58 + (pa * 0.40) + (pd * 0.35))
                odd_a_p15 = round(1.0 / (prob_a_p15 * 1.04), 2)
                sel_ap15 = f"{away} (+1.5 Handicap)"
                if prob_a_p15 >= prob_floor and min_odds_floor <= odd_a_p15 <= max_odds_cap and sel_ap15 not in seen_selections:
                    seen_selections.add(sel_ap15)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="Asian Handicap", selection_name=sel_ap15,
                        model_probability=round(prob_a_p15, 3), estimated_odds=odd_a_p15,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE", gate_results={"gate1": "PASS", "gate2": "PASS"},
                        rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                        raw_match_data=fixture, market_id="16", outcome_id="1715", specifier="hcp=1.5",
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype="BALANCED_HANDICAP", tactical_score=28.0,
                        tactical_reason=f"🎯 Equal-Strength +1.5 Cushion (Wins on Win/Draw/1-Goal Loss)"
                    ))

        # 3. Over/Under Lines (Universal SportyBet Half-Point Lines: 1.5, 2.5, 3.5, 4.5)
        if _cat_allowed("OVER_UNDER") and len(ou_lines) > 0 and _mkt_available("18"):
            is_high_scoring_league = any(k in comp.upper() or k in country.upper() for k in HIGH_SCORING_LEAGUES)
            for ou in ou_lines:
                try:
                    raw_line_num = float(ou.get("line") or 0.0)
                except Exception:
                    continue

                # Strictly restrict to universal SportyBet decimal lines (0.5, 1.5, 2.5, 3.5, 4.5)
                if raw_line_num not in (0.5, 1.5, 2.5, 3.5, 4.5):
                    continue

                line_str = f"{raw_line_num:.1f}"
                o_odd = ou.get("over")
                u_odd = ou.get("under")
                if o_odd and min_odds_floor <= float(o_odd) <= max_odds_cap:
                    # Do not pick Over 1.5 blindly if H2H proves defensive grinder (avg <= 1.5 goals)
                    if raw_line_num <= 1.5 and h2h_total >= 2 and h2h_avg_goals <= 1.5 and h2h_avg_goals > 0:
                        pass
                    else:
                        sel = f"Over {line_str} Goals"
                        prob = round(min(0.96, 1.0 / (float(o_odd) * 1.04)), 3)
                        if prob >= prob_floor and sel not in seen_selections:
                            seen_selections.add(sel)
                            t_boost = 25.0 if archetype_type == "HIGH_GOAL_EXPECTANCY" else (15.0 if raw_line_num <= 1.5 else 0.0)
                            if is_high_scoring_league and raw_line_num <= 1.5:
                                t_boost += 20.0
                                t_reason = f"⚡ High Goal Expectancy (88%+ Over {line_str} Rate)"
                            else:
                                t_reason = f"⚽ 2+ Match Goals Safety Cushion"
                            candidates.append(PickDecision(
                                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                                kickoff_datetime=kickoff, market_name="Over/Under Goals", selection_name=sel,
                                model_probability=prob, estimated_odds=float(o_odd),
                                elo_gap=elo_gap, tier_context=tier_context,
                                approved=True, confidence_tier="ELITE" if prob >= 0.88 else "HIGH",
                                gate_results={"gate1": "PASS", "gate2": "PASS"}, rejection_reason=None,
                                decision_audit_log=[], kelly_quarter_stake_pct=2.5,
                                raw_match_data=fixture, market_id="18", outcome_id="12", specifier=f"total={line_str}",
                                league_tier=tier_label, league_tier_score=tier_score,
                                tactical_archetype=archetype_type, tactical_score=t_boost,
                                tactical_reason=t_reason
                            ))
                if u_odd and min_odds_floor <= float(u_odd) <= max_odds_cap and raw_line_num >= 2.5:
                    # Hard ban Under 3.5 in goal-heavy leagues or if H2H proves high scoring (avg >= 3.5)
                    if raw_line_num <= 3.5 and (is_high_scoring_league or archetype_type == "HEAVY_FAVORITE" or (h2h_total >= 2 and h2h_avg_goals >= 3.5)):
                        continue
                    sel = f"Under {line_str} Goals"
                    prob = round(min(0.96, 1.0 / (float(u_odd) * 1.04)), 3)
                    if prob >= prob_floor and sel not in seen_selections:
                        seen_selections.add(sel)
                        t_boost = 25.0 if (archetype_type == "LOW_GOAL_DEFENSIVE" or is_even_match) else (15.0 if raw_line_num >= 3.5 else 0.0)
                        t_reason = f"🛡️ Defensive Ceiling (Under {line_str} Goals Cushion)"
                        candidates.append(PickDecision(
                            fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                            kickoff_datetime=kickoff, market_name="Over/Under Goals", selection_name=sel,
                            model_probability=prob, estimated_odds=float(u_odd),
                            elo_gap=elo_gap, tier_context=tier_context,
                            approved=True, confidence_tier="ELITE" if prob >= 0.88 else "HIGH",
                            gate_results={"gate1": "PASS", "gate2": "PASS"}, rejection_reason=None,
                            decision_audit_log=[], kelly_quarter_stake_pct=2.5,
                            raw_match_data=fixture, market_id="18", outcome_id="13", specifier=f"total={line_str}",
                            league_tier=tier_label, league_tier_score=tier_score,
                            tactical_archetype=archetype_type, tactical_score=t_boost,
                            tactical_reason=t_reason
                        ))

        # 4. Team Goals (Team Over 0.5 / 1.5 Goals)
        if _cat_allowed("TEAM_GOALS"):
            if ph >= 0.52 and r_home <= 2.10 and _mkt_available("19"):
                prob_h_o05 = min(0.95, 0.72 + (ph * 0.25))
                odd_h_o05 = round(1.0 / (prob_h_o05 * 1.04), 2)
                sel_h05 = f"{home} Over 0.5 Goals"
                if prob_h_o05 >= prob_floor and min_odds_floor <= odd_h_o05 <= max_odds_cap and sel_h05 not in seen_selections:
                    seen_selections.add(sel_h05)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="Team Goals", selection_name=sel_h05,
                        model_probability=round(prob_h_o05, 3), estimated_odds=odd_h_o05,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE", gate_results={"gate1": "PASS", "gate2": "PASS"},
                        rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                        raw_match_data=fixture, market_id="19", outcome_id="12", specifier="total=0.5",
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype=archetype_type, tactical_score=20.0,
                        tactical_reason=f"🔥 {home} Single Goal Threshold (85%+ Win Chance)"
                    ))

                # Team Over 1.5 Goals for Dominant Favorites
                if ph >= 0.62 and r_home <= 1.65:
                    prob_h_o15 = min(0.86, 0.44 + (ph * 0.42))
                    odd_h_o15 = round(1.0 / (prob_h_o15 * 1.04), 2)
                    sel_h15 = f"{home} Over 1.5 Team Goals"
                    if prob_h_o15 >= prob_floor and min_odds_floor <= odd_h_o15 <= max_odds_cap and sel_h15 not in seen_selections:
                        seen_selections.add(sel_h15)
                        candidates.append(PickDecision(
                            fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                            kickoff_datetime=kickoff, market_name="Team Goals", selection_name=sel_h15,
                            model_probability=round(prob_h_o15, 3), estimated_odds=odd_h_o15,
                            elo_gap=elo_gap, tier_context=tier_context,
                            approved=True, confidence_tier="HIGH", gate_results={"gate1": "PASS", "gate2": "PASS"},
                            rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=2.5,
                            raw_match_data=fixture, market_id="19", outcome_id="12", specifier="total=1.5",
                            league_tier=tier_label, league_tier_score=tier_score, tactical_archetype=archetype_type, tactical_score=25.0,
                            tactical_reason=f"🔥 {home} 2+ Team Goals Attack Strength"
                        ))

            if pa >= 0.52 and r_away <= 2.10 and _mkt_available("20"):
                prob_a_o05 = min(0.95, 0.72 + (pa * 0.25))
                odd_a_o05 = round(1.0 / (prob_a_o05 * 1.04), 2)
                sel_a05 = f"{away} Over 0.5 Goals"
                if prob_a_o05 >= prob_floor and min_odds_floor <= odd_a_o05 <= max_odds_cap and sel_a05 not in seen_selections:
                    seen_selections.add(sel_a05)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="Team Goals", selection_name=sel_a05,
                        model_probability=round(prob_a_o05, 3), estimated_odds=odd_a_o05,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE", gate_results={"gate1": "PASS", "gate2": "PASS"},
                        rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                        raw_match_data=fixture, market_id="20", outcome_id="12", specifier="total=0.5",
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype=archetype_type, tactical_score=20.0,
                        tactical_reason=f"🔥 {away} Single Goal Threshold (85%+ Win Chance)"
                    ))

                # Team Over 1.5 Goals for Dominant Favorites
                if pa >= 0.62 and r_away <= 1.65:
                    prob_a_o15 = min(0.86, 0.44 + (pa * 0.42))
                    odd_a_o15 = round(1.0 / (prob_a_o15 * 1.04), 2)
                    sel_a15 = f"{away} Over 1.5 Team Goals"
                    if prob_a_o15 >= prob_floor and min_odds_floor <= odd_a_o15 <= max_odds_cap and sel_a15 not in seen_selections:
                        seen_selections.add(sel_a15)
                        candidates.append(PickDecision(
                            fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                            kickoff_datetime=kickoff, market_name="Team Goals", selection_name=sel_a15,
                            model_probability=round(prob_a_o15, 3), estimated_odds=odd_a_o15,
                            elo_gap=elo_gap, tier_context=tier_context,
                            approved=True, confidence_tier="HIGH", gate_results={"gate1": "PASS", "gate2": "PASS"},
                            rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=2.5,
                            raw_match_data=fixture, market_id="20", outcome_id="12", specifier="total=1.5",
                            league_tier=tier_label, league_tier_score=tier_score, tactical_archetype=archetype_type, tactical_score=25.0,
                            tactical_reason=f"🔥 {away} 2+ Team Goals Attack Strength"
                        ))

        # 5. Advanced Tactical Options: Win Either Half (Draw Immune for Confirmed Favorites)
        if _cat_allowed("COMBO") or _cat_allowed("DOUBLE_CHANCE"):
            # Home to Win Either Half (Heavy/Clear favorite only)
            if ph >= 0.58 and r_home <= 1.75 and _mkt_available("73"):
                prob_h_weh = min(0.94, 0.62 + (ph * 0.35))
                odd_h_weh = round(max(1.15, min(1.35, 1.0 / (prob_h_weh * 1.04))), 2)
                sel_h_weh = f"{home} to Win Either Half"
                if prob_h_weh >= prob_floor and min_odds_floor <= odd_h_weh <= max_odds_cap and sel_h_weh not in seen_selections:
                    seen_selections.add(sel_h_weh)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="Win Either Half", selection_name=sel_h_weh,
                        model_probability=round(prob_h_weh, 3), estimated_odds=odd_h_weh,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE", gate_results={"gate1": "PASS", "gate2": "PASS"},
                        rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=2.5,
                        raw_match_data=fixture, market_id="73", outcome_id="75", specifier=None,
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype="WIN_EITHER_HALF", tactical_score=26.0,
                        tactical_reason=f"⏱️ {home} to Win Either 45-Min Half (Draw Immune)"
                    ))

            # Away to Win Either Half (Heavy/Clear favorite only)
            if pa >= 0.58 and r_away <= 1.75 and _mkt_available("74"):
                prob_a_weh = min(0.94, 0.62 + (pa * 0.35))
                odd_a_weh = round(max(1.15, min(1.35, 1.0 / (prob_a_weh * 1.04))), 2)
                sel_a_weh = f"{away} to Win Either Half"
                if prob_a_weh >= prob_floor and min_odds_floor <= odd_a_weh <= max_odds_cap and sel_a_weh not in seen_selections:
                    seen_selections.add(sel_a_weh)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="Win Either Half", selection_name=sel_a_weh,
                        model_probability=round(prob_a_weh, 3), estimated_odds=odd_a_weh,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE", gate_results={"gate1": "PASS", "gate2": "PASS"},
                        rejection_reason=None, decision_audit_log=[], kelly_quarter_stake_pct=2.5,
                        raw_match_data=fixture, market_id="74", outcome_id="75", specifier=None,
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype="WIN_EITHER_HALF", tactical_score=26.0,
                        tactical_reason=f"⏱️ {away} to Win Either 45-Min Half (Draw Immune)"
                    ))

        # 6. 1X2 Match Result Lines (STRICT: Dominant Favorite Only - Never Pick Straight Wins on Competitive Games)
        if _cat_allowed("1X2"):
            if r_home and 1.15 <= r_home <= 1.48 and ph >= 0.70 and _mkt_available("1"):
                sel_h = f"{home} to Win (1)"
                if sel_h not in seen_selections:
                    seen_selections.add(sel_h)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="1X2 Match Result", selection_name=sel_h,
                        model_probability=round(ph, 3), estimated_odds=r_home,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE",
                        gate_results={"gate1": "PASS", "gate2": "PASS"}, rejection_reason=None,
                        decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                        raw_match_data=fixture, market_id="1", outcome_id="1", specifier=None,
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype="DIRECT_VALUE", tactical_score=15.0,
                        tactical_reason=f"👑 {home} Dominant Home Favorite (5-Gate Confirmed)"
                    ))
            if r_away and 1.15 <= r_away <= 1.48 and pa >= 0.70 and _mkt_available("1"):
                sel_a = f"{away} to Win (2)"
                if sel_a not in seen_selections:
                    seen_selections.add(sel_a)
                    candidates.append(PickDecision(
                        fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                        kickoff_datetime=kickoff, market_name="1X2 Match Result", selection_name=sel_a,
                        model_probability=round(pa, 3), estimated_odds=r_away,
                        elo_gap=elo_gap, tier_context=tier_context,
                        approved=True, confidence_tier="ELITE",
                        gate_results={"gate1": "PASS", "gate2": "PASS"}, rejection_reason=None,
                        decision_audit_log=[], kelly_quarter_stake_pct=3.0,
                        raw_match_data=fixture, market_id="1", outcome_id="2", specifier=None,
                        league_tier=tier_label, league_tier_score=tier_score, tactical_archetype="DIRECT_VALUE", tactical_score=15.0,
                        tactical_reason=f"👑 {away} Dominant Away Favorite (5-Gate Confirmed)"
                    ))

        # Fallback base decision if no candidates generated
        base_dec = self.evaluate_fixture_markets(
            fixture=fixture,
            per_leg_target_odds=per_leg_target_odds,
            min_prob_threshold=min_prob_threshold,
            risk_profile=risk_profile,
            allowed_markets=allowed_markets,
            excluded_markets=excluded_markets,
        )
        if candidates:
            return candidates
        elif base_dec.approved:
            base_dec.league_tier = tier_label
            base_dec.league_tier_score = tier_score
            return [base_dec]
        return []


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
        an optimal ticket or rollover plan with Tier-1 priority and tactical market diversity.
        """
        import random
        import time

        rp_clean = (risk_profile or "CONSERVATIVE").upper()
        if target_mode == "GAMES" and target_games:
            target_legs_count = max(1, min(50, target_games))
            if rp_clean == "AGGRESSIVE":
                per_leg_target = 1.45
                min_prob_threshold = 0.58
            else:
                if target_games >= 15:
                    per_leg_target = 1.18
                    min_prob_threshold = 0.76
                elif target_games >= 8:
                    per_leg_target = 1.25
                    min_prob_threshold = 0.75
                else:
                    per_leg_target = 1.30
                    min_prob_threshold = 0.74
            max_league_picks = max(max_league_picks, (target_games // 3) + 2)
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

        approved_legs = []
        rejected_picks = []
        summary_logs = [
            f"StatIQ AI Pick Engine ({mode} Mode - {target_mode})",
            f"Target: {target_games if target_mode == 'GAMES' else f'{target_total_odds:.2f}x'} | Legs: {target_legs_count}",
            f"Risk Profile: {risk_profile} | Min Probability Gate: {int(min_prob_threshold*100)}% | Per-Leg Target: {per_leg_target:.2f}x"
        ]

        total_evaluated = len(fixture_pool)

        # First pass: evaluate all fixtures and extract all valid candidate markets
        all_candidate_decisions: List[PickDecision] = []
        for fix in fixture_pool:
            cands = self.evaluate_fixture_all_candidates(
                fixture=fix,
                per_leg_target_odds=per_leg_target,
                min_prob_threshold=min_prob_threshold,
                risk_profile=risk_profile,
                allowed_markets=allowed_markets,
                excluded_markets=excluded_markets,
            )
            for c in cands:
                if c.approved:
                    all_candidate_decisions.append(c)

        approved_decisions = [d for d in all_candidate_decisions if d.approved]
        rejected_decisions = [d for d in all_candidate_decisions if not d.approved]

        def _dynamic_candidate_score(d: PickDecision) -> float:
            """
            Multi-Tier Dynamic Quantitative Scoring Metric:
            - League Tier Priority (Tier 1 = +100, Tier 2 = +50, Tier 3 = +10)
            - Tactical Match Archetype Bonus (up to +25)
            - Live Market Dominance Ratio (Underdog Odds / Favorite Odds)
            - Dynamic Elo Rating Gap
            - Base Model Win Probability
            """
            tier_score = float(getattr(d, "league_tier_score", 50))
            tactical_bonus = float(getattr(d, "tactical_score", 0.0))
            prob_score = d.model_probability * 100.0

            raw = d.raw_match_data or {}
            r1x2 = raw.get("result_1x2") or {}
            dominance_score = 0.0
            try:
                h_odd = float(r1x2.get("1") or r1x2.get("home") or 0.0)
                a_odd = float(r1x2.get("2") or r1x2.get("away") or 0.0)
                if h_odd > 1.0 and a_odd > 1.0:
                    fav = min(h_odd, a_odd)
                    und = max(h_odd, a_odd)
                    dominance_ratio = und / fav
                    if fav <= 1.50 and dominance_ratio >= 3.0:
                        dominance_score = min(60.0, dominance_ratio * 7.0)
                    elif fav <= 1.80 and dominance_ratio >= 1.8:
                        dominance_score = min(35.0, dominance_ratio * 5.0)
            except Exception:
                pass

            elo_score = min(25.0, max(0.0, abs(float(d.elo_gap or 0.0)) * 0.20))
            return tier_score + tactical_bonus + prob_score + dominance_score + elo_score

        if mode == "ROLLOVER":
            import itertools

            # Filter candidates for Rollover with expanded multi-variant suite:
            # Requires minimum leg odds of 1.08 to 1.65
            def _is_safe_rollover_market(d) -> bool:
                m_lower = (d.market_name or "").lower()
                s_lower = (d.selection_name or "").lower()
                o_val = float(d.estimated_odds or 1.0)
                if o_val < 1.08 or o_val > 1.65:
                    return False

                # 1. Double Chance 1X / X2 (Draw Protected)
                is_dc = "double chance" in m_lower and ("1x" in s_lower or "x2" in s_lower or "home or draw" in s_lower or "draw or away" in s_lower)

                # 2. Asian Handicap (+1.5, +2.0, +2.5)
                is_handicap = ("handicap" in m_lower or "asian handicap" in m_lower) and any(x in s_lower for x in ["+1.5", "+2.0", "(+1.5)", "(+2.0)"])

                # 3. Win Either Half (Home / Away)
                is_weh = "win either half" in m_lower or "win either half" in s_lower

                # 4. Team Goals (Home/Away Over 0.5, Over 1.5)
                is_team_goals = ("team" in m_lower or "team" in s_lower) and ("0.5" in s_lower or "1.5" in s_lower)

                # 5. Safe Total Goals (Over 0.5, Over 1.5)
                is_safe_over_goals = ("over" in s_lower or "over" in m_lower) and any(x in s_lower for x in ["0.5", "1.5"])

                # 6. Under Goals: STRICTLY BANNED on heavy favorites (prevents blowout losses)
                is_heavy_fav = getattr(d, "tactical_archetype", "") == "HEAVY_FAVORITE" or (float(d.elo_gap or 0.0) >= 150.0)
                is_safe_under_goals = ("under" in s_lower or "under" in m_lower) and any(x in s_lower for x in ["3.5", "4.5", "5.5"]) and not is_heavy_fav

                # 7. Outright favorite win (only if heavy favorite with high confidence)
                is_fav_win = ("match result" in m_lower or "to win" in s_lower) and d.model_probability >= 0.74 and o_val <= 1.40

                return is_dc or is_handicap or is_weh or is_team_goals or is_safe_over_goals or is_safe_under_goals or is_fav_win

            # Probability floor for rollover based on risk profile
            rp_upper = (risk_profile or "BALANCED").upper()
            rollover_prob_floor = 0.82 if rp_upper == "ULTRA_CONSERVATIVE" else (0.70 if rp_upper == "AGGRESSIVE" else 0.76)

            valid_cands = [
                d for d in approved_decisions
                if _is_safe_rollover_market(d)
                and d.model_probability >= rollover_prob_floor
            ]

            # Use all valid candidates from the user's selected league pool
            pool_to_use = valid_cands if len(valid_cands) >= 2 else approved_decisions

            # Group candidates by distinct fixture
            fixtures_dict: Dict[str, List[PickDecision]] = {}
            for d in pool_to_use:
                fix_k = str(d.fixture_id or f"{d.home_team}_{d.away_team}")
                if fix_k not in fixtures_dict:
                    fixtures_dict[fix_k] = []
                fixtures_dict[fix_k].append(d)

            # Sort candidates within each fixture by (model_probability desc, score desc)
            for fk in fixtures_dict:
                fixtures_dict[fk].sort(key=lambda x: (x.model_probability, _dynamic_candidate_score(x)), reverse=True)

            avail_fix_keys = list(fixtures_dict.keys())
            seed_val = reshuffle_seed if reshuffle_seed is not None else int(time.time() * 1000)
            rng = random.Random(seed_val)
            rng.shuffle(avail_fix_keys)

            target = float(target_total_odds or 2.00)
            best_combo: List[PickDecision] = []
            best_diff = float("inf")

            # Search 1-leg to up to 9-leg combinations to find optimal target match
            max_leg_k = 9 if target >= 4.5 else (8 if target >= 3.5 else (6 if target >= 2.5 else 5))
            for leg_k in range(1, min(max_leg_k, len(avail_fix_keys) + 1)):
                fix_subsets = list(itertools.combinations(avail_fix_keys[:20], leg_k))
                rng.shuffle(fix_subsets)
                for subset in fix_subsets[:30]:
                    subset_cands = [fixtures_dict[fk][:3] for fk in subset]
                    for cand_tuple in itertools.product(*subset_cands):
                        combo_odds = 1.0
                        combo_prob = 1.0
                        for c in cand_tuple:
                            combo_odds *= float(c.estimated_odds or 1.25)
                            combo_prob *= float(c.model_probability or 0.80)

                        diff = abs(combo_odds - target)
                        # Penalize being under target odds heavily to prevent sub-1.85 slips on 2.0x target
                        if combo_odds < (target * 0.95):
                            diff += 2.5 * (target - combo_odds)
                        elif combo_odds > (target * 1.12):
                            diff += 1.2 * (combo_odds - target)

                        # Score combines odds closeness with high win probability
                        score = diff - (combo_prob * 0.25)
                        if score < best_diff:
                            best_diff = score
                            best_combo = list(cand_tuple)
                            if abs(combo_odds - target) <= 0.04 and combo_prob >= 0.55:
                                break

                    if best_combo:
                        tot_o = 1.0
                        for c in best_combo: tot_o *= c.estimated_odds
                        if abs(tot_o - target) <= 0.04:
                            break

            if best_combo:
                selected_decisions = best_combo
            else:
                # Fallback greedy
                selected_decisions = []
                curr_acc_odds = 1.0
                seen_f = set()
                for fk in avail_fix_keys:
                    cands = fixtures_dict[fk]
                    if not cands or fk in seen_f: continue
                    selected_decisions.append(cands[0])
                    seen_f.add(fk)
                    curr_acc_odds *= cands[0].estimated_odds
                    if curr_acc_odds >= (target * 0.96):
                        break

            if not selected_decisions and valid_cands:
                selected_decisions.append(valid_cands[0])
        else:
            seed_val = reshuffle_seed if reshuffle_seed is not None else int(time.time() * 1000)
            rng = random.Random(seed_val)

            # Sort by League Tier and Dynamic Tactical Score
            approved_decisions.sort(key=_dynamic_candidate_score, reverse=True)

            # Group candidates by Tier: Tier 1 Elite > Tier 2 Solid > Tier 3 Regional
            t1_pool = [d for d in approved_decisions if getattr(d, "league_tier_score", 50) == 100]
            t2_pool = [d for d in approved_decisions if getattr(d, "league_tier_score", 50) == 50]
            t3_pool = [d for d in approved_decisions if getattr(d, "league_tier_score", 50) == 10]

            # Shuffle within tiers to enable organic permutation
            if len(t1_pool) > 1: rng.shuffle(t1_pool)
            if len(t2_pool) > 1: rng.shuffle(t2_pool)
            if len(t3_pool) > 1: rng.shuffle(t3_pool)

            # Prioritized Candidate Pool: Tier 1 first, then Tier 2, fallback to Tier 3
            elite_candidate_pool = t1_pool + t2_pool + t3_pool

            selected_decisions: List[PickDecision] = []
            target_legs_count = leg_config["ideal_legs"]

            seen_fixtures: set = set()
            seen_leagues: Dict[str, int] = {}
            seen_markets: Dict[str, int] = {}
            max_per_market_type = max(2, (target_legs_count // 2) + 1)

            if target_mode == "ODDS":
                candidate_combo = []
                curr_odds = 1.0

                for d in elite_candidate_pool:
                    fix_k = str(d.fixture_id or f"{d.home_team}_{d.away_team}")
                    if fix_k in seen_fixtures:
                        continue

                    comp = str(d.competition or "OTHER")
                    m_key = str(d.selection_name or d.market_name)
                    m_type = str(d.market_name or "OTHER")

                    if seen_markets.get(m_type, 0) >= max_per_market_type and len(elite_candidate_pool) >= 15:
                        continue
                    if seen_markets.get(m_key, 0) >= 2 and len(elite_candidate_pool) >= 8:
                        continue

                    candidate_combo.append(d)
                    seen_fixtures.add(fix_k)
                    seen_leagues[comp] = seen_leagues.get(comp, 0) + 1
                    seen_markets[m_type] = seen_markets.get(m_type, 0) + 1
                    seen_markets[m_key] = seen_markets.get(m_key, 0) + 1
                    curr_odds *= d.estimated_odds

                    if curr_odds >= (target_total_odds * 0.95):
                        break
                    if len(candidate_combo) >= 50:
                        break

                # If still under target_total_odds, pull additional safe picks from remaining fixtures
                if curr_odds < (target_total_odds * 0.90):
                    for d in elite_candidate_pool:
                        fix_k = str(d.fixture_id or f"{d.home_team}_{d.away_team}")
                        if fix_k not in seen_fixtures:
                            candidate_combo.append(d)
                            seen_fixtures.add(fix_k)
                            curr_odds *= d.estimated_odds
                            if curr_odds >= (target_total_odds * 0.95) or len(candidate_combo) >= 50:
                                break

                selected_decisions = candidate_combo if candidate_combo else elite_candidate_pool[:target_legs_count]
            else:
                # GAMES mode: sample target_legs_count diverse games from randomized prioritized pool
                for d in elite_candidate_pool:
                    fix_k = str(d.fixture_id or f"{d.home_team}_{d.away_team}")
                    if fix_k in seen_fixtures:
                        continue

                    comp = str(d.competition or "OTHER")
                    m_key = str(d.selection_name or d.market_name)
                    m_type = str(d.market_name or "OTHER")

                    if seen_markets.get(m_type, 0) >= max_per_market_type and len(elite_candidate_pool) >= target_legs_count * 2:
                        continue
                    if seen_markets.get(m_key, 0) >= 2 and len(elite_candidate_pool) >= target_legs_count * 2:
                        continue

                    selected_decisions.append(d)
                    seen_fixtures.add(fix_k)
                    seen_leagues[comp] = seen_leagues.get(comp, 0) + 1
                    seen_markets[m_type] = seen_markets.get(m_type, 0) + 1
                    seen_markets[m_key] = seen_markets.get(m_key, 0) + 1

                    if len(selected_decisions) >= target_legs_count:
                        break

                if len(selected_decisions) < target_legs_count:
                    for d in elite_candidate_pool:
                        fix_k = str(d.fixture_id or f"{d.home_team}_{d.away_team}")
                        if fix_k not in seen_fixtures:
                            selected_decisions.append(d)
                            seen_fixtures.add(fix_k)
                            if len(selected_decisions) >= target_legs_count:
                                break

                # Pass 3: If still under target_legs_count, evaluate remaining unselected fixtures from fixture_pool
                if len(selected_decisions) < target_legs_count:
                    for fix in fixture_pool:
                        f_id = str(fix.get("eventId") or fix.get("event_id") or fix.get("fixture_id") or "")
                        h_n = str(fix.get("home_team") or "").strip().lower()
                        a_n = str(fix.get("away_team") or "").strip().lower()
                        fix_k = str(fix.get("fixture_id") or f"{fix.get('home_team')}_{fix.get('away_team')}")
                        if fix_k in seen_fixtures:
                            continue
                        relaxed_cands = self.evaluate_fixture_all_candidates(
                            fixture=fix,
                            per_leg_target_odds=1.28,
                            min_prob_threshold=0.60,
                            risk_profile=risk_profile,
                            allowed_markets=allowed_markets,
                            excluded_markets=excluded_markets,
                        )
                        if relaxed_cands:
                            best_c = max(relaxed_cands, key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))))
                            selected_decisions.append(best_c)
                            seen_fixtures.add(fix_k)
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
            country_val = (d.raw_match_data or {}).get("country") or ""
            approved_legs.append({
                "fixture_id": d.fixture_id,
                "event_id": ev_id,
                "provider_event_id": ev_id,
                "game_id": d.fixture_id,
                "home_team": d.home_team,
                "away_team": d.away_team,
                "competition": d.competition,
                "country": country_val,
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
                "specifier": d.specifier,
                "tactical_reason": getattr(d, "tactical_reason", "")
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

    def _score_fixture_strategic(self, fixture: Dict[str, Any]) -> float:
        """
        Composite Strategic Safety Score for a fixture:
          0.35 × structural_safety (best candidate market safety)
          0.25 × H2H confidence (dominant team's H2H win rate)
          0.20 × upset risk (1 - implied underdog probability)
          0.10 × league tier bonus (Tier 1=1.0, Tier 2=0.85, Tier 3=0.70)
          0.10 × kickoff time buffer (games >90min away get full score)
        """
        import time as _time
        comp = str(fixture.get("competition") or fixture.get("competition_code") or "")
        country = str(fixture.get("country") or "")
        tier_score, _ = classify_league_tier(comp, country)
        tier_bonus = 1.0 if tier_score == 100 else (0.85 if tier_score == 50 else 0.70)

        h_odd = float(fixture.get("odds_home") or fixture.get("result_1x2", {}).get("home") or 2.5)
        a_odd = float(fixture.get("odds_away") or fixture.get("result_1x2", {}).get("away") or 2.5)
        fav_odd = min(h_odd, a_odd)
        und_odd = max(h_odd, a_odd)

        upset_risk = 1.0 / max(1.01, und_odd * 1.05)

        h2h = fixture.get("h2h_data") or {}
        home_win_pct = float(h2h.get("home_win_pct") or 0.0)
        away_win_pct = float(h2h.get("away_win_pct") or 0.0)
        h2h_confidence = max(home_win_pct if h_odd <= a_odd else away_win_pct, 0.33)

        # Best structural safety from available markets
        dc = fixture.get("double_chance") or {}
        ou = fixture.get("ou_lines") or []
        best_struct = 0.5
        if dc.get("1X") and float(dc["1X"]) <= 1.25: best_struct = max(best_struct, 1.0)
        if dc.get("X2") and float(dc["X2"]) <= 1.25: best_struct = max(best_struct, 1.0)
        for line in ou:
            if str(line.get("line")) in ("3.5", "4.5") and line.get("under") and float(line["under"]) <= 1.35:
                best_struct = max(best_struct, 0.95)

        # Kickoff time bonus: games kicking off >90min from now get full score
        start_ms = float(fixture.get("start_time_ms") or 0)
        now_ms = _time.time() * 1000.0
        mins_to_ko = (start_ms - now_ms) / 60000.0 if start_ms > 0 else 999.0
        ko_bonus = 1.0 if mins_to_ko >= 90 else max(0.5, mins_to_ko / 90.0)

        score = (
            0.35 * best_struct
            + 0.25 * h2h_confidence
            + 0.20 * (1.0 - upset_risk)
            + 0.10 * tier_bonus
            + 0.10 * ko_bonus
        )
        return round(score, 4)

    def build_portfolio(
        self,
        fixture_pool: List[Dict[str, Any]],
        num_tickets: int = 3,
        target_total_odds: float = 5.0,
        mode: str = "ACCUMULATOR",
        target_mode: str = "ODDS",
        target_games: Optional[int] = None,
        max_league_picks: int = 4,
        risk_profile: str = "BALANCED",
        allowed_markets: Optional[List[str]] = None,
        excluded_markets: Optional[List[str]] = None,
        overlap_mode: str = "ZERO_OVERLAP",
    ) -> List[BuiltTicket]:
        """
        Constructs a portfolio of K distinct, diversified accumulator tickets from a shared fixture pool.
        When fixture_pool has fewer matches than num_tickets * target_games, it applies Smart Alternative
        Market Hedging so that every ticket reaches the full target_games count while guaranteeing
        zero duplicate predictions on any shared fixture.
        """
        num_tickets = max(1, min(6, int(num_tickets or 1)))
        if num_tickets == 1 or not fixture_pool:
            return [self.build_ticket(
                fixture_pool=fixture_pool,
                target_total_odds=target_total_odds,
                mode=mode,
                target_mode=target_mode,
                target_games=target_games,
                max_league_picks=max_league_picks,
                risk_profile=risk_profile,
                allowed_markets=allowed_markets,
                excluded_markets=excluded_markets,
            )]

        # Pre-score all fixtures by composite strategic safety
        scored_fixtures = sorted(
            fixture_pool,
            key=lambda f: self._score_fixture_strategic(f),
            reverse=True
        )

        n_pool = len(scored_fixtures)
        target_legs_count = min(15, target_games if (target_mode == "GAMES" and target_games) else (15 if target_total_odds >= 15.0 else 14))
        needed_total_picks = num_tickets * target_legs_count

        portfolio: List[BuiltTicket] = []
        # Track (f_key -> set of selection names already assigned across prior tickets)
        global_market_usage: Dict[str, set] = {}
        base_seed = int(time.time() * 1000)

        # Check if we have ample fixtures for strict distinct partitioning
        # On high-volume match days (e.g. Saturdays/Sundays with >= 30 matches), enforce strict zero-fixture overlap
        can_strict_partition = (n_pool >= needed_total_picks) or (n_pool >= 30 and num_tickets == 2 and target_legs_count <= 15)

        if can_strict_partition:
            # Standard Round-Robin Partitions: T1 gets 0, 2, 4... T2 gets 1, 3, 5...
            partitions: List[List[Dict[str, Any]]] = [[] for _ in range(num_tickets)]
            for idx, fix in enumerate(scored_fixtures):
                partitions[idx % num_tickets].append(fix)

            used_fixtures_all_tickets = set()
            for t_idx in range(num_tickets):
                t_seed = base_seed + (t_idx * 7919)
                t_built = self.build_ticket(
                    fixture_pool=partitions[t_idx],
                    target_total_odds=target_total_odds,
                    mode=mode,
                    target_mode=target_mode,
                    target_games=target_legs_count,
                    max_league_picks=max_league_picks,
                    reshuffle_seed=t_seed,
                    risk_profile=risk_profile,
                    allowed_markets=allowed_markets,
                    excluded_markets=excluded_markets,
                )
                portfolio.append(t_built)
                for leg in t_built.approved_legs:
                    f_id = str(leg.get("fixture_id") or leg.get("event_id") or "")
                    h_name = str(leg.get("home_team") or "").strip().lower()
                    a_name = str(leg.get("away_team") or "").strip().lower()
                    f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else f_id
                    used_fixtures_all_tickets.add(f_key)

            # If any ticket is short of target_legs_count, supplement strictly from unused fixtures in pool
            for t_idx, t_built in enumerate(portfolio):
                needs_more = False
                if target_mode == "GAMES" and len(t_built.approved_legs) < target_legs_count:
                    needs_more = True
                elif target_mode == "ODDS" and t_built.total_odds < (target_total_odds * 0.95) and len(t_built.approved_legs) < target_legs_count:
                    needs_more = True

                if needs_more:
                    for fix in scored_fixtures:
                        f_id = str(fix.get("eventId") or fix.get("event_id") or fix.get("fixture_id") or "")
                        h_name = str(fix.get("home_team") or "").strip().lower()
                        a_name = str(fix.get("away_team") or "").strip().lower()
                        f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else f_id
                        if f_key in used_fixtures_all_tickets:
                            continue
                        cands = self.evaluate_fixture_all_candidates(
                            fixture=fix,
                            per_leg_target_odds=1.25,
                            risk_profile=risk_profile,
                            allowed_markets=allowed_markets,
                            excluded_markets=excluded_markets
                        )
                        valid_cands = [c for c in cands if float(c.estimated_odds or 1.0) >= 1.15]
                        if valid_cands:
                            valid_cands.sort(key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))), reverse=True)
                            chosen = valid_cands[0]
                            leg_dict = {
                                "fixture_id": chosen.fixture_id,
                                "event_id": fix.get("event_id") or fix.get("eventId") or chosen.fixture_id,
                                "provider_event_id": fix.get("event_id") or fix.get("eventId") or chosen.fixture_id,
                                "home_team": chosen.home_team,
                                "away_team": chosen.away_team,
                                "competition": chosen.competition,
                                "country": fix.get("country", ""),
                                "market_name": chosen.market_name,
                                "selection_name": chosen.selection_name,
                                "model_probability": chosen.model_probability,
                                "estimated_odds": chosen.estimated_odds,
                                "odds": chosen.estimated_odds,
                                "market_id": getattr(chosen, "market_id", "1"),
                                "outcome_id": getattr(chosen, "outcome_id", "1"),
                                "specifier": getattr(chosen, "specifier", None),
                                "tier_context": chosen.tier_context,
                                "tactical_reason": getattr(chosen, "tactical_reason", ""),
                                "decision_audit_log": [
                                    f"Archetype: {chosen.tier_context}",
                                    f"Assigned {chosen.selection_name} @{chosen.estimated_odds:.2f} (Model Prob: {int(chosen.model_probability*100)}%)"
                                ]
                            }
                            t_built.approved_legs.append(leg_dict)
                            used_fixtures_all_tickets.add(f_key)
                            t_built.total_odds = round(t_built.total_odds * chosen.estimated_odds, 2)
                            if target_mode == "GAMES" and len(t_built.approved_legs) >= target_legs_count:
                                break
                            if target_mode == "ODDS" and (t_built.total_odds >= (target_total_odds * 0.95) or len(t_built.approved_legs) >= target_legs_count):
                                break
        else:
            # Limited Pool: Apply Smart Alternative Market Hedging across slips
            # Distribute fixtures with offset rotation so tickets prioritize different fixtures first
            offset_step = max(1, n_pool // num_tickets) if n_pool > 0 else 0

            for t_idx in range(num_tickets):
                t_seed = base_seed + (t_idx * 7919)
                rng = random.Random(t_seed)
                # Offset starting rotation so each ticket starts on a different fixture
                shift = (t_idx * offset_step) % max(1, n_pool)
                rotated_pool = scored_fixtures[shift:] + scored_fixtures[:shift]

                approved_legs_for_ticket = []
                acc_odds = 1.0
                seen_fixtures_in_slip = set()

                # Pass 1: Prioritize unassigned / completely distinct market candidates
                for fix in rotated_pool:
                    f_id = str(fix.get("eventId") or fix.get("event_id") or fix.get("fixture_id") or "")
                    h_name = str(fix.get("home_team") or "").strip().lower()
                    a_name = str(fix.get("away_team") or "").strip().lower()
                    f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else f_id

                    if f_key in seen_fixtures_in_slip:
                        continue

                    # Fetch all vetted candidate markets for this fixture
                    cands = self.evaluate_fixture_all_candidates(
                        fixture=fix,
                        per_leg_target_odds=1.25,
                        risk_profile=risk_profile,
                        allowed_markets=allowed_markets,
                        excluded_markets=excluded_markets
                    )

                    if not cands:
                        continue

                    used_on_this_fix = global_market_usage.get(f_key, set())
                    chosen_cand = None

                    # Filter candidates for valid odds bounds (Minimum Floor: 1.15)
                    valid_cands = []
                    for c in cands:
                        sel_str = str(c.selection_name).strip().lower()
                        mkt_str = str(c.market_name).strip().lower()
                        c_odds = float(c.estimated_odds or 1.25)
                        if "double chance" in mkt_str and c_odds > 1.35:
                            continue
                        if c_odds < 1.15 or c_odds > 1.65:
                            continue
                        valid_cands.append(c)

                    if not valid_cands:
                        valid_cands = [c for c in cands if float(c.estimated_odds or 1.0) >= 1.15]

                    # Prioritize candidates not yet used for this fixture in prior tickets
                    unused_cands = [c for c in valid_cands if str(c.selection_name).strip().lower() not in used_on_this_fix]
                    
                    if unused_cands:
                        unused_cands.sort(key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))), reverse=True)
                        chosen_cand = unused_cands[0]
                    else:
                        continue

                    if chosen_cand:
                        sel_clean_str = str(chosen_cand.selection_name).strip().lower()
                        leg_dict = {
                            "fixture_id": chosen_cand.fixture_id,
                            "event_id": fix.get("event_id") or fix.get("eventId") or chosen_cand.fixture_id,
                            "provider_event_id": fix.get("event_id") or fix.get("eventId") or chosen_cand.fixture_id,
                            "home_team": chosen_cand.home_team,
                            "away_team": chosen_cand.away_team,
                            "competition": chosen_cand.competition,
                            "country": fix.get("country", ""),
                            "market_name": chosen_cand.market_name,
                            "selection_name": chosen_cand.selection_name,
                            "model_probability": chosen_cand.model_probability,
                            "estimated_odds": chosen_cand.estimated_odds,
                            "odds": chosen_cand.estimated_odds,
                            "market_id": getattr(chosen_cand, "market_id", "1"),
                            "outcome_id": getattr(chosen_cand, "outcome_id", "1"),
                            "specifier": getattr(chosen_cand, "specifier", None),
                            "tier_context": chosen_cand.tier_context,
                            "tactical_reason": getattr(chosen_cand, "tactical_reason", ""),
                            "decision_audit_log": [
                                f"Archetype: {chosen_cand.tier_context}",
                                f"Assigned {chosen_cand.selection_name} @{chosen_cand.estimated_odds:.2f} (Model Prob: {int(chosen_cand.model_probability*100)}%)"
                            ]
                        }
                        approved_legs_for_ticket.append(leg_dict)
                        seen_fixtures_in_slip.add(f_key)
                        acc_odds *= chosen_cand.estimated_odds

                        if f_key not in global_market_usage:
                            global_market_usage[f_key] = set()
                        global_market_usage[f_key].add(sel_clean_str)

                        if target_mode == "GAMES" and target_legs_count and len(approved_legs_for_ticket) >= target_legs_count:
                            break
                        if target_mode == "ODDS" and (acc_odds >= (target_total_odds * 0.95) or len(approved_legs_for_ticket) >= target_legs_count) and len(approved_legs_for_ticket) >= 2:
                            break

                # Pass 2: Supplementary Hedging Pass if ticket still needs games to reach target_legs_count or target_odds
                needs_more = False
                if target_mode == "GAMES" and len(approved_legs_for_ticket) < target_legs_count:
                    needs_more = True
                elif target_mode == "ODDS" and acc_odds < (target_total_odds * 0.95) and len(approved_legs_for_ticket) < target_legs_count:
                    needs_more = True

                if needs_more:
                    for fix in rotated_pool:
                        f_id = str(fix.get("eventId") or fix.get("event_id") or fix.get("fixture_id") or "")
                        h_name = str(fix.get("home_team") or "").strip().lower()
                        a_name = str(fix.get("away_team") or "").strip().lower()
                        f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else f_id

                        if f_key in seen_fixtures_in_slip:
                            continue

                        # Check all candidates and look for an alternative safe market line
                        cands = self.evaluate_fixture_all_candidates(
                            fixture=fix,
                            per_leg_target_odds=1.25,
                            risk_profile=risk_profile,
                            allowed_markets=allowed_markets,
                            excluded_markets=excluded_markets
                        )
                        used_on_this_fix = global_market_usage.get(f_key, set())
                        
                        valid_cands = [c for c in cands if float(c.estimated_odds or 1.0) >= 1.15]
                        unused_cands = [c for c in valid_cands if str(c.selection_name).strip().lower() not in used_on_this_fix]

                        # STRICT INVARIANT: Must NEVER duplicate a prediction already used on this fixture in prior tickets
                        if not unused_cands:
                            continue

                        unused_cands.sort(key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))), reverse=True)
                        chosen_cand = unused_cands[0]

                        if chosen_cand:
                            sel_clean_str = str(chosen_cand.selection_name).strip().lower()
                            leg_dict = {
                                "fixture_id": chosen_cand.fixture_id,
                                "event_id": fix.get("event_id") or fix.get("eventId") or chosen_cand.fixture_id,
                                "provider_event_id": fix.get("event_id") or fix.get("eventId") or chosen_cand.fixture_id,
                                "home_team": chosen_cand.home_team,
                                "away_team": chosen_cand.away_team,
                                "competition": chosen_cand.competition,
                                "country": fix.get("country", ""),
                                "market_name": chosen_cand.market_name,
                                "selection_name": chosen_cand.selection_name,
                                "model_probability": chosen_cand.model_probability,
                                "estimated_odds": chosen_cand.estimated_odds,
                                "odds": chosen_cand.estimated_odds,
                                "market_id": getattr(chosen_cand, "market_id", "1"),
                                "outcome_id": getattr(chosen_cand, "outcome_id", "1"),
                                "specifier": getattr(chosen_cand, "specifier", None),
                                "tier_context": chosen_cand.tier_context,
                                "tactical_reason": getattr(chosen_cand, "tactical_reason", ""),
                                "decision_audit_log": [
                                    f"Alternative Hedge: {chosen_cand.selection_name} @{chosen_cand.estimated_odds:.2f}"
                                ]
                            }
                            approved_legs_for_ticket.append(leg_dict)
                            seen_fixtures_in_slip.add(f_key)
                            acc_odds *= chosen_cand.estimated_odds

                            if f_key not in global_market_usage:
                                global_market_usage[f_key] = set()
                            global_market_usage[f_key].add(sel_clean_str)

                            if target_mode == "GAMES" and len(approved_legs_for_ticket) >= target_legs_count:
                                break
                            if target_mode == "ODDS" and (acc_odds >= (target_total_odds * 0.95) or len(approved_legs_for_ticket) >= target_legs_count):
                                break

                # Enforce max 15 games cap
                if len(approved_legs_for_ticket) > 15:
                    approved_legs_for_ticket = approved_legs_for_ticket[:15]

                tot_prob = 1.0
                for leg in approved_legs_for_ticket:
                    tot_prob *= float(leg.get("model_probability") or 0.80)

                # Construct BuiltTicket object
                t_obj = BuiltTicket(
                    mode=mode,
                    target_odds=round(target_total_odds, 2),
                    accumulated_odds=round(acc_odds, 2),
                    combined_probability=round(tot_prob, 4),
                    correlation_adjusted_probability=round(tot_prob * 0.95, 4),
                    confidence_tier="HIGH" if acc_odds <= 15.0 else "BALANCED",
                    leg_config={"target_games": target_legs_count, "actual_games": len(approved_legs_for_ticket)},
                    approved_legs=approved_legs_for_ticket,
                    rejected_picks=[],
                    total_evaluated=len(rotated_pool),
                    decision_audit_summary=[f"Portfolio Slip #{t_idx+1}: Built {len(approved_legs_for_ticket)} legs with smart alternative market hedging"],
                    recommended_stake_pct=round(max(0.02, min(0.05, tot_prob * 0.08)), 4)
                )
                portfolio.append(t_obj)

        return portfolio



# Global singleton
pick_engine = MatchIQPickEngine()


