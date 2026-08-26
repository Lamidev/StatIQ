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

router = APIRouter(prefix="/fronttest", tags=["Virtual Front-Testing"])

class FrontTestConfigUpdate(BaseModel):
    target_odds: Optional[float] = 2.0
    preferred_market: Optional[str] = "ALL"
    enable_per_league: Optional[bool] = True
    enable_master_slip: Optional[bool] = True
    stake_amount: Optional[float] = 1000.0
    active_leagues: Optional[List[str]] = ["Master Multi-League", "England Virtual"]


@router.get("/status")
def get_fronttest_status(db: Session = Depends(get_db)):
    """
    Returns current automation status, win rate, P&L, and recent dispatched slips.
    """
    return VirtualFrontTestWorker.get_status(db)

@router.post("/toggle")
def toggle_fronttest_automation(enabled: bool = Query(...), db: Session = Depends(get_db)):
    """
    Switch the automated front-testing agent ON or OFF.
    """
    VirtualFrontTestWorker.set_enabled(enabled)
    return {
        "status": "SUCCESS",
        "is_enabled": VirtualFrontTestWorker.is_enabled(),
        "message": f"Front-testing automation is now {'ENABLED (Active 24/7)' if enabled else 'PAUSED'}."
    }

@router.post("/config")
def update_fronttest_config(payload: FrontTestConfigUpdate, db: Session = Depends(get_db)):
    """
    Update preset target odds, preferred betting markets, and slip types.
    """
    cfg = payload.dict(exclude_unset=True)
    VirtualFrontTestWorker.update_config(cfg)
    return {
        "status": "SUCCESS",
        "config": VirtualFrontTestWorker.config,
        "message": "Front-testing configuration updated."
    }

@router.post("/reset-ledger")
def reset_fronttest_ledger(db: Session = Depends(get_db)):
    """
    Clears all front-testing slips and match history from the database to start afresh.
    """
    from virtual.models.virtual_models import VirtualFrontTestSlip, VirtualMatchHistory
    deleted_slips = db.query(VirtualFrontTestSlip).delete()
    deleted_history = db.query(VirtualMatchHistory).delete()
    db.commit()
    return {
        "status": "SUCCESS",
        "message": f"Ledger reset. Cleared {deleted_slips} slips and {deleted_history} history records."
    }

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
