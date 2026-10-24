"""
Autonomous Background Cron Scheduler for StatIQ Basketball.
Executes daily at 09:00 AM WAT sharp to build the 3-Leg 2.0x Cushion Slip,
books on SportyBet, dispatches Telegram VIP signals, and logs execution history.
"""
import os
import json
import time
import logging
import threading
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from app.basketball.basketball_ticket_builder import BasketballTicketBuilder
from app.basketball.basketball_telegram_notifier import BasketballTelegramNotifier

logger = logging.getLogger("statiq.basketball.scheduler")

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "basketball_schedule_config.json")
)

DEFAULT_CONFIG: Dict[str, Any] = {
    "is_enabled": True,
    "active_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
    "daytime_enabled": True,
    "daytime_dispatch_time": "09:00",       # 09:00 AM WAT (EuroLeague, ACB, NBL, Asian Leagues)
    "midnight_enabled": True,
    "midnight_dispatch_time": "22:00",      # 10:00 PM WAT (USA NBA, NCAA Division 1)
    "dispatch_time": "09:00",               # Backward-compatible alias
    "target_odds": 2.00,                    # 2.00x Total Multiplier
    "min_leg_odds": 1.23,                   # Minimum leg odds
    "max_leg_odds": 1.28,                   # Maximum leg odds
    "leg_count": 3,                         # 3 Banker Cushion Legs
    "preferred_market": "FULL_TIME_OVERS",  # Primary focus: Full-Time Cushion Overs
    "send_telegram": True,
    "last_daytime_run_date": None,
    "last_midnight_run_date": None,
    "last_run_date": None,
    "last_ticket": None,
    "run_history": []
}

class BasketballCronScheduler:
    """
    Background daemon running 24/7.
    Checks the system clock in West Africa Time (WAT / UTC+1) and triggers
    at 09:00 AM WAT (Daytime Euro/Asia) and 22:00 PM WAT (Midnight USA NBA/NCAA).
    """
    _instance = None
    _lock = threading.Lock()
    _running = False
    _thread: Optional[threading.Thread] = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BasketballCronScheduler, cls).__new__(cls)
                cls._instance._init_scheduler()
            return cls._instance

    def _init_scheduler(self):
        self._lock_file = None
        self._last_daytime_dispatched: Optional[str] = None
        self._last_midnight_dispatched: Optional[str] = None
        self._ensure_config_file()

    def _acquire_process_lock(self) -> bool:
        lock_path = os.path.join(tempfile.gettempdir(), "statiq_basketball_cron.lock")
        try:
            self._lock_file = open(lock_path, "a+")
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except (IOError, OSError):
                    return False
            else:
                import fcntl
                try:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except (IOError, OSError):
                    return False
        except Exception as e:
            logger.warning(f"[BasketballScheduler] Lock warning: {e}")
            return True

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
            logger.error(f"[BasketballScheduler] Error reading config: {e}")
            return dict(DEFAULT_CONFIG)

    def save_config(self, new_config: Dict[str, Any]):
        self._ensure_config_file()
        try:
            current = self.get_config()
            merged = {**current, **new_config}
            with open(CONFIG_PATH, "w") as f:
                json.dump(merged, f, indent=2)
            logger.info("[BasketballScheduler] Configuration saved successfully.")
        except Exception as e:
            logger.error(f"[BasketballScheduler] Error saving config: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status, slot schedule, and configuration."""
        cfg = self.get_config()
        wat_tz = timezone(timedelta(hours=1))
        now_wat = datetime.now(wat_tz)
        return {
            "status": "SUCCESS",
            "is_running": self._running,
            "current_time_wat": now_wat.strftime("%Y-%m-%d %H:%M:%S"),
            "config": cfg,
            "slots": {
                "daytime": {
                    "title": "Daytime Euro/Asia (09:00 AM WAT)",
                    "enabled": cfg.get("daytime_enabled", True),
                    "time": cfg.get("daytime_dispatch_time", "09:00"),
                    "last_run": cfg.get("last_daytime_run_date")
                },
                "midnight": {
                    "title": "Midnight USA NBA/NCAA (22:00 PM WAT)",
                    "enabled": cfg.get("midnight_enabled", True),
                    "time": cfg.get("midnight_dispatch_time", "22:00"),
                    "last_run": cfg.get("last_midnight_run_date")
                }
            }
        }

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="StatIQ-BasketballCron")
            self._thread.start()
            logger.info("[BasketballScheduler] 24/7 Basketball Dual-Slate Cron Daemon active.")

    def _run_loop(self):
        # Grace period for server cold start
        time.sleep(8)
        if not self._acquire_process_lock():
            logger.info("[BasketballScheduler] Another worker holds cron lock. Standing by as standby replica.")
            return

        wat_tz = timezone(timedelta(hours=1))

        while self._running:
            try:
                now_wat = datetime.now(wat_tz)
                cfg = self.get_config()

                if cfg.get("is_enabled", True):
                    day_abbr = now_wat.strftime("%a").upper()
                    active_days = cfg.get("active_days", ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
                    current_time_str = now_wat.strftime("%H:%M")
                    today_str = now_wat.strftime("%Y-%m-%d")

                    if day_abbr in active_days:
                        # 1. Daytime Slot (09:00 AM WAT - Euro/Asia)
                        daytime_time = cfg.get("daytime_dispatch_time", "09:00")
                        if cfg.get("daytime_enabled", True) and current_time_str == daytime_time:
                            if cfg.get("last_daytime_run_date") != today_str and self._last_daytime_dispatched != today_str:
                                logger.info(f"[BasketballScheduler] Triggering Daytime 09:00 AM dispatch for {today_str}.")
                                self.execute_now(
                                    session_slate="DAYTIME",
                                    slot_name="DAYTIME",
                                    custom_title="🏀 <b>StatIQ Daytime 2.0x Basketball VIP Slip (Euro/Asia)</b>",
                                    force=False,
                                    send_telegram=cfg.get("send_telegram", True)
                                )
                                self._last_daytime_dispatched = today_str

                        # 2. Midnight Slot (22:00 PM WAT - USA NBA/NCAA)
                        midnight_time = cfg.get("midnight_dispatch_time", "22:00")
                        if cfg.get("midnight_enabled", True) and current_time_str == midnight_time:
                            if cfg.get("last_midnight_run_date") != today_str and self._last_midnight_dispatched != today_str:
                                logger.info(f"[BasketballScheduler] Triggering Midnight 22:00 PM dispatch for {today_str}.")
                                self.execute_now(
                                    session_slate="MIDNIGHT",
                                    slot_name="MIDNIGHT",
                                    custom_title="🏀 <b>StatIQ Midnight 2.0x Basketball VIP Slip (USA NBA/NCAA)</b>",
                                    force=False,
                                    send_telegram=cfg.get("send_telegram", True)
                                )
                                self._last_midnight_dispatched = today_str
            except Exception as e:
                logger.error(f"[BasketballScheduler] Loop exception: {e}")

            time.sleep(25)

    def execute_now(
        self,
        session_slate: str = "ALL",
        slot_name: str = "MANUAL",
        custom_title: Optional[str] = None,
        force: bool = True,
        send_telegram: bool = True
    ) -> Dict[str, Any]:
        """
        Executes slip generation immediately for the given slate (DAYTIME, MIDNIGHT, or ALL).
        Can be triggered manually via API or autonomously by the cron daemon.
        """
        wat_tz = timezone(timedelta(hours=1))
        now_wat = datetime.now(wat_tz)
        today_str = now_wat.strftime("%Y-%m-%d")

        cfg = self.get_config()
        min_odds = float(cfg.get("min_leg_odds", 1.23))
        max_odds = float(cfg.get("max_leg_odds", 1.28))
        target_legs = int(cfg.get("leg_count", 3))

        slip = BasketballTicketBuilder.build_daily_2x_cushion_slip(
            session_slate=session_slate,
            min_leg_odds=min_odds,
            max_leg_odds=max_odds,
            target_legs=target_legs
        )

        booking_code = slip.get("booking_code")
        telegram_sent = False

        if slip.get("status") == "SUCCESS":
            if send_telegram and booking_code and booking_code not in ("N/A", "", None):
                telegram_sent = BasketballTelegramNotifier.dispatch_daily_2x_slip(slip, custom_title=custom_title)
                slip["telegram_dispatched"] = telegram_sent

            # Update history and config
            run_entry = {
                "date": today_str,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "slot": slot_name,
                "session_slate": session_slate,
                "status": "SUCCESS",
                "booking_code": booking_code,
                "actual_odds": slip.get("actual_odds"),
                "legs": len(slip.get("picks", [])),
                "telegram_dispatched": telegram_sent
            }
            history = cfg.get("run_history", [])
            history.insert(0, run_entry)
            cfg["run_history"] = history[:40]

            if slot_name == "DAYTIME":
                cfg["last_daytime_run_date"] = today_str
            elif slot_name == "MIDNIGHT":
                cfg["last_midnight_run_date"] = today_str
            cfg["last_run_date"] = today_str
            cfg["last_ticket"] = slip
            self.save_config(cfg)
        else:
            logger.warning(f"[BasketballScheduler] Execution status: {slip.get('status')} - {slip.get('message')}")

        return {
            "status": slip.get("status"),
            "slot": slot_name,
            "session_slate": session_slate,
            "ticket": slip,
            "telegram_sent": telegram_sent,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

# Global singleton
basketball_scheduler = BasketballCronScheduler()
