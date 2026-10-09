from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from typing import Optional, List, Dict, Any
import datetime

from app.db.session import get_db
from app.db.models import (
    SportyBetCompetition,
    SportyBetEvent,
    SportyBetMarket,
    SportyBetOutcome,
    SportyBetOddsSnapshot
)
from app.integrations.sportybet.discovery import SportyBetDiscoveryService
from app.integrations.sportybet.events import SportyBetEventSyncService
from app.integrations.sportybet.scheduler import SportyBetFeedScheduler

router = APIRouter()

# Global feed scheduler reference
feed_scheduler = SportyBetFeedScheduler()

@router.get("/competitions", summary="List discovered SportyBet competitions")
def get_competitions(
    country: Optional[str] = Query(None, description="Filter by country"),
    status: Optional[str] = Query("ACTIVE", description="Filter by status"),
    db: Session = Depends(get_db)
):
    query = select(SportyBetCompetition)
    if country:
        query = query.where(SportyBetCompetition.country.ilike(f"%{country}%"))
    if status:
        query = query.where(SportyBetCompetition.status == status)
    query = query.order_by(SportyBetCompetition.country, SportyBetCompetition.name)

    results = db.execute(query).scalars().all()
    return [
        {
            "id": c.id,
            "sporty_competition_id": c.sporty_competition_id,
            "name": c.name,
            "country": c.country,
            "category": c.category,
            "status": c.status,
            "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None
        }
        for c in results
    ]


@router.get("/events", summary="List synchronized SportyBet events from mirror DB")
def get_events(
    date: Optional[str] = Query(None, description="Filter: 'today', 'tomorrow', or 'YYYY-MM-DD'"),
    competition_id: Optional[str] = Query(None, description="Filter by SportyBet competition ID"),
    country: Optional[str] = Query(None, description="Filter by country"),
    status: Optional[str] = Query("SCHEDULED", description="Filter by status (SCHEDULED, LIVE, FINISHED)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = select(SportyBetEvent)

    if competition_id:
        comp = db.execute(
            select(SportyBetCompetition).where(SportyBetCompetition.sporty_competition_id == competition_id)
        ).scalar_one_or_none()
        if comp:
            query = query.where(SportyBetEvent.competition_id == comp.id)

    if status and status != "ALL":
        query = query.where(SportyBetEvent.status == status)

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

    output = []
    for ev in events:
        comp_name = ev.competition_rel.name if ev.competition_rel else "Football"
        comp_country = ev.competition_rel.country if ev.competition_rel else None

        output.append({
            "id": ev.id,
            "sporty_event_id": ev.sporty_event_id,
            "sporty_game_id": ev.sporty_game_id,
            "home_team": ev.home_team,
            "away_team": ev.away_team,
            "competition": comp_name,
            "country": comp_country,
            "start_time": ev.start_time.isoformat(),
            "start_time_ms": ev.start_time_ms,
            "status": ev.status,
            "event_state": ev.event_state,
            "total_markets": len(ev.markets)
        })

    return output


@router.get("/events/{event_id}", summary="Get detailed event with full generic markets")
def get_event_detail(
    event_id: str,
    db: Session = Depends(get_db)
):
    ev = db.execute(
        select(SportyBetEvent).where(
            (SportyBetEvent.sporty_event_id == event_id) | (SportyBetEvent.sporty_game_id == event_id)
        )
    ).scalar_one_or_none()

    if not ev:
        raise HTTPException(status_code=404, detail="SportyBet event not found in mirror DB")

    markets_output = []
    for m in ev.markets:
        outcomes_output = [
            {
                "outcome_id": oc.sporty_outcome_id,
                "label": oc.label,
                "selection": oc.selection,
                "odds": oc.odds,
                "probability": oc.probability,
                "status": oc.status
            }
            for oc in m.outcomes
        ]

        markets_output.append({
            "market_id": m.sporty_market_id,
            "market_name": m.market_name,
            "market_type": m.market_type,
            "line": m.line,
            "specifier": m.specifier,
            "status": m.status,
            "outcomes": outcomes_output
        })

    return {
        "event_id": ev.sporty_event_id,
        "game_id": ev.sporty_game_id,
        "home_team": ev.home_team,
        "away_team": ev.away_team,
        "start_time": ev.start_time.isoformat(),
        "status": ev.status,
        "markets": markets_output
    }


@router.get("/feed/health", summary="Get SportyBet feed ingestion health status")
def get_feed_health():
    return feed_scheduler.get_health_status()


@router.post("/feed/sync", summary="Trigger manual full feed synchronization")
async def trigger_manual_sync(db: Session = Depends(get_db)):
    disc = SportyBetDiscoveryService()
    d_res = await disc.discover_and_sync_competitions(db)

    ev_svc = SportyBetEventSyncService()
    e_res = await ev_svc.sync_all_upcoming_events(db)

    return {
        "status": "SUCCESS",
        "discovery": d_res,
        "events": e_res
    }
