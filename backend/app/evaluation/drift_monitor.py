import math
import datetime
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy import select, and_

from app.db.models import LivePredictionLedger

class ModelDriftMonitorEngine:
    """
    Phase 13 Model & Calibration Drift Monitor Engine.
    Tracks rolling 30-day, 90-day, and 180-day performance windows:
    - 1X2 Accuracy (%)
    - Brier Score
    - Log Loss
    - Expected Calibration Error (ECE)
    - Automated Drift Health Alerts (STABLE, WARNING, CRITICAL_DRIFT)
    """
    def __init__(self, session):
        self.session = session

    def compute_rolling_drift(self, window_days: int = 30) -> Dict[str, Any]:
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=window_days)
        
        stmt = select(LivePredictionLedger).where(
            and_(
                LivePredictionLedger.status.in_(["WIN", "LOSS"]),
                LivePredictionLedger.resolved_at >= cutoff_date
            )
        )
        predictions = list(self.session.execute(stmt).scalars().all())

        if not predictions:
            return {
                "window_days": window_days,
                "sample_size": 0,
                "accuracy_pct": None,
                "brier_score": None,
                "log_loss": None,
                "ece": None,
                "status": "INSUFFICIENT_DATA"
            }

        correct_count = 0
        total_brier = 0.0
        total_log_loss = 0.0
        confidences = []
        accuracies = []

        for p in predictions:
            probs = [p.prob_home, p.prob_draw, p.prob_away]
            max_p = max(probs)
            max_idx = probs.index(max_p)
            outcomes = ["HOME", "DRAW", "AWAY"]
            predicted = outcomes[max_idx]

            actual = p.actual_outcome
            is_correct = (predicted == actual)
            if is_correct:
                correct_count += 1

            y_vec = [1.0 if outcomes[k] == actual else 0.0 for k in range(3)]
            brier_val = sum((probs[k] - y_vec[k]) ** 2 for k in range(3))
            total_brier += brier_val

            p_actual = probs[outcomes.index(actual)] if actual in outcomes else 0.333
            p_safe = max(p_actual, 1e-15)
            total_log_loss += -math.log(p_safe)

            confidences.append(max_p)
            accuracies.append(1.0 if is_correct else 0.0)

        n = len(predictions)
        acc_pct = (correct_count / n) * 100.0
        avg_brier = total_brier / n
        avg_log_loss = total_log_loss / n

        # Expected Calibration Error (ECE) calculation with 10 bins
        ece_val = self._calculate_ece(confidences, accuracies)

        # Health Alert Status
        if ece_val > 0.05 or acc_pct < 42.0:
            health_status = "CRITICAL_DRIFT"
        elif ece_val > 0.03 or acc_pct < 45.0:
            health_status = "WARNING"
        else:
            health_status = "STABLE"

        return {
            "window_days": window_days,
            "sample_size": n,
            "accuracy_pct": round(acc_pct, 2),
            "brier_score": round(avg_brier, 4),
            "log_loss": round(avg_log_loss, 4),
            "ece": round(ece_val, 4),
            "status": health_status
        }

    def _calculate_ece(self, confidences: List[float], accuracies: List[float], n_bins: int = 10) -> float:
        if not confidences:
            return 0.0

        bins = np.linspace(0.0, 1.0, n_bins + 1)
        conf_arr = np.array(confidences)
        acc_arr = np.array(accuracies)
        n = len(confidences)
        ece = 0.0

        for i in range(n_bins):
            bin_lower, bin_upper = bins[i], bins[i + 1]
            in_bin = (conf_arr > bin_lower) & (conf_arr <= bin_upper)
            bin_size = np.sum(in_bin)

            if bin_size > 0:
                bin_acc = np.mean(acc_arr[in_bin])
                bin_conf = np.mean(conf_arr[in_bin])
                ece += (bin_size / n) * abs(bin_acc - bin_conf)

        return float(ece)

    def get_full_drift_report(self) -> Dict[str, Any]:
        """
        Runs rolling 30-day, 90-day, and 180-day drift evaluation.
        """
        r30 = self.compute_rolling_drift(30)
        r90 = self.compute_rolling_drift(90)
        r180 = self.compute_rolling_drift(180)

        # Determine overall system drift status
        statuses = [r30["status"], r90["status"], r180["status"]]
        if "CRITICAL_DRIFT" in statuses:
            overall = "CRITICAL_DRIFT"
        elif "WARNING" in statuses:
            overall = "WARNING"
        else:
            overall = "STABLE"

        return {
            "overall_status": overall,
            "report_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "rolling_30_days": r30,
            "rolling_90_days": r90,
            "rolling_180_days": r180
        }
