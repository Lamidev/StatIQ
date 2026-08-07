from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db.session import get_db
from app.db.models import MarketShadowLedger, Fixture, LivePredictionLedger
from app.markets.market_analyzer import MarketAnalyzerEngine

router = APIRouter()

@router.get("/value-opportunities")
def get_value_opportunities(min_edge: float = Query(default=0.03, ge=0.01), min_ev: float = Query(default=0.05, ge=0.01), db: Session = Depends(get_db)):
    """
    Returns positive EV value bets identified by comparing MatchIQ probabilities vs Bookmaker Odds.
    """
    stmt = (
        select(MarketShadowLedger, Fixture)
        .join(Fixture, MarketShadowLedger.fixture_id == Fixture.id)
        .where(
            and_(
                MarketShadowLedger.status == "PENDING",
                MarketShadowLedger.model_edge >= min_edge,
                MarketShadowLedger.expected_value >= min_ev
            )
        )
        .order_by(MarketShadowLedger.expected_value.desc())
    )
    results = db.execute(stmt).all()

    items = []
    for bet, fix in results:
        items.append({
            "fixture_id": fix.id,
            "match": f"{fix.home_team_id} vs {fix.away_team_id}",
            "competition": fix.competition_code,
            "kickoff_datetime": fix.kickoff_datetime.isoformat(),
            "market": bet.market,
            "selection": bet.selection,
            "bookmaker": bet.bookmaker,
            "odds": bet.odds,
            "model_probability_pct": round(bet.model_probability * 100, 2),
            "implied_probability_pct": round(bet.implied_probability * 100, 2),
            "model_edge_pct": round(bet.model_edge * 100, 2),
            "expected_value_pct": round(bet.expected_value * 100, 2)
        })
    return {"total": len(items), "value_opportunities": items}

@router.get("/stats")
def get_market_performance_stats(db: Session = Depends(get_db)):
    """
    Returns betting ROI, net profit units, win rate, and total value bets metrics.
    """
    engine = MarketAnalyzerEngine(db)
    return engine.get_market_performance_stats()

@router.get("/ledger")
def get_market_ledger(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    """
    Returns history of market value bets with P&L.
    """
    stmt = (
        select(MarketShadowLedger, Fixture)
        .join(Fixture, MarketShadowLedger.fixture_id == Fixture.id)
        .order_by(MarketShadowLedger.created_at.desc())
        .limit(limit)
    )
    results = db.execute(stmt).all()

    items = []
    for bet, fix in results:
        items.append({
            "fixture_id": fix.id,
            "competition": fix.competition_code,
            "market": bet.market,
            "selection": bet.selection,
            "bookmaker": bet.bookmaker,
            "odds": bet.odds,
            "model_probability_pct": round(bet.model_probability * 100, 2),
            "model_edge_pct": round(bet.model_edge * 100, 2),
            "expected_value_pct": round(bet.expected_value * 100, 2),
            "status": bet.status,
            "profit_loss_units": bet.profit_loss
        })
    return {"total": len(items), "market_bets": items}
