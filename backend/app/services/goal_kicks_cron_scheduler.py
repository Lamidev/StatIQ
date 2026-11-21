import os
import json
import time
import tempfile
import threading
import logging
import datetime
import asyncio
from typing import Dict, Any, List, Optional

from app.services.goal_kicks_service import goal_kicks_service
from app.services.rollover_telegram_notifier import RolloverTelegramNotifier

logger = logging.getLogger("statiq.goalkicks.scheduler")

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "goal_kicks_schedule_config.json"))

DEFAULT_CONFIG = {
    "is_enabled": True,
    "active_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],  # Daily automation (Mon-Sun)
    "dispatch_time": "09:00",              # 09:00 AM WAT (Delivered before 10:00 AM main suite!)
    "enable_first_half_2x": True,          # 2.0x 1H Goal Kicks Under 8.5 / 7.5
    "enable_under_2x": True,               # 2.0x FT Goal Kicks UNDER Fortress (Under 17.5–20.5)
    "enable_over_2x": False,               # 2.0x FT Goal Kicks OVER Floor (disabled by default)
    "target_odds": 2.00,                   # 2.00x sweet spot (3–4 tactical legs)
    "last_run_date": None,
    "last_duo_result": None,
    "run_history": []
}


class GoalKicksCronScheduler:
    """
    Autonomous Background Cron Scheduler for StatIQ 2.0x Goal Kicks Rollover.
    
    Monitors system clock, checks SportyBet today's games endpoint daily at 10:15 AM WAT,
    generates 2.0x FT UNDER Fortress and 2.0x FT OVER Floor tickets, books SportyBet codes,
    and dispatches live alerts to Telegram.
    
    Includes cross-worker file locking and stale PID detection to prevent duplicate runs.
    """

    _instance = None
    _lock = threading.Lock()
    _running = False
    _thread: Optional[threading.Thread] = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GoalKicksCronScheduler, cls).__new__(cls)
                cls._instance._last_dispatched_date = None
                cls._instance._lock_file = None
                cls._instance._retry_count = 0
                cls._instance._ensure_config_file()
            return cls._instance

    def _acquire_process_lock(self) -> bool:
        """Cross-worker file lock to guarantee exactly one active worker runs the cron loop."""
        lock_path = os.path.join(tempfile.gettempdir(), "statiq_goal_kicks_cron.lock")
        try:
            self._lock_file = open(lock_path, "a+")
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except (IOError, OSError):
                    return True
            else:
                import fcntl
                try:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except (IOError, OSError):
                    try:
                        with open(lock_path, "r") as rf:
                            content = rf.read().strip()
                        if content.isdigit():
                            pid = int(content)
                            if pid != os.getpid() and not os.path.exists(f"/proc/{pid}"):
                                logger.info(f"[GoalKicksScheduler] Stale lock from dead PID {pid}. Reclaiming lock.")
                                return True
                    except Exception:
                        pass
                    return True
        except Exception as e:
            logger.warning(f"[GoalKicksScheduler] Process lock check note: {e}")
            return True
        return True

    def _ensure_config_file(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            self.save_config(DEFAULT_CONFIG)

    def load_config(self) -> Dict[str, Any]:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(data)
                # Migrate legacy 10:15 dispatch time to 09:00 AM WAT
                if merged.get("dispatch_time") == "10:15":
                    merged["dispatch_time"] = "09:00"
                if "enable_first_half_2x" not in merged:
                    merged["enable_first_half_2x"] = True
                return merged
        except Exception as e:
            logger.error(f"[GoalKicksScheduler] Error loading config: {e}")
            return DEFAULT_CONFIG.copy()

    def save_config(self, cfg: Dict[str, Any]):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logger.error(f"[GoalKicksScheduler] Error saving config: {e}")

    def start(self):
        """Starts the autonomous background Goal Kicks daemon thread."""
        with self._lock:
            if self._running:
                return
            if not self._acquire_process_lock():
                logger.info("[GoalKicksScheduler] Another worker holds the lock. Skipping daemon launch.")
                return

            self._running = True
            self._thread = threading.Thread(target=self._run_cron_loop, daemon=True, name="statiq-goalkicks-scheduler")
            self._thread.start()
            logger.info("[GoalKicksScheduler] 2.0x Goal Kicks Daily Cron Daemon started.")

    def stop(self):
        """Stops the background daemon."""
        with self._lock:
            self._running = False
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass

    def _run_cron_loop(self):
        """Background loop monitoring system time for daily morning dispatch."""
        logger.info("[GoalKicksScheduler] Cron loop active. Monitoring WAT dispatch time...")
        while self._running:
            try:
                cfg = self.load_config()
                if cfg.get("is_enabled", True):
                    # West Africa Time (WAT) is UTC+1
                    now_wat = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
                    current_time_str = now_wat.strftime("%H:%M")
                    current_day_code = now_wat.strftime("%a").upper()
                    today_str = now_wat.strftime("%Y-%m-%d")

                    active_days = cfg.get("active_days", ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
                    dispatch_time = cfg.get("dispatch_time", "09:00")
                    last_run = cfg.get("last_run_date")

                    # Check if today is active, time matches or has passed, and hasn't dispatched today
                    if (current_day_code in active_days) and (current_time_str >= dispatch_time) and (last_run != today_str) and (self._last_dispatched_date != today_str) and (now_wat.hour < 21):
                        logger.info(f"[GoalKicksScheduler] Triggering scheduled 2.0x Goal Kicks run for {current_day_code} ({today_str} @ {current_time_str})...")
                        target_odds = float(cfg.get("target_odds", 2.00))

                        # Build duo asynchronously
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            duo_res = loop.run_until_complete(
                                goal_kicks_service.build_daily_goal_kicks_duo(
                                    time_horizon="TODAY",
                                    target_odds=target_odds
                                )
                            )
                        finally:
                            loop.close()

                        dispatched_any = False
                        first_half_ticket = duo_res.get("first_half_ticket", {})
                        under_ticket = duo_res.get("under_ticket", {})
                        over_ticket = duo_res.get("over_ticket", {})

                        if cfg.get("enable_first_half_2x", True) and first_half_ticket.get("status") == "SUCCESS":
                            sent = RolloverTelegramNotifier.dispatch_goal_kicks_slip(first_half_ticket, mode_label="1H UNDER")
                            if sent:
                                dispatched_any = True
                                logger.info(f"[GoalKicksScheduler] Dispatched 2.0x 1H Under slip ({first_half_ticket.get('booking_code')}).")

                        if cfg.get("enable_under_2x", True) and under_ticket.get("status") == "SUCCESS":
                            sent = RolloverTelegramNotifier.dispatch_goal_kicks_slip(under_ticket, mode_label="FT UNDER")
                            if sent:
                                dispatched_any = True
                                logger.info(f"[GoalKicksScheduler] Dispatched 2.0x FT Under slip ({under_ticket.get('booking_code')}).")

                        if cfg.get("enable_over_2x", False) and over_ticket.get("status") == "SUCCESS":
                            sent = RolloverTelegramNotifier.dispatch_goal_kicks_slip(over_ticket, mode_label="FT OVER")
                            if sent:
                                dispatched_any = True
                                logger.info(f"[GoalKicksScheduler] Dispatched 2.0x FT Over slip ({over_ticket.get('booking_code')}).")

                        if dispatched_any:
                            self._last_dispatched_date = today_str
                            self._retry_count = 0
                            cfg["last_run_date"] = today_str
                            cfg["last_duo_result"] = duo_res
                            history = cfg.get("run_history", [])
                            history.insert(0, {
                                "date": today_str,
                                "time": current_time_str,
                                "status": "SUCCESS",
                                "first_half_code": first_half_ticket.get("booking_code"),
                                "under_code": under_ticket.get("booking_code"),
                                "over_code": over_ticket.get("booking_code"),
                                "first_half_odds": first_half_ticket.get("actual_odds"),
                                "under_odds": under_ticket.get("actual_odds"),
                                "over_odds": over_ticket.get("actual_odds")
                            })
                            cfg["run_history"] = history[:30]
                            self.save_config(cfg)
                            logger.info("[GoalKicksScheduler] Daily 2.0x Goal Kicks dispatch completed successfully.")
                        else:
                            self._retry_count = getattr(self, "_retry_count", 0) + 1
                            logger.warning(f"[GoalKicksScheduler] Daily run attempt {self._retry_count}/3 did not yield active slips.")
                            if self._retry_count >= 3 or now_wat.hour >= 18:
                                self._last_dispatched_date = today_str
                                cfg["last_run_date"] = today_str
                                self.save_config(cfg)
                                self._retry_count = 0
                                logger.info("[GoalKicksScheduler] Marked day rested after 3 attempts or late hour.")
                            else:
                                time.sleep(300)

            except Exception as e:
                logger.error(f"[GoalKicksScheduler] Error in cron tick: {e}")

            time.sleep(30)

    def run_now(self, force: bool = True) -> Dict[str, Any]:
        """Manually trigger the 2.0x Goal Kicks generator and dispatch immediately."""
        cfg = self.load_config()
        target_odds = float(cfg.get("target_odds", 2.00))
        logger.info(f"[GoalKicksScheduler] Manual trigger initiated (target_odds={target_odds})...")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            duo_res = loop.run_until_complete(
                goal_kicks_service.build_daily_goal_kicks_duo(
                    time_horizon="TODAY",
                    target_odds=target_odds
                )
            )
        finally:
            loop.close()

        first_half_ticket = duo_res.get("first_half_ticket", {})
        under_ticket = duo_res.get("under_ticket", {})
        over_ticket = duo_res.get("over_ticket", {})

        if cfg.get("enable_first_half_2x", True) and first_half_ticket.get("status") == "SUCCESS":
            RolloverTelegramNotifier.dispatch_goal_kicks_slip(first_half_ticket, mode_label="1H UNDER")

        if cfg.get("enable_under_2x", True) and under_ticket.get("status") == "SUCCESS":
            RolloverTelegramNotifier.dispatch_goal_kicks_slip(under_ticket, mode_label="FT UNDER")

        if cfg.get("enable_over_2x", False) and over_ticket.get("status") == "SUCCESS":
            RolloverTelegramNotifier.dispatch_goal_kicks_slip(over_ticket, mode_label="FT OVER")

        return duo_res


goal_kicks_scheduler = GoalKicksCronScheduler()
