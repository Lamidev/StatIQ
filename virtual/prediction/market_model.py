from typing import Dict, Any, Optional
from virtual.research.odds_analyzer import OddsAnalyzer

class MarketModel:
    """
    Model B — Fair Market Consensus Probability Model.
    Strips SportyBet bookmaker overround to establish fair market implied probabilities.
    """
    MODEL_CODE = "MODEL_B_MARKET"
    VERSION = "v1.0.0"

    @classmethod
    def calculate_1x2_market_probabilities(cls, odds_home: float, odds_draw: float, odds_away: float) -> Dict[str, float]:
        return OddsAnalyzer.strip_1x2_overround(odds_home, odds_draw, odds_away)

    @classmethod
    def calculate_two_way_market_probabilities(cls, odds_a: float, odds_b: float) -> Dict[str, float]:
        return OddsAnalyzer.strip_two_way_overround(odds_a, odds_b)

    @classmethod
    def get_selection_implied_probability(cls, selection: str, odds: float, market_type: str = "1X2", all_odds: Optional[Dict[str, float]] = None) -> float:
        """
        Extracts fair normalized market probability for a specific pick.
        """
        if not odds or odds <= 1.0:
            return 0.50

        # If full 1X2 odds are provided, calculate normalized fair probability
        if market_type == "1X2" and all_odds:
            h = all_odds.get("odds_home", 0.0)
            d = all_odds.get("odds_draw", 0.0)
            a = all_odds.get("odds_away", 0.0)
            if h > 1.0 and d > 1.0 and a > 1.0:
                normalized = OddsAnalyzer.strip_1x2_overround(h, d, a)
                sel = selection.upper().strip()
                if sel in ["1", "HOME"]:
                    return normalized["prob_home"]
                elif sel in ["X", "DRAW"]:
                    return normalized["prob_draw"]
                elif sel in ["2", "AWAY"]:
                    return normalized["prob_away"]

        # Default fallback: 1 / odds with average 7.5% overround reduction
        raw_p = 1.0 / odds
        return round(raw_p / 1.075, 4)
