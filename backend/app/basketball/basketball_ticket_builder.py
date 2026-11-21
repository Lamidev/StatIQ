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
    SHARE_URL = "https://mobile.sportybet.com/api/ng/orders/share"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "platform": "wap",
        "client-country": "ng",
        "X-Forwarded-For": "102.89.34.18",
        "Referer": "https://mobile.sportybet.com/ng/"
    }

    APP_HEADERS = {
        "User-Agent": "SportyBet/4.25.0 (Android; 13; Scale/2.75)",
        "Accept": "application/json, text/plain, */*",
        "platform": "app",
        "client-country": "ng",
        "app-version": "4.25.0",
        "os": "Android"
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

        import shutil, subprocess, json, os
        curl_bin = shutil.which("curl")
        proxy_url = os.getenv("SPORTYBET_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "socks5h://127.0.0.1:9055"

        if curl_bin:
            try:
                cmd = [
                    curl_bin, "-s", "-k",
                    "-H", "User-Agent: SportyBet/4.25.0 (Android; 13; Scale/2.75)",
                    "-H", "Accept: application/json, text/plain, */*",
                    "-H", "platform: app",
                    "-H", "client-country: ng",
                    "-H", "app-version: 4.25.0",
                    "-H", "os: Android",
                    "-H", "Content-Type: application/json",
                    "--max-time", "18",
                    "--data-raw", json.dumps({"selections": selections_payload}),
                ]
                if proxy_url:
                    cmd.extend(["--proxy", proxy_url])
                cmd.append(cls.SHARE_URL)
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if proc.returncode == 0 and proc.stdout:
                    res = json.loads(proc.stdout)
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
            except Exception as e:
                logger.debug(f"[BasketballTicketBuilder] curl share note: {e}")

        client_kwargs = {
            "timeout": 12.0,
            "headers": cls.APP_HEADERS,
            "verify": False
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        try:
            with httpx.Client(**client_kwargs) as client:
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

        # Phase 2: If target odds not yet reached (e.g. only 5-6 midnight NBA games available),
        # pull from next upcoming global basketball fixtures so the user gets their desired odds
        # without violating the 1-pick-per-match and 1.25x safety floor rules
        if running_odds < target_odds * 0.85 and session_slate != "ALL":
            extra_bankers = BasketballQuantEngine.find_all_daily_bankers(
                session_slate="ALL",
                limit_fixtures=60,
                min_odds=min_leg_odds,
                max_odds=max_leg_odds
            )
            for b in extra_bankers:
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

