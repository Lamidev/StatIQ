from typing import Dict, Any, Tuple
from dataclasses import dataclass

@dataclass
class MarketOddsAnalysis:
    odds_home: float
    odds_draw: float
    odds_away: float
    margin: float
    prob_home_true: float
    prob_draw_true: float
    prob_away_true: float
    match_profile: str  # STRONG_FAVORITE, MODERATE_FAVORITE, EVENLY_MATCHED
    favorite_team: str  # HOME, AWAY, NONE
    underdog_team: str  # HOME, AWAY, NONE
    favorite_odds: float
    underdog_odds: float
    recommended_safe_market: str
    recommended_selection: str
    recommended_odds: float
    market_id: str
    outcome_id: str
    specifier: str = ""

class MarketProbabilityEngine:
    """
    StatIQ V2.0 Market Probability & Odds Engine.
    Strips bookmaker overround margins and calculates true statistical probabilities,
    identifying favorites, underdogs, and safe high-probability selections.
    """

    @classmethod
    def analyze_fixture_odds(cls, odds_home: float, odds_draw: float, odds_away: float, home_name: str = "Home", away_name: str = "Away") -> MarketOddsAnalysis:
        o1 = max(odds_home or 2.50, 1.01)
        ox = max(odds_draw or 3.00, 1.01)
        o2 = max(odds_away or 2.50, 1.01)

        # 1. Raw Implied Probabilities
        p1_raw = 1.0 / o1
        px_raw = 1.0 / ox
        p2_raw = 1.0 / o2
        p_total = p1_raw + px_raw + p2_raw
        margin = round(p_total - 1.0, 4)

        # 2. True Normalized Probabilities (Bookmaker margin stripped)
        p1_true = round(p1_raw / p_total, 4)
        px_true = round(px_raw / p_total, 4)
        p2_true = round(p2_raw / p_total, 4)

        # 3. Dynamic Favorite & Underdog Classification
        odds_diff = abs(o1 - o2)
        prob_diff = abs(p1_true - p2_true)

        if prob_diff <= 0.08 or odds_diff <= 0.25:
            match_profile = "EVENLY_MATCHED"
            favorite_team = "NONE"
            underdog_team = "NONE"
            favorite_odds = min(o1, o2)
            underdog_odds = max(o1, o2)
            # For even matches, recommend Under 3.5 / Double Chance / BTTS
            safe_mkt = "Double Chance"
            safe_sel = "1X or X2"
            safe_odds = 1.35
            m_id, o_id, spec = "10", "9", ""
        elif o1 < o2:
            favorite_team = "HOME"
            underdog_team = "AWAY"
            favorite_odds = o1
            underdog_odds = o2
            if p1_true >= 0.65 or o1 <= 1.45:
                match_profile = "STRONG_FAVORITE"
                safe_mkt = "Double Chance"
                safe_sel = f"{home_name} or Draw (1X)"
                safe_odds = round(1.0 / (p1_true + px_true * 0.85), 2)
                m_id, o_id, spec = "10", "9", ""
            else:
                match_profile = "MODERATE_FAVORITE"
                safe_mkt = "Win Either Half"
                safe_sel = f"{home_name} to Win Either Half"
                safe_odds = round(min(1.40, o1 * 0.70), 2)
                m_id, o_id, spec = "73", "75", ""
        else:
            favorite_team = "AWAY"
            underdog_team = "HOME"
            favorite_odds = o2
            underdog_odds = o1
            if p2_true >= 0.65 or o2 <= 1.45:
                match_profile = "STRONG_FAVORITE"
                safe_mkt = "Double Chance"
                safe_sel = f"Draw or {away_name} (X2)"
                safe_odds = round(1.0 / (p2_true + px_true * 0.85), 2)
                m_id, o_id, spec = "10", "11", ""
            else:
                match_profile = "MODERATE_FAVORITE"
                safe_mkt = "Win Either Half"
                safe_sel = f"{away_name} to Win Either Half"
                safe_odds = round(min(1.40, o2 * 0.70), 2)
                m_id, o_id, spec = "74", "75", ""

        return MarketOddsAnalysis(
            odds_home=o1,
            odds_draw=ox,
            odds_away=o2,
            margin=margin,
            prob_home_true=p1_true,
            prob_draw_true=px_true,
            prob_away_true=p2_true,
            match_profile=match_profile,
            favorite_team=favorite_team,
            underdog_team=underdog_team,
            favorite_odds=favorite_odds,
            underdog_odds=underdog_odds,
            recommended_safe_market=safe_mkt,
            recommended_selection=safe_sel,
            recommended_odds=max(safe_odds, 1.10),
            market_id=m_id,
            outcome_id=o_id,
            specifier=spec
        )
