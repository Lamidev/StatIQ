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
        target_odds = ticket_data.get("target_odds", 1.50)
        actual_odds = ticket_data.get("actual_odds", target_odds)
        confidence = ticket_data.get("confidence_score", 90.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"
        title_line = f"🎯 <b>StatIQ Elite Rollover Slip ({actual_odds:.2f}x)</b>"

        lines = [
            title_line,
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Target Multiplier:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} Banker Matches (2–3 Low-Variance Cushions)\n"
        ]

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
        lines.append("🤖 <i>Automated via StatIQ Elite Rollover Scheduler · 1.50x Compounding Corridor</i>")

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def dispatch_value_acca_slip(cls, ticket_data: Dict[str, Any]) -> bool:
        """
        Formats and sends the Precision Multiplier alert to Telegram with Zero-Overlap assurance.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = float(ticket_data.get("target_odds", 5.0))
        actual_odds = float(ticket_data.get("actual_odds", target_odds))
        confidence = ticket_data.get("confidence_score", 65.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            f"🎯 <b>StatIQ {target_odds:.1f}x Precision Multiplier Slip</b>",
            "🔒 <b>Elite Selection:</b> High-Assurance Cushions (Zero Obscure Leagues)",
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
        Formats and sends the Mega Multiplier alert to Telegram with Zero-Overlap assurance.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = float(ticket_data.get("target_odds", 10.0))
        actual_odds = float(ticket_data.get("actual_odds", target_odds))
        confidence = ticket_data.get("confidence_score", 52.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"
        variant_idx = ticket_data.get("variant_index")

        slip_title = f"⚡ <b>StatIQ {target_odds:.1f}x Mega Multiplier Slip #{variant_idx}</b>" if variant_idx else f"⚡ <b>StatIQ {target_odds:.1f}x Mega Multiplier Slip</b>"

        lines = [
            slip_title,
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures (Zero Overlap across all Slips)",
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
        Formats and sends the Monster Multiplier alert to Telegram with Calendar Adaptive Guarantee.
        """
        code = ticket_data.get("booking_code") or "N/A"
        target_odds = float(ticket_data.get("target_odds", 20.0))
        actual_odds = float(ticket_data.get("actual_odds", target_odds))
        confidence = ticket_data.get("confidence_score", 35.0)
        picks = ticket_data.get("picks", [])
        date_str = ticket_data.get("date_str", "Today")
        share_url = ticket_data.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            f"🚀 <b>StatIQ {target_odds:.1f}x Monster Multiplier Slip</b>",
            "🔒 <b>Zero-Overlap Guarantee:</b> 100% Unique Fixtures (No Clash with Rollover)",
            f"📅 <b>Date:</b> {date_str} (10:00 AM WAT Dispatch)",
            f"⚡ <b>Total Multiplier:</b> {actual_odds:.2f}x | <b>Combined Confidence:</b> {confidence:.1f}%",
            f"📊 <b>Leg Count:</b> {len(picks)} Vetted Matches\n"
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

    @classmethod
    def notify_schedule_updated(cls, config: Dict[str, Any]) -> bool:
        """
        Sends an instant Telegram notification whenever the Daily VIP Automation schedule
        or target odds are modified from the web interface.
        """
        ro_on = config.get("enable_rollover_2x", True)
        ro_odds = float(config.get("rollover_target_odds") or config.get("target_odds") or 1.50)

        a5_on = config.get("enable_acca_5x", True)
        a5_odds = float(config.get("acca_5x_target_odds") or 5.00)

        a10_on = config.get("enable_acca_10x", True)
        a10_odds = float(config.get("acca_10x_target_odds") or 10.00)

        a20_on = config.get("enable_acca_20x", False)
        a20_odds = float(config.get("acca_20x_target_odds") or 20.00)

        disp_time = config.get("dispatch_time", "10:00")
        active_days = ", ".join(config.get("active_days", ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]))
        max_leg = float(config.get("max_leg_odds", 1.45))
        is_active = config.get("is_enabled", True)

        status_badge = "🟢 <b>ACTIVE</b>" if is_active else "🔴 <b>PAUSED</b>"

        lines = [
            "⚙️ <b>StatIQ Daily VIP Automation Settings Updated</b>",
            f"Status: {status_badge} · Time: <b>{disp_time} AM WAT</b>",
            f"📅 Active Days: <b>{active_days}</b>\n",
            f"• 🎯 <b>Slip 1 (Rollover):</b> {'✅ ON' if ro_on else '❌ OFF'} ➔ <b>{ro_odds:.2f}x Target</b> (2–3 Banker Legs)",
            f"• ⚡ <b>Slip 2 (Precision):</b> {'✅ ON' if a5_on else '❌ OFF'} ➔ <b>{a5_odds:.2f}x Target</b> (Zero-Overlap Cushions)",
            f"• 🚀 <b>Slip 3 (Mega Multiplier):</b> {'✅ ON' if a10_on else '❌ OFF'} ➔ <b>{a10_odds:.2f}x Target</b> (High-Dominance Acca)",
            f"• ⚡ <b>Slip 4 (Monster Acca):</b> {'✅ ON' if a20_on else '❌ OFF'} ➔ <b>{a20_odds:.2f}x Target</b>\n",
            f"🛡️ <i>Max Single-Leg Odds Ceiling: {max_leg:.2f}x (Golden Safety Corridor)</i>",
            f"✅ <i>Sync Complete: Next 10:00 AM dispatch will generate slips matching these exact multipliers!</i>"
        ]

        msg = "\n".join(lines)
        return cls.send_message(msg)


