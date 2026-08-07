import numpy as np
from scipy.optimize import minimize
from typing import Tuple, List

class WeightedEnsemblePredictor:
    """
    Weighted Ensemble Predictor combining Statistical Models (Dixon-Coles) and Machine Learning (XGBoost).
        P_ensemble = w * P_DixonColes + (1 - w) * P_XGBoost
    Fits weight w in [0, 1] strictly out-of-sample on expanding past historical windows (t < T).
    """
    def __init__(self, weight_dc: float = 0.6):
        self.weight_dc = weight_dc

    def fit(self, past_dc_probs: List[Tuple[float, float, float]], past_xgb_probs: List[Tuple[float, float, float]], past_actuals: List[int]):
        """
        Fits optimal blending weight w on past match historical predictions.
        """
        if len(past_dc_probs) < 50:
            self.weight_dc = 0.6
            return

        dc_arr = np.array(past_dc_probs)
        xgb_arr = np.array(past_xgb_probs)
        act_arr = np.array(past_actuals)

        eps = 1e-6

        def ensemble_loss(w_val: float) -> float:
            w = max(min(w_val[0], 1.0), 0.0)
            ens_p = w * dc_arr + (1.0 - w) * xgb_arr
            ens_p = np.clip(ens_p, eps, 1.0 - eps)
            ens_p /= np.sum(ens_p, axis=1, keepdims=True)
            
            picked = ens_p[np.arange(len(act_arr)), act_arr]
            loss = -np.mean(np.log(np.clip(picked, eps, 1.0)))
            return float(loss)

        res = minimize(ensemble_loss, x0=[0.5], method="Nelder-Mead", bounds=[(0.0, 1.0)])
        if res.success:
            self.weight_dc = float(np.clip(res.x[0], 0.0, 1.0))

    def predict(self, p_dc: Tuple[float, float, float], p_xgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
        w = self.weight_dc
        p_h = w * p_dc[0] + (1.0 - w) * p_xgb[0]
        p_d = w * p_dc[1] + (1.0 - w) * p_xgb[1]
        p_a = w * p_dc[2] + (1.0 - w) * p_xgb[2]
        
        tot = p_h + p_d + p_a
        return p_h / tot, p_d / tot, p_a / tot
