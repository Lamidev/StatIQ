import math
import numpy as np
from scipy.optimize import minimize
from typing import List, Tuple

class MultinomialTemperatureScaler:
    """
    Multinomial Temperature Scaling for 1X2 Match Probabilities.
    Scales raw probability logits via a temperature parameter T > 0:
        P_i' = exp(z_i / T) / sum(exp(z_j / T))
    where z_i = log(p_i).
    Fitted strictly out-of-sample on expanding historical windows (t < T) to minimize Log Loss.
    Preserves ordinal ranking (argmax P_i' == argmax P_i) while fixing overconfidence.
    """
    def __init__(self, temperature: float = 1.0):
        self.temperature = max(temperature, 0.1)

    def fit(self, historical_probs: List[Tuple[float, float, float]], historical_actuals: List[int]):
        """
        Fits temperature parameter T on expanding historical past predictions.
        historical_probs: List of (p_home, p_draw, p_away) tuples
        historical_actuals: List of actual outcomes (0: Home, 1: Draw, 2: Away)
        """
        if len(historical_probs) < 30:
            self.temperature = 1.0
            return

        probs_arr = np.array(historical_probs)
        actuals_arr = np.array(historical_actuals)

        # Convert probabilities to log-odds (logits)
        eps = 1e-6
        probs_clipped = np.clip(probs_arr, eps, 1.0 - eps)
        logits = np.log(probs_clipped)

        def nll_loss(t_val: float) -> float:
            t = max(t_val[0], 0.1)
            scaled_logits = logits / t
            # Softmax
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits, axis=1, keepdims=True))
            scaled_probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
            
            # Cross entropy loss
            picked_probs = scaled_probs[np.arange(len(actuals_arr)), actuals_arr]
            loss = -np.mean(np.log(np.clip(picked_probs, eps, 1.0)))
            return float(loss)

        res = minimize(nll_loss, x0=[1.0], method="Nelder-Mead", bounds=[(0.1, 5.0)])
        if res.success and res.x[0] > 0.1:
            self.temperature = float(res.x[0])

    def calibrate(self, probs: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Applies temperature scaling to a single raw (p_home, p_draw, p_away) distribution.
        """
        if self.temperature == 1.0:
            return probs

        eps = 1e-6
        p_arr = np.clip(np.array(probs), eps, 1.0 - eps)
        logits = np.log(p_arr) / self.temperature
        
        # Softmax
        exp_l = np.exp(logits - np.max(logits))
        scaled_p = exp_l / np.sum(exp_l)
        
        return float(scaled_p[0]), float(scaled_p[1]), float(scaled_p[2])
