"""
MatchIQ AI Ticket & Rollover Builder API Endpoint
===================================================
Uses MatchIQPickEngine 5-Gate Pipeline to evaluate live/historical fixture pools
and build high-confidence accumulator tickets or multi-day rollover strategies.
"""

import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.pick_engine import MatchIQPickEngine
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger("matchiq.ticket_builder")

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

class BuildTicketRequest(BaseModel):
    target_odds: float = 5.0
    mode: str = "ACCUMULATOR"  # "ACCUMULATOR" or "ROLLOVER"
    league_scope: str = "MULTI"  # "MULTI" or "SINGLE"
    single_league: str = "PL"
    gameweek: int = 1
    season: Optional[int] = None
    use_live_odds: bool = False
    custom_fixtures: Optional[List[Dict[str, Any]]] = None
    reshuffle_seed: Optional[int] = None
    kickoff_scope: Optional[str] = "TODAY"  # "TODAY", "NEXT_24H", "ALL"

async def _fetch_fixtures_for_league(comp: str, matchday: int, season: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetches fixtures from football-data.org with intelligent season fallback (2026 -> 2025).
    """
    target_season = season if season is not None else 2026
    headers = {
        "X-Auth-Token": settings.FOOTBALL_DATA_API_KEY,
        "User-Agent": "MatchIQ-Engine/1.0",
    }
    url = f"{FOOTBALL_DATA_BASE}/competitions/{comp}/matches"
    params = {"matchday": matchday, "season": target_season}

    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                matches = resp.json().get("matches", [])
                if matches:
                    return matches
            # Fall back to 2025 if 2026 returned empty or 404 (e.g. pre-season)
            if target_season == 2026:
                params["season"] = 2025
                resp2 = await client.get(url, headers=headers, params=params)
                if resp2.status_code == 200:
                    return resp2.json().get("matches", [])
        except Exception as e:
            logger.warning(f"Failed to fetch live fixtures for {comp} GW{matchday}: {e}")
    return []

def _normalize_fixture_item(m: Dict[str, Any], default_comp: str) -> Dict[str, Any]:
    home = m.get("homeTeam", {}).get("name") or m.get("home_team") or "Home"
    away = m.get("awayTeam", {}).get("name") or m.get("away_team") or "Away"
    return {
        "fixture_id": str(m.get("id") or m.get("fixture_id") or f"{home}_{away}"),
        "home_team": home,
        "away_team": away,
        "competition_code": m.get("competition", {}).get("code") or m.get("competition_code") or default_comp,
        "kickoff_datetime": m.get("utcDate") or m.get("kickoff_datetime"),
        "ai_prob_home": m.get("ai_prob_home"),
        "ai_prob_draw": m.get("ai_prob_draw"),
        "ai_prob_away": m.get("ai_prob_away"),
        "ai_prob_over_1_5": m.get("ai_prob_over_1_5"),
        "ai_prob_over_2_5": m.get("ai_prob_over_2_5"),
    }

@router.post("/build")
async def build_ai_ticket(req: BuildTicketRequest):
    """
    Executes MatchIQ 5-Gate Pick Engine on live/historical fixture pool.
    Returns built ticket with decision audit logs, confidence tiers, and fractional Kelly stake sizing.
    """
    if req.target_odds < 1.10:
        raise HTTPException(status_code=400, detail="Target odds must be at least 1.10")

    fixture_pool = []
    effective_multi = (req.league_scope.upper() == "MULTI") or (req.target_odds >= 35.0)

    if req.custom_fixtures and len(req.custom_fixtures) > 0:
        fixture_pool = [_normalize_fixture_item(f, req.single_league) for f in req.custom_fixtures]
    else:
        # 1. PRIMARY SOURCE: Fetch live upcoming fixtures directly from SportyBet API
        # Guarantees 24/7/365 availability of real games currently active on SportyBet today.
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        from app.services.ticket_reeditor import _fetch_live_replacements_safe
        live_sporty_events = await asyncio.to_thread(_fetch_live_replacements_safe)
        if live_sporty_events and len(live_sporty_events) > 0:
            sporty_pool = []
            for ev in live_sporty_events:
                h = ev.get("homeTeamName") or "Home"
                a = ev.get("awayTeamName") or "Away"
                start_ms = ev.get("estimateStartTime")

                # Filter by kickoff_scope (TODAY, NEXT_24H, ALL)
                if start_ms:
                    try:
                        ts_sec = (start_ms / 1000.0) if start_ms > 1e11 else float(start_ms)
                        dt = datetime.datetime.fromtimestamp(ts_sec, tz=datetime.timezone.utc)
                        dt_date = dt.strftime("%Y-%m-%d")
                        diff_sec = (dt - now).total_seconds()

                        # Skip matches that ended in the past (more than 2 hours ago)
                        if diff_sec < -7200:
                            continue

                        if req.kickoff_scope == "TODAY":
                            # Strictly enforce that kickoff date matches today's date
                            if dt_date != today_str and diff_sec > 86400:
                                continue
                        elif req.kickoff_scope == "NEXT_24H":
                            if diff_sec > 86400:
                                continue
                    except Exception:
                        pass

                comp_name = ev.get("tournamentName") or ev.get("categoryName") or f"League_{len(sporty_pool)+1}"
                sporty_pool.append({
                    "fixture_id": str(ev.get("eventId") or f"{h}_{a}"),
                    "home_team": h,
                    "away_team": a,
                    "competition_code": comp_name,
                    "kickoff_datetime": ev.get("estimateStartTime"),
                    "markets": ev.get("markets", []),
                })
            if sporty_pool and len(sporty_pool) >= 4:
                fixture_pool = sporty_pool

        # 2. SECONDARY FALLBACK: Fetch from football-data.org if SportyBet feed returned empty
        if not fixture_pool or len(fixture_pool) < 4:
            leagues = ["PL", "PD", "SA", "BL1", "FL1"] if effective_multi else [req.single_league]
            results = await asyncio.gather(*[_fetch_fixtures_for_league(lg, req.gameweek, req.season) for lg in leagues], return_exceptions=True)
            for lg, raw_matches in zip(leagues, results):
                if isinstance(raw_matches, list):
                    for m in raw_matches:
                        fixture_pool.append(_normalize_fixture_item(m, lg))

    # Allow accumulating legs up to max ticket size requested by user (e.g. 5, 10, 15 games)
    max_league_picks = 99 if not effective_multi else max(5, int(getattr(req, 'target_games', 10)))

    use_live = req.use_live_odds or (bool(fixture_pool) and "markets" in (fixture_pool[0] if fixture_pool else {}))
    engine = MatchIQPickEngine(use_live_odds=use_live)
    built_ticket = engine.build_ticket(
        fixture_pool=fixture_pool,
        target_total_odds=req.target_odds,
        mode=req.mode.upper(),
        max_league_picks=max_league_picks,
        reshuffle_seed=req.reshuffle_seed
    )

    booking_code = None
    share_url = None
    verification_status = None
    reconciliation_summary = None

    if built_ticket.approved_legs:
        try:
            from app.services.sportybet_reconciliation import SportyBetVerificationEngine
            ver_engine = SportyBetVerificationEngine(db)
            ver_res = await ver_engine.generate_verified_booking(
                statiq_ticket_id="AI-TKT-BUILD",
                selections=built_ticket.approved_legs,
                region="ng"
            )
            if ver_res.get("status") == "VERIFIED":
                booking_code = ver_res.get("booking_code")
                share_url = ver_res.get("share_url")
                verification_status = ver_res.get("status")
                reconciliation_summary = ver_res.get("reconciliation_summary")
        except Exception as e:
            logger.warning(f"Auto verified booking generation error in AI ticket builder: {e}")

    return {
        "status": "SUCCESS",
        "ticket": {
            "mode": built_ticket.mode,
            "target_odds": built_ticket.target_odds,
            "accumulated_odds": built_ticket.accumulated_odds,
            "combined_probability": built_ticket.combined_probability,
            "correlation_adjusted_probability": built_ticket.correlation_adjusted_probability,
            "confidence_tier": built_ticket.confidence_tier,
            "recommended_stake_pct": built_ticket.recommended_stake_pct,
            "leg_config": built_ticket.leg_config,
            "approved_legs": built_ticket.approved_legs,
            "rejected_picks": built_ticket.rejected_picks,
            "total_evaluated": built_ticket.total_evaluated,
            "decision_audit_summary": built_ticket.decision_audit_summary,
            "booking_code": booking_code,
            "share_url": share_url,
            "verification_status": verification_status,
            "reconciliation_summary": reconciliation_summary
        }
    }

