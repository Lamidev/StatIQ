import os
import json
import time
import threading
import logging
import datetime
import asyncio
from typing import Dict, Any, List, Optional

from app.services.elite_rollover_engine import EliteRolloverEngine

logger = logging.getLogger("statiq.rollover.scheduler")

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "rollover_schedule_config.json"))

DEFAULT_CONFIG = {
    "is_enabled": True,
    "active_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],  # Daily rollover by default
    "target_odds": 2.00,                   # 1.50 or 2.00
    "max_leg_odds": 1.45,                  # Upper safety bound per leg (1.15 to 1.45 corridor)
    "dispatch_time": "10:00",              # 10:00 AM WAT sharp
    "campaign_mode": "CONTINUOUS",         # "CONTINUOUS" or "CHALLENGE"
    "challenge_days": 10,                  # Total duration in days (e.g. 3, 5, 7, 10)
    "challenge_day_current": 1,            # Current day in compounding ladder
    "challenge_start_date": None,          # Start date string YYYY-MM-DD
    "challenge_end_date": None,            # Projected end date string
    "starting_stake": 5000,                # Initial stake in NGN
    "challenge_status": "ACTIVE",          # "ACTIVE", "PAUSED", "COMPLETED"
    "last_run_date": None,
    "last_ticket": None,
    "run_history": []
}

class RolloverCronScheduler:
    """
    Autonomous Background Cron Scheduler for StatIQ Rollover.
    Monitors system clock, discovers scheduled active days, executes at 10:00 AM sharp,
    generates SportyBet booking code, dispatches Telegram signals, and audits tickets.
    """

    _instance = None
    _lock = threading.Lock()
    _running = False
    _thread: Optional[threading.Thread] = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RolloverCronScheduler, cls).__new__(cls)
                cls._instance._init_scheduler()
            return cls._instance

    def _init_scheduler(self):
        self._ensure_config_file()

    def _ensure_config_file(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)

    def get_config(self) -> Dict[str, Any]:
        self._ensure_config_file()
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            logger.error(f"[RolloverScheduler] Error reading config: {e}")
            return dict(DEFAULT_CONFIG)

    def save_config(self, new_config: Dict[str, Any]):
        self._ensure_config_file()
        try:
            current = self.get_config()
            merged = {**current, **new_config}
            with open(CONFIG_PATH, "w") as f:
                json.dump(merged, f, indent=2)
            logger.info("[RolloverScheduler] Configuration saved successfully.")
        except Exception as e:
            logger.error(f"[RolloverScheduler] Error saving config: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_cron_loop, daemon=True, name="StatIQ-RolloverCron")
        self._thread.start()
        logger.info("[RolloverScheduler] 10:00 AM Rollover Cron daemon started.")

    def stop(self):
        self._running = False
        logger.info("[RolloverScheduler] Rollover Cron daemon stopped.")

    def _run_cron_loop(self):
        logger.info("[RolloverScheduler] Background loop active. Monitoring 10:00 AM WAT trigger...")
        WAT_TZ = datetime.timezone(datetime.timedelta(hours=1))
        while self._running:
            try:
                now_wat = datetime.datetime.now(WAT_TZ)
                cfg = self.get_config()

                if cfg.get("is_enabled"):
                    # Check Challenge mode status if active
                    if cfg.get("campaign_mode") == "CHALLENGE":
                        if cfg.get("challenge_status") == "COMPLETED":
                            time.sleep(30)
                            continue
                        current_day = int(cfg.get("challenge_day_current", 1))
                        total_days = int(cfg.get("challenge_days", 10))
                        if current_day > total_days:
                            cfg["challenge_status"] = "COMPLETED"
                            cfg["is_enabled"] = False
                            self.save_config(cfg)
                            logger.info(f"[RolloverScheduler] Compounding Challenge completed ({total_days} days reached). Pausing cron.")
                            time.sleep(30)
                            continue

                    # Check current weekday in WAT: MON, TUE, WED, THU, FRI, SAT, SUN
                    weekdays = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
                    current_day_code = weekdays[now_wat.weekday()]
                    current_time_str = now_wat.strftime("%H:%M")
                    today_str = now_wat.strftime("%Y-%m-%d")

                    active_days = cfg.get("active_days", [])
                    dispatch_time = cfg.get("dispatch_time", "10:00")
                    last_run = cfg.get("last_run_date")

                    # Check if today is an active day and current time matches dispatch_time
                    if (current_day_code in active_days) and (current_time_str == dispatch_time) and (last_run != today_str):
                        logger.info(f"[RolloverScheduler] Triggering scheduled 10:00 AM WAT Rollover run for {current_day_code} ({today_str})...")
                        target_odds = float(cfg.get("target_odds", 2.00))
                        max_leg_odds = float(cfg.get("max_leg_odds", 1.45))

                        challenge_info = None
                        current_stake = float(cfg.get("starting_stake", 5000))
                        if cfg.get("campaign_mode") == "CHALLENGE":
                            curr_day = int(cfg.get("challenge_day_current", 1))
                            tot_days = int(cfg.get("challenge_days", 10))
                            challenge_info = f"Day {curr_day} of {tot_days}"
                            current_stake = round(current_stake * (target_odds ** (curr_day - 1)))

                        # Execute async run in dedicated event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        ticket_res = loop.run_until_complete(
                            EliteRolloverEngine.book_and_dispatch_rollover(
                                target_odds=target_odds,
                                send_telegram=True,
                                max_leg_odds=max_leg_odds,
                                challenge_day_info=challenge_info,
                                stake=current_stake
                            )
                        )
                        loop.close()

                        # Update run history & state
                        cfg["last_run_date"] = today_str
                        cfg["last_ticket"] = ticket_res

                        history_entry = {
                            "date": today_str,
                            "time": current_time_str,
                            "target_odds": target_odds,
                            "status": ticket_res.get("status"),
                            "booking_code": ticket_res.get("booking_code"),
                            "actual_odds": ticket_res.get("actual_odds"),
                            "confidence": ticket_res.get("confidence_score"),
                            "telegram_dispatched": ticket_res.get("telegram_dispatched", False),
                            "picks_count": ticket_res.get("leg_count", 0),
                            "campaign_mode": cfg.get("campaign_mode", "CONTINUOUS"),
                            "stake": current_stake
                        }

                        # If Challenge mode, record day and progress counter
                        if cfg.get("campaign_mode") == "CHALLENGE":
                            curr_day = int(cfg.get("challenge_day_current", 1))
                            tot_days = int(cfg.get("challenge_days", 10))
                            history_entry["challenge_day"] = f"Day {curr_day} of {tot_days}"
                            
                            # Increment day for next run
                            next_day = curr_day + 1
                            cfg["challenge_day_current"] = next_day
                            if curr_day >= tot_days:
                                cfg["challenge_status"] = "COMPLETED"
                                cfg["is_enabled"] = False
                                logger.info(f"[RolloverScheduler] Reached final day {curr_day} of challenge. Marked COMPLETED.")

                        history = cfg.get("run_history", [])
                        history.insert(0, history_entry)
                        cfg["run_history"] = history[:30]  # Retain last 30 runs
                        self.save_config(cfg)
                        logger.info(f"[RolloverScheduler] Scheduled run completed with status: {ticket_res.get('status')}")

            except Exception as e:
                logger.error(f"[RolloverScheduler] Error in cron tick: {e}")

            time.sleep(30)  # Check every 30 seconds

    async def run_now(self, target_odds: Optional[float] = None, max_leg_odds: Optional[float] = None) -> Dict[str, Any]:
        """
        Manually triggers an immediate run of the Elite Rollover Engine (e.g. for testing or on-demand use).
        """
        cfg = self.get_config()
        odds = target_odds if target_odds is not None else float(cfg.get("target_odds", 2.00))
        leg_cap = max_leg_odds if max_leg_odds is not None else float(cfg.get("max_leg_odds", 1.45))

        challenge_info = None
        current_stake = float(cfg.get("starting_stake", 5000))
        if cfg.get("campaign_mode") == "CHALLENGE":
            curr_day = int(cfg.get("challenge_day_current", 1))
            tot_days = int(cfg.get("challenge_days", 10))
            challenge_info = f"Day {curr_day} of {tot_days}"
            current_stake = round(current_stake * (odds ** (curr_day - 1)))

        logger.info(f"[RolloverScheduler] Executing manual 'Run Now' rollover for {odds}x odds (max leg odds {leg_cap}x)...")
        ticket_res = await EliteRolloverEngine.book_and_dispatch_rollover(
            target_odds=odds,
            send_telegram=True,
            max_leg_odds=leg_cap,
            challenge_day_info=challenge_info,
            stake=current_stake
        )

        WAT_TZ = datetime.timezone(datetime.timedelta(hours=1))
        now_wat = datetime.datetime.now(WAT_TZ)
        today_str = now_wat.strftime("%Y-%m-%d")
        cfg["last_ticket"] = ticket_res
        history = cfg.get("run_history", [])
        history.insert(0, {
            "date": today_str,
            "time": now_wat.strftime("%H:%M:%S"),
            "target_odds": odds,
            "status": ticket_res.get("status"),
            "booking_code": ticket_res.get("booking_code"),
            "actual_odds": ticket_res.get("actual_odds"),
            "confidence": ticket_res.get("confidence_score"),
            "telegram_dispatched": ticket_res.get("telegram_dispatched", False),
            "picks_count": ticket_res.get("leg_count", 0),
            "challenge_day": challenge_info,
            "stake": current_stake,
            "manual_trigger": True
        })
        cfg["run_history"] = history[:30]
        self.save_config(cfg)

        return ticket_res

# Global singleton
rollover_scheduler = RolloverCronScheduler()
