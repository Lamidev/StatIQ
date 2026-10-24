"""
FastAPI Endpoints for StatIQ Basketball Intelligence & 09:00 AM Daily Automation.
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.basketball.basketball_ingestion import BasketballIngestionService
from app.basketball.basketball_quant_engine import BasketballQuantEngine
from app.basketball.basketball_ticket_builder import BasketballTicketBuilder
from app.basketball.basketball_cron_scheduler import basketball_scheduler
from app.basketball.basketball_telegram_notifier import BasketballTelegramNotifier

router = APIRouter()

class BasketballConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    daytime_enabled: Optional[bool] = None
    daytime_dispatch_time: Optional[str] = None
    midnight_enabled: Optional[bool] = None
    midnight_dispatch_time: Optional[str] = None
    dispatch_time: Optional[str] = None
    target_odds: Optional[float] = None
    min_leg_odds: Optional[float] = None
    max_leg_odds: Optional[float] = None
    leg_count: Optional[int] = None
    active_days: Optional[List[str]] = None
    send_telegram: Optional[bool] = None

class CustomSlipRequest(BaseModel):
    session_slate: Optional[str] = "ALL"
    min_leg_odds: Optional[float] = 1.23
    max_leg_odds: Optional[float] = 1.28
    target_legs: Optional[int] = 3
    book_on_sportybet: Optional[bool] = True

class BasketballAccumulatorRequest(BaseModel):
    target_odds: Optional[float] = 10.0
    session_slate: Optional[str] = "ALL"  # "ALL", "DAYTIME", "MIDNIGHT"
    min_leg_odds: Optional[float] = 1.22
    max_leg_odds: Optional[float] = 1.35
    max_legs: Optional[int] = 20

@router.get("/fixtures")
def get_basketball_fixtures(
    session_slate: str = Query("ALL", description="Filter by ALL, DAYTIME, or MIDNIGHT"),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Returns upcoming global basketball fixtures normalized to West Africa Time (WAT).
    Tagged with session slate (DAYTIME vs MIDNIGHT USA) and tournament metadata.
    """
    fixtures = BasketballIngestionService.fetch_upcoming_fixtures(
        session_filter=session_slate,
        limit=limit
    )
    return {
        "status": "SUCCESS",
        "count": len(fixtures),
        "session_slate": session_slate.upper(),
        "fixtures": fixtures
    }

@router.get("/markets/{event_id}")
def get_basketball_markets(event_id: str):
    """
    Returns deep markets (120+ lines) for a specific basketball match,
    including Full-Time Alternative Cushion lines, Team Totals, and 1st Half/Quarter totals.
    """
    markets = BasketballIngestionService.fetch_deep_match_markets(event_id)
    if not markets:
        raise HTTPException(status_code=404, detail="Markets not found or event concluded.")
    return {
        "status": "SUCCESS",
        "event_id": event_id,
        "markets": markets
    }

@router.get("/bankers")
def get_daily_bankers(
    session_slate: str = Query("ALL", description="Filter by ALL, DAYTIME, or MIDNIGHT"),
    min_odds: float = Query(1.23, ge=1.15, le=1.50),
    max_odds: float = Query(1.28, ge=1.20, le=1.60)
):
    """
    Scans upcoming basketball fixtures and returns all vetted banker picks
    in the 1.23 - 1.28 odds corridor, prioritizing Full-Time Cushion Overs.
    """
    bankers = BasketballQuantEngine.find_all_daily_bankers(
        session_slate=session_slate,
        limit_fixtures=40,
        min_odds=min_odds,
        max_odds=max_odds
    )
    return {
        "status": "SUCCESS",
        "count": len(bankers),
        "corridor": f"{min_odds:.2f} - {max_odds:.2f}",
        "bankers": bankers
    }

@router.post("/generate-slip")
def generate_basketball_slip(payload: Optional[CustomSlipRequest] = None):
    """
    Builds a 3-Leg 2.0x Banker Cushion Slip on demand with a genuine SportyBet booking code.
    """
    req = payload or CustomSlipRequest()
    slip = BasketballTicketBuilder.build_daily_2x_cushion_slip(
        session_slate=req.session_slate or "ALL",
        min_leg_odds=req.min_leg_odds or 1.23,
        max_leg_odds=req.max_leg_odds or 1.28,
        target_legs=req.target_legs or 3
    )
    return slip

@router.post("/accumulator")
def generate_basketball_accumulator(payload: Optional[BasketballAccumulatorRequest] = Body(None)):
    """
    Builds a multi-leg accumulator ticket (5x, 10x, 20x odds, etc.)
    using diverse prediction varieties (Full-Time Cushion Overs, Cushion Unders,
    Team Totals, 1st Half/Quarter, Moneyline) and books it directly on SportyBet.
    """
    req = payload or BasketballAccumulatorRequest()
    slip = BasketballTicketBuilder.build_accumulator_slip(
        target_odds=req.target_odds or 10.0,
        session_slate=req.session_slate or "ALL",
        min_leg_odds=req.min_leg_odds or 1.22,
        max_leg_odds=req.max_leg_odds or 1.35,
        max_legs=req.max_legs or 20
    )
    return slip

@router.get("/cron/status")
def get_scheduler_status():
    """
    Returns the current configuration, active slots (Daytime Euro/Asia vs Midnight NBA),
    and history for the Basketball Automation suite.
    """
    return basketball_scheduler.get_status()

@router.post("/cron/config")
def update_scheduler_config(payload: BasketballConfigUpdate):
    """
    Updates configuration for the 09:00 AM Basketball Automation suite.
    """
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    basketball_scheduler.save_config(updates)
    return {
        "status": "SUCCESS",
        "message": "Basketball automation configuration updated successfully.",
        "config": basketball_scheduler.get_config()
    }

@router.post("/cron/trigger-now")
def trigger_scheduler_now(
    session_slate: str = Query("ALL", description="Filter by ALL, DAYTIME, or MIDNIGHT"),
    send_telegram: bool = Query(True)
):
    """
    Manually triggers the Basketball Automation suite immediately for the given slate.
    Builds the 3-Leg 2.0x slip, books on SportyBet, and dispatches to Telegram.
    """
    result = basketball_scheduler.execute_now(session_slate=session_slate, force=True, send_telegram=send_telegram)
    return result

@router.post("/cron/telegram-test")
def test_telegram_connection():
    """
    Sends a test ping to the configured Telegram bot & chat ID.
    """
    sent = BasketballTelegramNotifier.send_test_ping()
    return {
        "status": "SUCCESS" if sent else "FAILED",
        "message": "Basketball test ping sent to Telegram successfully!" if sent else "Failed to send ping. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
    }
