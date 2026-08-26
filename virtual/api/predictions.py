from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from virtual.core.db import get_db
from virtual.strategy.signal_generator import SignalGenerator
from virtual.strategy.strategy_registry import StrategyRegistry

router = APIRouter()

@router.get("")
def get_predictions(
    signal: Optional[str] = Query(None),
    limit: int = Query(30, ge=5, le=100),
    db: Session = Depends(get_db)
):
    """
    Returns live generated predictions & BET / SKIP / WAIT signals for upcoming virtual fixtures.
    """
    signals = SignalGenerator.generate_signals_for_upcoming_events(db, limit=limit)
    if signal:
        signals = [s for s in signals if s.get("signal", "").upper() == signal.upper()]

    bet_count = sum(1 for s in signals if s.get("signal") == "BET")
    wait_count = sum(1 for s in signals if s.get("signal") == "WAIT")
    skip_count = sum(1 for s in signals if s.get("signal") == "SKIP")

    return {
        "count": len(signals),
        "summary": {
            "bet_signals": bet_count,
            "wait_signals": wait_count,
            "skip_signals": skip_count
        },
        "predictions": signals
    }

@router.get("/strategies")
def get_strategies():
    """
    Returns registered trading strategies and their lifecycle states.
    """
    return {"strategies": StrategyRegistry.get_all_strategies()}
