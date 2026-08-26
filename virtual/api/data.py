from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from virtual.core.db import get_db
from virtual.models.virtual_models import VirtualLeague, VirtualEvent, VirtualOddsSnapshot

router = APIRouter()

@router.get("/events")
def get_virtual_events(
    limit: int = Query(50, ge=1, le=200),
    league_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(VirtualEvent)
    if league_id:
        query = query.filter(VirtualEvent.league_id == league_id)
    if status:
        query = query.filter(VirtualEvent.status == status.upper())

    events = query.order_by(VirtualEvent.scheduled_time.desc()).limit(limit).all()

    results = []
    for ev in events:
        latest_odds = (
            db.query(VirtualOddsSnapshot)
            .filter(VirtualOddsSnapshot.event_id == ev.id)
            .order_by(VirtualOddsSnapshot.observed_at.desc())
            .first()
        )

        results.append({
            "id": ev.id,
            "provider": ev.provider,
            "provider_event_id": ev.provider_event_id,
            "league_name": ev.league.name if ev.league else "Virtual Football",
            "home_team": ev.home_team,
            "away_team": ev.away_team,
            "scheduled_time": ev.scheduled_time.isoformat() if ev.scheduled_time else None,
            "status": ev.status,
            "last_seen_at": ev.last_seen_at.isoformat() if ev.last_seen_at else None,
            "latest_odds": {
                "market_type": latest_odds.market_type if latest_odds else None,
                "odds_home": latest_odds.odds_home if latest_odds else None,
                "odds_draw": latest_odds.odds_draw if latest_odds else None,
                "odds_away": latest_odds.odds_away if latest_odds else None,
                "odds_over": latest_odds.odds_over if latest_odds else None,
                "odds_under": latest_odds.odds_under if latest_odds else None,
                "observed_at": latest_odds.observed_at.isoformat() if latest_odds else None
            } if latest_odds else None
        })

    return {
        "count": len(results),
        "events": results
    }

@router.get("/leagues")
def get_virtual_leagues(db: Session = Depends(get_db)):
    leagues = db.query(VirtualLeague).all()
    res = []
    for lg in leagues:
        event_count = db.query(VirtualEvent).filter(VirtualEvent.league_id == lg.id).count()
        res.append({
            "id": lg.id,
            "code": lg.league_code,
            "name": lg.name,
            "country": lg.country,
            "is_active": lg.is_active,
            "total_events_collected": event_count
        })
    return {"leagues": res}
