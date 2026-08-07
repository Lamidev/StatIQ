import math
from typing import Dict, Tuple, Any

class PoissonEngine:
    """
    Independent Bivariate Poisson Engine for Football Match Prediction.
    Derives full goal score matrix and calculates probabilities for:
    - 1X2 (Home, Draw, Away)
    - Over / Under (0.5, 1.5, 2.5, 3.5)
    - Both Teams to Score (BTTS Yes / No)
    """
    def __init__(self, max_goals: int = 10):
        self.max_goals = max_goals
        self.home_attack: Dict[int, float] = {}
        self.home_defense: Dict[int, float] = {}
        self.away_attack: Dict[int, float] = {}
        self.away_defense: Dict[int, float] = {}
        self.league_avg_home_goals: float = 1.45
        self.league_avg_away_goals: float = 1.15

    def fit_team_strengths(self, team_stats: Dict[int, Dict[str, float]]):
        """
        Updates team attack and defense relative parameters.
        team_stats mapping: team_id -> {'goals_scored_avg': float, 'goals_conceded_avg': float}
        """
        for team_id, stats in team_stats.items():
            scored = stats.get('goals_scored_avg', 1.3)
            conceded = stats.get('goals_conceded_avg', 1.3)
            self.home_attack[team_id] = max(scored / self.league_avg_home_goals, 0.2)
            self.home_defense[team_id] = max(conceded / self.league_avg_away_goals, 0.2)
            self.away_attack[team_id] = max(scored / self.league_avg_away_goals, 0.2)
            self.away_defense[team_id] = max(conceded / self.league_avg_home_goals, 0.2)

    def calculate_expected_goals(self, home_team_id: int, away_team_id: int) -> Tuple[float, float]:
        att_h = self.home_attack.get(home_team_id, 1.0)
        def_a = self.away_defense.get(away_team_id, 1.0)
        att_a = self.away_attack.get(away_team_id, 1.0)
        def_h = self.home_defense.get(home_team_id, 1.0)

        exp_home = att_h * def_a * self.league_avg_home_goals
        exp_away = att_a * def_h * self.league_avg_away_goals
        return max(exp_home, 0.1), max(exp_away, 0.1)

    def _poisson_pmf(self, k: int, lam: float) -> float:
        return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)

    def generate_score_matrix(self, lam_home: float, lam_away: float) -> Dict[Tuple[int, int], float]:
        matrix = {}
        for i in range(self.max_goals + 1):
            p_i = self._poisson_pmf(i, lam_home)
            for j in range(self.max_goals + 1):
                p_j = self._poisson_pmf(j, lam_away)
                matrix[(i, j)] = p_i * p_j
        
        # Proper tail normalization so sum P(i, j) == 1.0
        total_mass = sum(matrix.values())
        if total_mass > 0:
            for k in matrix:
                matrix[k] /= total_mass

        return matrix


    def predict_markets(self, home_team_id: int, away_team_id: int) -> Dict[str, Any]:
        exp_home, exp_away = self.calculate_expected_goals(home_team_id, away_team_id)
        matrix = self.generate_score_matrix(exp_home, exp_away)

        p_home = 0.0
        p_draw = 0.0
        p_away = 0.0

        p_btts_yes = 0.0
        p_btts_no = 0.0

        total_goals_prob = {0.5: 0.0, 1.5: 0.0, 2.5: 0.0, 3.5: 0.0}

        for (i, j), prob in matrix.items():
            # 1X2
            if i > j:
                p_home += prob
            elif i == j:
                p_draw += prob
            else:
                p_away += prob

            # BTTS
            if i > 0 and j > 0:
                p_btts_yes += prob
            else:
                p_btts_no += prob

            # Goals Over/Under
            total_goals = i + j
            for line in total_goals_prob:
                if total_goals > line:
                    total_goals_prob[line] += prob

        # Normalize 1X2
        total_1x2 = p_home + p_draw + p_away
        p_home /= total_1x2
        p_draw /= total_1x2
        p_away /= total_1x2

        return {
            "expected_home_goals": round(exp_home, 3),
            "expected_away_goals": round(exp_away, 3),
            # 1X2
            "p_home": round(p_home, 4),
            "p_draw": round(p_draw, 4),
            "p_away": round(p_away, 4),
            # Over/Under
            "p_over_0_5": round(total_goals_prob[0.5], 4),
            "p_under_0_5": round(1.0 - total_goals_prob[0.5], 4),
            "p_over_1_5": round(total_goals_prob[1.5], 4),
            "p_under_1_5": round(1.0 - total_goals_prob[1.5], 4),
            "p_over_2_5": round(total_goals_prob[2.5], 4),
            "p_under_2_5": round(1.0 - total_goals_prob[2.5], 4),
            "p_over_3_5": round(total_goals_prob[3.5], 4),
            "p_under_3_5": round(1.0 - total_goals_prob[3.5], 4),
            # BTTS
            "p_btts_yes": round(p_btts_yes, 4),
            "p_btts_no": round(p_btts_no, 4),
        }
