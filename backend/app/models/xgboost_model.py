import numpy as np
from typing import List, Dict, Any, Tuple

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

class XGBoostPredictor:
    """
    Multi-Class XGBoost Model for Football Prediction.
    Trained strictly out-of-sample on expanding historical point-in-time feature vectors (t < T).
    Outputs 1X2 probabilities (p_home, p_draw, p_away).
    """
    def __init__(self, max_depth: int = 3, learning_rate: float = 0.05, n_estimators: int = 80):
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.n_estimators = n_estimators
        self.model = None

    def fit(self, X_train: np.ndarray, y_train: np.ndarray):
        """
        Fits XGBoost classifier on past feature matrix X_train (N x F) and labels y_train (N,).
        Labels: 0 = HOME_TEAM, 1 = DRAW, 2 = AWAY_TEAM
        """
        if not XGBOOST_AVAILABLE or len(X_train) < 50:
            return

        self.model = xgb.XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            n_estimators=self.n_estimators,
            eval_metric="mlogloss",
            random_state=42
        )
        self.model.fit(X_train, y_train)

    def predict_probabilities(self, feature_vector_arr: np.ndarray, fallback_probs: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Predicts out-of-sample 1X2 probabilities for a single fixture feature vector.
        Falls back to fallback_probs (e.g. Calibrated Dixon-Coles) if model is not yet fitted.
        """
        if self.model is None or not XGBOOST_AVAILABLE:
            return fallback_probs

        probs = self.model.predict_proba(feature_vector_arr.reshape(1, -1))[0]
        # Softmax safety check
        total = float(np.sum(probs))
        if total <= 0:
            return fallback_probs
        return float(probs[0] / total), float(probs[1] / total), float(probs[2] / total)
