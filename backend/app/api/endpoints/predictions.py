import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db.session import get_db
from app.db.models import LivePredictionLedger, Fixture
from app.predictions.shadow_engine import LiveShadowEngine

router = APIRouter()

@router.get("/stats")
def get_live_shadow_stats(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db)):

    """
    Returns live shadow prediction performance statistics over rolling X days.
    """
    engine = LiveShadowEngine(db)
    return engine.get_performance_stats(days=days)

@router.get("/today")
def get_today_predictions(db: Session = Depends(get_db)):
    """
    Returns live predictions scheduled for today.
    """
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)

    stmt = (
        select(LivePredictionLedger, Fixture)
        .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
        .where(
            and_(
                Fixture.kickoff_datetime >= today_start,
                Fixture.kickoff_datetime < today_end
            )
        )
        .order_by(Fixture.kickoff_datetime.asc())
    )
    results = db.execute(stmt).all()

    items = []
    for pred, fix in results:
        items.append({
            "fixture_id": fix.id,
            "match": f"{fix.home_team_id} vs {fix.away_team_id}",
            "competition": fix.competition_code,
            "kickoff_datetime": fix.kickoff_datetime.isoformat(),
            "status": pred.status,
            "prob_home": round(pred.prob_home * 100, 2),
            "prob_draw": round(pred.prob_draw * 100, 2),
            "prob_away": round(pred.prob_away * 100, 2),
            "prob_over_2_5": round((pred.prob_over_2_5 or 0) * 100, 2),
            "prob_btts_yes": round((pred.prob_btts_yes or 0) * 100, 2),
            "model_version": pred.model_version
        })
    return {"total": len(items), "predictions": items}

@router.get("/upcoming")
def get_upcoming_predictions(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    """
    Returns all pending pre-kickoff live shadow predictions.
    """
    stmt = (
        select(LivePredictionLedger, Fixture)
        .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
        .where(LivePredictionLedger.status == "PENDING")
        .order_by(Fixture.kickoff_datetime.asc())
        .limit(limit)
    )
    results = db.execute(stmt).all()

    items = []
    for pred, fix in results:
        items.append({
            "fixture_id": fix.id,
            "competition": fix.competition_code,
            "kickoff_datetime": fix.kickoff_datetime.isoformat(),
            "status": pred.status,
            "prob_home": round(pred.prob_home * 100, 2),
            "prob_draw": round(pred.prob_draw * 100, 2),
            "prob_away": round(pred.prob_away * 100, 2),
            "prediction_timestamp": pred.prediction_timestamp.isoformat(),
            "snapshot_hash": pred.feature_snapshot_hash
        })
    return {"total": len(items), "predictions": items}


@router.get("/completed")
def get_completed_predictions(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    """
    Returns resolved live shadow predictions with actual results.
    """
    stmt = (
        select(LivePredictionLedger, Fixture)
        .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
        .where(LivePredictionLedger.status == "COMPLETED")
        .order_by(LivePredictionLedger.resolved_at.desc())
        .limit(limit)
    )
    results = db.execute(stmt).all()

    items = []
    for pred, fix in results:
        items.append({
            "fixture_id": fix.id,
            "competition": fix.competition_code,
            "kickoff_datetime": fix.kickoff_datetime.isoformat(),
            "prob_home": round(pred.prob_home * 100, 2),
            "prob_draw": round(pred.prob_draw * 100, 2),
            "prob_away": round(pred.prob_away * 100, 2),
            "actual_score": f"{pred.actual_home_score} - {pred.actual_away_score}",
            "actual_result": pred.actual_result,
            "is_correct": pred.is_correct,
            "brier_score": round(pred.brier_score, 4) if pred.brier_score is not None else None,
            "log_loss": round(pred.log_loss, 4) if pred.log_loss is not None else None
        })
    return {"total": len(items), "completed_predictions": items}
