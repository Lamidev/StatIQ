"""
Basketball Ticket Builder Engine for StatIQ.
Builds the daily 2.0x 3-Leg Banker Cushion Slip, enforces Zero-Overlap across fixtures,
and books tickets on SportyBet to generate live booking codes and preload links.
"""
import time
import logging
from typing import Dict, Any, List, Optional
import httpx

from app.basketball.basketball_quant_engine import BasketballQuantEngine

logger = logging.getLogger("statiq.basketball.builder")

class BasketballTicketBuilder:
    SHARE_URL = "https://www.sportybet.com/api/ng/orders/share"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sportybet.com/ng/",
        "Origin": "https://www.sportybet.com"
    }

    @classmethod
    def book_on_sportybet(cls, picks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Dispatches selected basketball legs to SportyBet's orders/share endpoint
        to create an authoritative booking code.
        """
        selections_payload = []
        for p in picks:
            eid = p.get("event_id")
            m_id = str(p.get("market_id") or "225")
            o_id = str(p.get("outcome_id") or "12")
            spec = str(p.get("specifier") or "")

            item = {
                "eventId": eid,
                "marketId": m_id,
                "outcomeId": o_id
            }
            if spec:
                item["specifier"] = spec
            selections_payload.append(item)

        if not selections_payload:
            return {"status": "FAILED", "booking_code": "N/A", "message": "No valid picks to book."}

        try:
            with httpx.Client(timeout=8.0, headers=cls.HEADERS, verify=False) as client:
                r = client.post(cls.SHARE_URL, json={"selections": selections_payload})
                if r.status_code == 200:
                    res = r.json()
                    if res.get("bizCode") == 10000:
                        data = res.get("data", {})
                        code = data.get("shareCode")
                        load_url = data.get("shareURL") or f"https://www.sportybet.com/ng/?shareCode={code}"
                        return {
                            "status": "SUCCESS",
                            "booking_code": code,
                            "share_url": load_url,
                            "raw_response": data
                        }
                    else:
                        logger.warning(f"[BasketballTicketBuilder] SportyBet booking error: {res.get('message')}")
        except Exception as e:
            logger.error(f"[BasketballTicketBuilder] Network error booking basketball slip: {e}")

        return {"status": "FAILED", "booking_code": "N/A", "message": "Could not connect to SportyBet API."}

    @classmethod
    def build_daily_2x_cushion_slip(
        cls,
        session_slate: str = "ALL",
        min_leg_odds: float = 1.23,
        max_leg_odds: float = 1.28,
        target_legs: int = 3
    ) -> Dict[str, Any]:
        """
        Builds the premier 3-Leg Banker Cushion Slip targeting ~2.00x total odds.
        Strictly enforces 1 pick per distinct match, prioritizing Full-Time Cushion Overs.
        """
        # Scan daily bankers
        bankers = BasketballQuantEngine.find_all_daily_bankers(
            session_slate=session_slate,
            limit_fixtures=40,
            min_odds=min_leg_odds,
            max_odds=max_leg_odds
        )

        # Fallback expansion if line availability in strict 1.23-1.28 corridor is lean
        if len(bankers) < target_legs:
            logger.info("[BasketballTicketBuilder] Expanding corridor to 1.20 - 1.30 to fulfill 3 banker legs.")
            bankers = BasketballQuantEngine.find_all_daily_bankers(
                session_slate=session_slate,
                limit_fixtures=40,
                min_odds=1.20,
                max_odds=1.30
            )

        # Group by match/event_id to guarantee zero match overlap
        selected_picks: List[Dict[str, Any]] = []
        seen_events = set()

        for b in bankers:
            eid = b.get("event_id")
            if eid in seen_events:
                continue
            seen_events.add(eid)
            selected_picks.append(b)
            if len(selected_picks) == target_legs:
                break

        if len(selected_picks) < target_legs:
            return {
                "status": "INSUFFICIENT_MATCHES",
                "message": f"Found {len(selected_picks)} vetted basketball banker legs, need {target_legs}. Waiting for liquid markets.",
                "picks": selected_picks,
                "booking_code": None
            }

        # Calculate combined multiplier
        actual_odds = 1.0
        combined_prob = 1.0
        for p in selected_picks:
            odd = float(p.get("odds", 1.25))
            actual_odds *= odd
            combined_prob *= (p.get("confidence_score", 88.0) / 100.0)

        actual_odds = round(actual_odds, 2)
        combined_confidence = round(combined_prob * 100.0, 1)

        # Book slip directly on SportyBet
        book_res = cls.book_on_sportybet(selected_picks)
        booking_code = book_res.get("booking_code") or "N/A"
        share_url = book_res.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={booking_code}"

        return {
            "status": "SUCCESS",
            "title": "🎯 StatIQ Daily 2.0x Basketball Cushion Slip",
            "date_str": time.strftime("%Y-%m-%d"),
            "target_odds": 2.00,
            "actual_odds": actual_odds,
            "leg_count": len(selected_picks),
            "session_slate": session_slate,
            "combined_confidence": combined_confidence,
            "booking_code": booking_code,
            "share_url": share_url,
            "picks": selected_picks,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    @classmethod
    def build_accumulator_slip(
        cls,
        target_odds: float = 10.0,
        session_slate: str = "ALL",
        min_leg_odds: float = 1.22,
        max_leg_odds: float = 1.35,
        max_legs: int = 20
    ) -> Dict[str, Any]:
        """
        Builds a multi-leg accumulator ticket (5x, 10x, 20x odds, etc.)
        using a vetted mix of varieties: Full-Time Cushion Overs, Cushion Unders,
        Team Totals, 1st Half/1st Quarter Totals, and Heavy Favorites Moneyline.
        Strictly enforces 1 selection per match (Zero Match Overlap).
        """
        bankers = BasketballQuantEngine.find_all_daily_bankers(
            session_slate=session_slate,
            limit_fixtures=60,
            min_odds=min_leg_odds,
            max_odds=max_leg_odds
        )

        if len(bankers) < 4:
            bankers = BasketballQuantEngine.find_all_daily_bankers(
                session_slate=session_slate,
                limit_fixtures=60,
                min_odds=1.18,
                max_odds=1.45
            )

        selected_picks: List[Dict[str, Any]] = []
        seen_events = set()
        running_odds = 1.0
        running_prob = 1.0
        variety_tally: Dict[str, int] = {}

        for b in bankers:
            eid = b.get("event_id")
            if eid in seen_events:
                continue

            odd = float(b.get("odds", 1.25))
            if running_odds * odd > target_odds * 1.35 and len(selected_picks) >= 3:
                continue

            seen_events.add(eid)
            selected_picks.append(b)
            running_odds *= odd
            running_prob *= (b.get("confidence_score", 85.0) / 100.0)

            m_type = b.get("market_type", "OTHER")
            variety_tally[m_type] = variety_tally.get(m_type, 0) + 1

            if running_odds >= target_odds or len(selected_picks) >= max_legs:
                break

        if not selected_picks:
            return {
                "status": "INSUFFICIENT_MATCHES",
                "message": f"Unable to assemble basketball accumulator for {target_odds}x odds. Markets currently lean.",
                "picks": [],
                "booking_code": None
            }

        actual_odds = round(running_odds, 2)
        combined_confidence = round(running_prob * 100.0, 1)

        # Book slip directly on SportyBet
        book_res = cls.book_on_sportybet(selected_picks)
        booking_code = book_res.get("booking_code") or "N/A"
        share_url = book_res.get("share_url") or f"https://www.sportybet.com/ng/?shareCode={booking_code}"

        return {
            "status": "SUCCESS",
            "title": f"🏀 StatIQ {actual_odds:.1f}x Basketball Multiplier Accumulator",
            "date_str": time.strftime("%Y-%m-%d"),
            "target_odds": target_odds,
            "actual_odds": actual_odds,
            "leg_count": len(selected_picks),
            "session_slate": session_slate,
            "combined_confidence": combined_confidence,
            "varieties_breakdown": variety_tally,
            "booking_code": booking_code,
            "share_url": share_url,
            "picks": selected_picks,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

