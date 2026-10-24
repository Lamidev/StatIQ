"""
Basketball Telegram Notification Dispatcher for StatIQ.
Formats and dispatches the daily 9:00 AM WAT 2.0x Basketball Cushion Slip
directly to the VIP Telegram channel with instant SportyBet preload links.
"""
import os
import logging
import time
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("statiq.basketball.telegram")

class BasketballTelegramNotifier:
    _dispatched_codes: set = set()

    @classmethod
    def get_credentials(cls) -> Dict[str, str]:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").replace('"', '').strip() or "8979207719:AAHmjFvyDDijF4xli6On0QyuGkX6IcCcuKI"
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").replace('"', '').strip() or "1034502587"
        return {"bot_token": token, "chat_id": chat_id}

    @classmethod
    def send_message(cls, text: str, parse_mode: str = "HTML") -> bool:
        creds = cls.get_credentials()
        bot_token = creds["bot_token"]
        chat_id = creds["chat_id"]

        if not bot_token or not chat_id:
            logger.warning("[BasketballTelegram] Bot token or chat ID missing.")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.post(url, json=payload)
                if r.status_code == 200:
                    logger.info("[BasketballTelegram] Message delivered successfully.")
                    return True
                logger.warning(f"[BasketballTelegram] Failed to send message: {r.status_code} - {r.text}")
        except Exception as e:
            logger.error(f"[BasketballTelegram] Network error sending message: {e}")
        return False

    @classmethod
    def build_html_card(cls, ticket_data: Dict[str, Any], custom_title: Optional[str] = None) -> str:
        """
        Builds the authoritative rich HTML message card for Telegram.
        """
        code = ticket_data.get("booking_code") or "N/A"
        actual_odds = float(ticket_data.get("actual_odds") or 2.00)
        confidence = float(ticket_data.get("combined_confidence") or 82.0)
        picks = ticket_data.get("picks") or []
        date_str = ticket_data.get("date_str") or time.strftime("%Y-%m-%d")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"
        title = custom_title or ticket_data.get("title") or "🏀 <b>StatIQ Basketball VIP Slip</b>"

        slot = ticket_data.get("session_slate", "ALL")
        slot_desc = "Daytime (Euro/Asia)" if slot == "DAYTIME" else ("Midnight (USA NBA/NCAA)" if slot == "MIDNIGHT" else "Global")

        lines = [
            title,
            f"🎯 <b>Strategy:</b> Banker Cushion Portfolio ({slot_desc})",
            f"📅 <b>Date:</b> {date_str}",
            f"⚡ <b>Total Multiplier:</b> <b>{actual_odds:.2f}x</b> | <b>Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} Vetted Matches (Strict Zero Overlap)\n"
        ]

        for i, p in enumerate(picks, 1):
            h = p.get("home_team")
            a = p.get("away_team")
            tourn = p.get("tournament") or "Basketball"
            mkt = p.get("market_name") or "Over/Under"
            sel = p.get("selection_desc") or "Pick"
            odd = float(p.get("odds") or 1.25)
            just = p.get("justification") or "High scoring clearance."
            kickoff = p.get("kickoff_wat_str") or ""
            kickoff_display = f" · <i>{kickoff.split()[-2]} WAT</i>" if kickoff else ""

            lines.append(f"<b>{i}. {h} vs {a}</b> ({tourn}{kickoff_display})")
            lines.append(f"   ➔ <b>Pick:</b> <code>{sel}</code> [{mkt}] @ <b>{odd:.2f}</b>")
            lines.append(f"   🛡️ <i>{just}</i>\n")

        lines.append(f"🔥 <b>Total Multiplier:</b> <b>{actual_odds:.2f}x</b>")
        lines.append(f"🎟️ <b>SportyBet Code:</b> <code>{code}</code>")
        lines.append(f"🔗 <a href=\"{share_url}\"><b>Click to Pre-Load on SportyBet</b></a>\n")
        lines.append("🤖 <i>StatIQ Basketball Quant Engine · Full-Time Cushion Overs & High-Floor Banking</i>")

        return "\n".join(lines)

    # Backward-compatible alias
    _build_html_card = build_html_card

    @classmethod
    def dispatch_daily_2x_slip(cls, ticket_data: Dict[str, Any], custom_title: Optional[str] = None) -> bool:
        """
        Formats and dispatches the Basketball Banker Slip to Telegram.
        """
        code = ticket_data.get("booking_code") or "N/A"
        if code and code != "N/A" and code in cls._dispatched_codes:
            logger.info(f"[BasketballTelegram] Slip {code} already dispatched today. Suppressing duplicate.")
            return True

        msg = cls.build_html_card(ticket_data, custom_title=custom_title)
        sent = cls.send_message(msg)
        if sent and code and code != "N/A":
            cls._dispatched_codes.add(code)
        return sent

    @classmethod
    def send_test_ping(cls) -> bool:
        msg = (
            "🔔 <b>StatIQ Basketball Scheduler Test</b>\n\n"
            "Basketball 9:00 AM WAT 2.0x cushion automation service is active and operational! 🏀"
        )
        return cls.send_message(msg)
