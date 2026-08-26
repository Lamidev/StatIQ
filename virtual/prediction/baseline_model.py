from typing import Dict, Any
from virtual.research.frequency_analyzer import FrequencyAnalyzer

class BaselineModel:
    """
    Model A — Historical Frequency Baseline Model.
    Establishes ground truth empirical probability distributions from league history.
    """
    MODEL_CODE = "MODEL_A_BASELINE"
    VERSION = "v1.0.0"

    @classmethod
    def predict_market_probability(cls, market_type: str, selection: str, league_freq: Dict[str, Any]) -> float:
        """
        Returns empirical probability for a given market selection.
        """
        outcomes_1x2 = league_freq.get("outcomes_1x2", {})
        market_rates = league_freq.get("market_hit_rates", {})

        sel = selection.upper().strip()
        m_type = market_type.upper().strip()

        if m_type in ["1X2", "3WAY", "3 WAY"]:
            if sel in ["1", "HOME"]:
                return (outcomes_1x2.get("home_win_pct") or 42.4) / 100.0
            elif sel in ["X", "DRAW"]:
                return (outcomes_1x2.get("draw_pct") or 26.8) / 100.0
            elif sel in ["2", "AWAY"]:
                return (outcomes_1x2.get("away_win_pct") or 30.8) / 100.0

        elif "OVER" in m_type or "UNDER" in m_type:
            if "1.5" in sel or "1.5" in m_type:
                over_p = (market_rates.get("over_1_5_pct") or 78.6) / 100.0
                return over_p if "OVER" in sel else round(1.0 - over_p, 4)
            elif "2.5" in sel or "2.5" in m_type:
                over_p = (market_rates.get("over_2_5_pct") or 54.2) / 100.0
                return over_p if "OVER" in sel else round(1.0 - over_p, 4)
            elif "3.5" in sel or "3.5" in m_type:
                over_p = (market_rates.get("over_3_5_pct") or 29.5) / 100.0
                return over_p if "OVER" in sel else round(1.0 - over_p, 4)

        elif "BTTS" in m_type:
            btts_p = (market_rates.get("btts_yes_pct") or 52.1) / 100.0
            return btts_p if "YES" in sel else round(1.0 - btts_p, 4)

        elif "DOUBLE_CHANCE" in m_type or "DC" in m_type:
            if sel in ["1X", "1/X"]:
                return (market_rates.get("double_chance_1x_pct") or 69.2) / 100.0
            elif sel in ["X2", "X/2"]:
                return (market_rates.get("double_chance_x2_pct") or 57.6) / 100.0

        return 0.50
