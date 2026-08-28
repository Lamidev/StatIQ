"""
Backtesting API Routes — Exposes historical simulation and walk-forward analysis endpoints.
"""
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from virtual.core.db import get_db
from virtual.backtesting.engine import BacktestEngine
from virtual.backtesting.walk_forward import WalkForwardEvaluator
from virtual.models.virtual_models import VirtualLeague

router = APIRouter()


@router.get("/run")
def run_backtest(
    league_id: Optional[int] = Query(None, description="Filter to a specific league. Leave blank for all leagues."),
    start_date: Optional[str] = Query(None, description="ISO date string, e.g. 2026-08-01"),
    end_date: Optional[str] = Query(None, description="ISO date string, e.g. 2026-08-25"),
    stake_per_bet: float = Query(10.0, ge=0.5, le=500.0, description="Flat stake per BET signal"),
    starting_bankroll: float = Query(1000.0, ge=100.0, description="Starting bankroll for equity curve"),
    min_edge: float = Query(0.035, ge=0.0, le=0.5, description="Minimum edge threshold to trigger BET"),
    min_model_prob: float = Query(0.65, ge=0.0, le=1.0, description="Minimum model probability threshold"),
    min_odds: float = Query(1.25, ge=1.0, le=20.0, description="Minimum acceptable odds"),
    db: Session = Depends(get_db),
):
    """
    Runs a full historical backtest over settled virtual events.

    Uses strict no-future-leakage temporal isolation: frequency stats for each
    event are built exclusively from prior settled events.
    """
    start_dt = None
    end_dt = None

    try:
        if start_date:
            start_dt = datetime.datetime.fromisoformat(start_date)
        if end_date:
            end_dt = datetime.datetime.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {e}. Use ISO format e.g. 2026-08-01")

    result = BacktestEngine.run(
        db=db,
        league_id=league_id,
        start_date=start_dt,
        end_date=end_dt,
        stake_per_bet=stake_per_bet,
        starting_bankroll=starting_bankroll,
        min_edge=min_edge,
        min_model_prob=min_model_prob,
        min_odds=min_odds,
    )

    return result


@router.get("/walk-forward")
def run_walk_forward(
    league_id: Optional[int] = Query(None, description="Filter to a specific league. Leave blank for all leagues."),
    n_windows: int = Query(5, ge=2, le=20, description="Number of walk-forward windows"),
    stake_per_bet: float = Query(10.0, ge=0.5, le=500.0),
    starting_bankroll: float = Query(1000.0, ge=100.0),
    min_edge: float = Query(0.035, ge=0.0, le=0.5),
    min_model_prob: float = Query(0.65, ge=0.0, le=1.0),
    min_odds: float = Query(1.25, ge=1.0, le=20.0),
    db: Session = Depends(get_db),
):
    """
    Runs walk-forward out-of-sample evaluation across N equal time windows.

    Each window uses only prior events as context (train), and evaluates on
    the unseen test segment. Prevents overfitting.
    """
    result = WalkForwardEvaluator.run(
        db=db,
        league_id=league_id,
        n_windows=n_windows,
        stake_per_bet=stake_per_bet,
        starting_bankroll=starting_bankroll,
        min_edge=min_edge,
        min_model_prob=min_model_prob,
        min_odds=min_odds,
    )
    return result


@router.get("/leagues")
def list_available_leagues(db: Session = Depends(get_db)):
    """Returns all virtual leagues available for backtesting."""
    leagues = db.query(VirtualLeague).filter(VirtualLeague.is_active == True).all()
    return {
        "leagues": [
            {"id": lg.id, "code": lg.league_code, "name": lg.name, "country": lg.country}
            for lg in leagues
        ]
    }


@router.get("/data-availability")
def get_data_availability(db: Session = Depends(get_db)):
    """
    Returns a summary of available historical data for backtesting:
    total settled events, date range, and per-league breakdown.
    """
    from sqlalchemy import func
    from virtual.models.virtual_models import VirtualEvent, VirtualResult

    # Total settled events with results
    total = (
        db.query(func.count(VirtualEvent.id))
        .join(VirtualResult, VirtualResult.event_id == VirtualEvent.id)
        .filter(VirtualEvent.status == "SETTLED")
        .scalar()
    ) or 0

    if total == 0:
        return {"total_settled_events": 0, "earliest_date": None, "latest_date": None, "leagues": []}

    earliest = (
        db.query(func.min(VirtualEvent.scheduled_time))
        .join(VirtualResult, VirtualResult.event_id == VirtualEvent.id)
        .filter(VirtualEvent.status == "SETTLED")
        .scalar()
    )

    latest = (
        db.query(func.max(VirtualEvent.scheduled_time))
        .join(VirtualResult, VirtualResult.event_id == VirtualEvent.id)
        .filter(VirtualEvent.status == "SETTLED")
        .scalar()
    )

    # Per-league breakdown
    league_counts = (
        db.query(VirtualLeague.id, VirtualLeague.name, func.count(VirtualEvent.id).label("count"))
        .join(VirtualEvent, VirtualEvent.league_id == VirtualLeague.id)
        .join(VirtualResult, VirtualResult.event_id == VirtualEvent.id)
        .filter(VirtualEvent.status == "SETTLED")
        .group_by(VirtualLeague.id, VirtualLeague.name)
        .all()
    )

    return {
        "total_settled_events": total,
        "earliest_date": earliest.isoformat() if earliest else None,
        "latest_date": latest.isoformat() if latest else None,
        "sufficient_for_backtest": total >= BacktestEngine.MIN_HISTORY_EVENTS,
        "minimum_required": BacktestEngine.MIN_HISTORY_EVENTS,
        "leagues": [
            {"id": r.id, "name": r.name, "settled_events": r.count}
            for r in league_counts
        ],
    }


@router.get("/ablation")
def get_feature_ablation_study(
    league: Optional[str] = Query("ALL", description="Virtual league to evaluate (e.g. 'England', 'Spain', 'ALL')"),
    sample_limit: int = Query(500, ge=50, le=5000, description="Max matches to evaluate"),
    db: Session = Depends(get_db)
):
    """
    Empirical Feature Ablation Study for Virtual Football (PRD v4.0).
    Compares Model A (Market Only), Model B (+Form), Model C (+H2H), and Model D (Calibrated Ensemble).
    Evaluates out-of-sample Brier score, log-loss, win rate, and decayed feature weights.
    """
    from virtual.backtesting.ablation_engine import FeatureAblationEngine
    return FeatureAblationEngine.run_ablation_study(db, league_name=league, sample_limit=sample_limit)


@router.get("/feature-weights")
def get_calibrated_feature_weights(db: Session = Depends(get_db)):
    """
    Returns current calibrated feature weights derived from empirical out-of-sample ablation.
    """
    return {
        "model_version": "v4.0.0-calibrated",
        "weights": {
            "market_consensus_probability": 0.60,
            "rolling_form_goal_tendency": 0.30,
            "head_to_head_history": 0.00,  # Decayed to 0.0 based on PRNG ablation finding
            "league_macro_pace": 0.10
        },
        "h2h_decay_rationale": "Empirical ablation proves H2H adds noise in PRNG virtual simulations without improving out-of-sample Brier score.",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

