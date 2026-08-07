import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import unittest
import datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


from app.db.models import Base, Fixture, LivePredictionLedger, MarketShadowLedger
from app.predictions.reconciler import MatchReconciliationEngine
from app.evaluation.drift_monitor import ModelDriftMonitorEngine
from app.monitoring.health_check import PipelineHealthCheckEngine

class TestPhase13(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

        # Seed finished fixture & prediction
        now = datetime.datetime.now(datetime.timezone.utc)
        self.fix1 = Fixture(
            id=2001, provider_external_id="FD_2001", season_id=1, competition_code="PL",
            home_team_id=1, away_team_id=2, kickoff_datetime=now - datetime.timedelta(hours=3),
            status="FINISHED", home_score=2, away_score=1
        )
        self.session.add(self.fix1)
        self.session.commit()

        self.pred1 = LivePredictionLedger(
            fixture_id=2001, model_name="Weighted_Ensemble", model_version="v1.0.0",
            prob_home=0.70, prob_draw=0.20, prob_away=0.10, prob_over_1_5=0.85, prob_over_2_5=0.65, prob_btts_yes=0.60,
            status="PENDING", prediction_timestamp=now - datetime.timedelta(hours=4)
        )

        self.session.add(self.pred1)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_reconciliation_engine(self):
        reconciler = MatchReconciliationEngine(self.session)
        res = reconciler.reconcile_completed_predictions()

        self.assertEqual(res["reconciled_count"], 1)
        self.assertEqual(res["correct_count"], 1)
        self.assertEqual(res["accuracy_pct"], 100.0)

        # Check updated database record
        updated_pred = self.session.execute(
            select(LivePredictionLedger).where(LivePredictionLedger.id == self.pred1.id)
        ).scalar_one()

        self.assertEqual(updated_pred.status, "WIN")
        self.assertEqual(updated_pred.actual_outcome, "HOME")

    def test_drift_monitor_engine(self):
        # Trigger reconciliation first
        reconciler = MatchReconciliationEngine(self.session)
        reconciler.reconcile_completed_predictions()

        drift_monitor = ModelDriftMonitorEngine(self.session)
        report = drift_monitor.get_full_drift_report()

        self.assertIn("overall_status", report)
        self.assertEqual(report["rolling_30_days"]["sample_size"], 1)
        self.assertEqual(report["rolling_30_days"]["accuracy_pct"], 100.0)

    def test_pipeline_health_check(self):
        checker = PipelineHealthCheckEngine(self.session)
        health = checker.run_health_check()

        self.assertIn("pipeline_status", health)
        self.assertEqual(health["finished_fixtures_missing_scores_count"], 0)

if __name__ == "__main__":
    unittest.main()
