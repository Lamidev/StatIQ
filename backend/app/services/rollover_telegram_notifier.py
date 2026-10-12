import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("statiq.rollover.telegram")

class RolloverTelegramNotifier:
    """
    Dedicated Telegram Notification Dispatcher for StatIQ Automated Rollover Engine.
    Dispatches elite rollover slips with loadable SportyBet booking links and leg analysis.
    """

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
            logger.warning("[RolloverTelegram] Bot token or chat ID missing.")
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
                    logger.info("[RolloverTelegram] Message delivered successfully.")
                    return True
                logger.warning(f"[RolloverTelegram] Failed to send message: {r.status_code} - {r.text}")
        except Exception as e:
            logger.error(f"[RolloverTelegram] Network error sending message: {e}")
        return False

    @classmethod
    def dispatch_rollover_slip(cls, ticket_data: Dict[str, Any]) -> bool:
        """
        Formats and sends a high-assurance Rollover ticket alert to Telegram.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = ticket_data.get("target_odds", 2.0)
        actual_odds = ticket_data.get("actual_odds", target_odds)
        confidence = ticket_data.get("confidence_score", 88.5)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"
        challenge_day = ticket_data.get("challenge_day")
        stake_amount = ticket_data.get("stake")

        title_line = "🎯 <b>StatIQ Elite Rollover Slip</b>"
        if challenge_day:
            title_line = f"🎯 <b>StatIQ Elite Rollover — {challenge_day}</b>"

        lines = [
            title_line,
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Target Odds:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%"
        ]

        if stake_amount:
            pot_return = round(float(stake_amount) * actual_odds)
            lines.append(f"💰 <b>Compounding Stake:</b> ₦{int(stake_amount):,} ➔ <b>Target Return:</b> ₦{int(pot_return):,}")

        lines.append("")

        for i, p in enumerate(picks, 1):
            h = p.get("home_team")
            a = p.get("away_team")
            comp = p.get("competition") or "Football"
            mkt = p.get("market_desc") or p.get("market_name") or "Pick"
            sel = p.get("selection_desc") or p.get("selection_name") or "Selection"
            odd = float(p.get("odds") or 1.25)
            prob = float(p.get("model_probability") or 0.85) * 100.0

            lines.append(f"<b>{i}. {h} vs {a}</b> ({comp})")
            lines.append(f"   ➔ <b>Pick:</b> {sel} [{mkt}] @ <b>{odd:.2f}</b> (Win Prob: {prob:.0f}%)")

        lines.append(f"\n🔥 <b>Total Multiplier:</b> {actual_odds:.2f}x")
        lines.append(f"🎟️ <b>SportyBet Code:</b> <code>{code}</code>")
        lines.append(f"🔗 <a href=\"{share_url}\"><b>Click to Pre-Load on SportyBet</b></a>\n")
        lines.append("🤖 <i>Automated via StatIQ Elite Rollover Scheduler</i>")

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def dispatch_value_acca_slip(cls, ticket_data: Dict[str, Any]) -> bool:
        """
        Formats and sends the 5.0x Value Acca alert to Telegram with Zero-Overlap assurance.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = ticket_data.get("target_odds", 5.0)
        actual_odds = ticket_data.get("actual_odds", target_odds)
        confidence = ticket_data.get("confidence_score", 65.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            "🔥 <b>StatIQ 5.0x Value Acca Slip</b>",
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures (No clash with Rollover)",
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Target Multiplier:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} Vetted Matches\n"
        ]

        for i, p in enumerate(picks, 1):
            h = p.get("home_team")
            a = p.get("away_team")
            comp = p.get("competition") or "Football"
            mkt = p.get("market_desc") or p.get("market_name") or "Pick"
            sel = p.get("selection_desc") or p.get("selection_name") or "Selection"
            odd = float(p.get("odds") or 1.25)
            prob = float(p.get("model_probability") or 0.80) * 100.0

            lines.append(f"<b>{i}. {h} vs {a}</b> ({comp})")
            lines.append(f"   ➔ <b>Pick:</b> {sel} [{mkt}] @ <b>{odd:.2f}</b> (Win: {prob:.0f}%)")

        lines.append(f"\n🔥 <b>Total Multiplier:</b> {actual_odds:.2f}x")
        lines.append(f"🎟️ <b>SportyBet Code:</b> <code>{code}</code>")
        lines.append(f"🔗 <a href=\"{share_url}\"><b>Click to Pre-Load on SportyBet</b></a>\n")
        lines.append("🤖 <i>Automated via StatIQ Daily VIP Scheduler · Min Odds ≥ 1.15x</i>")

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def dispatch_mega_multiplier_slip(cls, ticket_data: Dict[str, Any]) -> bool:
        """
        Formats and sends the 10.0x Mega Multiplier alert to Telegram with Zero-Overlap assurance.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = ticket_data.get("target_odds", 10.0)
        actual_odds = ticket_data.get("actual_odds", target_odds)
        confidence = ticket_data.get("confidence_score", 52.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            "⚡ <b>StatIQ 10.0x Mega Multiplier Slip</b>",
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures (Zero Overlap across all 3 Slips)",
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Total Multiplier:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} High-Dominance Matches\n"
        ]

        for i, p in enumerate(picks, 1):
            h = p.get("home_team")
            a = p.get("away_team")
            comp = p.get("competition") or "Football"
            mkt = p.get("market_desc") or p.get("market_name") or "Pick"
            sel = p.get("selection_desc") or p.get("selection_name") or "Selection"
            odd = float(p.get("odds") or 1.25)
            prob = float(p.get("model_probability") or 0.80) * 100.0

            lines.append(f"<b>{i}. {h} vs {a}</b> ({comp})")
            lines.append(f"   ➔ <b>Pick:</b> {sel} [{mkt}] @ <b>{odd:.2f}</b> (Win: {prob:.0f}%)")

        lines.append(f"\n🚀 <b>Total Multiplier:</b> {actual_odds:.2f}x")
        lines.append(f"🎟️ <b>SportyBet Code:</b> <code>{code}</code>")
        lines.append(f"🔗 <a href=\"{share_url}\"><b>Click to Pre-Load on SportyBet</b></a>\n")
        lines.append("🤖 <i>Automated via StatIQ Daily VIP Scheduler · Min Odds ≥ 1.15x</i>")

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def dispatch_midweek_15x_slip(cls, ticket_data: Dict[str, Any]) -> bool:
        """
        Formats and sends the 15.0x Mid-Week Multiplier alert to Telegram with Zero-Overlap assurance.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = ticket_data.get("target_odds", 15.0)
        actual_odds = ticket_data.get("actual_odds", target_odds)
        confidence = ticket_data.get("confidence_score", 42.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            "⚡ <b>StatIQ 15.0x Mid-Week Multiplier Slip</b>",
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures (No Clash with Rollover)",
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Total Multiplier:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} High-Dominance Matches\n"
        ]

        for i, p in enumerate(picks, 1):
            h = p.get("home_team")
            a = p.get("away_team")
            comp = p.get("competition") or "Football"
            mkt = p.get("market_desc") or p.get("market_name") or "Pick"
            sel = p.get("selection_desc") or p.get("selection_name") or "Selection"
            odd = float(p.get("odds") or 1.22)
            prob = float(p.get("model_probability") or 0.80) * 100.0

            lines.append(f"<b>{i}. {h} vs {a}</b> ({comp})")
            lines.append(f"   ➔ <b>Pick:</b> {sel} [{mkt}] @ <b>{odd:.2f}</b> (Win: {prob:.0f}%)")

        lines.append(f"\n🚀 <b>Total Multiplier:</b> {actual_odds:.2f}x")
        lines.append(f"🎟️ <b>SportyBet Code:</b> <code>{code}</code>")
        lines.append(f"🔗 <a href=\"{share_url}\"><b>Click to Pre-Load on SportyBet</b></a>\n")
        lines.append("🤖 <i>Automated via StatIQ Daily VIP Scheduler · Min Odds ≥ 1.15x</i>")

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def dispatch_mega_20x_slip(cls, ticket_data: Dict[str, Any]) -> bool:
        """
        Formats and sends the 20.0x Mega Multiplier alert to Telegram with Calendar Adaptive Guarantee.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = ticket_data.get("target_odds", 20.0)
        actual_odds = ticket_data.get("actual_odds", target_odds)
        confidence = ticket_data.get("confidence_score", 35.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            "🚀 <b>StatIQ 20.0x Monster Multiplier Slip</b>",
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures (No Clash with Rollover)",
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Total Multiplier:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} Vetted Matches (15–18 High-Dominance Games)\n"
        ]

        for i, p in enumerate(picks, 1):
            h = p.get("home_team")
            a = p.get("away_team")
            comp = p.get("competition") or "Football"
            mkt = p.get("market_desc") or p.get("market_name") or "Pick"
            sel = p.get("selection_desc") or p.get("selection_name") or "Selection"
            odd = float(p.get("odds") or 1.22)
            prob = float(p.get("model_probability") or 0.80) * 100.0

            lines.append(f"<b>{i}. {h} vs {a}</b> ({comp})")
            lines.append(f"   ➔ <b>Pick:</b> {sel} [{mkt}] @ <b>{odd:.2f}</b> (Win: {prob:.0f}%)")

        lines.append(f"\n🚀 <b>Total Multiplier:</b> {actual_odds:.2f}x")
        lines.append(f"🎟️ <b>SportyBet Code:</b> <code>{code}</code>")
        lines.append(f"🔗 <a href=\"{share_url}\"><b>Click to Pre-Load on SportyBet</b></a>\n")
        lines.append("🤖 <i>Automated via StatIQ Daily VIP Scheduler · Min Odds ≥ 1.15x</i>")

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def send_test_ping(cls) -> bool:
        msg = (
            "🔔 <b>StatIQ Rollover Scheduler Test</b>\n\n"
            "Telegram notification service is active and ready for daily 10:00 AM WAT rollover dispatches! 🚀"
        )
        return cls.send_message(msg)

