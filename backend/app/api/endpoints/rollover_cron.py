from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.services.rollover_cron_scheduler import rollover_scheduler
from app.services.rollover_telegram_notifier import RolloverTelegramNotifier

router = APIRouter(prefix="/rollover-cron", tags=["StatIQ Automated Rollover Cron"])

class ScheduleUpdateRequest(BaseModel):
    is_enabled: Optional[bool] = None
    active_days: Optional[List[str]] = None
    target_odds: Optional[float] = None
    max_leg_odds: Optional[float] = None      # e.g. 1.35, 1.40, 1.45, 1.50
    dispatch_time: Optional[str] = None
    campaign_mode: Optional[str] = None       # "CONTINUOUS" or "CHALLENGE"
    challenge_days: Optional[int] = None       # e.g. 3, 5, 7, 10
    challenge_day_current: Optional[int] = None # e.g. 1
    challenge_start_date: Optional[str] = None
    challenge_end_date: Optional[str] = None
    starting_stake: Optional[float] = None
    challenge_status: Optional[str] = None     # "ACTIVE", "PAUSED", "COMPLETED"

class RunNowRequest(BaseModel):
    target_odds: Optional[float] = None
    max_leg_odds: Optional[float] = None

class ChallengeResetRequest(BaseModel):
    challenge_days: int = 10
    starting_stake: float = 5000.0

@router.get("/schedule")
def get_schedule():
    """Returns the current Rollover Cron schedule configuration and runtime status."""
    return {
        "status": "SUCCESS",
        "config": rollover_scheduler.get_config(),
        "is_daemon_running": rollover_scheduler._running
    }

@router.post("/schedule")
def update_schedule(req: ScheduleUpdateRequest):
    """Updates the Rollover Cron schedule (active days, target odds, dispatch time, campaign mode, challenge duration)."""
    current = rollover_scheduler.get_config()
    update_data = {}

    if req.is_enabled is not None:
        update_data["is_enabled"] = req.is_enabled
    if req.active_days is not None:
        valid_days = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
        cleaned = [d.upper() for d in req.active_days if d.upper() in valid_days]
        update_data["active_days"] = cleaned
    if req.target_odds is not None:
        update_data["target_odds"] = round(float(req.target_odds), 2)
    if req.max_leg_odds is not None:
        update_data["max_leg_odds"] = round(float(req.max_leg_odds), 2)
    if req.dispatch_time is not None:
        update_data["dispatch_time"] = req.dispatch_time.strip()
    if req.campaign_mode is not None:
        update_data["campaign_mode"] = req.campaign_mode.upper()
    if req.challenge_days is not None:
        update_data["challenge_days"] = max(1, int(req.challenge_days))
    if req.challenge_day_current is not None:
        update_data["challenge_day_current"] = max(1, int(req.challenge_day_current))
    if req.challenge_start_date is not None:
        update_data["challenge_start_date"] = req.challenge_start_date
    if req.challenge_end_date is not None:
        update_data["challenge_end_date"] = req.challenge_end_date
    if req.starting_stake is not None:
        update_data["starting_stake"] = max(100.0, float(req.starting_stake))
    if req.challenge_status is not None:
        update_data["challenge_status"] = req.challenge_status.upper()

    rollover_scheduler.save_config(update_data)
    return {
        "status": "SUCCESS",
        "message": "Rollover Cron configuration updated successfully.",
        "config": rollover_scheduler.get_config()
    }

@router.post("/challenge/reset")
def reset_challenge(req: ChallengeResetRequest = Body(default=ChallengeResetRequest())):
    """Resets the compounding challenge to Day 1 with specified duration and stake."""
    import datetime
    today_str = datetime.date.today().isoformat()
    end_date = (datetime.date.today() + datetime.timedelta(days=req.challenge_days - 1)).isoformat()
    update_data = {
        "campaign_mode": "CHALLENGE",
        "challenge_days": req.challenge_days,
        "challenge_day_current": 1,
        "challenge_start_date": today_str,
        "challenge_end_date": end_date,
        "starting_stake": req.starting_stake,
        "challenge_status": "ACTIVE",
        "is_enabled": True
    }
    rollover_scheduler.save_config(update_data)
    return {
        "status": "SUCCESS",
        "message": f"Started fresh {req.challenge_days}-day compounding challenge from Day 1.",
        "config": rollover_scheduler.get_config()
    }

@router.post("/run-now")
async def run_now(req: RunNowRequest = Body(default=RunNowRequest())):
    """
    Manually triggers an immediate run of the Elite Rollover Engine:
    Pulls SportyBet today's endpoint directly, evaluates fixtures with Dixon-Coles/Poisson models,
    generates a genuine SportyBet booking code, dispatches to Telegram, and records to history.
    """
    try:
        res = await rollover_scheduler.run_now(target_odds=req.target_odds, max_leg_odds=req.max_leg_odds)
        return {
            "status": "SUCCESS",
            "result": res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
def get_history():
    """Returns the history of automated and manual Rollover runs."""
    cfg = rollover_scheduler.get_config()
    return {
        "status": "SUCCESS",
        "history": cfg.get("run_history", []),
        "last_ticket": cfg.get("last_ticket")
    }

@router.post("/telegram-test")
def test_telegram_alert():
    """Sends a verification ping to the configured Telegram bot & chat ID."""
    creds = RolloverTelegramNotifier.get_credentials()
    if not creds["bot_token"] or not creds["chat_id"]:
        return {
            "status": "CONFIG_MISSING",
            "message": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured in .env."
        }
    sent = RolloverTelegramNotifier.send_test_ping()
    return {
        "status": "SUCCESS" if sent else "FAILED",
        "sent": sent,
        "message": "Telegram test alert delivered successfully!" if sent else "Failed to send message to Telegram API."
    }
