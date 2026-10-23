from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.services.rollover_cron_scheduler import rollover_scheduler
from app.services.rollover_telegram_notifier import RolloverTelegramNotifier

router = APIRouter(prefix="/rollover-cron", tags=["StatIQ Automated Rollover Cron"])

class ScheduleUpdateRequest(BaseModel):
    is_enabled: Optional[bool] = None
    active_days: Optional[List[str]] = None
    enable_rollover_2x: Optional[bool] = None
    enable_acca_5x: Optional[bool] = None
    enable_acca_10x: Optional[bool] = None
    enable_acca_20x: Optional[bool] = None
    target_odds: Optional[float] = None
    rollover_target_odds: Optional[float] = None
    acca_5x_target_odds: Optional[float] = None
    acca_10x_target_odds: Optional[float] = None
    acca_20x_target_odds: Optional[float] = None
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
    rollover_target_odds: Optional[float] = None
    acca_5x_target_odds: Optional[float] = None
    acca_10x_target_odds: Optional[float] = None
    acca_20x_target_odds: Optional[float] = None
    max_leg_odds: Optional[float] = None
    enable_rollover_2x: Optional[bool] = None
    enable_acca_5x: Optional[bool] = None
    enable_acca_10x: Optional[bool] = None
    enable_acca_20x: Optional[bool] = None

class ChallengeResetRequest(BaseModel):
    challenge_days: int = 10
    starting_stake: float = 5000.0

class UpdateDayRequest(BaseModel):
    day: int
    status: str  # "WON" or "LOST"
    notes: Optional[str] = None

class StartCampaignRequest(BaseModel):
    challenge_days: int = 3
    starting_stake: float = 5000.0
    target_odds: float = 2.0

@router.get("/active-campaign")
def get_active_campaign():
    """Returns the currently active running campaign/challenge, days progress, stake compounding ladder, and today's leg."""
    campaign = rollover_scheduler.get_active_campaign()
    return {
        "status": "SUCCESS",
        "campaign": campaign
    }

@router.post("/campaign/update-day")
def update_campaign_day(req: UpdateDayRequest = Body(...)):
    """Marks a challenge day as WON or LOST, advances current day counter, or completes challenge."""
    res = rollover_scheduler.update_challenge_day(day_num=req.day, status=req.status.upper(), notes=req.notes)
    return {
        "status": "SUCCESS",
        "campaign": res
    }

@router.post("/campaign/dismiss")
def dismiss_campaign():
    """Dismisses and clears the active or finished challenge from the running card."""
    res = rollover_scheduler.dismiss_campaign()
    return res

@router.post("/campaign/start")
def start_campaign(req: StartCampaignRequest = Body(...)):
    """Starts a new custom compounding challenge."""
    res = rollover_scheduler.start_challenge(
        days=req.challenge_days,
        starting_stake=req.starting_stake,
        target_odds=req.target_odds
    )
    return {
        "status": "SUCCESS",
        "message": f"Started {req.challenge_days}-Day Compounding Challenge.",
        "campaign": res
    }

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
    """Updates the Rollover Cron schedule (active days, ticket toggles, target odds, dispatch time, campaign mode, challenge duration)."""
    current = rollover_scheduler.get_config()
    update_data = {}

    if req.is_enabled is not None:
        update_data["is_enabled"] = req.is_enabled
    if req.enable_rollover_2x is not None:
        update_data["enable_rollover_2x"] = req.enable_rollover_2x
    if req.enable_acca_5x is not None:
        update_data["enable_acca_5x"] = req.enable_acca_5x
    if req.enable_acca_10x is not None:
        update_data["enable_acca_10x"] = req.enable_acca_10x
    if req.enable_acca_20x is not None:
        update_data["enable_acca_20x"] = req.enable_acca_20x
    if req.active_days is not None:
        valid_days = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
        cleaned = [d.upper() for d in req.active_days if d.upper() in valid_days]
        update_data["active_days"] = cleaned
    if req.target_odds is not None:
        update_data["target_odds"] = round(float(req.target_odds), 2)
        update_data["rollover_target_odds"] = round(float(req.target_odds), 2)
    if req.rollover_target_odds is not None:
        update_data["rollover_target_odds"] = round(float(req.rollover_target_odds), 2)
        update_data["target_odds"] = round(float(req.rollover_target_odds), 2)
    if req.acca_5x_target_odds is not None:
        update_data["acca_5x_target_odds"] = round(float(req.acca_5x_target_odds), 2)
    if req.acca_10x_target_odds is not None:
        update_data["acca_10x_target_odds"] = round(float(req.acca_10x_target_odds), 2)
    if req.acca_20x_target_odds is not None:
        update_data["acca_20x_target_odds"] = round(float(req.acca_20x_target_odds), 2)
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
    new_cfg = rollover_scheduler.get_config()

    # Automatically notify Telegram chat of updated settings
    try:
        RolloverTelegramNotifier.notify_schedule_updated(new_cfg)
    except Exception as e:
        import logging
        logging.getLogger("rollover_cron").warning(f"Could not dispatch schedule update alert to Telegram: {e}")

    return {
        "status": "SUCCESS",
        "message": "Rollover Cron configuration updated successfully.",
        "config": new_cfg
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
    Manually triggers an immediate run of the Daily VIP Trio:
    Pulls SportyBet today's endpoint directly, evaluates fixtures with Dixon-Coles/Poisson models,
    generates genuine SportyBet booking codes for Rollover, 5.0x, and 10.0x with zero overlap,
    dispatches to Telegram, and records to history.
    """
    try:
        res = await rollover_scheduler.run_now(
            target_odds=req.target_odds,
            rollover_target_odds=req.rollover_target_odds,
            acca_5x_target_odds=req.acca_5x_target_odds,
            acca_10x_target_odds=req.acca_10x_target_odds,
            acca_20x_target_odds=req.acca_20x_target_odds,
            max_leg_odds=req.max_leg_odds,
            enable_rollover=req.enable_rollover_2x,
            enable_10odds=req.enable_acca_10x,
            enable_20odds=req.enable_acca_20x,
            enable_5odds=req.enable_acca_5x
        )
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
        "last_ticket": cfg.get("last_ticket"),
        "last_trio_result": cfg.get("last_trio_result")
    }

@router.post("/clear-last-slip")
def clear_last_slip():
    """Clears/dismisses the cached last dispatched VIP slip from the active view."""
    cfg = rollover_scheduler.get_config()
    cfg["last_ticket"] = None
    cfg["last_trio_result"] = None
    rollover_scheduler.save_config(cfg)
    return {
        "status": "SUCCESS",
        "message": "Cached VIP slip dismissed successfully.",
        "config": rollover_scheduler.get_config()
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
