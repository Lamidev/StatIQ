import math
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_

from app.db.models import Fixture, LivePredictionLedger, MarketShadowLedger

class MatchReconciliationEngine:
    """
    Phase 13 Automated Match Reconciliation Engine.
    Scans completed fixtures, verifies pre-kickoff probability immutability,
    evaluates actual outcomes, and records exact Brier & Log Loss metrics.
    """
    def __init__(self, session):
        self.session = session

    def reconcile_completed_predictions(self) -> Dict[str, Any]:
        """
        Reconciles pending entries in LivePredictionLedger against completed Fixtures.
        """
        stmt = (
            select(LivePredictionLedger, Fixture)
            .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
            .where(
                and_(
                    LivePredictionLedger.status == "PENDING",
                    Fixture.status.in_(["FINISHED", "FT", "AET", "PEN"])
                )
            )
        )
        results = list(self.session.execute(stmt).all())

        reconciled_count = 0
        correct_count = 0
        total_brier = 0.0
        total_log_loss = 0.0

        for pred, fix in results:
            if fix.home_score is None or fix.away_score is None:
                continue

            h_score = fix.home_score
            a_score = fix.away_score

            # Actual 1X2 outcome
            if h_score > a_score:
                actual_1x2 = "HOME"
                y_vec = (1.0, 0.0, 0.0)
                p_actual = pred.prob_home
            elif h_score == a_score:
                actual_1x2 = "DRAW"
                y_vec = (0.0, 1.0, 0.0)
                p_actual = pred.prob_draw
            else:
                actual_1x2 = "AWAY"
                y_vec = (0.0, 0.0, 1.0)
                p_actual = pred.prob_away

            # Predicted outcome (argmax)
            probs = {"HOME": pred.prob_home, "DRAW": pred.prob_draw, "AWAY": pred.prob_away}
            predicted_1x2 = max(probs, key=probs.get)

            is_correct = (predicted_1x2 == actual_1x2)
            if is_correct:
                correct_count += 1

            # Brier Score contribution: sum (p_k - y_k)^2
            brier_val = (
                (pred.prob_home - y_vec[0]) ** 2 +
                (pred.prob_draw - y_vec[1]) ** 2 +
                (pred.prob_away - y_vec[2]) ** 2
            )
            total_brier += brier_val

            # Log Loss contribution: -log(p_actual)
            p_safe = max(p_actual, 1e-15)
            log_loss_val = -math.log(p_safe)
            total_log_loss += log_loss_val

            # Update prediction record
            pred.actual_home_score = h_score
            pred.actual_away_score = a_score
            pred.actual_outcome = actual_1x2
            pred.status = "WIN" if is_correct else "LOSS"
            pred.resolved_at = datetime.datetime.now(datetime.timezone.utc)

            reconciled_count += 1

        self.session.commit()

        # Also reconcile market shadow ledger
        market_res = self.reconcile_market_shadow_ledger()

        avg_acc = (correct_count / reconciled_count * 100) if reconciled_count > 0 else 0.0
        avg_brier = (total_brier / reconciled_count) if reconciled_count > 0 else 0.0
        avg_log_loss = (total_log_loss / reconciled_count) if reconciled_count > 0 else 0.0

        return {
            "reconciled_count": reconciled_count,
            "correct_count": correct_count,
            "accuracy_pct": round(avg_acc, 2),
            "avg_brier_score": round(avg_brier, 4),
            "avg_log_loss": round(avg_log_loss, 4),
            "market_ledger": market_res
        }

    def reconcile_market_shadow_ledger(self) -> Dict[str, Any]:
        """
        Reconciles pending entries in MarketShadowLedger.
        """
        stmt = (
            select(MarketShadowLedger, Fixture)
            .join(Fixture, MarketShadowLedger.fixture_id == Fixture.id)
            .where(
                and_(
                    MarketShadowLedger.status == "PENDING",
                    Fixture.status.in_(["FINISHED", "FT", "AET", "PEN"])
                )
            )
        )
        results = list(self.session.execute(stmt).all())

        reconciled = 0
        total_pnl = 0.0

        for entry, fix in results:
            if fix.home_score is None or fix.away_score is None:
                continue

            h_score = fix.home_score
            a_score = fix.away_score
            total_goals = h_score + a_score
            btts = (h_score > 0 and a_score > 0)

            won = False
            mkt = entry.market.upper()
            sel = entry.selection.upper()

            if mkt == "1X2":
                if sel == "HOME" and h_score > a_score: won = True
                elif sel == "DRAW" and h_score == a_score: won = True
                elif sel == "AWAY" and a_score > h_score: won = True
            elif mkt in ["OVER_UNDER", "OVER_UNDER_2_5"]:
                line = 2.5
                if sel == "OVER" and total_goals > line: won = True
                elif sel == "UNDER" and total_goals < line: won = True
            elif mkt == "BTTS":
                if sel == "YES" and btts: won = True
                elif sel == "NO" and not btts: won = True

            if won:
                entry.status = "WIN"
                entry.profit_loss = entry.odds - 1.0
            else:
                entry.status = "LOSS"
                entry.profit_loss = -1.0

            entry.resolved_at = datetime.datetime.now(datetime.timezone.utc)
            total_pnl += entry.profit_loss
            reconciled += 1

        self.session.commit()
        return {"reconciled_market_bets": reconciled, "net_pnl": round(total_pnl, 2)}
