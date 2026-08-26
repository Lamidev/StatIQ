"""
VirtualTelegramService - Real-time Telegram alerts for vFootball automated front-testing.
Dispatches pre-match tickets with SportyBet auto-load booking links, kickoff alerts,
post-round win/loss settlement audits, and 12:00 AM daily summary reports.
"""
import os
import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger("statiq.virtual.telegram_service")

class VirtualTelegramService:
    """
    Handles formatting and dispatching Telegram messages for the vFootball front-testing agent.
    """

    @classmethod
    def get_credentials(cls) -> Dict[str, str]:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            load_dotenv(os.path.join(root_dir, ".env"))
            load_dotenv(os.path.join(root_dir, "backend", ".env"))
        except Exception:
            pass

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").replace('"', '').strip() or "8979207719:AAHmjFvyDDijF4xli6On0QyuGkX6IcCcuKI"
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").replace('"', '').strip() or "1034502587"
        return {"bot_token": token, "chat_id": chat_id}


    @classmethod
    def is_configured(cls) -> bool:
        creds = cls.get_credentials()
        return bool(creds["bot_token"] and creds["chat_id"])

    @classmethod
    def send_message(cls, text: str, parse_mode: str = "HTML") -> bool:
        creds = cls.get_credentials()
        bot_token = creds["bot_token"]
        chat_id = creds["chat_id"]

        if not bot_token or not chat_id:
            logger.info(f"[Telegram] Bot token or chat ID not set. Message preview:\n{text}")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.post(url, json=payload)
                if r.status_code == 200:
                    logger.info("[Telegram] Alert sent successfully.")
                    return True
                else:
                    logger.warning(f"[Telegram] Failed to send alert: {r.status_code} - {r.text}")
        except Exception as e:
            logger.error(f"[Telegram] Network error sending alert: {e}")
        return False

    @classmethod
    def send_ticket_alert(cls, slip: Dict[str, Any]) -> bool:
        """
        Dispatches a pre-match vFootball 2.0x ticket with clear demarcation
        and a direct SportyBet preload link.
        """
        league = slip.get("league_name", "vFootball")
        code = slip.get("booking_code", "N/A")
        total_odds = slip.get("actual_odds", 2.0)
        round_time = slip.get("round_time_str", "Upcoming")
        selections = slip.get("selections", [])

        # Direct SportyBet betslip pre-loading link
        preload_url = f"https://www.sportybet.com/ng/?shareCode={code}"

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🎯 <b>NEW ROUND BOOKED — {league}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"⏱ <b>Kickoff:</b> <code>{round_time}</code>",
            f"🎫 <b>SportyBet Code:</b> <code>{code}</code>",
            f"📊 <b>Total Odds:</b> <code>{total_odds}x</code>",
            "",
            "📋 <b>Selected Matches & Picks:</b>"
        ]

        for idx, s in enumerate(selections, 1):
            match = s.get("match", "Match")
            pick = s.get("pick", "Pick")
            odds = s.get("odds", "1.00")
            lines.append(f"  {idx}. <b>{match}</b> → <i>{pick}</i> (@ {odds}x)")

        lines.extend([
            "",
            f"⚡ <a href='{preload_url}'><b>Click here to load Slip directly on SportyBet</b></a>",
            "<i>#StatIQ #vFootball #FrontTesting</i>"
        ])

        msg = "\n".join(lines)
        return cls.send_message(msg)

    @classmethod
    def send_kickoff_alert(cls, slip: Dict[str, Any]) -> bool:
        """
        Dispatches an in-play alert when a round officially starts, listing matches.
        """
        league = slip.get("league_name", "vFootball")
        code = slip.get("booking_code", "N/A")
        total_odds = slip.get("actual_odds", 2.0)
        round_time = slip.get("round_time_str", "Now")
        selections = slip.get("selections", [])

        lines = [
            f"▶️ <b>[ROUND LIVE / IN-PLAY] {league}</b>",
            f"⏱ <b>Started:</b> <code>{round_time}</code>",
            f"🎫 <b>Ticket Code:</b> <code>{code}</code> (Odds: <b>{total_odds}x</b>)",
            "",
            "📋 <b>Matches In-Play:</b>"
        ]

        for idx, s in enumerate(selections, 1):
            match = s.get("match", "Match")
            pick = s.get("pick", "Pick")
            odds = s.get("odds", "1.00")
            lines.append(f"  {idx}. <b>{match}</b> → <i>{pick}</i> (@ {odds}x)")

        lines.extend([
            "",
            "<i>⚡ Match simulations in progress. Result audit at Full-Time!</i>"
        ])

        msg = "\n".join(lines)
        return cls.send_message(msg)


    @classmethod
    def send_settlement_alert(cls, slip: Dict[str, Any], is_won: bool, stats: Dict[str, Any]) -> bool:
        """
        Dispatches a post-round settlement alert with match scores, leg results,
        and cumulative front-testing performance stats.
        """
        league = slip.get("league_name", "vFootball")
        code = slip.get("booking_code", "N/A")
        total_odds = slip.get("actual_odds", 2.0)
        status_emoji = "✅ <b>[WON]</b>" if is_won else "❌ <b>[LOST]</b>"
        pnl = f"+{round(total_odds - 1.0, 2)}u" if is_won else "-1.00u"

        total_slips = stats.get("total_slips", 0)
        won_count = stats.get("won_slips", 0)
        lost_count = stats.get("lost_slips", 0)
        win_rate = stats.get("win_rate_pct", 0.0)
        net_profit = stats.get("net_profit_units", 0.0)
        selections = slip.get("selections", [])

        lines = [
            f"{status_emoji} <b>vFootball Round Settled ({league})</b>",
            f"🎫 <b>Ticket Code:</b> <code>{code}</code> | <b>Return:</b> <code>{pnl}</code>",
            "",
            "📋 <b>Match Results & Scores:</b>"
        ]

        for idx, s in enumerate(selections, 1):
            match = s.get("match", "Match")
            pick = s.get("pick", "Pick")
            odds = s.get("odds", "1.00")
            score = s.get("final_score")
            score_str = f" [<b>{score}</b>]" if score else ""
            leg_won = s.get("leg_won")
            icon = "✅" if leg_won is True else ("❌" if leg_won is False else "•")
            lines.append(f"  {idx}. <b>{match}</b>{score_str} → <i>{pick}</i> (@ {odds}x) {icon}")

        lines.extend([
            "",
            "📈 <b>Live Front-Test Tracker:</b>",
            f"• Total Dispatches: <b>{total_slips}</b>",
            f"• Record: <b>{won_count}W - {lost_count}L</b>",
            f"• Win Rate: <b>{win_rate}%</b>",
            f"• Net Yield: <b>{net_profit:+.2f} Units</b>",
            "",
            "<i>StatIQ Autonomous Front-Testing Engine</i>"
        ])

        msg = "\n".join(lines)
        return cls.send_message(msg)


    @classmethod
    def send_daily_summary_report(cls, stats: Dict[str, Any]) -> bool:
        """
        Dispatches the 12:00 AM (00:00) Daily Performance Audit Report.
        """
        total_today = stats.get("today_total_slips", 0)
        won_today = stats.get("today_won_slips", 0)
        lost_today = stats.get("today_lost_slips", 0)
        win_rate_today = stats.get("today_win_rate_pct", 0.0)
        net_profit_today = stats.get("today_net_profit_units", 0.0)
        roi_today = stats.get("today_roi_pct", 0.0)

        cum_total = stats.get("total_slips", 0)
        cum_win_rate = stats.get("win_rate_pct", 0.0)
        cum_profit = stats.get("net_profit_units", 0.0)

        lines = [
            "📊 <b>StatIQ vFootball — Daily Midnight Performance Report</b>",
            "📅 <b>Audit Period:</b> <i>24-Hour Cycle (00:00 - 23:59)</i>",
            "",
            "⚡ <b>Today's Front-Testing Results:</b>",
            f"• Slips Dispatched Today: <b>{total_today}</b>",
            f"• Daily Record: <b>{won_today}W - {lost_today}L</b>",
            f"• Daily Win Rate: <b>{win_rate_today}%</b>",
            f"• Daily Net Yield: <b>{net_profit_today:+.2f} Units</b>",
            f"• Daily ROI: <b>{roi_today:+.1f}%</b>",
            "",
            "🏆 <b>Cumulative All-Time Front-Test Stats:</b>",
            f"• Total Slips Evaluated: <b>{cum_total}</b>",
            f"• All-Time Win Rate: <b>{cum_win_rate}%</b>",
            f"• Cumulative Net P&L: <b>{cum_profit:+.2f} Units</b>",
            "",
            "<i>#StatIQ #DailyAudit #vFootball</i>"
        ]

        msg = "\n".join(lines)
        return cls.send_message(msg)
