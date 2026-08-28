"""
API Endpoints for vFootball Automated Front-Testing & Telegram Signal Dispatcher.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from virtual.core.db import get_db
from virtual.workers.fronttest_worker import VirtualFrontTestWorker
from virtual.services.telegram_service import VirtualTelegramService
from virtual.api.agent_control_routes import (
    get_or_create_agent_config, get_agent_status,
    pause_agent_endpoint, resume_agent_endpoint,
    update_persistent_agent_config, PersistentAgentConfigUpdate
)

router = APIRouter(prefix="/fronttest", tags=["Virtual Front-Testing"])

class FrontTestConfigUpdate(BaseModel):
    target_odds: Optional[float] = 2.0
    preferred_market: Optional[str] = "ALL"
    league_count: Optional[int] = 2
    stake_amount: Optional[float] = 1000.0
    selected_leagues: Optional[List[str]] = None
    enabled: Optional[bool] = None


@router.get("/status")
def get_fronttest_status(db: Session = Depends(get_db)):
    """
    Returns authoritative automation status, win rate, P&L, and recent dispatched slips.
    """
    return get_agent_status(db)

@router.post("/toggle")
def toggle_fronttest_automation(enabled: bool = Query(...), db: Session = Depends(get_db)):
    """
    Switch the automated front-testing agent ON or OFF with authoritative DB persistence.
    """
    if enabled:
        res = resume_agent_endpoint(db)
    else:
        res = pause_agent_endpoint(db)
    
    return {
        "status": "SUCCESS",
        "is_enabled": enabled,
        "worker_state": res.get("worker_state"),
        "config_version": res.get("config_version"),
        "message": f"Front-testing automation is now {'ENABLED (Active 24/7)' if enabled else 'PAUSED'} (Config v{res.get('config_version')})."
    }

@router.post("/config")
def update_fronttest_config(payload: FrontTestConfigUpdate, db: Session = Depends(get_db)):
    """
    Update preset target odds, preferred betting markets, and league counts with DB persistence.
    """
    update_payload = PersistentAgentConfigUpdate(
        target_odds=payload.target_odds,
        preferred_market=payload.preferred_market,
        league_count=payload.league_count,
        stake_amount=payload.stake_amount,
        selected_leagues=payload.selected_leagues,
        enabled=payload.enabled
    )
    return update_persistent_agent_config(update_payload, db)

@router.post("/reset-ledger")
def reset_fronttest_ledger(
    force_override: bool = Query(False, description="Override active bet safety lock"),
    db: Session = Depends(get_db)
):
    """
    Safely purges historical virtual events, odds snapshots, and slips with active bet locks.
    """
    from virtual.services.purge_service import VirtualDatabasePurgeService
    res = VirtualDatabasePurgeService.purge_virtual_database(db, force_override=force_override, operator="UI_FRONTTEST")
    if res.get("status") == "BLOCKED":
        raise HTTPException(status_code=409, detail=res)
    elif res.get("status") == "FAILED":
        raise HTTPException(status_code=500, detail=res)
    return res

@router.post("/trigger-now")

def trigger_immediate_round_scan(db: Session = Depends(get_db)):
    """
    Manually triggers an immediate scan of all vFootball leagues,
    books 2.0x tickets with SportyBet, and dispatches to Telegram.
    """
    try:
        VirtualFrontTestWorker._process_pre_match_dispatches(db)
        return {
            "status": "SUCCESS",
            "message": "Immediate scan completed. Check recent slips or Telegram channel.",
            "data": VirtualFrontTestWorker.get_status(db)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Immediate scan failed: {e}")

@router.post("/telegram-test")
def send_telegram_test():
    """
    Sends a test ping to the configured Telegram bot & chat ID.
    """
    if not VirtualTelegramService.is_configured():
        return {
            "status": "NOT_CONFIGURED",
            "message": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set in environment variables."
        }
    sent = VirtualTelegramService.send_message(
        "🔔 <b>StatIQ vFootball Bot Test</b>\n\nTelegram alert dispatcher is connected and operational!"
    )
    return {
        "status": "SUCCESS" if sent else "FAILED",
        "message": "Test alert sent to Telegram successfully!" if sent else "Failed to send message to Telegram API."
    }
