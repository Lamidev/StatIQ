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
            "🎯 <b>Generate by Target Odds (1 or 2 Zero-Overlap Slips):</b>\n"
            "• <code>/odds 2.0</code> — 2.0x Safe Multiplier (1 Slip)\n"
            "• <code>/odds 2.0 2 tickets</code> — <b>2 Variant Slips (Zero Overlap!)</b>\n"
            "• <code>/odds 5.0 2 tickets</code> — 2 Multiplier Slips (100% Unique Fixtures)\n\n"
            "⚽ <b>Generate by Match Count (1 or 2 Zero-Overlap Slips):</b>\n"
            "• <code>/games 10</code> — Top 10 High-Confidence Matches (1 Slip)\n"
            "• <code>/games 10 2 tickets</code> — <b>2 Variant Slips of 10 Matches Each</b>\n"
            "• <code>/games 12 2 tickets</code> — 2 Variant Slips of 12 Matches Each\n\n"
            "🚀 <b>Daily Elite Rollover:</b>\n"
            "• <code>/rollover</code> — Instant 2.0x Low-Variance Day Slip\n\n"
            "✂️ <b>Ticket Trimmer & Risk Purge (REMOVE Mode):</b>\n"
            "Send or trim any SportyBet 30+ game slip into 10–12 winnable picks:\n"
            "• <code>/trim CODE 10 games 2 tickets</code> ➔ <i>Zero Overlap Guarantee!</i>\n"
            "• <code>/remove CODE 2 tickets</code> ➔ <i>Purges risky legs into 2 independent slips</i>\n"
            "• <code>/trim CODE 10 games</code> ➔ 1 Core Slip of 10 Games\n\n"
            "📱 <b>Command Menu Modal:</b> Tap the <b>[Menu]</b> button at the bottom-left corner of your chat to view and run all commands with one tap!\n\n"
            "🛡️ <b>Strict Odds Floor:</b> Min odds ≥ <b>1.15x</b> strictly enforced across all picks."
        )

        keyboard = {
            "inline_keyboard": [
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
                ],
                [
                    {"text": "🚀 Daily Rollover Slip", "callback_data": "gen:rollover"}
                ]
            ]
        }
        return self.send_message(chat_id, msg, reply_markup=keyboard)

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
            f"⏳ <b>StatIQ 7-Gate Engine:</b> Building {variant_desc} targeting <b>{target_odds:.2f}x</b> odds (Min Odds ≥ 1.15x)..."
        )

        try:
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
            finally:
                loop.close()

            portfolio = res.get("portfolio_tickets") or []
            if not portfolio and res.get("ticket"):
                portfolio = [res.get("ticket")]

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
                    f"🎯 StatIQ AI Accumulator — Slip #{slip_idx} of {len(portfolio)} ({len(approved_legs)} Legs)"
                    if len(portfolio) > 1
                    else f"🎯 StatIQ AI Accumulator ({len(approved_legs)} Legs)"
                )
                extra_note = (
                    f"Target: {target_odds:.2f}x · 🔒 Zero-Overlap Guarantee (100% Unique Fixtures) · Min Odds ≥ 1.15x"
                    if len(portfolio) > 1
                    else f"Target: {target_odds:.2f}x · Min Odds ≥ 1.15x Strictly Enforced"
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
                self.send_message(chat_id, f"⚠️ <b>Builder Notice:</b> {res.get('message', 'No suitable fixtures available right now.')}")
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
            f"⏳ <b>StatIQ 7-Gate Engine:</b> Selecting {variant_desc} (Min Odds ≥ 1.15x)..."
        )

        try:
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
            finally:
                loop.close()

            portfolio = res.get("portfolio_tickets") or []
            if not portfolio and res.get("ticket"):
                portfolio = [res.get("ticket")]

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
                self.send_message(chat_id, f"⚠️ <b>Builder Notice:</b> {res.get('message', 'No suitable fixtures available right now.')}")
        except Exception as e:
            logger.error(f"[TelegramBot] Games build error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error:</b> Failed to generate ticket ({_esc(str(e))}).")

    def handle_trim_command(
        self,
        chat_id: int | str,
        code: str,
        target_mode: str = "GAMES",
        target_val: float = 10,
        num_tickets: int = 1
    ):
        """
        Trims/Removes risky legs from an external SportyBet ticket.
        Supports 1 or 2 tickets (with zero overlap guarantee).
        """
        code = code.strip().upper()
        self.send_chat_action(chat_id, "typing")
        mode_desc = f"{int(target_val)} games" if target_mode == "GAMES" else f"{target_val:.1f}x odds"
        variant_desc = "2 separate slips (Zero Overlap)" if num_tickets == 2 else "1 core slip"
        self.send_message(
            chat_id,
            f"⏳ <b>Auditing SportyBet Ticket <code>{code}</code>...</b>\n"
            f"➔ Extracting: <b>{variant_desc}</b> targeting <b>{mode_desc}</b>\n"
            f"➔ Enforcing: Dixon-Coles/Poisson models & strict Min Odds ≥ <b>1.15x</b>"
        )

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

            # Step 2: Run Re-Editor with REMOVE mode
            target_games = int(target_val) if target_mode == "GAMES" else 10
            target_odds = float(target_val) if target_mode == "ODDS" else 5.0

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(
                    re_edit_ticket(
                        selections=selections,
                        target_odds=target_odds,
                        mode="REMOVE",
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
                self.send_message(chat_id, "⚠️ <b>Audit Result:</b> None of the matches in this ticket met the 70%+ safety cushion threshold.")
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

                slip_title = f"✂️ Trimmed Core Slip #{slip_idx} ({len(booked_picks)} of {original_count} Matches)"
                overlap_tag = "🔒 <b>Zero-Overlap Partition:</b> 100% Independent Fixtures" if num_tickets > 1 else f"Trims {original_count} matches down to high-confidence core"

                self._dispatch_ticket_message(
                    chat_id=chat_id,
                    title=slip_title,
                    booking_code=booked_code,
                    share_url=booked_url,
                    total_odds=round(acc_odd, 2),
                    confidence=round((slip.get("avg_win_prob") or 0.82) * 100.0, 1),
                    picks=booked_picks,
                    extra_note=f"{overlap_tag} · Min Odds ≥ 1.15x Strictly Kept"
                )

        except Exception as e:
            logger.error(f"[TelegramBot] Trim error: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ <b>Error processing ticket:</b> {_esc(str(e))}")

    def handle_raw_code_detected(self, chat_id: int | str, code: str):
        """When user pastes a booking code, inspect it and offer 1-tap action buttons."""
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
                f"Select an action below to let StatIQ optimize or trim this ticket:"
            )

            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": f"✂️ Trim to 10 Games (1 Slip)", "callback_data": f"trim:{code}:10:games:1"},
                        {"text": f"✂️ Trim to 12 Games (1 Slip)", "callback_data": f"trim:{code}:12:games:1"}
                    ],
                    [
                        {"text": f"✂️ 2 Tickets (Zero Overlap - 10 Games)", "callback_data": f"trim:{code}:10:games:2"},
                        {"text": f"✂️ 2 Tickets (Zero Overlap - 12 Games)", "callback_data": f"trim:{code}:12:games:2"}
                    ],
                    [
                        {"text": f"🎯 Trim to 2.0x (2 Slips)", "callback_data": f"trim:{code}:2.0:odds:2"},
                        {"text": f"🎯 Trim to 5.0x (1 Slip)", "callback_data": f"trim:{code}:5.0:odds:1"}
                    ]
                ]
            }
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
        chat_id = message.get("chat", {}).get("id")

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

        # Case 2: Trimmer button (trim:<code>:<val>:<mode>:<num_tickets>)
        elif data.startswith("trim:"):
            parts = data.split(":")
            if len(parts) >= 5:
                code = parts[1]
                val = float(parts[2])
                mode = parts[3].upper()  # GAMES or ODDS
                num_tickets = int(parts[4])
                self.handle_trim_command(
                    chat_id=chat_id,
                    code=code,
                    target_mode=mode,
                    target_val=val,
                    num_tickets=num_tickets
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

        # 2. /rollover or /roll
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

        # Shortcuts: /2odds, /5odds, /10odds [num_tickets]
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

        # 5. /trim or /remove
        # Examples:
        # /trim D99K41 12 games
        # /trim D99K41 10 games 2 tickets
        # /trim D99K41 5.0 odds
        # /remove D99K41 2 tickets
        trim_prefix = re.match(r"^/(?:trim|remove|reedit)\s+([A-Za-z0-9]+)(.*)", text, re.IGNORECASE)
        if trim_prefix:
            code = trim_prefix.group(1).upper()
            rest = trim_prefix.group(2).lower()

            target_mode = "GAMES"
            is_two = any(k in rest for k in ["2 ticket", "2 variant", "2 slip", "two ticket", "two variant", "two slip", " 2 "]) or rest.strip().startswith("2")
            num_tickets = 2 if is_two else 1

            # Check if odds specified
            odds_m = re.search(r"(\d+\.?\d*)\s*(?:odd|odds|x)", rest)
            games_m = re.search(r"(\d+)\s*(?:game|games|leg|legs|match|matches)", rest)

            if odds_m:
                target_mode = "ODDS"
                target_val = float(odds_m.group(1))
            elif games_m:
                target_mode = "GAMES"
                target_val = float(games_m.group(1))
            else:
                # Default to 10 games
                target_mode = "GAMES"
                target_val = 10.0

            self.handle_trim_command(
                chat_id=chat_id,
                code=code,
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
            {"command": "start", "description": "Show main menu & 1-tap quick buttons"},
            {"command": "rollover", "description": "Generate today's 2.0x Safe Rollover slip"},
            {"command": "odds", "description": "Target odds (/odds 2.0 or /odds 2.0 2 tickets)"},
            {"command": "games", "description": "Top matches (/games 10 or /games 10 2 tickets)"},
            {"command": "trim", "description": "Trim 30+ game slip (/trim CODE 10 games 2 tickets)"},
            {"command": "remove", "description": "Purge risky picks (/remove CODE 2 tickets)"},
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

        # Ensure no hanging webhook conflicts and flush any old pending backlog on startup
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(f"{self.base_url}/deleteWebhook", json={"drop_pending_updates": True})
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
                "allowed_updates": ["message", "callback_query"]
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
                                    self.process_message(update["message"])
                                except Exception as me:
                                    logger.error(f"[TelegramBot] Error handling message: {me}", exc_info=True)

                            elif "callback_query" in update:
                                try:
                                    self.handle_callback_query(update["callback_query"])
                                except Exception as ce:
                                    logger.error(f"[TelegramBot] Error handling callback: {ce}", exc_info=True)

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
