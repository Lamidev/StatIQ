from typing import Dict, Any, Tuple

class PredictionScoreEngine:
    """
    Evaluates candidates across Model Probabilities vs Fair Market Consensus.
    Calculates Edge (Delta P), Confidence, and Weighted Composite Score.
    """

    @classmethod
    def score_candidate(
        cls,
        model_prob: float,
        market_prob: float,
        sample_size: int = 250,
        odds: float = 1.80
    ) -> Dict[str, Any]:
        """
        Computes edge, confidence rating, and final composite score.
        """
        edge = round(model_prob - market_prob, 4)
        edge_pct = round(edge * 100.0, 2)

        # Confidence assessment based on sample size and probability range
        if sample_size >= 1000 and 0.55 <= model_prob <= 0.85:
            confidence = "HIGH"
            conf_score = 0.90
        elif sample_size >= 200:
            confidence = "MEDIUM"
            conf_score = 0.75
        else:
            confidence = "LOW"
            conf_score = 0.50

        # Composite score (Weighted combination: 40% Model P, 35% Edge, 25% Calibration/Confidence)
        composite_score = round(
            (model_prob * 0.40) +
            (max(0.0, min(1.0, (edge + 0.10) / 0.20)) * 0.35) +
            (conf_score * 0.25),
            3
        )

        return {
            "model_probability": round(model_prob, 4),
            "market_probability": round(market_prob, 4),
            "edge": edge,
            "edge_pct": edge_pct,
            "confidence": confidence,
            "confidence_score": conf_score,
            "composite_score": composite_score,
            "has_positive_edge": edge > 0.02  # min 2% positive edge
        }
