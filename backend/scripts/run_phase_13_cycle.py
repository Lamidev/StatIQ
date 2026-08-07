import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.session import SessionLocal, engine
from app.db.models import Base
from app.predictions.reconciler import MatchReconciliationEngine
from app.evaluation.drift_monitor import ModelDriftMonitorEngine
from app.monitoring.health_check import PipelineHealthCheckEngine

def main():
    print("=" * 80)
    print("MATCHIQ PHASE 13 — PRODUCTION VALIDATION & RELIABILITY CYCLE")
    print("=" * 80)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Automated Match Reconciliation
        print("\n[1/3] Running Automated Match Reconciliation...")
        reconciler = MatchReconciliationEngine(db)
        recon_res = reconciler.reconcile_completed_predictions()
        print(f" -> Reconciled Predictions: {recon_res['reconciled_count']}")
        print(f" -> Accuracy: {recon_res['accuracy_pct']}%")
        print(f" -> Brier Score: {recon_res['avg_brier_score']}")
        print(f" -> Log Loss: {recon_res['avg_log_loss']}")
        print(f" -> Market Bets Reconciled: {recon_res['market_ledger']['reconciled_market_bets']}, Net P&L: {recon_res['market_ledger']['net_pnl']} units")

        # 2. Model & Calibration Drift Monitor
        print("\n[2/3] Running Model Drift & Calibration Health Audit...")
        drift_monitor = ModelDriftMonitorEngine(db)
        drift_res = drift_monitor.get_full_drift_report()
        print(f" -> Overall Drift Status: {drift_res['overall_status']}")
        print(f" -> 30-Day Window: Acc={drift_res['rolling_30_days']['accuracy_pct']}%, ECE={drift_res['rolling_30_days']['ece']}, Status={drift_res['rolling_30_days']['status']}")

        # 3. Data Quality & Pipeline Health Check
        print("\n[3/3] Running Data Quality & Pipeline Health Audit...")
        checker = PipelineHealthCheckEngine(db)
        health_res = checker.run_health_check()
        print(f" -> Pipeline Status: {health_res['pipeline_status']}")
        print(f" -> Unpredicted Upcoming Fixtures: {health_res['unpredicted_upcoming_fixtures_count']}")
        print(f" -> Issues Found: {health_res['issues']}")

        print("\n" + "=" * 80)
        print("PHASE 13 CYCLE COMPLETED SUCCESSFULLY")
        print("=" * 80)
    finally:
        db.close()

if __name__ == "__main__":
    main()
