import math
from typing import Dict, Tuple, Any
from app.models.poisson import PoissonEngine

class DixonColesEngine(PoissonEngine):
    """
    Dixon-Coles Adjusted Bivariate Model for Football Prediction.
    Extends Independent Poisson with low-score correlation parameter rho (rho)
    to accurately model draw inflation and low-scoring matches (0-0, 1-0, 0-1, 1-1).
    """
    def __init__(self, max_goals: int = 10, rho: float = -0.13, time_decay_xi: float = 0.0035):
        super().__init__(max_goals=max_goals)
        self.rho = rho
        self.time_decay_xi = time_decay_xi

    def _tau_adjustment(self, x: int, y: int, lam: float, mu: float) -> float:
        """
        Dixon-Coles tau factor for low scores (0,0), (1,0), (0,1), (1,1).
        """
        if x == 0 and y == 0:
            return 1.0 - (lam * mu * self.rho)
        elif x == 1 and y == 0:
            return 1.0 + (mu * self.rho)
        elif x == 0 and y == 1:
            return 1.0 + (lam * self.rho)
        elif x == 1 and y == 1:
            return 1.0 - self.rho
        else:
            return 1.0

    def generate_score_matrix(self, lam_home: float, lam_away: float) -> Dict[Tuple[int, int], float]:
        matrix = {}
        for i in range(self.max_goals + 1):
            p_i = self._poisson_pmf(i, lam_home)
            for j in range(self.max_goals + 1):
                p_j = self._poisson_pmf(j, lam_away)
                tau = self._tau_adjustment(i, j, lam_home, lam_away)
                matrix[(i, j)] = max(p_i * p_j * tau, 0.0)

        # Proper tail normalization so sum P(i, j) == 1.0
        total_mass = sum(matrix.values())
        if total_mass > 0:
            for k in matrix:
                matrix[k] /= total_mass

        return matrix

