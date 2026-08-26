import math
from typing import Dict, Any, Tuple

class StatisticalModel:
    """
    Model C — Quantitative Statistical & Goal Expectancy Model for Virtuals.
    Uses Poisson bivariate goal expectancy formulations calibrated to match odds strength.
    """
    MODEL_CODE = "MODEL_C_STATISTICAL"
    VERSION = "v1.0.0"

    @classmethod
    def estimate_lambdas(cls, odds_home: float, odds_away: float, avg_league_goals: float = 2.68) -> Tuple[float, float]:
        """
        Estimates expected goals (lambda_home, lambda_away) from relative team odds strength.
        """
        if not (odds_home > 1.0 and odds_away > 1.0):
            return 1.40, 1.28

        # Strength ratio based on odds inverse
        inv_h = 1.0 / odds_home
        inv_a = 1.0 / odds_away
        total_inv = inv_h + inv_a
        ratio_h = inv_h / total_inv

        lambda_h = round(avg_league_goals * ratio_h, 2)
        lambda_a = round(avg_league_goals * (1.0 - ratio_h), 2)
        return max(0.5, lambda_h), max(0.5, lambda_a)

    @classmethod
    def poisson_pmf(cls, k: int, lam: float) -> float:
        """
        P(X = k) = (lam^k * e^-lam) / k!
        """
        return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

    @classmethod
    def calculate_match_probabilities(cls, odds_home: float, odds_away: float, avg_league_goals: float = 2.68) -> Dict[str, float]:
        """
        Generates full probability matrix for 1X2, Over/Under, and BTTS.
        """
        lam_h, lam_a = cls.estimate_lambdas(odds_home, odds_away, avg_league_goals)

        p_home = 0.0
        p_draw = 0.0
        p_away = 0.0
        p_over_1_5 = 0.0
        p_over_2_5 = 0.0
        p_btts = 0.0

        for h in range(7):
            for a in range(7):
                p_score = cls.poisson_pmf(h, lam_h) * cls.poisson_pmf(a, lam_a)
                
                # 1X2
                if h > a:
                    p_home += p_score
                elif h == a:
                    p_draw += p_score
                else:
                    p_away += p_score

                # Goals
                if (h + a) > 1.5:
                    p_over_1_5 += p_score
                if (h + a) > 2.5:
                    p_over_2_5 += p_score

                # BTTS
                if h > 0 and a > 0:
                    p_btts += p_score

        # Normalize 1X2
        total_1x2 = p_home + p_draw + p_away
        return {
            "lambda_home": lam_h,
            "lambda_away": lam_a,
            "prob_home": round(p_home / total_1x2, 4),
            "prob_draw": round(p_draw / total_1x2, 4),
            "prob_away": round(p_away / total_1x2, 4),
            "prob_over_1_5": round(p_over_1_5, 4),
            "prob_over_2_5": round(p_over_2_5, 4),
            "prob_under_2_5": round(1.0 - p_over_2_5, 4),
            "prob_btts_yes": round(p_btts, 4),
            "prob_double_chance_1x": round((p_home + p_draw) / total_1x2, 4),
            "prob_double_chance_x2": round((p_away + p_draw) / total_1x2, 4),
        }
