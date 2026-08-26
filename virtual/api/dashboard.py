from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from virtual.core.db import get_db
from virtual.core.config import virtual_config
from virtual.workers.ingestion_worker import VirtualIngestionWorker
from virtual.models.virtual_models import (
    VirtualLeague,
    VirtualRound,
    VirtualEvent,
    VirtualOddsSnapshot,
    VirtualBankroll,
    VirtualAgentLog
)

router = APIRouter()

@router.get("/dashboard")
def get_virtual_dashboard(db: Session = Depends(get_db)):
    worker_health = VirtualIngestionWorker.get_status()
    
    total_events = db.query(VirtualEvent).count()
    total_odds_snapshots = db.query(VirtualOddsSnapshot).count()
    active_leagues = db.query(VirtualLeague).filter(VirtualLeague.is_active == True).count()
    
    bankroll = db.query(VirtualBankroll).order_by(VirtualBankroll.id.desc()).first()
    bankroll_data = {
        "balance": bankroll.current_balance if bankroll else virtual_config.INITIAL_PAPER_BANKROLL,
        "starting_balance": bankroll.starting_balance if bankroll else virtual_config.INITIAL_PAPER_BANKROLL,
        "daily_profit_loss": bankroll.daily_profit_loss if bankroll else 0.0,
        "cumulative_roi": bankroll.cumulative_roi if bankroll else 0.0,
        "total_bets": bankroll.total_bets if bankroll else 0,
        "won_bets": bankroll.won_bets if bankroll else 0,
        "lost_bets": bankroll.lost_bets if bankroll else 0,
        "win_rate": (bankroll.won_bets / bankroll.total_bets * 100.0) if (bankroll and bankroll.total_bets > 0) else 0.0,
    }

    recent_logs = db.query(VirtualAgentLog).order_by(VirtualAgentLog.created_at.desc()).limit(15).all()
    logs_data = [
        {
            "id": log.id,
            "worker_name": log.worker_name,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None
        }
        for log in recent_logs
    ]

    return {
        "agent_mode": virtual_config.AGENT_MODE,
        "kill_switch_active": virtual_config.KILL_SWITCH_ACTIVE,
        "worker_health": worker_health,
        "data_warehouse": {
            "total_events_collected": total_events,
            "total_odds_snapshots": total_odds_snapshots,
            "active_leagues_tracked": active_leagues,
        },
        "bankroll": bankroll_data,
        "recent_logs": logs_data
    }
