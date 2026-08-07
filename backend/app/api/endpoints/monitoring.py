from typing import Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.predictions.reconciler import MatchReconciliationEngine
from app.evaluation.drift_monitor import ModelDriftMonitorEngine
from app.monitoring.health_check import PipelineHealthCheckEngine

router = APIRouter()

@router.post("/reconcile")
def trigger_match_reconciliation(db: Session = Depends(get_db)):
    """
    Phase 13 Automated Match Reconciliation API.
    Reconciles completed fixtures against pre-kickoff live predictions & market bets.
    """
    engine = MatchReconciliationEngine(db)
    return engine.reconcile_completed_predictions()

@router.get("/drift")
def get_model_drift_report(db: Session = Depends(get_db)):
    """
    Phase 13 Model Drift & Calibration Health API.
    Returns rolling 30-day, 90-day, and 180-day accuracy, Brier Score, Log Loss, and ECE.
    """
    monitor = ModelDriftMonitorEngine(db)
    return monitor.get_full_drift_report()

@router.get("/pipeline-health")
def get_pipeline_health_report(db: Session = Depends(get_db)):
    """
    Phase 13 Data Quality & Pipeline Health Check API.
    """
    checker = PipelineHealthCheckEngine(db)
    return checker.run_health_check()
