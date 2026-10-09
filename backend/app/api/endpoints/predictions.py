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


# ── ADAPTIVE MULTI-MARKET PREDICTION ENDPOINTS ───────────────────────────────

from app.db.models import SportyBetEvent
from app.predictions.adaptive_engine import AdaptiveMultiMarketEngine

@router.get("/adaptive-analysis/{event_id}", summary="Get deep multi-market prediction evaluation for a match")
def get_adaptive_fixture_analysis(
    event_id: str,
    min_prob: float = Query(0.55, ge=0.40, le=0.95),
    min_edge: float = Query(0.02, ge=0.0, le=0.30),
    min_ev: float = Query(0.03, ge=0.0, le=0.50),
    db: Session = Depends(get_db)
):
    ev = db.execute(
        select(SportyBetEvent).where(
            (SportyBetEvent.sporty_event_id == event_id) | (SportyBetEvent.sporty_game_id == event_id)
        )
    ).scalar_one_or_none()

    if not ev:
        return {"error": "Event not found in SportyBet mirror DB", "has_qualified_bet": False}

    event_dict = {
        "event_id": ev.sporty_event_id,
        "game_id": ev.sporty_game_id,
        "home_team": ev.home_team,
        "away_team": ev.away_team,
        "competition": ev.competition_rel.name if ev.competition_rel else "Football",
        "start_time": ev.start_time.isoformat(),
        "markets": []
    }

    for m in ev.markets:
        m_dict = {
            "market_id": m.sporty_market_id,
            "market_name": m.market_name,
            "market_type": m.market_type,
            "specifier": m.specifier,
            "outcomes": []
        }
        for oc in m.outcomes:
            m_dict["outcomes"].append({
                "outcome_id": oc.sporty_outcome_id,
                "selection_name": oc.selection,
                "odds": oc.odds,
                "probability": oc.probability
            })
        event_dict["markets"].append(m_dict)

    engine = AdaptiveMultiMarketEngine(
        min_probability=min_prob,
        min_edge=min_edge,
        min_ev=min_ev
    )
    report = engine.evaluate_fixture(event_dict)

    qualified_out = [
        {
            "market_id": c.market_id,
            "outcome_id": c.outcome_id,
            "market_name": c.market_name,
            "selection_name": c.selection_name,
            "specifier": c.specifier,
            "odds": c.sportybet_odds,
            "model_probability": round(c.model_probability * 100, 1),
            "implied_probability": round(c.normalized_implied_prob * 100, 1),
            "fair_odds": c.fair_odds,
            "edge": f"+{round(c.edge * 100, 1)}%",
            "expected_value": f"+{round(c.expected_value * 100, 1)}%",
            "confidence": c.confidence
        }
        for c in report.qualified_candidates
    ]

    return {
        "event_id": report.event_id,
        "match": f"{report.home_team} vs {report.away_team}",
        "competition": report.competition,
        "kickoff_time": report.kickoff_time,
        "classification": report.match_classification,
        "expected_home_goals": report.expected_home_goals,
        "expected_away_goals": report.expected_away_goals,
        "total_expected_goals": report.total_expected_goals,
        "data_quality_score": f"{int(report.data_quality_score * 100)}%",
        "key_factors": report.key_factors,
        "counter_factors": report.counter_factors,
        "has_qualified_bet": report.has_qualified_bet,
        "total_markets_evaluated": len(report.all_evaluated_candidates),
        "qualified_candidates_count": len(qualified_out),
        "best_selection": qualified_out[0] if qualified_out else None,
        "all_qualified_candidates": qualified_out
    }


@router.get("/adaptive-board", summary="Get qualified AI value picks across entire SportyBet board")
def get_adaptive_daily_board(
    date: str = Query("today", description="'today', 'tomorrow', or 'all'"),
    limit: int = Query(50, ge=1, le=200),
    min_edge: float = Query(0.02, ge=0.0, le=0.30),
    db: Session = Depends(get_db)
):
    query = select(SportyBetEvent).where(SportyBetEvent.status == "SCHEDULED")

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if date == "today":
        start_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = start_day + datetime.timedelta(days=1)
        query = query.where(SportyBetEvent.start_time >= start_day, SportyBetEvent.start_time < end_day)
    elif date == "tomorrow":
        start_day = (now_utc + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = start_day + datetime.timedelta(days=1)
        query = query.where(SportyBetEvent.start_time >= start_day, SportyBetEvent.start_time < end_day)

    query = query.order_by(SportyBetEvent.start_time.asc()).limit(limit)
    events = db.execute(query).scalars().all()

    engine = AdaptiveMultiMarketEngine(min_edge=min_edge)
    qualified_matches = []
    no_bet_matches = 0

    for ev in events:
        event_dict = {
            "event_id": ev.sporty_event_id,
            "game_id": ev.sporty_game_id,
            "home_team": ev.home_team,
            "away_team": ev.away_team,
            "competition": ev.competition_rel.name if ev.competition_rel else "Football",
            "start_time": ev.start_time.isoformat(),
            "markets": []
        }
        for m in ev.markets:
            m_dict = {
                "market_id": m.sporty_market_id,
                "market_name": m.market_name,
                "market_type": m.market_type,
                "specifier": m.specifier,
                "outcomes": []
            }
            for oc in m.outcomes:
                m_dict["outcomes"].append({
                    "outcome_id": oc.sporty_outcome_id,
                    "selection_name": oc.selection,
                    "odds": oc.odds,
                    "probability": oc.probability
                })
            event_dict["markets"].append(m_dict)

        report = engine.evaluate_fixture(event_dict)
        if report.has_qualified_bet and report.best_candidate:
            b = report.best_candidate
            qualified_matches.append({
                "event_id": report.event_id,
                "match": f"{report.home_team} vs {report.away_team}",
                "competition": report.competition,
                "kickoff_time": report.kickoff_time,
                "classification": report.match_classification,
                "best_market": b.market_name,
                "selection": b.selection_name,
                "odds": b.sportybet_odds,
                "model_probability": f"{round(b.model_probability * 100, 1)}%",
                "edge": f"+{round(b.edge * 100, 1)}%",
                "expected_value": f"+{round(b.expected_value * 100, 1)}%",
                "confidence": b.confidence,
                "sporty_market_id": b.market_id,
                "sporty_outcome_id": b.outcome_id,
                "specifier": b.specifier
            })
        else:
            no_bet_matches += 1

    return {
        "total_analyzed": len(events),
        "qualified_picks_count": len(qualified_matches),
        "no_bet_count": no_bet_matches,
        "picks": qualified_matches
    }
