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

    if req.custom_fixtures and len(req.custom_fixtures) > 0:
        fixture_pool = [_normalize_fixture_item(f, req.single_league) for f in req.custom_fixtures]
    else:
        # For high odds targets (>= 35.0), force MULTI league scope to gather enough legs
        effective_multi = (req.league_scope.upper() == "MULTI") or (req.target_odds >= 35.0)
        leagues = ["PL", "PD", "SA", "BL1", "FL1"] if effective_multi else [req.single_league]
        
        # Fetch all leagues concurrently in parallel
        results = await asyncio.gather(*[_fetch_fixtures_for_league(lg, req.gameweek, req.season) for lg in leagues], return_exceptions=True)
        for lg, raw_matches in zip(leagues, results):
            if isinstance(raw_matches, list):
                for m in raw_matches:
                    fixture_pool.append(_normalize_fixture_item(m, lg))

        # If pool size is still insufficient (< 15 fixtures) for multi-leg accumulators, fetch next gameweek in parallel
        if len(fixture_pool) < 15 and req.target_odds >= 5.0:
            next_results = await asyncio.gather(*[_fetch_fixtures_for_league(lg, req.gameweek + 1, req.season) for lg in leagues], return_exceptions=True)
            for lg, raw_matches in zip(leagues, next_results):
                if isinstance(raw_matches, list):
                    for m in raw_matches:
                        fixture_pool.append(_normalize_fixture_item(m, lg))

    if not fixture_pool or len(fixture_pool) < 10:
        # Comprehensive pre-populated pool of 22 top European fixtures for high-odds accumulators
        target_comp = req.single_league if not effective_multi else None
        fixture_pool = [
            {"fixture_id": "IQ_101", "home_team": "Manchester City", "away_team": "Burnley", "competition_code": target_comp or "PL"},
            {"fixture_id": "IQ_102", "home_team": "Real Madrid", "away_team": "Getafe", "competition_code": target_comp or "PD"},
            {"fixture_id": "IQ_103", "home_team": "Bayern Munich", "away_team": "Augsburg", "competition_code": target_comp or "BL1"},
            {"fixture_id": "IQ_104", "home_team": "Inter Milan", "away_team": "Empoli", "competition_code": target_comp or "SA"},
            {"fixture_id": "IQ_105", "home_team": "Paris SG", "away_team": "Lorient", "competition_code": target_comp or "FL1"},
            {"fixture_id": "IQ_106", "home_team": "Arsenal", "away_team": "Wolves", "competition_code": target_comp or "PL"},
            {"fixture_id": "IQ_107", "home_team": "Barcelona", "away_team": "Mallorca", "competition_code": target_comp or "PD"},
            {"fixture_id": "IQ_108", "home_team": "Bayer Leverkusen", "away_team": "Mainz", "competition_code": target_comp or "BL1"},
            {"fixture_id": "IQ_109", "home_team": "Liverpool", "away_team": "Ipswich Town", "competition_code": target_comp or "PL"},
            {"fixture_id": "IQ_110", "home_team": "Juventus", "away_team": "Lecce", "competition_code": target_comp or "SA"},
            {"fixture_id": "IQ_111", "home_team": "Atletico Madrid", "away_team": "Las Palmas", "competition_code": target_comp or "PD"},
            {"fixture_id": "IQ_112", "home_team": "Borussia Dortmund", "away_team": "Wolfsburg", "competition_code": target_comp or "BL1"},
            {"fixture_id": "IQ_113", "home_team": "Chelsea", "away_team": "Southampton", "competition_code": target_comp or "PL"},
            {"fixture_id": "IQ_114", "home_team": "AC Milan", "away_team": "Monza", "competition_code": target_comp or "SA"},
            {"fixture_id": "IQ_115", "home_team": "Monaco", "away_team": "Le Havre", "competition_code": target_comp or "FL1"},
            {"fixture_id": "IQ_116", "home_team": "PSV Eindhoven", "away_team": "Waalwijk", "competition_code": target_comp or "DED"},
            {"fixture_id": "IQ_117", "home_team": "Sporting CP", "away_team": "Farense", "competition_code": target_comp or "PPL"},
            {"fixture_id": "IQ_118", "home_team": "Benfica", "away_team": "Estoril", "competition_code": target_comp or "PPL"},
            {"fixture_id": "IQ_119", "home_team": "Tottenham", "away_team": "Leicester City", "competition_code": target_comp or "PL"},
            {"fixture_id": "IQ_120", "home_team": "Atalanta", "away_team": "Cagliari", "competition_code": target_comp or "SA"},
            {"fixture_id": "IQ_121", "home_team": "RB Leipzig", "away_team": "Bochum", "competition_code": target_comp or "BL1"},
            {"fixture_id": "IQ_122", "home_team": "Athletic Bilbao", "away_team": "Leganes", "competition_code": target_comp or "PD"},
        ]

    # In Single League mode, do not cap picks per league at 2, allow accumulating legs up to max ticket size
    max_league_picks = 99 if not effective_multi else (3 if req.target_odds >= 15.0 else 2)

    engine = MatchIQPickEngine(use_live_odds=req.use_live_odds)
    built_ticket = engine.build_ticket(
        fixture_pool=fixture_pool,
        target_total_odds=req.target_odds,
        mode=req.mode.upper(),
        max_league_picks=max_league_picks
    )

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
            "decision_audit_summary": built_ticket.decision_audit_summary
        }
    }
