import os
import json
import time
import tempfile
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
    "active_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],  # Daily VIP Suite (Mon-Sun)
    "enable_rollover_2x": True,            # Slip 1: 1.50x Rollover (2–3 banker legs)
    "enable_acca_5x": True,                # Slip 2: 5.0x Precision Acca (7–8 banker legs)
    "enable_acca_10x": True,               # Slip 3: 10.0x Mega Multiplier (10–12 banker legs)
    "enable_acca_20x": False,              # Disabled by default
    "target_odds": 1.50,                   # 1.50x Rollover sweet spot (2–3 banker games)
    "rollover_target_odds": 1.50,          # Configurable via web/telegram
    "acca_5x_target_odds": 5.00,           # Configurable via web/telegram
    "acca_10x_target_odds": 10.00,         # Configurable via web/telegram
    "acca_20x_target_odds": 20.00,         # Configurable via web/telegram
    "max_leg_odds": 1.35,                  # Banker safety corridor
    "dispatch_time": "10:00",              # 10:00 AM WAT sharp
    "campaign_mode": "CONTINUOUS",         # "CONTINUOUS" or "CHALLENGE"
    "challenge_days": 10,                  # Total duration in days (e.g. 3, 4, 5, 7, 10)
    "challenge_day_current": 1,            # Current day in compounding ladder
    "challenge_start_date": None,          # Start date string YYYY-MM-DD
    "challenge_end_date": None,            # Projected end date string
    "starting_stake": 5000,                # Initial stake in NGN
    "challenge_status": "ACTIVE",          # "ACTIVE", "PAUSED", "COMPLETED"
    "last_run_date": None,
    "last_ticket": None,
    "last_trio_result": None,
    "run_history": []
}

class RolloverCronScheduler:
    """
    Autonomous Background Cron Scheduler for StatIQ Rollover.
    Monitors system clock, discovers scheduled active days, executes at 10:00 AM sharp,
    generates SportyBet booking code, dispatches Telegram signals, and audits tickets.
    Includes cross-worker file locking to strictly prevent duplicate dispatches.
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
        self._lock_file = None
        self._last_dispatched_date: Optional[str] = None
        self._ensure_config_file()

    def _acquire_process_lock(self) -> bool:
        """
        Cross-worker file lock: Ensures only 1 process/worker on the server
        runs the Rollover Cron daemon to prevent duplicate daily dispatches.
        """
        lock_path = os.path.join(tempfile.gettempdir(), "statiq_rollover_cron.lock")
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
            logger.warning(f"[RolloverScheduler] Process lock check note: {e}")
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
        if not self._acquire_process_lock():
            logger.info("[RolloverScheduler] Another worker holds the cron lock. Skipping daemon in this worker.")
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
                            self.save_config(cfg)
                            logger.info(f"[RolloverScheduler] Compounding Challenge completed ({total_days} days reached). Daily VIP Automation remains active.")
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

                    # Check if today is an active day and current time matches or has passed dispatch_time
                    if (current_day_code in active_days) and (current_time_str >= dispatch_time) and (last_run != today_str) and (self._last_dispatched_date != today_str) and (now_wat.hour < 21):
                        self._last_dispatched_date = today_str
                        # CRITICAL: Persist last_run_date IMMEDIATELY before launching async generation
                        # This prevents concurrent worker processes or subsequent ticks from double-triggering
                        cfg["last_run_date"] = today_str
                        self.save_config(cfg)
                        logger.info(f"[RolloverScheduler] Triggering scheduled Daily VIP run for {current_day_code} ({today_str} @ {current_time_str})...")
                        target_odds = float(cfg.get("target_odds", 1.50))

                        challenge_info = None
                        current_stake = float(cfg.get("starting_stake", 5000))
                        if cfg.get("campaign_mode") == "CHALLENGE":
                            curr_day = int(cfg.get("challenge_day_current", 1))
                            tot_days = int(cfg.get("challenge_days", 10))
                            challenge_info = f"Day {curr_day} of {tot_days}"
                            current_stake = round(current_stake * (target_odds ** (curr_day - 1)))

                        en_ro = bool(cfg.get("enable_rollover_2x", True))
                        en_10x = bool(cfg.get("enable_acca_10x", True))
                        en_20x = bool(cfg.get("enable_acca_20x", False))
                        en_5x = bool(cfg.get("enable_acca_5x", True))

                        ro_target = float(cfg.get("rollover_target_odds") or cfg.get("target_odds") or 1.50)
                        a5_target = float(cfg.get("acca_5x_target_odds") or 5.00)
                        a10_target = float(cfg.get("acca_10x_target_odds") or 10.00)
                        a20_target = float(cfg.get("acca_20x_target_odds") or 20.00)

                        # Execute async run in dedicated event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        trio_res = loop.run_until_complete(
                            EliteRolloverEngine.book_and_dispatch_daily_trio(
                                enable_rollover=en_ro,
                                enable_10odds=en_10x,
                                enable_20odds=en_20x,
                                enable_5odds=en_5x,
                                send_telegram=True,
                                rollover_stake=current_stake,
                                rollover_target_odds=ro_target,
                                acca_5x_target_odds=a5_target,
                                acca_10x_target_odds=a10_target,
                                acca_20x_target_odds=a20_target,
                                challenge_day_info=challenge_info
                            )
                        )
                        loop.close()

                        # Update run history & state on SUCCESS or if ticket was already dispatched to Telegram
                        is_success = (trio_res.get("status") == "SUCCESS")
                        is_dispatched = bool(
                            trio_res.get("rollover_ticket", {}).get("telegram_dispatched")
                            or trio_res.get("acca_5x_ticket", {}).get("telegram_dispatched")
                            or trio_res.get("acca_10x_ticket", {}).get("telegram_dispatched")
                        )

                        if is_success or is_dispatched:
                            cfg["last_run_date"] = today_str
                            cfg["last_trio_result"] = trio_res
                            primary_ticket = (trio_res.get("rollover_ticket") 
                                              or trio_res.get("acca_5x_ticket")
                                              or trio_res.get("acca_10x_ticket")
                                              or trio_res.get("acca_20x_ticket"))
                            cfg["last_ticket"] = primary_ticket

                            history_entry = {
                                "date": today_str,
                                "time": current_time_str,
                                "status": "SUCCESS" if is_success else "PARTIAL_DISPATCH",
                                "unique_fixtures": trio_res.get("total_unique_fixtures", 0),
                                "rollover_code": trio_res.get("rollover_ticket", {}).get("booking_code") if trio_res.get("rollover_ticket") else None,
                                "acca_5x_code": trio_res.get("acca_5x_ticket", {}).get("booking_code") if trio_res.get("acca_5x_ticket") else None,
                                "acca_10x_code": trio_res.get("acca_10x_ticket", {}).get("booking_code") if trio_res.get("acca_10x_ticket") else None,
                                "acca_20x_code": trio_res.get("acca_20x_ticket", {}).get("booking_code") if trio_res.get("acca_20x_ticket") else None,
                                "zero_overlap": trio_res.get("zero_overlap_guaranteed", True),
                                "calendar_mode": trio_res.get("calendar_mode", "DAILY_VIP_BANKER_SUITE"),
                                "campaign_mode": cfg.get("campaign_mode", "CONTINUOUS"),
                                "stake": current_stake
                            }

                            # If Challenge mode, record day and progress counter
                            if cfg.get("campaign_mode") == "CHALLENGE":
                                curr_day = int(cfg.get("challenge_day_current", 1))
                                tot_days = int(cfg.get("challenge_days", 10))
                                history_entry["challenge_day"] = f"Day {curr_day} of {tot_days}"
                                
                                # Increment day for next run if primary rollover succeeded or dispatched
                                if is_success or (trio_res.get("rollover_ticket") and trio_res["rollover_ticket"].get("booking_code") not in (None, "N/A", "", "RESTED")):
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
                            logger.info(f"[RolloverScheduler] Scheduled run completed successfully (is_success={is_success}, is_dispatched={is_dispatched}).")
                        else:
                            # True booking failure with ZERO Telegram dispatches: wait before retrying to prevent rapid loops
                            logger.warning(f"[RolloverScheduler] Scheduled run did not succeed ({trio_res.get('status')}: {trio_res.get('message')}). Retrying in 5 minutes.")
                            time.sleep(300)

            except Exception as e:
                logger.error(f"[RolloverScheduler] Error in cron tick: {e}")

            time.sleep(30)  # Check every 30 seconds

    async def run_now(
        self,
        target_odds: Optional[float] = None,
        rollover_target_odds: Optional[float] = None,
        acca_5x_target_odds: Optional[float] = None,
        acca_10x_target_odds: Optional[float] = None,
        acca_20x_target_odds: Optional[float] = None,
        max_leg_odds: Optional[float] = None,
        enable_rollover: Optional[bool] = None,
        enable_10odds: Optional[bool] = None,
        enable_20odds: Optional[bool] = None,
        enable_5odds: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Manually triggers an immediate run of the Daily VIP Trio with dynamic target odds.
        """
        cfg = self.get_config()
        en_ro = enable_rollover if enable_rollover is not None else bool(cfg.get("enable_rollover_2x", True))
        en_10x = enable_10odds if enable_10odds is not None else bool(cfg.get("enable_acca_10x", True))
        en_20x = enable_20odds if enable_20odds is not None else bool(cfg.get("enable_acca_20x", False))
        en_5x = enable_5odds if enable_5odds is not None else bool(cfg.get("enable_acca_5x", True))

        ro_target = rollover_target_odds if rollover_target_odds is not None else (target_odds if target_odds is not None else float(cfg.get("rollover_target_odds") or cfg.get("target_odds") or 1.50))
        a5_target = acca_5x_target_odds if acca_5x_target_odds is not None else float(cfg.get("acca_5x_target_odds") or 5.00)
        a10_target = acca_10x_target_odds if acca_10x_target_odds is not None else float(cfg.get("acca_10x_target_odds") or 10.00)
        a20_target = acca_20x_target_odds if acca_20x_target_odds is not None else float(cfg.get("acca_20x_target_odds") or 20.00)

        challenge_info = None
        current_stake = float(cfg.get("starting_stake", 5000))
        if cfg.get("campaign_mode") == "CHALLENGE":
            curr_day = int(cfg.get("challenge_day_current", 1))
            tot_days = int(cfg.get("challenge_days", 10))
            challenge_info = f"Day {curr_day} of {tot_days}"
            current_stake = round(current_stake * (ro_target ** (curr_day - 1)))

        logger.info(f"[RolloverScheduler] Executing manual 'Run Now' Daily VIP Trio (ro: {en_ro} @ {ro_target}x, 5x: {en_5x} @ {a5_target}x, 10x: {en_10x} @ {a10_target}x)...")
        trio_res = await EliteRolloverEngine.book_and_dispatch_daily_trio(
            enable_rollover=en_ro,
            enable_10odds=en_10x,
            enable_20odds=en_20x,
            enable_5odds=en_5x,
            send_telegram=True,
            rollover_stake=current_stake,
            rollover_target_odds=ro_target,
            acca_5x_target_odds=a5_target,
            acca_10x_target_odds=a10_target,
            acca_20x_target_odds=a20_target,
            challenge_day_info=challenge_info
        )

        WAT_TZ = datetime.timezone(datetime.timedelta(hours=1))
        now_wat = datetime.datetime.now(WAT_TZ)
        today_str = now_wat.strftime("%Y-%m-%d")
        cfg["last_trio_result"] = trio_res
        primary_ticket = (trio_res.get("rollover_ticket") 
                          or trio_res.get("acca_5x_ticket")
                          or trio_res.get("acca_10x_ticket")
                          or trio_res.get("acca_20x_ticket"))
        cfg["last_ticket"] = primary_ticket

        history = cfg.get("run_history", [])
        history.insert(0, {
            "date": today_str,
            "time": now_wat.strftime("%H:%M:%S"),
            "status": trio_res.get("status"),
            "unique_fixtures": trio_res.get("total_unique_fixtures", 0),
            "rollover_code": trio_res.get("rollover_ticket", {}).get("booking_code") if trio_res.get("rollover_ticket") else None,
            "acca_5x_code": trio_res.get("acca_5x_ticket", {}).get("booking_code") if trio_res.get("acca_5x_ticket") else None,
            "acca_10x_code": trio_res.get("acca_10x_ticket", {}).get("booking_code") if trio_res.get("acca_10x_ticket") else None,
            "acca_20x_code": trio_res.get("acca_20x_ticket", {}).get("booking_code") if trio_res.get("acca_20x_ticket") else None,
            "zero_overlap": trio_res.get("zero_overlap_guaranteed", True),
            "calendar_mode": trio_res.get("calendar_mode", "DAILY_VIP_BANKER_SUITE"),
            "manual_trigger": True
        })
        cfg["run_history"] = history[:30]
        self.save_config(cfg)

        return trio_res

    def get_active_campaign(self) -> Dict[str, Any]:
        """
        Returns a rich representation of the active running campaign (Compounding Challenge or Continuous Daily VIP).
        Calculates ladder days, progress, stake compounding, won/loss statuses, and today's active leg.
        """
        cfg = self.get_config()
        is_enabled = bool(cfg.get("is_enabled", True))
        campaign_mode = cfg.get("campaign_mode", "CHALLENGE")
        challenge_status = cfg.get("challenge_status", "ACTIVE")
        
        # If challenge status is DISMISSED or removed
        if challenge_status in ("DISMISSED", "REMOVED") and campaign_mode == "CHALLENGE":
            return {
                "has_active": False,
                "campaign_mode": "CHALLENGE",
                "challenge_status": challenge_status,
                "is_enabled": is_enabled
            }

        target_odds = float(cfg.get("target_odds", 2.00))
        starting_stake = float(cfg.get("starting_stake", 5000))
        total_days = int(cfg.get("challenge_days", 3 if campaign_mode == "CHALLENGE" else 1))
        current_day = int(cfg.get("challenge_day_current", 1))
        start_date_str = cfg.get("challenge_start_date") or datetime.date.today().isoformat()
        
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
        except Exception:
            start_date = datetime.date.today()

        today = datetime.date.today()
        # Compute days elapsed
        days_diff = (today - start_date).days
        calculated_day = max(1, min(total_days, days_diff + 1))
        if calculated_day > current_day and challenge_status == "ACTIVE":
            current_day = calculated_day

        run_history = cfg.get("run_history", [])
        
        # Build day ladder
        days = []
        won_count = 0
        current_stake = starting_stake
        for d in range(1, total_days + 1):
            day_date = start_date + datetime.timedelta(days=d - 1)
            day_str = day_date.isoformat()
            weekday_name = day_date.strftime("%A")
            day_stake = round(starting_stake * (target_odds ** (d - 1)))
            day_potential = round(day_stake * target_odds)
            
            # Determine status of this day
            matched_hist = None
            for h in run_history:
                if h.get("date") == day_str or h.get("day") == d:
                    matched_hist = h
                    break
            
            if matched_hist and matched_hist.get("status") in ("WON", "LOST"):
                d_status = matched_hist.get("status")
                d_code = matched_hist.get("rollover_code") or matched_hist.get("booking_code")
            elif d < current_day:
                d_status = "WON"
                d_code = f"RO-DAY{d}"
            elif d == current_day:
                d_status = "RUNNING"
                d_code = (cfg.get("last_ticket") or {}).get("booking_code") if cfg.get("last_ticket") else None
            else:
                d_status = "PENDING"
                d_code = None

            if d_status == "WON":
                won_count += 1
                if d == current_day - 1:
                    current_stake = day_potential
            elif d == current_day:
                current_stake = day_stake

            real_stake = float((matched_hist.get("stake") or day_stake) if matched_hist else day_stake)
            real_payout = float((matched_hist.get("payout") or day_potential) if matched_hist else day_potential)
            real_odds = float((matched_hist.get("actual_odds") or matched_hist.get("target_odds") or target_odds) if matched_hist else target_odds)

            days.append({
                "day": d,
                "date": day_str,
                "weekday": weekday_name,
                "stake": real_stake,
                "odds": real_odds,
                "potential_payout": real_payout,
                "status": d_status,
                "ticket_id": matched_hist.get("ticket_id") if matched_hist else None,
                "booking_code": d_code,
                "legs": matched_hist.get("legs") if matched_hist else None,
                "is_today": (day_str == today.isoformat() or d == current_day),
                "summary": matched_hist.get("summary") if matched_hist else None
            })

        final_goal = round(starting_stake * (target_odds ** total_days))
        progress_pct = round((won_count / max(1, total_days)) * 100, 1)
        is_completed = (challenge_status == "COMPLETED") or (won_count >= total_days)

        active_ticket = cfg.get("last_ticket")

        has_active = is_enabled and (campaign_mode == "CHALLENGE") and (challenge_status not in ("DISMISSED", "COMPLETED"))

        return {
            "has_active": has_active,
            "campaign_mode": campaign_mode,
            "challenge_status": "COMPLETED" if is_completed else challenge_status,
            "is_completed": is_completed,
            "is_enabled": is_enabled,
            "target_odds": target_odds,
            "starting_stake": starting_stake,
            "current_stake": current_stake,
            "final_goal": final_goal,
            "total_days": total_days,
            "current_day": current_day,
            "start_date": start_date_str,
            "end_date": (start_date + datetime.timedelta(days=total_days - 1)).isoformat(),
            "won_count": won_count,
            "progress_pct": progress_pct,
            "days": days,
            "active_ticket": active_ticket,
            "last_trio_result": cfg.get("last_trio_result"),
            "dispatch_time": cfg.get("dispatch_time", "10:00")
        }

    def update_challenge_day(self, day_num: int, status: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Updates a specific challenge day result (WON or LOST)."""
        cfg = self.get_config()
        run_history = cfg.get("run_history", [])
        
        found = False
        for h in run_history:
            if h.get("day") == day_num:
                h["status"] = status
                if notes:
                    h["summary"] = notes
                found = True
                break
        if not found:
            run_history.append({
                "day": day_num,
                "status": status,
                "summary": notes
            })
        cfg["run_history"] = run_history

        total_days = int(cfg.get("challenge_days", 3))
        if status == "WON":
            if day_num < total_days:
                cfg["challenge_day_current"] = day_num + 1
            else:
                cfg["challenge_status"] = "COMPLETED"
                cfg["challenge_day_current"] = total_days
        elif status == "LOST":
            cfg["challenge_status"] = "LOST"

        self.save_config(cfg)
        return self.get_active_campaign()

    def dismiss_campaign(self) -> Dict[str, Any]:
        """Dismisses and clears the completed or active challenge, removing it from the running card."""
        cfg = self.get_config()
        cfg["challenge_status"] = "DISMISSED"
        cfg["campaign_mode"] = "CONTINUOUS"
        self.save_config(cfg)
        return {"status": "SUCCESS", "message": "Campaign concluded and removed."}

    def start_challenge(self, days: int = 3, starting_stake: float = 5000.0, target_odds: float = 1.50) -> Dict[str, Any]:
        """Starts a fresh compounding challenge ladder."""
        today_str = datetime.date.today().isoformat()
        end_date = (datetime.date.today() + datetime.timedelta(days=days - 1)).isoformat()
        cfg = {
            "campaign_mode": "CHALLENGE",
            "challenge_days": int(days),
            "challenge_day_current": 1,
            "challenge_start_date": today_str,
            "challenge_end_date": end_date,
            "starting_stake": float(starting_stake),
            "target_odds": float(target_odds),
            "challenge_status": "ACTIVE",
            "is_enabled": True,
            "run_history": []
        }
        self.save_config(cfg)
        return self.get_active_campaign()

# Global singleton
rollover_scheduler = RolloverCronScheduler()
