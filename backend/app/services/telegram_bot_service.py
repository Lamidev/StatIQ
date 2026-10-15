"""
StatIQ Autonomous Telegram Bot Service
======================================
Enables complete remote control of StatIQ directly from Telegram:
- On-demand AI Accumulator generation by Target Odds (/odds 2.0, /odds 5.0, etc.)
- On-demand AI Accumulator generation by Game Count (/games 10, /games 12)
- On-demand Daily Elite Rollover (/rollover)
- External Ticket Trimmer / Risk Purge (/trim <code>, /remove <code>)
- Multi-Ticket generation with Strict Zero-Overlap Guarantee (2 tickets of 10-12 games each)
- Direct SportyBet code & URL recognition with interactive 1-tap inline buttons
- Strict 1.15 minimum odds floor enforced on every selection
"""

import os
import re
import html
import time
import math
import json
import asyncio
import logging
import threading
import tempfile
import collections
from typing import Dict, Any, List, Optional, Tuple

import httpx

logger = logging.getLogger("statiq.telegram_bot")


def _esc(val: Any) -> str:
    """Escapes string safely for Telegram HTML parse mode."""
    if val is None:
        return ""
    return html.escape(str(val))


class StatIQTelegramBot:
    """
    Standalone long-polling Telegram Bot daemon for StatIQ.
    Requires no external telegram library; runs natively via HTTPX.
    Includes strict multi-process deduplication and update tracking.
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0
        self._processed_msg_keys = collections.deque(maxlen=2000)
        self._processed_msg_keys_set = set()
        self._processed_cq_ids = collections.deque(maxlen=2000)
        self._processed_cq_ids_set = set()
        self._lock_file = None

    def _acquire_process_lock(self) -> bool:
        """
        Cross-worker file lock: Ensures only 1 process/worker on the server
        runs the Telegram long-polling worker to prevent duplicate deliveries.
        """
        lock_path = os.path.join(tempfile.gettempdir(), "statiq_telegram_bot.lock")
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
            logger.warning(f"[TelegramBot] Process lock check note: {e}")
            return True

    @property
    def bot_token(self) -> str:
        return (os.getenv("TELEGRAM_BOT_TOKEN", "").replace('"', '').strip()
                or "8979207719:AAHmjFvyDDijF4xli6On0QyuGkX6IcCcuKI")

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[int] = None,
        parse_mode: str = "HTML"
    ) -> Optional[Dict[str, Any]]:
        """Sends an HTML formatted message with optional inline keyboard."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        for attempt in range(3):
            try:
                with httpx.Client(timeout=25.0) as client:
                    r = client.post(url, json=payload)
                    if r.status_code == 200:
                        return r.json().get("result")
                    else:
                        logger.warning(f"[TelegramBot] sendMessage failed (attempt {attempt+1}): {r.status_code} - {r.text}")
            except Exception as e:
                logger.warning(f"[TelegramBot] Attempt {attempt+1} error sending message: {e}")
                time.sleep(1.0)
        return None

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None):
        """Acknowledges button press."""
        url = f"{self.base_url}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(url, json=payload)
        except Exception as e:
            logger.warning(f"[TelegramBot] answerCallbackQuery error: {e}")

    def send_chat_action(self, chat_id: int | str, action: str = "typing"):
        """Sends a 'typing' status while crunching algorithms."""
        url = f"{self.base_url}/sendChatAction"
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(url, json={"chat_id": chat_id, "action": action})
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Command & Message Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def handle_start_or_help(self, chat_id: int | str):
        """Sends main StatIQ control panel menu."""
        msg = (
            "🤖 <b>Welcome to StatIQ AI Football Intelligence Engine</b>\n\n"
            "Control all StatIQ betting engines directly from Telegram without opening the web app:\n\n"
            "⚙️ <b>Daily VIP Automation (10:00 AM WAT Dispatch):</b>\n"
            "• <code>/auto</code> — View automation status & 1-tap toggles (2.0x, 5.0x, 10.0x)\n"
            "• <code>/dispatch</code> — <b>Run & dispatch today's 3 slips immediately</b>\n"
            "• 🔒 <i>Zero-Overlap Guarantee: All 3 daily tickets share 0 common fixtures!</i>\n\n"
            "🎯 <b>Generate by Target Odds (1 or 2 Zero-Overlap Slips):</b>\n"
            "• <code>/odds 2.0</code> — 2.0x Safe Multiplier (1 Slip)\n"
            "• <code>/odds 2.0 2 tickets</code> — <b>2 Variant Slips (Zero Overlap!)</b>\n"
            "• <code>/odds 5.0 2 tickets</code> — 2 Multiplier Slips (100% Unique Fixtures)\n\n"
            "⚽ <b>Generate by Match Count (1 or 2 Zero-Overlap Slips):</b>\n"
            "• <code>/games 10</code> — Top 10 High-Confidence Matches (1 Slip)\n"
            "• <code>/games 10 2 tickets</code> — <b>2 Variant Slips of 10 Matches Each</b>\n"
            "• <code>/games 12 2 tickets</code> — 2 Variant Slips of 12 Matches Each\n\n"
            "🚀 <b>On-Demand Rollover:</b>\n"
            "• <code>/rollover</code> — Instant 2.0x Low-Variance Day Slip\n\n"
            "🛡️ <b>Purge Bettor's Code As-Is (/remove):</b>\n"
            "Purges 50-50 traps, underdogs, and sub-1.15 legs while preserving bettor's exact picks:\n"
            "• <code>/remove CODE 15 games 2 tickets</code> ➔ <i>Extracts 2 Zero-Overlap Slips of 15 games!</i>\n"
            "• <code>/remove CODE</code> ➔ <i>Purges risk down to clean core games</i>\n\n"
            "⚡ <b>Upgrade Bettor's Markets (/edit):</b>\n"
            "Upgrades risky straight wins & Over 2.5 to verified live SportyBet safety markets (Double Chance, Over 1.5, Team Goals):\n"
            "• <code>/edit CODE 15 games 2 tickets</code> ➔ <i>Upgrades & extracts 2 Zero-Overlap Slips!</i>\n"
            "• <code>/edit CODE</code> ➔ <i>Upgrades slip to verified safe markets</i>\n\n"
            "📱 <b>Command Menu Modal:</b> Tap the <b>[Menu]</b> button at the bottom-left corner of your chat to view and run all commands with one tap!\n\n"
            "🛡️ <b>Strict Odds Floor:</b> Min odds ≥ <b>1.15x</b> strictly enforced across all picks."
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "⚙️ Daily Automation Hub", "callback_data": "auto:menu"},
                    {"text": "🚀 Dispatch Slips Now", "callback_data": "auto:dispatch"}
                ],
                [
                    {"text": "🎯 2.0x (1 Slip)", "callback_data": "gen:odds:2.0:1"},
                    {"text": "🎯 2.0x (2 Slips · Zero Overlap)", "callback_data": "gen:odds:2.0:2"}
                ],
                [
                    {"text": "🔥 5.0x (1 Slip)", "callback_data": "gen:odds:5.0:1"},
                    {"text": "🔥 5.0x (2 Slips · Zero Overlap)", "callback_data": "gen:odds:5.0:2"}
                ],
                [
                    {"text": "⚽ 10 Games (1 Slip)", "callback_data": "gen:games:10:1"},
                    {"text": "⚽ 10 Games (2 Slips · Zero Overlap)", "callback_data": "gen:games:10:2"}
                ]
            ]
        }
        return self.send_message(chat_id, msg, reply_markup=keyboard)

    def handle_auto_command(self, chat_id: int | str, text: str = ""):
        """Displays Daily VIP Automation status with 1-tap toggles, or processes direct commands like /auto on, /auto off."""
        from app.services.rollover_cron_scheduler import rollover_scheduler

        t_clean = text.lower().strip()
        if " on" in t_clean or t_clean in ("/start_auto", "/autoon") or "enable" in t_clean:
            rollover_scheduler.save_config({"is_enabled": True})
            self.send_message(
                chat_id,
                "🟢 <b>Daily VIP Automation Activated!</b>\n\n"
                "The engine will automatically book and dispatch 2.0x, 10.0x, and 20.0x slips daily at <b>10:00 AM WAT</b>.\n"
                "Adaptive Calendar Engine is active (Weekend Strict Zero-Overlap | Weekday Smart Hybrid)."
            )
        elif " off" in t_clean or t_clean in ("/stop_auto", "/autooff") or "disable" in t_clean or "pause" in t_clean:
            rollover_scheduler.save_config({"is_enabled": False})
            self.send_message(
                chat_id,
                "⏸️ <b>Daily VIP Automation Paused.</b>\n\n"
                "Scheduled 10:00 AM WAT dispatches are paused. Send <code>/auto on</code> to resume at any time."
            )

        cfg = rollover_scheduler.get_config()

        master_on = cfg.get("is_enabled", True)
        ro_on = cfg.get("enable_rollover_2x", True)
        acca10_on = cfg.get("enable_acca_10x", True)
        acca20_on = cfg.get("enable_acca_20x", True)
        disp_time = cfg.get("dispatch_time", "10:00")
        active_days = cfg.get("active_days", ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])

        active_days_set = set(d.upper() for d in active_days)
        if active_days_set >= {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}:
            days_label = "Daily (Mon–Sun)"
        elif active_days_set == {"MON", "TUE", "WED", "THU", "FRI"}:
            days_label = "Weekdays (Mon–Fri)"
        elif active_days_set == {"SAT", "SUN"}:
            days_label = "Weekends (Sat–Sun)"
        else:
            days_label = ", ".join(active_days)

        ro_icon = "✅ ON" if ro_on else "❌ OFF"
        acca10_icon = "✅ ON" if acca10_on else "❌ OFF"
        acca20_icon = "✅ ON" if acca20_on else "❌ OFF"
        master_icon = "🟢 ACTIVE" if master_on else "⏸️ PAUSED"

        msg = (
            "⚙️ <b>StatIQ Daily VIP Automation Controller</b>\n\n"
            f"🤖 <b>Scheduler Status:</b> {master_icon}\n"
            f"⏰ <b>Dispatch Time:</b> <b>{disp_time} AM WAT</b>\n"
            f"📅 <b>Active Days:</b> <b>{days_label}</b>\n"
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures Across All Daily Slips\n\n"
            "<b>📅 Daily VIP Slips (100% Zero-Overlap):</b>\n"
            f"• 🎯 <b>2.0x Rollover:</b> {ro_icon} (3–4 Banker Legs, 100% Isolated)\n"
            f"• ⚡ <b>10.0x Mega Slip #1:</b> {acca10_icon} (10–13 High-Dominance Legs)\n"
            f"• ⚡ <b>10.0x Mega Slip #2:</b> {acca10_icon} (10–13 High-Dominance Legs, 100% Unique)\n\n"
            "<i>Tap any button below to toggle tickets on/off, cycle active days, or dispatch today's slips instantly:</i>"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"🎯 2.0x Rollover ({'ON' if ro_on else 'OFF'})", "callback_data": "auto:toggle:ro"},
                    {"text": f"⚡ 10.0x Mega ({'ON' if acca10_on else 'OFF'})", "callback_data": "auto:toggle:10x"}
                ],
                [
                    {"text": f"🚀 20.0x Monster ({'ON' if acca20_on else 'OFF'})", "callback_data": "auto:toggle:20x"},
                    {"text": f"🤖 Master ({'Active' if master_on else 'Paused'})", "callback_data": "auto:toggle:master"}
                ],
                [
                    {"text": f"📅 Active Days: {days_label}", "callback_data": "auto:cycle:days"}
                ],
                [
                    {"text": "🚀 Dispatch Today's Slips Now", "callback_data": "auto:dispatch"}
                ]
            ]
        }
        return self.send_message(chat_id, msg, reply_markup=keyboard)

    def handle_schedule_command(self, chat_id: int | str, command_text: str):
        """Allows configuring dispatch time and active days via /schedule command."""
        from app.services.rollover_cron_scheduler import rollover_scheduler
        cfg = rollover_scheduler.get_config()
        t_lower = command_text.lower().strip()

        updates = {}
        # Check for time pattern (e.g. 10:00, 09:30)
        time_match = re.search(r"\b(\d{1,2}:\d{2})\b", t_lower)
        if time_match:
            raw_time = time_match.group(1)
            parts = raw_time.split(":")
            formatted_time = f"{int(parts[0]):02d}:{parts[1]}"
            updates["dispatch_time"] = formatted_time

        # Check for days pattern
        if "daily" in t_lower or "all" in t_lower or "everyday" in t_lower:
            updates["active_days"] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        elif "weekday" in t_lower or "weekdays" in t_lower or "mon-fri" in t_lower:
            updates["active_days"] = ["MON", "TUE", "WED", "THU", "FRI"]
        elif "weekend" in t_lower or "weekends" in t_lower or "sat-sun" in t_lower:
            updates["active_days"] = ["SAT", "SUN"]

        if updates:
            rollover_scheduler.save_config(updates)
            self.send_message(
                chat_id,
                f"✅ <b>Automation Schedule Updated!</b>\n"
                f"⏰ <b>Dispatch Time:</b> {updates.get('dispatch_time', cfg.get('dispatch_time', '10:00'))} AM WAT\n"
                f"📅 <b>Active Days:</b> {', '.join(updates.get('active_days', cfg.get('active_days', [])))}\n"
            )
        self.handle_auto_command(chat_id)

    def handle_challenge_command(self, chat_id: int | str):
        """Displays Compounding Challenge ladder status with current day, stake, and picks."""
        from app.services.rollover_cron_scheduler import rollover_scheduler
        camp = rollover_scheduler.get_active_campaign()
        
        curr_day = camp.get("current_day", 1)
        tot_days = camp.get("total_days", 3)
        curr_stake = camp.get("current_stake", 5000)
        target_odds = camp.get("target_odds", 2.0)
        pot_win = round(curr_stake * target_odds)
        won_cnt = camp.get("won_count", 0)
        final_goal = camp.get("final_goal", round(camp.get("starting_stake", 5000) * (target_odds ** tot_days)))
        
        lines = [
            f"🏆 <b>StatIQ {tot_days}-Day Compounding Challenge</b>",
            f"📅 <b>Progress:</b> Day <b>{curr_day} of {tot_days}</b> ({won_cnt}/{tot_days} Days Won)",
            f"💰 <b>Current Day Stake:</b> ₦{curr_stake:,.0f} ➔ Target: <b>₦{pot_win:,.0f}</b>",
            f"🎯 <b>Final Campaign Goal:</b> <b>₦{final_goal:,.0f}</b>",
            ""
        ]
        
        for d in camp.get("days", []):
            d_num = d.get("day")
            d_stk = d.get("stake")
            d_payout = d.get("potential_payout")
            status = d.get("status")
            wday = d.get("weekday")
            if status == "WON":
                icon = "✅ WON"
            elif status == "LOST":
                icon = "❌ LOST"
            elif status == "RUNNING":
                icon = "⏳ IN PLAY (TODAY)"
            else:
                icon = "⚪ PENDING"
            lines.append(f"• <b>Day {d_num} ({wday}):</b> {icon} — ₦{d_stk:,.0f} ➔ ₦{d_payout:,.0f}")
            
        active_t = camp.get("active_ticket")
        if active_t and active_t.get("booking_code"):
            code = active_t.get("booking_code")
            act_odds = active_t.get("actual_odds") or target_odds
            lines.append("")
            lines.append(f"🎟️ <b>Today's Day {curr_day} SportyBet Code:</b> <code>{code}</code> (@ <b>{act_odds:.2f}x</b>)")
            lines.append(f"🔗 <a href=\"https://www.sportybet.com/ng/?shareCode={code}\"><b>Open Directly in SportyBet</b></a>")

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🚀 Dispatch Slips Now", "callback_data": "auto:dispatch"},
                    {"text": f"✅ Mark Day {curr_day} Won", "callback_data": f"camp:won:{curr_day}"}
                ],
                [
                    {"text": "🔄 Start Fresh 3-Day Challenge", "callback_data": "camp:start:3"},
                    {"text": "🗑️ Conclude / Remove Campaign", "callback_data": "camp:dismiss"}
                ]
            ]
        }
        return self.send_message(chat_id, "\n".join(lines), reply_markup=keyboard)

    def handle_dispatch_command(self, chat_id: int | str):
        """Immediately executes and delivers the Daily VIP Trio tickets to Telegram."""
        now_ts = time.time()
        last_ts = getattr(self, "_last_dispatch_ts", 0)
        if (now_ts - last_ts) < 30:
            self.send_message(chat_id, "⏳ <b>Dispatch in progress or completed recently.</b> Please allow 30s between runs.")
            return
        self._last_dispatch_ts = now_ts

        self.send_message(
            chat_id,
            "⏳ <b>StatIQ Daily VIP Automation:</b> Querying today's fixtures and generating <b>2.0x Rollover, 5.0x Precision, and 10.0x Mega slips</b> with <b>Strict Zero-Overlap</b>..."
        )

        try:
            from app.services.rollover_cron_scheduler import rollover_scheduler
            from app.services.rollover_telegram_notifier import RolloverTelegramNotifier

            creds = RolloverTelegramNotifier.get_credentials()
            vip_chat_id = str(creds.get("chat_id") or "")
            is_same_channel = (str(chat_id) == vip_chat_id)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                trio_res = loop.run_until_complete(
                    rollover_scheduler.run_now()
                )
            finally:
                loop.close()

            status = trio_res.get("status")
            if status != "SUCCESS":
                self.send_message(chat_id, f"⚠️ <b>Notice:</b> {trio_res.get('message', 'Could not assemble tickets.')}")
                return

            dispatched_count = 0

            # If this command was run outside the VIP main channel, also forward the slips to the requester's chat
            if not is_same_channel:
                # 1. Rollover slip (2.0x)
                ro_ticket = trio_res.get("rollover_ticket")
                if ro_ticket and ro_ticket.get("picks"):
                    self._dispatch_ticket_message(
                        chat_id=chat_id,
                        title="🎯 StatIQ 2.0x Rollover Slip",
                        booking_code=ro_ticket.get("booking_code"),
                        share_url=ro_ticket.get("share_url"),
                        total_odds=ro_ticket.get("actual_odds", 2.0),
                        confidence=ro_ticket.get("confidence_score", 88.0),
                        picks=ro_ticket.get("picks", []),
                        extra_note="Daily VIP Slip 1 of 3 · 🎯 2.0x Rollover (100% Isolated Banker Legs) · Min Odds ≥ 1.15x"
                    )
                    dispatched_count += 1

                # 2. Midweek 5.0x Precision Multiplier (if present)
                acca5 = trio_res.get("acca_5x_ticket")
                if acca5 and acca5.get("picks"):
                    self._dispatch_ticket_message(
                        chat_id=chat_id,
                        title="🎯 StatIQ 5.0x Precision Multiplier Slip",
                        booking_code=acca5.get("booking_code"),
                        share_url=acca5.get("share_url"),
                        total_odds=acca5.get("actual_odds", 5.0),
                        confidence=acca5.get("confidence_score", 65.0),
                        picks=acca5.get("picks", []),
                        extra_note="Daily VIP Slip 2 of 3 · 🎯 5.0x Precision Acca (Elite European Selections) · Min Odds ≥ 1.15x"
                    )
                    dispatched_count += 1

                # 3. Daily 10.0x Mega Multiplier Slip (Slip #3)
                acca10 = trio_res.get("acca_10x_ticket")
                if acca10 and acca10.get("picks"):
                    self._dispatch_ticket_message(
                        chat_id=chat_id,
                        title="⚡ StatIQ 10.0x Mega Multiplier Slip",
                        booking_code=acca10.get("booking_code"),
                        share_url=acca10.get("share_url"),
                        total_odds=acca10.get("actual_odds", 10.0),
                        confidence=acca10.get("confidence_score", 52.0),
                        picks=acca10.get("picks", []),
                        extra_note="Daily VIP Slip 3 of 3 · ⚡ 10.0x Mega Multiplier · 🔒 Zero-Overlap · Min Odds ≥ 1.15x"
                    )
                    dispatched_count += 1
            else:
                # In VIP channel, RolloverTelegramNotifier already delivered all slips directly
                dispatched_count = (
                    (1 if trio_res.get("rollover_ticket") else 0) +
                    (1 if trio_res.get("acca_5x_ticket") else 0) +
                    (1 if trio_res.get("acca_10x_ticket") else 0) +
                    (1 if trio_res.get("acca_20x_ticket") else 0)
                )

            if dispatched_count > 0:
                cal_mode = "Daily VIP Banker Suite (2.0x + 5.0x + 10.0x)"
                self.send_message(
                    chat_id,
                    f"✅ <b>Daily VIP Automation Complete!</b> Dispatched {dispatched_count} slips via <b>{cal_mode}</b> with <b>{trio_res.get('total_unique_fixtures', 0)} unique fixtures</b>."
                )
        except Exception as e:
            logger.error(f"[TelegramBot] Dispatch error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error:</b> Dispatch failed ({_esc(str(e))}).")

    def handle_rollover_command(self, chat_id: int | str):
        """Generates and delivers today's Elite Rollover ticket on demand."""
        self.send_chat_action(chat_id, "typing")
        self.send_message(chat_id, "⏳ <b>StatIQ Elite Rollover Engine:</b> Querying today's fixtures and calculating low-variance Poisson probabilities...")

        try:
            from app.services.elite_rollover_engine import EliteRolloverEngine

            # Run rollover generation asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    EliteRolloverEngine.book_and_dispatch_rollover(
                        target_odds=2.00,
                        send_telegram=False,
                        max_leg_odds=1.45
                    )
                )
            finally:
                loop.close()

            status = res.get("status")
            if status == "SUCCESS":
                self._dispatch_ticket_message(
                    chat_id=chat_id,
                    title="🎯 StatIQ Elite Rollover Slip",
                    booking_code=res.get("booking_code"),
                    share_url=res.get("share_url"),
                    total_odds=res.get("actual_odds", 2.0),
                    confidence=res.get("confidence_score", 88.0),
                    picks=res.get("picks", []),
                    extra_note="Automated via StatIQ Telegram Controller · Min Odds ≥ 1.15x"
                )
            else:
                msg = f"⚠️ <b>Rollover Notice:</b> {res.get('message', 'Unable to build rollover slip at this moment.')}"
                self.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"[TelegramBot] Rollover error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error:</b> Rollover engine failed ({_esc(str(e))}). Please try again.")

    def handle_odds_command(self, chat_id: int | str, target_odds: float, num_tickets: int = 1):
        """Generates an AI accumulator targeting a specific odds multiplier (1 or more slips)."""
        num_tickets = max(1, min(4, int(num_tickets or 1)))
        self.send_chat_action(chat_id, "typing")
        variant_desc = f"<b>{num_tickets} Zero-Overlap Variant Slips</b>" if num_tickets > 1 else "1 core slip"
        self.send_message(
            chat_id,
            f"⏳ <b>StatIQ Elite Selection Engine:</b> Building {variant_desc} targeting <b>{target_odds:.2f}x</b> odds (Min Odds ≥ 1.15x)..."
        )

        try:
            from app.services.elite_rollover_engine import EliteRolloverEngine

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                portfolio = loop.run_until_complete(
                    EliteRolloverEngine.generate_elite_accumulator(
                        target_odds=target_odds,
                        num_tickets=num_tickets
                    )
                )
            finally:
                loop.close()

            # Fallback to ticket builder if elite accumulator returned empty
            if not portfolio:
                from app.api.endpoints.ticket_builder import BuildTicketRequest, build_ai_ticket
                req = BuildTicketRequest(
                    target_odds=target_odds,
                    target_mode="ODDS",
                    mode="ACCUMULATOR",
                    num_tickets=num_tickets,
                    overlap_mode="ZERO_OVERLAP",
                    use_live_odds=True,
                    risk_profile="BALANCED"
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(build_ai_ticket(req))
                    portfolio = res.get("portfolio_tickets") or ([res.get("ticket")] if res.get("ticket") else [])
                finally:
                    loop.close()

            dispatched = 0
            for slip in portfolio:
                slip_idx = slip.get("ticket_index", dispatched + 1)
                approved_legs = slip.get("approved_legs") or []
                if not approved_legs:
                    continue

                booking_code = slip.get("booking_code")
                share_url = slip.get("share_url")
                acc_odds = slip.get("accumulated_odds") or target_odds
                comb_prob = (slip.get("combined_probability") or 0.65) * 100.0

                title = (
                    f"🎯 StatIQ Elite Multiplier — Slip #{slip_idx} of {len(portfolio)} ({len(approved_legs)} Legs)"
                    if len(portfolio) > 1
                    else f"🎯 StatIQ Elite Multiplier ({len(approved_legs)} Legs)"
                )
                extra_note = (
                    f"Target: {target_odds:.2f}x · 🔒 Zero-Overlap Guarantee (100% Unique Fixtures) · Min Odds ≥ 1.15x"
                    if len(portfolio) > 1
                    else f"Target: {target_odds:.2f}x · Top-Tier Dominance Only · Min Odds ≥ 1.15x"
                )

                self._dispatch_ticket_message(
                    chat_id=chat_id,
                    title=title,
                    booking_code=booking_code,
                    share_url=share_url,
                    total_odds=acc_odds,
                    confidence=comb_prob,
                    picks=approved_legs,
                    extra_note=extra_note
                )
                dispatched += 1

            if dispatched == 0:
                self.send_message(chat_id, "⚠️ <b>Notice:</b> No suitable elite fixtures available meeting safety & odds floor right now.")
        except Exception as e:
            logger.error(f"[TelegramBot] Odds build error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error:</b> Failed to generate ticket ({_esc(str(e))}).")

    def handle_games_command(self, chat_id: int | str, target_games: int, num_tickets: int = 1):
        """Generates an AI accumulator with an exact game count (1 or more slips)."""
        target_games = max(3, min(35, target_games))
        num_tickets = max(1, min(4, int(num_tickets or 1)))
        self.send_chat_action(chat_id, "typing")
        variant_desc = f"<b>{num_tickets} Zero-Overlap Slips</b> of {target_games} matches each" if num_tickets > 1 else f"top <b>{target_games}</b> matches"
        self.send_message(
            chat_id,
            f"⏳ <b>StatIQ Elite Selection Engine:</b> Selecting {variant_desc} (Min Odds ≥ 1.15x)..."
        )

        try:
            from app.services.elite_rollover_engine import EliteRolloverEngine

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                portfolio = loop.run_until_complete(
                    EliteRolloverEngine.generate_elite_accumulator(
                        target_games=target_games,
                        num_tickets=num_tickets
                    )
                )
            finally:
                loop.close()

            # Fallback to ticket builder if elite accumulator returned empty
            if not portfolio:
                from app.api.endpoints.ticket_builder import BuildTicketRequest, build_ai_ticket
                req = BuildTicketRequest(
                    target_games=target_games,
                    target_mode="GAMES",
                    mode="ACCUMULATOR",
                    num_tickets=num_tickets,
                    overlap_mode="ZERO_OVERLAP",
                    use_live_odds=True,
                    risk_profile="BALANCED"
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(build_ai_ticket(req))
                    portfolio = res.get("portfolio_tickets") or ([res.get("ticket")] if res.get("ticket") else [])
                finally:
                    loop.close()

            dispatched = 0
            for slip in portfolio:
                slip_idx = slip.get("ticket_index", dispatched + 1)
                approved_legs = slip.get("approved_legs") or []
                if not approved_legs:
                    continue

                booking_code = slip.get("booking_code")
                share_url = slip.get("share_url")
                acc_odds = slip.get("accumulated_odds") or 1.0
                comb_prob = (slip.get("combined_probability") or 0.60) * 100.0

                title = (
                    f"⚽ StatIQ Elite {len(approved_legs)}-Match Slip — Slip #{slip_idx} of {len(portfolio)}"
                    if len(portfolio) > 1
                    else f"⚽ StatIQ Elite {len(approved_legs)}-Match Slip"
                )
                extra_note = (
                    f"Picks: {len(approved_legs)} Matches · 🔒 Zero-Overlap Guarantee (100% Unique Fixtures) · Min Odds ≥ 1.15x"
                    if len(portfolio) > 1
                    else f"Picks: {len(approved_legs)} Top Matches · Min Odds ≥ 1.15x"
                )

                self._dispatch_ticket_message(
                    chat_id=chat_id,
                    title=title,
                    booking_code=booking_code,
                    share_url=share_url,
                    total_odds=acc_odds,
                    confidence=comb_prob,
                    picks=approved_legs,
                    extra_note=extra_note
                )
                dispatched += 1

            if dispatched == 0:
                self.send_message(chat_id, "⚠️ <b>Notice:</b> No suitable elite fixtures available meeting safety & odds floor right now.")
        except Exception as e:
            logger.error(f"[TelegramBot] Games build error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error:</b> Failed to generate ticket ({_esc(str(e))}).")

    def handle_remove_command(
        self,
        chat_id: int | str,
        code: str,
        mode: str = "REMOVE",
        target_mode: str = "GAMES",
        target_val: float = 15,
        num_tickets: int = 1,
        confirmed_action: Optional[str] = None
    ):
        """
        Audits and purges an external SportyBet ticket using live odds, H2H, and match dynamics.
        Purges even-strength 50-50 traps, underdogs, and sub-1.15 legs. Preserves bettor's exact picks as-is.
        Supports interactive audit alerts with 3 user directives (SINGLE, TOPUP, OVERRIDE).
        """
        code = code.strip().upper()
        self.send_chat_action(chat_id, "typing")
        mode_desc = f"{int(target_val)} games" if target_mode == "GAMES" else f"{target_val:.1f}x odds"
        variant_desc = f"{num_tickets} separate slips (Zero Overlap)" if num_tickets > 1 else "1 core slip"

        try:
            from app.adapters.bookmaker_adapter import SportyBetAdapter
            from app.services.ticket_reeditor import re_edit_ticket

            # Step 1: Decode booking code
            adapter = SportyBetAdapter()
            decoded = adapter.fetch_booking_code_details(code, "ng")
            selections = decoded.get("selections") or []

            if not selections:
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Could not load SportyBet code <code>{code}</code>.</b>\n"
                    f"Please confirm that the code is active on SportyBet Nigeria."
                )
                return

            original_count = len(selections)
            target_games = int(target_val) if target_mode == "GAMES" else 15
            target_odds = float(target_val) if target_mode == "ODDS" else 20.0

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # ── STEP 2: AUDIT SCAN ──
                allow_override = (confirmed_action == "OVERRIDE")
                eff_num_t = 1 if confirmed_action == "SINGLE" else num_tickets

                res = loop.run_until_complete(
                    re_edit_ticket(
                        selections=selections,
                        target_odds=target_odds,
                        mode=mode,
                        target_mode=target_mode,
                        target_games=target_games,
                        num_tickets=eff_num_t,
                        allow_volatile_override=allow_override
                    )
                )

                removed_selections = res.get("removed_selections") or []
                final_selections = res.get("final_selections") or []
                all_safe_selections = res.get("all_safe_selections") or final_selections
                dropped_count = len(removed_selections)
                safe_count = len(all_safe_selections)

                portfolio_slips = res.get("portfolio_tickets") or []

                # Calculate required game count to fill the requested tickets cleanly
                if target_mode == "GAMES":
                    needed_games = target_games * num_tickets
                    is_pool_constrained = (num_tickets > 1 and safe_count < needed_games)
                else:
                    # Dynamic Capacity Check:
                    # 1. If re_edit_ticket already cleanly assembled the requested number of tickets meeting target odds
                    if len(portfolio_slips) >= num_tickets and all(s.get("new_total_odds", 0) >= (target_odds * 0.80) for s in portfolio_slips):
                        is_pool_constrained = False
                        needed_games = sum(len(s.get("final_selections", [])) for s in portfolio_slips)
                    else:
                        # 2. Calculate based on the ACTUAL average odds of the uploaded safe matches
                        avg_odds = (sum(float(s.get("odds") or 1.25) for s in all_safe_selections) / max(1, len(all_safe_selections))) if all_safe_selections else 1.25
                        effective_base = max(1.18, min(1.45, avg_odds))
                        needed_per_t = max(4, int(math.ceil(math.log(max(1.5, target_odds), effective_base))))
                        needed_games = needed_per_t * num_tickets
                        is_pool_constrained = (num_tickets > 1 and safe_count < needed_games)

                # ── STEP 3: INTERACTIVE AUDIT CONFIRMATION IF GAMES ARE DROPPED & UNCONFIRMED ──
                if confirmed_action is None and dropped_count > 0:
                    # Categorize reasons for transparent breakdown
                    youth_cnt = sum(1 for r in removed_selections if any(k in str(r.get("reason", "")).lower() for k in ["youth", "u21", "u20", "u19", "u18", "reserve"]))
                    odds_cnt = sum(1 for r in removed_selections if "below 1.15" in str(r.get("reason", "")).lower())
                    trap_cnt = sum(1 for r in removed_selections if "50-50" in str(r.get("reason", "")).lower() or "trap" in str(r.get("reason", "")).lower() or "underdog" in str(r.get("reason", "")).lower())

                    reason_bits = []
                    if youth_cnt > 0: reason_bits.append(f"{youth_cnt} U20/U21 Youth matches")
                    if odds_cnt > 0: reason_bits.append(f"{odds_cnt} Sub-1.15 Odds")
                    if trap_cnt > 0: reason_bits.append(f"{trap_cnt} Even/Underdog Traps")
                    reason_str = f"({', '.join(reason_bits)})" if reason_bits else ""

                    btn_val_str = f"{target_val:.1f}x" if target_mode == "ODDS" else f"{int(target_val)} Games"

                    if is_pool_constrained:
                        # 3-Option Streamlined Audit Menu
                        audit_text = (
                            f"🛡️ <b>StatIQ Ticket Audit: Code <code>{code}</code></b>\n\n"
                            f"📊 <b>Input Breakdown:</b>\n"
                            f"• Total Games Uploaded: <b>{original_count}</b>\n"
                            f"• ⚠️ Flagged / Risky: <b>{dropped_count} Games</b> <i>{reason_str}</i>\n"
                            f"• ✅ Verified Safe Matches: <b>{safe_count} Games</b>\n\n"
                            f"⚠️ <b>Distribution Notice:</b>\n"
                            f"You requested <b>{num_tickets} tickets targeting {mode_desc}</b> (requires {needed_games}+ games for zero overlap).\n"
                            f"<b>{safe_count} safe matches</b> cannot cleanly fill two separate {mode_desc} slips without repeating games or lowering odds.\n\n"
                            f"<b>How would you like to proceed?</b>"
                        )
                        keyboard = {
                            "inline_keyboard": [
                                [
                                    {"text": f"🎯 Generate 1 Clean {btn_val_str} Slip (Recommended)", "callback_data": f"aud:sin:{code}:{mode}:{target_mode}:{target_val}"}
                                ],
                                [
                                    {"text": f"🌐 Top-Up from Live Board ({num_tickets} Slips @ {btn_val_str})", "callback_data": f"aud:top:{code}:{mode}:{target_mode}:{target_val}:{num_tickets}"}
                                ],
                                [
                                    {"text": f"⚡ Keep All {original_count} Games (Override)", "callback_data": f"aud:ovr:{code}:{mode}:{target_mode}:{target_val}:{num_tickets}"}
                                ]
                            ]
                        }
                        self.send_message(chat_id, audit_text, reply_markup=keyboard)
                        return
                    else:
                        # 1 Ticket requested or safe matches sufficient: confirm safe vs override
                        slips_desc = f"{num_tickets} Slips ({btn_val_str} each)" if num_tickets > 1 else f"1 {btn_val_str} Slip"
                        audit_text = (
                            f"🛡️ <b>StatIQ Ticket Audit: Code <code>{code}</code></b>\n\n"
                            f"📊 <b>Input Breakdown:</b>\n"
                            f"• Total Games Uploaded: <b>{original_count}</b>\n"
                            f"• ⚠️ Flagged / Risky: <b>{dropped_count} Games</b> <i>{reason_str}</i>\n"
                            f"• ✅ Verified Safe Matches: <b>{safe_count} Games</b>\n\n"
                            f"The remaining <b>{safe_count} safe matches</b> can cleanly build your requested <b>{slips_desc}</b> with <b>Strict Zero-Overlap</b>.\n\n"
                            f"<b>Select your preference:</b>"
                        )
                        btn_action = "proc" if num_tickets > 1 else "sin"
                        keyboard = {
                            "inline_keyboard": [
                                [
                                    {"text": f"✅ Proceed with {slips_desc}", "callback_data": f"aud:{btn_action}:{code}:{mode}:{target_mode}:{target_val}:{num_tickets}"}
                                ],
                                [
                                    {"text": f"⚡ Keep All {original_count} Games (Override)", "callback_data": f"aud:ovr:{code}:{mode}:{target_mode}:{target_val}:{num_tickets}"}
                                ]
                            ]
                        }
                        self.send_message(chat_id, audit_text, reply_markup=keyboard)
                        return

                # ── STEP 4: TOP-UP IMPLEMENTATION IF USER SELECTED TOPUP ──
                if confirmed_action == "TOPUP":
                    from app.services.elite_rollover_engine import EliteRolloverEngine
                    live_events = loop.run_until_complete(EliteRolloverEngine.fetch_sportybet_today_events(max_pages=10))
                    live_cands = EliteRolloverEngine.evaluate_elite_rollover_candidates(live_events, max_leg_odds=1.45)
                    existing_eids = {str(s.get("event_id")).lower() for s in final_selections}

                    needed_extra = max(0, needed_games - len(final_selections))
                    added_bankers = []
                    for c in live_cands:
                        eid = str(c.get("event_id")).lower()
                        if eid not in existing_eids and eid not in {x["event_id"].lower() for x in added_bankers}:
                            added_bankers.append({
                                "event_id": c["event_id"],
                                "fixture_id": c["event_id"],
                                "game_id": c["event_id"],
                                "provider_event_id": c["event_id"],
                                "home_team": c["home_team"],
                                "away_team": c["away_team"],
                                "competition": c["competition"],
                                "market_name": c["market_desc"],
                                "selection_name": c["selection_desc"],
                                "odds": c["odds"],
                                "estimated_odds": c["odds"],
                                "estimated_prob": c["model_probability"],
                                "provider_market_id": str(c["market_id"]),
                                "provider_outcome_id": str(c["outcome_id"]),
                                "provider_specifier": c.get("specifier") or "",
                                "status": "UPCOMING"
                            })
                            if len(added_bankers) >= needed_extra:
                                break

                    topped_up_pool = final_selections + added_bankers
                    res = loop.run_until_complete(
                        re_edit_ticket(
                            selections=topped_up_pool,
                            target_odds=target_odds,
                            mode=mode,
                            target_mode=target_mode,
                            target_games=target_games,
                            num_tickets=num_tickets,
                            allow_volatile_override=False
                        )
                    )

                portfolio = res.get("portfolio_tickets") or []
                if not portfolio and res.get("final_selections"):
                    portfolio = [{
                        "ticket_index": 1,
                        "final_selections": res.get("final_selections"),
                        "new_total_odds": res.get("new_total_odds"),
                        "avg_win_prob": res.get("avg_win_prob")
                    }]

                if not portfolio:
                    self.send_message(chat_id, "⚠️ <b>Audit Result:</b> None of the matches in this ticket met the safety cushion threshold.")
                    return

                # Book each slip on SportyBet and dispatch
                for slip in portfolio:
                    slip_idx = slip.get("ticket_index", 1)
                    final_picks = slip.get("final_selections") or []
                    if not final_picks:
                        continue

                    # Generate live booking code
                    book_res = adapter.generate_booking_code(final_picks, "ng")
                    booked_code = book_res.get("booking_code")
                    booked_url = book_res.get("load_url") or (f"https://www.sportybet.com/ng/?shareCode={booked_code}" if booked_code else None)
                    booked_picks = book_res.get("booked_selections") or final_picks

                    acc_odd = 1.0
                    for p in booked_picks:
                        acc_odd *= float(p.get("odds") or 1.20)

                    if confirmed_action == "SINGLE":
                        slip_title = f"🎯 Purged Core Slip ({len(booked_picks)} Matches)"
                        overlap_tag = f"Target: {mode_desc} · Safe Matches Only · Min Odds ≥ 1.15x"
                    elif confirmed_action == "TOPUP":
                        slip_title = f"🌐 Purged & Topped-Up Variant #{slip_idx} ({len(booked_picks)} Matches)"
                        overlap_tag = "🔒 <b>Zero-Overlap Partition:</b> 100% Unique Fixtures (Safe Code Matches + Live Bankers)"
                    elif confirmed_action == "OVERRIDE":
                        slip_title = f"⚡ Bettor Override Variant #{slip_idx} ({len(booked_picks)} Matches)"
                        overlap_tag = "⚠️ <b>User Override:</b> Original Picks Preserved (Includes Youth Matches)"
                    else:
                        slip_title = (
                            f"🛡️ Purged Variant #{slip_idx} ({len(booked_picks)} Matches)"
                            if eff_num_t > 1
                            else f"🛡️ Purged Core Slip ({len(booked_picks)} of {original_count} Matches)"
                        )
                        overlap_tag = (
                            "🔒 <b>Zero-Overlap Partition:</b> 100% Unique Fixtures"
                            if eff_num_t > 1
                            else "Even-Strength & Underdog Traps Purged (Original Picks Preserved)"
                        )

                    self._dispatch_ticket_message(
                        chat_id=chat_id,
                        title=slip_title,
                        booking_code=booked_code,
                        share_url=booked_url,
                        total_odds=round(acc_odd, 2),
                        confidence=round((slip.get("avg_win_prob") or 0.82) * 100.0, 1),
                        picks=booked_picks,
                        extra_note=f"{overlap_tag} · Min Odds ≥ 1.15x Strictly Enforced"
                    )

            finally:
                loop.close()

        except Exception as e:
            logger.error(f"[TelegramBot] Remove error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error processing ticket:</b> {_esc(str(e))}")

    def handle_edit_command(
        self,
        chat_id: int | str,
        code: str,
        mode: str = "EDIT",
        target_mode: str = "GAMES",
        target_val: float = 15,
        num_tickets: int = 1,
        confirmed_action: Optional[str] = None
    ):
        """
        Upgrades risky fixtures in an external SportyBet ticket to verified live SportyBet safety markets
        (Double Chance, Over 1.5, Team Goals). Ensures every upgraded option is active on SportyBet.
        Supports interactive audit alerts with 3 user directives (SINGLE, TOPUP, OVERRIDE).
        """
        code = code.strip().upper()
        self.send_chat_action(chat_id, "typing")
        mode_desc = f"{int(target_val)} games" if target_mode == "GAMES" else f"{target_val:.1f}x odds"

        try:
            from app.adapters.bookmaker_adapter import SportyBetAdapter
            from app.services.ticket_reeditor import re_edit_ticket

            adapter = SportyBetAdapter()
            decoded = adapter.fetch_booking_code_details(code, "ng")
            selections = decoded.get("selections") or []

            if not selections:
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Could not load SportyBet code <code>{code}</code>.</b>\n"
                    f"Please confirm that the code is active on SportyBet Nigeria."
                )
                return

            original_count = len(selections)
            target_games = int(target_val) if target_mode == "GAMES" else 15
            target_odds = float(target_val) if target_mode == "ODDS" else 20.0

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                allow_override = (confirmed_action == "OVERRIDE")
                eff_num_t = 1 if confirmed_action == "SINGLE" else num_tickets

                res = loop.run_until_complete(
                    re_edit_ticket(
                        selections=selections,
                        target_odds=target_odds,
                        mode="EDIT",
                        target_mode=target_mode,
                        target_games=target_games,
                        num_tickets=eff_num_t,
                        allow_volatile_override=allow_override
                    )
                )

                removed_selections = res.get("removed_selections") or []
                final_selections = res.get("final_selections") or []
                all_safe_selections = res.get("all_safe_selections") or final_selections
                dropped_count = len(removed_selections)
                safe_count = len(all_safe_selections)

                portfolio_slips = res.get("portfolio_tickets") or []

                if target_mode == "GAMES":
                    needed_games = target_games * num_tickets
                    is_pool_constrained = (num_tickets > 1 and safe_count < needed_games)
                else:
                    if len(portfolio_slips) >= num_tickets and all(s.get("new_total_odds", 0) >= (target_odds * 0.80) for s in portfolio_slips):
                        is_pool_constrained = False
                        needed_games = sum(len(s.get("final_selections", [])) for s in portfolio_slips)
                    else:
                        avg_odds = (sum(float(s.get("odds") or 1.25) for s in all_safe_selections) / max(1, len(all_safe_selections))) if all_safe_selections else 1.25
                        effective_base = max(1.18, min(1.45, avg_odds))
                        needed_per_t = max(4, int(math.ceil(math.log(max(1.5, target_odds), effective_base))))
                        needed_games = needed_per_t * num_tickets
                        is_pool_constrained = (num_tickets > 1 and safe_count < needed_games)

                if confirmed_action is None and dropped_count > 0:
                    youth_cnt = sum(1 for r in removed_selections if any(k in str(r.get("reason", "")).lower() for k in ["youth", "u21", "u20", "u19", "u18", "reserve"]))
                    odds_cnt = sum(1 for r in removed_selections if "below 1.15" in str(r.get("reason", "")).lower())
                    trap_cnt = sum(1 for r in removed_selections if "50-50" in str(r.get("reason", "")).lower() or "trap" in str(r.get("reason", "")).lower() or "underdog" in str(r.get("reason", "")).lower())

                    reason_bits = []
                    if youth_cnt > 0: reason_bits.append(f"{youth_cnt} U20/U21 Youth matches")
                    if odds_cnt > 0: reason_bits.append(f"{odds_cnt} Sub-1.15 Odds")
                    if trap_cnt > 0: reason_bits.append(f"{trap_cnt} Even/Underdog Traps")
                    reason_str = f"({', '.join(reason_bits)})" if reason_bits else ""

                    btn_val_str = f"{target_val:.1f}x" if target_mode == "ODDS" else f"{int(target_val)} Games"

                    if is_pool_constrained:
                        audit_text = (
                            f"⚡ <b>StatIQ Upgrade Audit: Code <code>{code}</code></b>\n\n"
                            f"📊 <b>Input Breakdown:</b>\n"
                            f"• Total Games Uploaded: <b>{original_count}</b>\n"
                            f"• ⚠️ Flagged / Risky: <b>{dropped_count} Games</b> <i>{reason_str}</i>\n"
                            f"• ✅ Verified Upgradable Matches: <b>{safe_count} Games</b>\n\n"
                            f"⚠️ <b>Distribution Notice:</b>\n"
                            f"You requested <b>{num_tickets} tickets targeting {mode_desc}</b> (requires {needed_games}+ games for zero overlap).\n"
                            f"<b>{safe_count} matches</b> cannot cleanly fill two separate {mode_desc} slips without repeating games or lowering odds.\n\n"
                            f"<b>How would you like to proceed?</b>"
                        )
                        keyboard = {
                            "inline_keyboard": [
                                [
                                    {"text": f"🎯 Generate 1 Clean {btn_val_str} Slip (Recommended)", "callback_data": f"aud:sin:{code}:EDIT:{target_mode}:{target_val}"}
                                ],
                                [
                                    {"text": f"🌐 Top-Up from Live Board ({num_tickets} Slips @ {btn_val_str})", "callback_data": f"aud:top:{code}:EDIT:{target_mode}:{target_val}:{num_tickets}"}
                                ],
                                [
                                    {"text": f"⚡ Keep All {original_count} Games (Override)", "callback_data": f"aud:ovr:{code}:EDIT:{target_mode}:{target_val}:{num_tickets}"}
                                ]
                            ]
                        }
                        self.send_message(chat_id, audit_text, reply_markup=keyboard)
                        return
                    else:
                        slips_desc = f"{num_tickets} Slips ({btn_val_str} each)" if num_tickets > 1 else f"1 {btn_val_str} Slip"
                        audit_text = (
                            f"⚡ <b>StatIQ Upgrade Audit: Code <code>{code}</code></b>\n\n"
                            f"📊 <b>Input Breakdown:</b>\n"
                            f"• Total Games Uploaded: <b>{original_count}</b>\n"
                            f"• ⚠️ Flagged / Risky: <b>{dropped_count} Games</b> <i>{reason_str}</i>\n"
                            f"• ✅ Verified Upgradable Matches: <b>{safe_count} Games</b>\n\n"
                            f"The remaining <b>{safe_count} matches</b> can cleanly build your upgraded <b>{slips_desc}</b> with <b>Strict Zero-Overlap</b>.\n\n"
                            f"<b>Select your preference:</b>"
                        )
                        btn_action = "proc" if num_tickets > 1 else "sin"
                        keyboard = {
                            "inline_keyboard": [
                                [
                                    {"text": f"✅ Proceed with {slips_desc}", "callback_data": f"aud:{btn_action}:{code}:EDIT:{target_mode}:{target_val}:{num_tickets}"}
                                ],
                                [
                                    {"text": f"⚡ Keep All {original_count} Games (Override)", "callback_data": f"aud:ovr:{code}:EDIT:{target_mode}:{target_val}:{num_tickets}"}
                                ]
                            ]
                        }
                        self.send_message(chat_id, audit_text, reply_markup=keyboard)
                        return

                if confirmed_action == "TOPUP":
                    from app.services.elite_rollover_engine import EliteRolloverEngine
                    live_events = loop.run_until_complete(EliteRolloverEngine.fetch_sportybet_today_events(max_pages=10))
                    live_cands = EliteRolloverEngine.evaluate_elite_rollover_candidates(live_events, max_leg_odds=1.45)
                    existing_eids = {str(s.get("event_id")).lower() for s in final_selections}

                    needed_extra = max(0, needed_games - len(final_selections))
                    added_bankers = []
                    for c in live_cands:
                        eid = str(c.get("event_id")).lower()
                        if eid not in existing_eids and eid not in {x["event_id"].lower() for x in added_bankers}:
                            added_bankers.append({
                                "event_id": c["event_id"],
                                "fixture_id": c["event_id"],
                                "game_id": c["event_id"],
                                "provider_event_id": c["event_id"],
                                "home_team": c["home_team"],
                                "away_team": c["away_team"],
                                "competition": c["competition"],
                                "market_name": c["market_desc"],
                                "selection_name": c["selection_desc"],
                                "odds": c["odds"],
                                "estimated_odds": c["odds"],
                                "estimated_prob": c["model_probability"],
                                "provider_market_id": str(c["market_id"]),
                                "provider_outcome_id": str(c["outcome_id"]),
                                "provider_specifier": c.get("specifier") or "",
                                "status": "UPCOMING"
                            })
                            if len(added_bankers) >= needed_extra:
                                break

                    topped_up_pool = final_selections + added_bankers
                    res = loop.run_until_complete(
                        re_edit_ticket(
                            selections=topped_up_pool,
                            target_odds=target_odds,
                            mode="EDIT",
                            target_mode=target_mode,
                            target_games=target_games,
                            num_tickets=num_tickets,
                            allow_volatile_override=False
                        )
                    )

                portfolio = res.get("portfolio_tickets") or []
                if not portfolio and res.get("final_selections"):
                    portfolio = [{
                        "ticket_index": 1,
                        "final_selections": res.get("final_selections"),
                        "new_total_odds": res.get("new_total_odds"),
                        "avg_win_prob": res.get("avg_win_prob")
                    }]

                if not portfolio:
                    self.send_message(chat_id, "⚠️ <b>Audit Result:</b> None of the matches in this ticket met the safety cushion threshold.")
                    return

                for slip in portfolio:
                    slip_idx = slip.get("ticket_index", 1)
                    final_picks = slip.get("final_selections") or []
                    if not final_picks:
                        continue

                    book_res = adapter.generate_booking_code(final_picks, "ng")
                    booked_code = book_res.get("booking_code")
                    booked_url = book_res.get("load_url") or (f"https://www.sportybet.com/ng/?shareCode={booked_code}" if booked_code else None)
                    booked_picks = book_res.get("booked_selections") or final_picks

                    acc_odd = 1.0
                    for p in booked_picks:
                        acc_odd *= float(p.get("odds") or 1.20)

                    if confirmed_action == "SINGLE":
                        slip_title = f"⚡ Upgraded Core Slip ({len(booked_picks)} Matches)"
                        overlap_tag = f"Target: {mode_desc} · Verified Safe Upgrades · Min Odds ≥ 1.15x"
                    elif confirmed_action == "TOPUP":
                        slip_title = f"🌐 Upgraded & Topped-Up Variant #{slip_idx} ({len(booked_picks)} Matches)"
                        overlap_tag = "🔒 <b>Zero-Overlap Partition:</b> 100% Unique Fixtures (Upgraded Matches + Live Bankers)"
                    elif confirmed_action == "OVERRIDE":
                        slip_title = f"⚡ Bettor Override Variant #{slip_idx} ({len(booked_picks)} Matches)"
                        overlap_tag = "⚠️ <b>User Override:</b> Original Picks Preserved (Includes Youth Matches)"
                    else:
                        slip_title = (
                            f"⚡ Upgraded Variant #{slip_idx} ({len(booked_picks)} Matches)"
                            if eff_num_t > 1
                            else f"⚡ Upgraded Core Slip ({len(booked_picks)} of {original_count} Matches)"
                        )
                        overlap_tag = (
                            "🔒 <b>Zero-Overlap Partition:</b> 100% Unique Fixtures"
                            if eff_num_t > 1
                            else "Risky Markets Upgraded to Verified SportyBet Safety Lines"
                        )

                    self._dispatch_ticket_message(
                        chat_id=chat_id,
                        title=slip_title,
                        booking_code=booked_code,
                        share_url=booked_url,
                        total_odds=round(acc_odd, 2),
                        confidence=round((slip.get("avg_win_prob") or 0.82) * 100.0, 1),
                        picks=booked_picks,
                        extra_note=f"{overlap_tag} · Min Odds ≥ 1.15x Strictly Enforced"
                    )

            finally:
                loop.close()

        except Exception as e:
            logger.error(f"[TelegramBot] Edit error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error upgrading ticket:</b> {_esc(str(e))}")

            # Step 1: Decode booking code
            adapter = SportyBetAdapter()
            decoded = adapter.fetch_booking_code_details(code, "ng")
            selections = decoded.get("selections") or []

            if not selections:
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Could not load SportyBet code <code>{code}</code>.</b>\n"
                    f"Please confirm that the code is active on SportyBet Nigeria."
                )
                return

            original_count = len(selections)

            # Step 2: Run Re-Editor in EDIT mode
            target_games = int(target_val) if target_mode == "GAMES" else 15
            target_odds = float(target_val) if target_mode == "ODDS" else 20.0

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    re_edit_ticket(
                        selections=selections,
                        target_odds=target_odds,
                        mode="EDIT",
                        target_mode=target_mode,
                        target_games=target_games,
                        num_tickets=num_tickets
                    )
                )
            finally:
                loop.close()

            portfolio = res.get("portfolio_tickets") or []
            if not portfolio and res.get("final_selections"):
                portfolio = [{
                    "ticket_index": 1,
                    "final_selections": res.get("final_selections"),
                    "new_total_odds": res.get("new_total_odds"),
                    "avg_win_prob": res.get("avg_win_prob")
                }]

            if not portfolio:
                self.send_message(chat_id, "⚠️ <b>Audit Result:</b> None of the matches in this ticket met the safety cushion threshold.")
                return

            # Book each slip on SportyBet and dispatch
            for slip in portfolio:
                slip_idx = slip.get("ticket_index", 1)
                final_picks = slip.get("final_selections") or []
                if not final_picks:
                    continue

                # Generate live booking code
                book_res = adapter.generate_booking_code(final_picks, "ng")
                booked_code = book_res.get("booking_code")
                booked_url = book_res.get("load_url") or (f"https://www.sportybet.com/ng/?shareCode={booked_code}" if booked_code else None)
                booked_picks = book_res.get("booked_selections") or final_picks

                # Compute odds
                acc_odd = 1.0
                for p in booked_picks:
                    acc_odd *= float(p.get("odds") or 1.20)

                slip_title = (
                    f"⚡ Upgraded Variant #{slip_idx} ({len(booked_picks)} Matches)"
                    if num_tickets > 1
                    else f"⚡ Upgraded Core Slip ({len(booked_picks)} of {original_count} Matches)"
                )
                overlap_tag = (
                    "🔒 <b>Zero-Overlap Partition:</b> 100% Unique Fixtures"
                    if num_tickets > 1
                    else "Risky Markets Upgraded to Verified SportyBet Safety Lines"
                )

                self._dispatch_ticket_message(
                    chat_id=chat_id,
                    title=slip_title,
                    booking_code=booked_code,
                    share_url=booked_url,
                    total_odds=round(acc_odd, 2),
                    confidence=round((slip.get("avg_win_prob") or 0.82) * 100.0, 1),
                    picks=booked_picks,
                    extra_note=f"{overlap_tag} · Min Odds ≥ 1.15x Strictly Enforced"
                )

        except Exception as e:
            logger.error(f"[TelegramBot] Edit error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error upgrading ticket:</b> {_esc(str(e))}")

    # Aliases for backwards compatibility
    handle_trim_command = handle_remove_command
    handle_reedit_command = handle_edit_command

    def handle_portfolio_command(
        self,
        chat_id: int | str,
        code: str,
        target_portfolio: str = "4_SLIPS",
        filter_risky: bool = False
    ):
        """
        Splits a bettor's mega slip into a diversified 4-slip or 2-slip investment portfolio.
        Can run unfiltered (using 100% of bettor's original picks) or filtered (purging risky legs first).
        """
        code = code.strip().upper()
        self.send_chat_action(chat_id, "typing")
        is_4_slips = str(target_portfolio).upper() in ("4", "4_SLIPS", "FOUR")
        mode_desc = "4 Diversified Slips (2x 5.0x + 2x 10.0x)" if is_4_slips else "2 Slips (1x 5.0x + 1x 10.0x)"
        filter_desc = "🛡️ Filtered: Risky picks purged" if filter_risky else "⚡ Unfiltered: 100% Original picks permuted"

        self.send_message(
            chat_id,
            f"⏳ <b>StatIQ Portfolio Splitter:</b> Decoding code <code>{code}</code> and generating {mode_desc} ({filter_desc})..."
        )

        try:
            from app.adapters.bookmaker_adapter import SportyBetAdapter
            from app.services.ticket_reeditor import split_ticket_into_portfolio

            adapter = SportyBetAdapter()
            decoded = adapter.fetch_booking_code_details(code, "ng")
            selections = decoded.get("selections") or []

            if not selections:
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Could not load SportyBet code <code>{code}</code>.</b> Please verify that the code is active on SportyBet Nigeria."
                )
                return

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    split_ticket_into_portfolio(
                        selections=selections,
                        target_portfolio="4_SLIPS" if is_4_slips else "2_SLIPS",
                        filter_risky=filter_risky
                    )
                )
            finally:
                loop.close()

            status = res.get("status")
            if status != "SUCCESS":
                self.send_message(chat_id, f"⚠️ <b>Notice:</b> {res.get('message', 'Could not assemble portfolio slips.')}")
                return

            slips = res.get("portfolio_tickets") or []
            if not slips:
                self.send_message(chat_id, "⚠️ <b>Notice:</b> Not enough unstarted matches in this ticket to construct portfolio.")
                return

            orig_cnt = res.get("original_count", len(selections))
            pool_cnt = res.get("working_pool_count", len(selections))

            header_msg = (
                f"🚀 <b>StatIQ Portfolio Permutation Complete!</b>\n"
                f"📊 <b>Source:</b> <code>{code}</code> ({orig_cnt} Matches ➔ {pool_cnt} Used)\n"
                f"🛡️ <b>Mode:</b> {filter_desc}\n"
                f"🔒 <b>Structure:</b> {mode_desc} with Strategic Leg Distribution"
            )
            self.send_message(chat_id, header_msg)

            for s in slips:
                idx = s.get("ticket_index", 1)
                title = s.get("title", f"Portfolio Slip #{idx}")
                b_code = s.get("booking_code")
                s_url = s.get("share_url")
                odds = s.get("actual_odds", 5.0)
                conf = s.get("confidence_score", 75.0)
                picks = s.get("picks", [])

                self._dispatch_ticket_message(
                    chat_id=chat_id,
                    title=f"🎟️ {title}",
                    booking_code=b_code,
                    share_url=s_url,
                    total_odds=odds,
                    confidence=conf,
                    picks=picks,
                    extra_note=f"Portfolio Slip {idx} of {len(slips)} · Shuffled Permutation Matrix · Min Odds ≥ 1.05x"
                )

        except Exception as e:
            logger.error(f"[TelegramBot] Portfolio split error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error generating portfolio:</b> {_esc(str(e))}")

    def handle_raw_code_detected(self, chat_id: int | str, code: str):
        """When user pastes a booking code, inspect it and offer 1-tap action buttons for /remove, /edit, and /portfolio."""
        code = code.strip().upper()
        self.send_chat_action(chat_id, "typing")

        try:
            from app.adapters.bookmaker_adapter import SportyBetAdapter
            adapter = SportyBetAdapter()
            decoded = adapter.fetch_booking_code_details(code, "ng")
            selections = decoded.get("selections") or []

            if not selections:
                self.send_message(
                    chat_id,
                    f"🎟️ Found code <code>{code}</code>, but could not load it from SportyBet Nigeria. "
                    f"Please verify the code is valid."
                )
                return

            n_matches = len(selections)
            total_odds = decoded.get("total_odds") or 1.0

            msg = (
                f"🎟️ <b>SportyBet Slip Detected: <code>{code}</code></b>\n\n"
                f"📊 <b>Total Matches:</b> {n_matches} Matches\n"
                f"⚡ <b>Original Multiplier:</b> {total_odds:.2f}x\n\n"
                f"Select an optimization mode below:\n"
                f"• <b>PORTFOLIO SPLIT:</b> Permutes games into 2x 5x + 2x 10x or 1x 5x + 1x 10x\n"
                f"• <b>REMOVE:</b> Purges risky legs, keeping bettor's picks as-is\n"
                f"• <b>EDIT:</b> Upgrades risky lines to verified SportyBet safety markets"
            )

            keyboard_rows = [
                [
                    {"text": "🚀 Split 4 Slips (2x 5x + 2x 10x)", "callback_data": f"port:{code}:4:unfiltered"},
                    {"text": "⚡ Split 2 Slips (1x 5x + 1x 10x)", "callback_data": f"port:{code}:2:unfiltered"}
                ],
                [
                    {"text": "🛡️ Split 4 Slips (Risk Filtered)", "callback_data": f"port:{code}:4:filtered"},
                ],
                [
                    {"text": "🗑️ /remove (15 Games)", "callback_data": f"rem:{code}:15:games:1"},
                    {"text": "🗑️ /remove (2 Variants)", "callback_data": f"rem:{code}:15:games:2"}
                ],
                [
                    {"text": "⚡ /edit (15 Games)", "callback_data": f"edt:{code}:15:games:1"},
                    {"text": "⚡ /edit (2 Variants)", "callback_data": f"edt:{code}:15:games:2"}
                ]
            ]

            keyboard = {"inline_keyboard": keyboard_rows}
            self.send_message(chat_id, msg, reply_markup=keyboard)

        except Exception as e:
            logger.warning(f"[TelegramBot] Code inspection error: {e}")
            self.send_message(chat_id, f"⚠️ Error inspecting booking code: {_esc(str(e))}")

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: Ticket Formatter & Message Dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    def _dispatch_ticket_message(
        self,
        chat_id: int | str,
        title: str,
        booking_code: Optional[str],
        share_url: Optional[str],
        total_odds: float,
        confidence: float,
        picks: List[Dict[str, Any]],
        extra_note: Optional[str] = None
    ):
        """Formats and sends a beautiful, structured StatIQ ticket to Telegram."""
        code_str = booking_code or "N/A"
        url_str = share_url or (f"https://www.sportybet.com/ng/?shareCode={code_str}" if booking_code else "https://www.sportybet.com/ng/")

        # Automatically lock into background live tracking system for auto-settlement
        if booking_code and picks:
            try:
                from app.services.ticket_tracker import lock_ticket
                lock_ticket({
                    "code": booking_code,
                    "mode": "TELEGRAM",
                    "target_odds": total_odds,
                    "total_odds": total_odds,
                    "stake": 1000.0,
                    "selections": picks,
                    "profile_id": str(chat_id),
                    "user_id": str(chat_id),
                    "flex_cut": "OFF",
                })
            except Exception as le:
                logger.debug(f"[TelegramBot] Auto-lock ticket tracking note: {le}")

        lines = [
            f"<b>{_esc(title)}</b>",
            f"⚡ <b>Total Multiplier:</b> <b>{total_odds:.2f}x</b> | <b>Confidence:</b> <b>{confidence:.1f}%</b>",
            f"🎟️ <b>SportyBet Code:</b> <code>{code_str}</code> (Tap to Copy)",
            f"🔗 <a href=\"{url_str}\"><b>Click to Pre-Load on SportyBet</b></a>",
            ""
        ]

        if extra_note:
            lines.insert(2, f"🛡️ <i>{_esc(extra_note)}</i>")

        for i, p in enumerate(picks, 1):
            h = _esc(p.get("home_team") or "Home")
            a = _esc(p.get("away_team") or "Away")
            comp = _esc(p.get("competition") or "Football")
            mkt = _esc(p.get("market_desc") or p.get("market_name") or "Pick")
            sel = _esc(p.get("selection_desc") or p.get("selection_name") or "Selection")
            odd = float(p.get("odds") or p.get("estimated_odds") or 1.25)
            prob = float(p.get("model_probability") or 0.80) * 100.0

            lines.append(f"<b>{i}. {h} vs {a}</b>")
            lines.append(f"   ➔ <b>Pick:</b> {sel} [{mkt}] @ <b>{odd:.2f}</b> (Win: {prob:.0f}%)")

        lines.append("")
        lines.append(f"🎟️ <b>Load Code:</b> <code>{code_str}</code>")
        lines.append(f"🔗 <a href=\"{url_str}\"><b>Open Directly in SportyBet Mobile / Web</b></a>")

        full_text = "\n".join(lines)

        # Telegram 4096 character limit safety splitting if ticket is massive
        if len(full_text) <= 4000:
            self.send_message(chat_id, full_text)
        else:
            chunks = []
            curr = []
            curr_len = 0
            for line in lines:
                if curr_len + len(line) + 2 > 3800:
                    chunks.append("\n".join(curr))
                    curr = [line]
                    curr_len = len(line)
                else:
                    curr.append(line)
                    curr_len += len(line) + 1
            if curr:
                chunks.append("\n".join(curr))

            for chunk in chunks:
                self.send_message(chat_id, chunk)

    # ─────────────────────────────────────────────────────────────────────────
    # Callback Query Dispatcher (Button Clicks)
    # ─────────────────────────────────────────────────────────────────────────

    def handle_callback_query(self, query: Dict[str, Any]):
        """Processes inline button clicks."""
        cq_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        chat_id = message.get("chat", {}).get("id") or query.get("from", {}).get("id")

        if not chat_id:
            return

        # Deduplicate callback queries (button clicks)
        if cq_id:
            if cq_id in self._processed_cq_ids_set:
                logger.info(f"[TelegramBot] Duplicate callback query ignored: {cq_id}")
                return
            self._processed_cq_ids.append(cq_id)
            self._processed_cq_ids_set.add(cq_id)
            if len(self._processed_cq_ids) >= 1800:
                self._processed_cq_ids_set = set(self._processed_cq_ids)

        self.answer_callback_query(cq_id, "Processing your request...")

        # Case 0: Automation button (auto:menu, auto:toggle:ro, auto:toggle:5x, auto:toggle:10x, auto:toggle:master, auto:dispatch)
        if data.startswith("auto:"):
            parts = data.split(":")
            subaction = parts[1]
            if subaction == "menu":
                self.handle_auto_command(chat_id)
            elif subaction == "dispatch":
                self.handle_dispatch_command(chat_id)
            elif subaction == "toggle":
                target = parts[2]
                from app.services.rollover_cron_scheduler import rollover_scheduler
                cfg = rollover_scheduler.get_config()
                if target == "ro":
                    curr = cfg.get("enable_rollover_2x", True)
                    rollover_scheduler.save_config({"enable_rollover_2x": not curr})
                elif target == "5x":
                    curr = cfg.get("enable_acca_5x", True)
                    rollover_scheduler.save_config({"enable_acca_5x": not curr})
                elif target == "10x":
                    curr = cfg.get("enable_acca_10x", True)
                    rollover_scheduler.save_config({"enable_acca_10x": not curr})
                elif target == "20x":
                    curr = cfg.get("enable_acca_20x", True)
                    rollover_scheduler.save_config({"enable_acca_20x": not curr})
                elif target == "master":
                    curr = cfg.get("is_enabled", True)
                    rollover_scheduler.save_config({"is_enabled": not curr})
                self.handle_auto_command(chat_id)
            elif subaction == "cycle":
                target = parts[2]
                if target == "days":
                    from app.services.rollover_cron_scheduler import rollover_scheduler
                    cfg = rollover_scheduler.get_config()
                    current_days = set(d.upper() for d in cfg.get("active_days", []))
                    if current_days >= {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}:
                        next_days = ["MON", "TUE", "WED", "THU", "FRI"]
                    elif current_days == {"MON", "TUE", "WED", "THU", "FRI"}:
                        next_days = ["SAT", "SUN"]
                    else:
                        next_days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
                    rollover_scheduler.save_config({"active_days": next_days})
                    self.handle_auto_command(chat_id)
            return

        if data == "auto:dispatch":
            self.handle_dispatch_command(chat_id)
            return

        if data == "auto:menu":
            self.handle_auto_command(chat_id)
            return

        if data.startswith("camp:won:"):
            day_num = int(data.split(":")[2])
            from app.services.rollover_cron_scheduler import rollover_scheduler
            rollover_scheduler.update_challenge_day(day_num, "WON")
            self.send_message(chat_id, f"✅ <b>Marked Day {day_num} as WON!</b> Compounding ladder advanced.")
            self.handle_challenge_command(chat_id)
            return

        if data.startswith("camp:dismiss"):
            from app.services.rollover_cron_scheduler import rollover_scheduler
            rollover_scheduler.dismiss_campaign()
            self.send_message(chat_id, "🗑️ <b>Compounding Challenge Removed.</b> You can start a fresh challenge anytime with <code>/challenge</code>.")
            return

        if data.startswith("camp:start:"):
            days = int(data.split(":")[2])
            from app.services.rollover_cron_scheduler import rollover_scheduler
            rollover_scheduler.start_challenge(days=days, starting_stake=5000, target_odds=2.0)
            self.send_message(chat_id, f"🚀 <b>Started Fresh {days}-Day Compounding Challenge!</b>")
            self.handle_challenge_command(chat_id)
            return

        # Case 1: Generator button (e.g. gen:odds:2.0:1 or gen:odds:2.0:2, gen:games:10:2, gen:rollover)
        if data.startswith("gen:"):
            parts = data.split(":")
            action = parts[1]
            if action == "rollover":
                self.handle_rollover_command(chat_id)
            elif action == "odds":
                val = float(parts[2]) if len(parts) > 2 else 2.0
                num_t = int(parts[3]) if len(parts) > 3 else 1
                self.handle_odds_command(chat_id, val, num_tickets=num_t)
            elif action == "games":
                val = int(parts[2]) if len(parts) > 2 else 10
                num_t = int(parts[3]) if len(parts) > 3 else 1
                self.handle_games_command(chat_id, val, num_tickets=num_t)

        # Case 2: Code Optimizer (/remove and /edit)
        elif data.startswith("trim:") or data.startswith("edit:") or data.startswith("rem:") or data.startswith("edt:"):
            parts = data.split(":")
            if len(parts) >= 5:
                code = parts[1]
                val = float(parts[2])
                target_mode = parts[3].upper()  # GAMES or ODDS
                num_tickets = int(parts[4])
                is_edit = data.startswith("edit:") or data.startswith("edt:")
                if is_edit:
                    self.handle_edit_command(
                        chat_id=chat_id,
                        code=code,
                        mode="EDIT",
                        target_mode=target_mode,
                        target_val=val,
                        num_tickets=num_tickets
                    )
                else:
                    self.handle_remove_command(
                        chat_id=chat_id,
                        code=code,
                        mode="REMOVE",
                        target_mode=target_mode,
                        target_val=val,
                        num_tickets=num_tickets
                    )

        # Case 2b: Portfolio Splitter
        elif data.startswith("port:"):
            parts = data.split(":")
            if len(parts) >= 4:
                code = parts[1]
                num_slips = parts[2]
                filt_mode = parts[3]
                self.handle_portfolio_command(
                    chat_id=chat_id,
                    code=code,
                    target_portfolio="4_SLIPS" if num_slips == "4" else "2_SLIPS",
                    filter_risky=(filt_mode == "filtered")
                )

        # Case 3: Interactive Audit Actions (aud:sin, aud:top, aud:ovr)
        elif data.startswith("aud:"):
            parts = data.split(":")
            # format: aud:action:code:mode:target_mode:target_val[:num_tickets]
            if len(parts) >= 6:
                subaction = parts[1]
                code = parts[2]
                mode = parts[3]
                target_mode = parts[4]
                target_val = float(parts[5])
                num_t = int(parts[6]) if len(parts) > 6 else 1

                is_edit = (mode == "EDIT")
                handler = self.handle_edit_command if is_edit else self.handle_remove_command

                if subaction == "sin":
                    handler(
                        chat_id=chat_id, code=code, mode=mode,
                        target_mode=target_mode, target_val=target_val,
                        num_tickets=1, confirmed_action="SINGLE"
                    )
                elif subaction == "proc":
                    handler(
                        chat_id=chat_id, code=code, mode=mode,
                        target_mode=target_mode, target_val=target_val,
                        num_tickets=num_t, confirmed_action="PROCEED"
                    )
                elif subaction == "top":
                    handler(
                        chat_id=chat_id, code=code, mode=mode,
                        target_mode=target_mode, target_val=target_val,
                        num_tickets=num_t, confirmed_action="TOPUP"
                    )
                elif subaction == "ovr":
                    handler(
                        chat_id=chat_id, code=code, mode=mode,
                        target_mode=target_mode, target_val=target_val,
                        num_tickets=num_t, confirmed_action="OVERRIDE"
                    )

    # ─────────────────────────────────────────────────────────────────────────
    # Text Message Parser
    # ─────────────────────────────────────────────────────────────────────────

    def process_message(self, message: Dict[str, Any]):
        """Parses incoming text messages and routes to the correct handler."""
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")
        text = (message.get("text") or "").strip()

        if not chat_id or not text:
            return

        # Deduplication check: strictly prevent processing any message twice
        if msg_id:
            msg_key = f"{chat_id}:{msg_id}"
            if msg_key in self._processed_msg_keys_set:
                logger.info(f"[TelegramBot] Duplicate message ignored: {msg_key}")
                return
            self._processed_msg_keys.append(msg_key)
            self._processed_msg_keys_set.add(msg_key)
            if len(self._processed_msg_keys) >= 1800:
                self._processed_msg_keys_set = set(self._processed_msg_keys)

        # 1. /start or /help
        if text.startswith("/start") or text.startswith("/help"):
            self.handle_start_or_help(chat_id)
            return

        # 2. Compounding Challenge: /challenge, /ladder, /campaign
        if any(text.startswith(cmd) for cmd in ["/challenge", "/ladder", "/campaign"]):
            self.handle_challenge_command(chat_id)
            return

        # 3. Daily VIP Automation: /auto, /automation, /dispatch, /schedule, /days, /start_auto, /stop_auto
        if any(text.startswith(cmd) for cmd in ["/auto", "/automation", "/autostatus", "/start_auto", "/stop_auto", "/autoon", "/autooff"]):
            self.handle_auto_command(chat_id, text)
            return

        if any(text.startswith(cmd) for cmd in ["/schedule", "/setdays", "/days"]):
            self.handle_schedule_command(chat_id, text)
            return

        if any(text.startswith(cmd) for cmd in ["/dispatch", "/autonow", "/runall", "/runnow"]):
            self.handle_dispatch_command(chat_id)
            return

        # 4. /rollover or /roll
        if text.startswith("/rollover") or text.startswith("/roll"):
            self.handle_rollover_command(chat_id)
            return

        # 3. /odds <target_odds> [num_tickets]
        odds_match = re.match(r"^/(?:odds|build|target)\s*(\d+\.?\d*)(.*)", text, re.IGNORECASE)
        if odds_match:
            val = float(odds_match.group(1))
            rest = (odds_match.group(2) or "").lower().strip()
            is_two = any(k in rest for k in ["2 ticket", "2 variant", "2 slip", "two ticket", "two variant", "two slip", " 2 "]) or rest.startswith("2")
            num_tickets = 2 if is_two else 1
            self.handle_odds_command(chat_id, val, num_tickets=num_tickets)
            return

        # Shortcuts: /2odds, /5odds, /10odds, /20odds [num_tickets]
        shortcut_odds = re.match(r"^/(\d+)odds(.*)", text, re.IGNORECASE)
        if shortcut_odds:
            val = float(shortcut_odds.group(1))
            rest = (shortcut_odds.group(2) or "").lower().strip()
            is_two = any(k in rest for k in ["2 ticket", "2 variant", "2 slip", "two ticket", "two variant", "two slip", " 2 "]) or rest.startswith("2")
            num_tickets = 2 if is_two else 1
            self.handle_odds_command(chat_id, val, num_tickets=num_tickets)
            return

        # 4. /games <count> [num_tickets]
        games_match = re.match(r"^/(?:games|matches)\s*(\d+)(.*)", text, re.IGNORECASE)
        if games_match:
            cnt = int(games_match.group(1))
            rest = (games_match.group(2) or "").lower().strip()
            is_two = any(k in rest for k in ["2 ticket", "2 variant", "2 slip", "two ticket", "two variant", "two slip", " 2 "]) or rest.startswith("2")
            num_tickets = 2 if is_two else 1
            self.handle_games_command(chat_id, cnt, num_tickets=num_tickets)
            return

        # 5. /portfolio (or alias /split, /permute, /distribute): Multi-ticket investment portfolio
        # Examples: /portfolio CODE | /portfolio CODE 2 | /portfolio CODE 4 | /portfolio CODE filtered
        port_match = re.match(r"^/(?:portfolio|split|permute|distribute)\s+([A-Za-z0-9]+)(.*)", text, re.IGNORECASE)
        if port_match:
            code = port_match.group(1).upper()
            rest = port_match.group(2).lower()
            target_port = "2_SLIPS" if any(k in rest for k in ["2", "single", "two", "1x"]) else "4_SLIPS"
            filter_r = any(k in rest for k in ["filter", "safe", "clean", "purge"])
            self.handle_portfolio_command(chat_id, code=code, target_portfolio=target_port, filter_risky=filter_r)
            return

        # 5a. /remove (or alias /trim): Risk purge preserving original picks as-is
        # Examples: /remove D99K41 15 games 2 tickets | /remove D99K41 2 tickets | /remove D99K41
        remove_match = re.match(r"^/(?:remove|trim)\s+([A-Za-z0-9]+)(.*)", text, re.IGNORECASE)
        if remove_match:
            code = remove_match.group(1).upper()
            rest = remove_match.group(2).lower()

            target_mode = "GAMES"
            is_two = any(k in rest for k in ["2 ticket", "2 variant", "2 slip", "two ticket", "two variant", "two slip", " 2 "]) or rest.strip().startswith("2")
            num_tickets = 2 if is_two else 1

            odds_m = re.search(r"(\d+\.?\d*)\s*(?:odd|odds|x)", rest)
            games_m = re.search(r"(\d+)\s*(?:game|games|leg|legs|match|matches)", rest)

            if odds_m:
                target_mode = "ODDS"
                target_val = float(odds_m.group(1))
            elif games_m:
                target_mode = "GAMES"
                target_val = float(games_m.group(1))
            else:
                target_mode = "GAMES"
                target_val = 15.0

            self.handle_remove_command(
                chat_id=chat_id,
                code=code,
                mode="REMOVE",
                target_mode=target_mode,
                target_val=target_val,
                num_tickets=num_tickets
            )
            return

        # 5b. /edit (or alias /reedit, /upgrade): Market upgrade to verified SportyBet safety markets
        # Examples: /edit D99K41 15 games 2 tickets | /edit D99K41 2 tickets | /edit D99K41
        edit_match = re.match(r"^/(?:edit|reedit|upgrade)\s+([A-Za-z0-9]+)(.*)", text, re.IGNORECASE)
        if edit_match:
            code = edit_match.group(1).upper()
            rest = edit_match.group(2).lower()

            target_mode = "GAMES"
            is_two = any(k in rest for k in ["2 ticket", "2 variant", "2 slip", "two ticket", "two variant", "two slip", " 2 "]) or rest.strip().startswith("2")
            num_tickets = 2 if is_two else 1

            odds_m = re.search(r"(\d+\.?\d*)\s*(?:odd|odds|x)", rest)
            games_m = re.search(r"(\d+)\s*(?:game|games|leg|legs|match|matches)", rest)

            if odds_m:
                target_mode = "ODDS"
                target_val = float(odds_m.group(1))
            elif games_m:
                target_mode = "GAMES"
                target_val = float(games_m.group(1))
            else:
                target_mode = "GAMES"
                target_val = 15.0

            self.handle_edit_command(
                chat_id=chat_id,
                code=code,
                mode="EDIT",
                target_mode=target_mode,
                target_val=target_val,
                num_tickets=num_tickets
            )
            return

        # 6. Check if text contains a SportyBet share link or booking code
        # e.g., https://www.sportybet.com/ng/?shareCode=GH7AKP or GH7AKP
        share_code_url_match = re.search(r"shareCode=([A-Za-z0-9]{4,10})", text, re.IGNORECASE)
        if share_code_url_match:
            found_code = share_code_url_match.group(1).upper()
            self.handle_raw_code_detected(chat_id, found_code)
            return

        # Standalone booking code: 5-8 alphanumeric uppercase characters
        clean_text = text.strip().upper()
        if re.match(r"^[A-Z0-9]{5,8}$", clean_text) and not clean_text.startswith("/"):
            self.handle_raw_code_detected(chat_id, clean_text)
            return

        # Default fallback: guide user
        self.send_message(
            chat_id,
            "💡 <b>Command Not Recognized</b>\n\n"
            "Use <code>/help</code> to view available commands, or paste any SportyBet booking code (e.g. <code>GH7AKP</code>) to trim it."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Long-Polling Daemon Loop & Command Registration
    # ─────────────────────────────────────────────────────────────────────────

    def register_bot_commands(self):
        """
        Registers the bot commands and persistent Chat Menu button with Telegram Bot API.
        Enables the native command modal popup when clicking [Menu] or typing '/'.
        """
        commands = [
            {"command": "start", "description": "Show main menu & quick action buttons"},
            {"command": "remove", "description": "Purge risky legs as-is (/remove CODE 15 games 2 tickets)"},
            {"command": "edit", "description": "Upgrade to safe SportyBet markets (/edit CODE 15 games 2 tickets)"},
            {"command": "auto", "description": "Daily 10 AM VIP Automation status & toggles"},
            {"command": "dispatch", "description": "Dispatch today's daily slips now"},
            {"command": "rollover", "description": "Generate today's 2.0x Safe Rollover slip"},
            {"command": "odds", "description": "Target odds (/odds 20 or /odds 20 2 tickets)"},
            {"command": "games", "description": "Top matches (/games 15 or /games 15 2 tickets)"},
            {"command": "schedule", "description": "Configure 10 AM dispatch time & active days"},
            {"command": "help", "description": "Help guide & full usage manual"},
        ]
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(f"{self.base_url}/setMyCommands", json={"commands": commands})
                client.post(f"{self.base_url}/setChatMenuButton", json={"menu_button": {"type": "commands"}})
            logger.info("[TelegramBot] Registered bot commands and Chat Menu Button successfully.")
        except Exception as e:
            logger.warning(f"[TelegramBot] Could not register bot commands: {e}")

    def poll_updates(self):
        """Infinite polling loop for Telegram updates."""
        logger.info("[TelegramBot] Polling loop started successfully.")

        # Ensure no hanging webhook conflicts
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(f"{self.base_url}/deleteWebhook", json={"drop_pending_updates": False})
        except Exception:
            pass

        # Register bot commands and enable persistent native Menu button
        try:
            self.register_bot_commands()
        except Exception:
            pass

        while self._running:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self._last_update_id + 1,
                "timeout": 20,
                "allowed_updates": json.dumps(["message", "callback_query", "edited_message"])
            }

            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            uid = update.get("update_id", 0)
                            # Strictly skip any duplicate or already-processed update IDs
                            if uid <= self._last_update_id:
                                continue
                            self._last_update_id = uid

                            if "message" in update:
                                try:
                                    threading.Thread(
                                        target=self.process_message,
                                        args=(update["message"],),
                                        daemon=True
                                    ).start()
                                except Exception as me:
                                    logger.error(f"[TelegramBot] Error dispatching message thread: {me}", exc_info=True)

                            elif "callback_query" in update:
                                cq = update["callback_query"]
                                try:
                                    cq_id = cq.get("id")
                                    if cq_id:
                                        self.answer_callback_query(cq_id)
                                    threading.Thread(
                                        target=self.handle_callback_query,
                                        args=(cq,),
                                        daemon=True
                                    ).start()
                                except Exception as ce:
                                    logger.error(f"[TelegramBot] Error dispatching callback thread: {ce}", exc_info=True)

                    elif resp.status_code == 409:
                        # Temporary conflict during PM2 restart or overlapping connection
                        logger.info("[TelegramBot] Polling connection conflict (HTTP 409). Backing off 5s for previous session to release...")
                        time.sleep(5.0)
                    elif resp.status_code in (401, 404):
                        logger.error(f"[TelegramBot] Invalid token or bot not found ({resp.status_code}). Polling halted.")
                        break
                    else:
                        logger.warning(f"[TelegramBot] getUpdates returned HTTP {resp.status_code}")
                        time.sleep(2.0)
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                # Normal for long-polling timeout
                continue
            except Exception as e:
                logger.warning(f"[TelegramBot] Polling loop exception: {e}")
                time.sleep(3.0)

        logger.info("[TelegramBot] Polling loop ended.")

    def start(self):
        """Starts the bot in a background thread with cross-process lock protection."""
        from pathlib import Path
        from dotenv import load_dotenv
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        run_bot_env = os.getenv("RUN_TELEGRAM_BOT", "true").strip().lower()
        if run_bot_env in ("false", "0", "no", "disabled"):
            logger.info("[TelegramBot] RUN_TELEGRAM_BOT is disabled in environment. Polling worker will not start.")
            return

        if self._running:
            logger.info("[TelegramBot] Bot is already running in this process.")
            return

        # Ensure only 1 worker process on the server runs the Telegram bot poller
        if not self._acquire_process_lock():
            logger.warning("[TelegramBot] Another worker process holds the polling lock. Skipping duplicate poller instance.")
            return

        self._running = True
        self._thread = threading.Thread(target=self.poll_updates, name="StatIQTelegramBotWorker", daemon=True)
        self._thread.start()
        logger.info("[TelegramBot] Background worker spawned.")

    def stop(self):
        """Stops the bot background worker and releases cross-process lock."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            logger.info("[TelegramBot] Bot worker stopped.")
        if self._lock_file:
            try:
                if os.name == "nt":
                    import msvcrt
                    try:
                        msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                self._lock_file.close()
                self._lock_file = None
            except Exception:
                pass


# Global Singleton Instance
statiq_telegram_bot = StatIQTelegramBot()
