import math
import logging
import asyncio
from typing import Dict, Any, List, Optional
import httpx

from app.services.goal_kicks_service import goal_kicks_service
from app.services.offsides_service import offsides_service
from app.services.time_horizon_service import TimeHorizonService

logger = logging.getLogger("statiq.hybrid_props")

class HybridPropsService:
    """
    StatIQ Tactical Hybrid Props Engine.
    
    Dynamically blends Goal Kicks Under Cushions (High Odds: 1.35x–1.75x) 
    with Offsides Over 1.5 Bankers (High Safety: 1.12x–1.30x) to reach ANY target odds
    with the minimum possible number of legs (typically 4–6 matches total).
    
    Solves the bookmaker bottleneck:
    - Overcomes limited Goal Kick availability by anchoring available matches
    - Bridges the multiplier to the exact target using abundant Offsides
    - Avoids 12+ leg accumulator variance
    """

    BASE_URL = "https://www.sportybet.com/api"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.sportybet.com",
        "Referer": "https://www.sportybet.com/ng/"
    }

    @classmethod
    async def build_hybrid_ticket(
        cls,
        target_odds: float = 10.0,
        time_horizon: str = "TODAY",
        allow_partial: bool = False
    ) -> Dict[str, Any]:
        """
        Builds and books a live SportyBet ticket blending Goal Kicks and Offsides.
        Accepts any user-directed target odds and time horizon.
        """
        target = float(target_odds or 10.0)
        _, _, _, horizon_desc = TimeHorizonService.get_horizon_bounds(time_horizon)

        logger.info(f"[HybridProps] Building hybrid ticket targeting {target:.1f}x ({horizon_desc})...")

        # Concurrently fetch candidate pools from both services
        gk_task = goal_kicks_service.fetch_goal_kicks_candidates(prefer_line="1H", time_horizon=time_horizon)
        offs_task = offsides_service.fetch_offsides_candidates(prefer_line="AUTO", time_horizon=time_horizon)

        gk_candidates, offs_candidates = await asyncio.gather(gk_task, offs_task, return_exceptions=True)

        if not isinstance(gk_candidates, list):
            gk_candidates = []
        if not isinstance(offs_candidates, list):
            offs_candidates = []

        if not gk_candidates and not offs_candidates:
            return {
                "status": "NO_FIXTURES",
                "message": f"No active matches on SportyBet currently offer Goal Kick or Offside props for {horizon_desc}."
            }

        selected_legs: List[Dict[str, Any]] = []
        used_eids = set()
        curr_odds = 1.0

        # Phase 1: Anchor with elite Goal Kicks (high odds multiplier: ~1.40 - 1.70)
        # Take up to 2-4 strong Goal Kick legs to build early multiplier compounding
        for leg in gk_candidates:
            eid = leg.get("event_id")
            if eid in used_eids:
                continue
            odd = float(leg.get("odds") or 1.0)
            if (curr_odds * odd) <= (target * 1.15):
                selected_legs.append(leg)
                used_eids.add(eid)
                curr_odds = round(curr_odds * odd, 2)
                # If we already reached close to target with Goal Kicks alone, stop
                if curr_odds >= (target * 0.90):
                    break

        # Phase 2: Waterfill with high-safety Offsides Over 1.5 bankers (1.12 - 1.30)
        for leg in offs_candidates:
            eid = leg.get("event_id")
            if eid in used_eids:
                continue
            odd = float(leg.get("odds") or 1.0)
            if (curr_odds * odd) <= (target * 1.35):
                selected_legs.append(leg)
                used_eids.add(eid)
                curr_odds = round(curr_odds * odd, 2)
                if curr_odds >= (target * 0.90):
                    break

        # Phase 3: Fine-tuning if still below target
        if curr_odds < (target * 0.85):
            # Check remaining Goal Kicks or Offsides
            pool = [c for c in gk_candidates + offs_candidates if c.get("event_id") not in used_eids]
            pool.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
            for leg in pool:
                eid = leg.get("event_id")
                if eid in used_eids:
                    continue
                odd = float(leg.get("odds") or 1.0)
                selected_legs.append(leg)
                used_eids.add(eid)
                curr_odds = round(curr_odds * odd, 2)
                if curr_odds >= (target * 0.85):
                    break

        if not selected_legs:
            return {
                "status": "FAILED_ASSEMBLY",
                "message": f"Could not assemble Hybrid Prop slip targeting {target:.1f}x odds for {horizon_desc}."
            }

        # User Decision Gate: If available odds fall short of requested target and user hasn't explicitly confirmed partial
        if not allow_partial and curr_odds < (target * 0.85):
            return {
                "status": "INSUFFICIENT_MULTIPLIER",
                "available_odds": curr_odds,
                "target_odds": target,
                "available_count": len(selected_legs),
                "time_horizon": time_horizon,
                "market_type": "hybrid",
                "prefer_line": "AUTO",
                "message": f"Only {len(selected_legs)} matches available on SportyBet ({curr_odds:.2f}x odds), falling short of your {target:.1f}x target."
            }

        # Sort chronologically by start_time so early matches finish first (cashout enablement)
        selected_legs.sort(key=lambda x: x.get("start_time", 0))

        # Request live SportyBet shareCode
        selections_payload = [
            {
                "eventId": leg["event_id"],
                "marketId": leg["market_id"],
                "outcomeId": leg["outcome_id"],
                "specifier": leg["specifier"]
            }
            for leg in selected_legs
        ]

        share_code = None
        share_url = None
        share_endpoint = f"{cls.BASE_URL}/ng/orders/share"

        try:
            async with httpx.AsyncClient(timeout=10.0, headers=cls.HEADERS) as http_c:
                resp = await http_c.post(share_endpoint, json={"selections": selections_payload})
                if resp.status_code == 200:
                    res_data = resp.json()
                    if res_data.get("bizCode") == 10000:
                        share_code = res_data.get("data", {}).get("shareCode")
                        share_url = res_data.get("data", {}).get("shareURL") or f"https://www.sportybet.com/ng/?shareCode={share_code}"
                        logger.info(f"[HybridProps] Generated SportyBet Booking Code: {share_code}")
                    else:
                        logger.warning(f"[HybridProps] SportyBet rejected booking: {res_data}")
        except Exception as e:
            logger.error(f"[HybridProps] Error calling SportyBet share code: {e}")

        gk_count = sum(1 for leg in selected_legs if "Goal Kicks" in leg.get("market_desc", ""))
        offs_count = sum(1 for leg in selected_legs if "Offsides" in leg.get("market_desc", ""))
        total_count = len(selected_legs)
        combined_prob = round(math.prod(leg.get("model_probability", 0.82) for leg in selected_legs) * 100.0, 1)

        scout_analysis = (
            f"⚡ <b>StatIQ Tactical Hybrid Prop Synergy ({horizon_desc}):</b>\n"
            f"• <b>Synergy Blend:</b> {gk_count} Goal Kick Cushions (odds anchor) + {offs_count} Over 1.5 Offsides (safety fill) = {total_count} legs total.\n"
            f"• <b>Low Match Exposure:</b> Reached <b>{curr_odds:.2f}x</b> multiplier with only {total_count} matches instead of a volatile 13-game slip.\n"
            f"• <b>Chronological Stagger:</b> Fixtures ordered chronologically for maximum cashout and re-betting flexibility."
        )

        return {
            "status": "SUCCESS",
            "title": f"⚡ StatIQ {curr_odds:.2f}x Hybrid Props Slip ({horizon_desc})",
            "booking_code": share_code or "N/A",
            "share_url": share_url or f"https://www.sportybet.com/ng/?shareCode={share_code}",
            "target_odds": target,
            "actual_odds": curr_odds,
            "confidence_score": combined_prob,
            "leg_count": total_count,
            "gk_count": gk_count,
            "offs_count": offs_count,
            "picks": selected_legs,
            "scout_analysis": scout_analysis,
            "horizon_desc": horizon_desc
        }

hybrid_props_service = HybridPropsService()

