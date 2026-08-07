import math
from typing import Dict, Tuple, List
from sqlalchemy import select
from app.db.models import Fixture

class EloEngine:
    """
    Dynamic Elo Rating Engine for Football.
    Features:
    - Configurable initial ratings, K-factor, venue advantage, and season mean regression.
    - Margin of victory multiplier
    """
    def __init__(
        self,
        initial_elo: float = 1500.0,
        k_factor: float = 32.0,
        home_advantage: float = 80.0,
        regression_factor: float = 0.25
    ):
        self.initial_elo = initial_elo
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.regression_factor = regression_factor
        self.ratings: Dict[int, float] = {}

    def reset(self):
        self.ratings.clear()


    def get_rating(self, team_id: int) -> float:
        return self.ratings.get(team_id, self.initial_elo)

    def predict_probabilities(self, home_team_id: int, away_team_id: int) -> Tuple[float, float, float]:
        r_home = self.get_rating(home_team_id) + self.home_advantage
        r_away = self.get_rating(away_team_id)

        # Expected score for home team
        e_home = 1.0 / (1.0 + math.pow(10.0, (r_away - r_home) / 400.0))
        
        # Empirical draw estimation based on rating difference
        diff = abs(r_home - r_away)
        p_draw = max(0.26 - (diff / 2000.0), 0.15)
        
        # Distribute remaining probability proportionally
        rem = 1.0 - p_draw
        p_home = e_home * rem
        p_away = (1.0 - e_home) * rem

        # Normalize
        total = p_home + p_draw + p_away
        return p_home / total, p_draw / total, p_away / total

    def update_ratings(self, home_team_id: int, away_team_id: int, home_score: int, away_score: int):
        r_home = self.get_rating(home_team_id)
        r_away = self.get_rating(away_team_id)

        p_home, p_draw, p_away = self.predict_probabilities(home_team_id, away_team_id)

        # Actual outcome S
        if home_score > away_score:
            s_home = 1.0
        elif home_score == away_score:
            s_home = 0.5
        else:
            s_home = 0.0

        # Margin of victory multiplier
        goal_diff = abs(home_score - away_score)
        if goal_diff <= 1:
            mult = 1.0
        elif goal_diff == 2:
            mult = 1.5
        else:
            mult = 1.75 + (goal_diff - 3) / 8.0

        delta_home = self.k_factor * mult * (s_home - (p_home + 0.5 * p_draw))
        self.ratings[home_team_id] = r_home + delta_home
        self.ratings[away_team_id] = r_away - delta_home

    def regress_to_mean(self, regression_factor: float = 0.25):
        for team_id in self.ratings:
            self.ratings[team_id] = (1.0 - regression_factor) * self.ratings[team_id] + regression_factor * self.initial_elo
