"""
MatchIQ AI Ticket & Rollover Builder API Endpoint
===================================================
Uses MatchIQPickEngine 5-Gate Pipeline to evaluate live/historical fixture pools
and build high-confidence accumulator tickets or multi-day rollover strategies.
"""

import httpx
import asyncio
import logging
import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.pick_engine import MatchIQPickEngine
from app.services.sportybet_ingestion import SportyBetIngestionService
from app.services.prediction_gate_service import PredictionGateService
from app.core.config import settings


router = APIRouter()
logger = logging.getLogger("matchiq.ticket_builder")

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

class BuildTicketRequest(BaseModel):
    target_odds: float = 5.0
    target_games: Optional[int] = None
    target_mode: str = "ODDS"  # "ODDS" or "GAMES"
    mode: str = "ACCUMULATOR"  # "ACCUMULATOR" or "ROLLOVER"
    selected_leagues: Optional[List[str]] = None  # e.g. ["PL", "PD", "SA", "BL1", "FL1", "ELC", "DED", "PPL"]
    league_scope: Optional[str] = "MULTI"
    single_league: Optional[str] = "PL"
    date_window: Optional[str] = "TODAY"  # "TODAY", "NEXT_24H", "WEEKEND", "NEXT_7D"
    flex_cut: Optional[int] = 0  # 0 = Straight, 1 = Cut 1, 2 = Cut 2
    use_live_odds: bool = True
    custom_fixtures: Optional[List[Dict[str, Any]]] = None
    reshuffle_seed: Optional[int] = None

async def _fetch_fixtures_for_league(comp: str, season: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetches upcoming fixtures for a league from football-data.org.
    """
    target_season = season if season is not None else 2026
    headers = {
        "X-Auth-Token": settings.FOOTBALL_DATA_API_KEY,
        "User-Agent": "MatchIQ-Engine/1.0",
    }
    url = f"{FOOTBALL_DATA_BASE}/competitions/{comp}/matches"
    params = {"status": "SCHEDULED", "season": target_season}

    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                matches = resp.json().get("matches", [])
                if matches:
                    return matches
            if target_season == 2026:
                params["season"] = 2025
                resp2 = await client.get(url, headers=headers, params=params)
                if resp2.status_code == 200:
                    return resp2.json().get("matches", [])
        except Exception as e:
            logger.warning(f"Failed to fetch live fixtures for {comp}: {e}")
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
    Executes StatIQ V2.0 7-Gate Pick Engine on native SportyBet live fixture pool.
    Returns built ticket with decision audit logs, confidence tiers, and verified SportyBet booking code.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    fixture_pool = []

    if req.custom_fixtures and len(req.custom_fixtures) > 0:
        fixture_pool = [_normalize_fixture_item(f, req.single_league or "PL") for f in req.custom_fixtures]
    else:
        # 1. Fetch live upcoming fixtures directly from SportyBet API
        raw_sporty_fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=250)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        today_date = now_utc.date()

        for ev in raw_sporty_fixtures:
            h = ev.get("home_team") or "Home"
            a = ev.get("away_team") or "Away"
            comp_name = ev.get("competition") or ev.get("country") or "Football"
            start_ms = ev.get("start_time_ms") or 0

            # 1. Strict Date Window Filter (Default is TODAY - only matches playing today)
            if start_ms > 0:
                match_dt = datetime.datetime.fromtimestamp(start_ms / 1000.0, tz=datetime.timezone.utc)
                win = (req.date_window or "TODAY").upper()
                if win in ("TODAY", "TODAYS_GAMES", "TODAY_ONLY", "DAILY", ""):
                    if match_dt.date() != today_date:
                        continue
                elif win == "TOMORROW":
                    if (match_dt.date() - today_date).days != 1:
                        continue
                elif win == "WEEKEND":
                    if match_dt.weekday() not in (4, 5, 6):
                        continue

            # 2. League Filter if user selected specific leagues
            if req.selected_leagues and len(req.selected_leagues) > 0 and "ALL" not in req.selected_leagues and "ALL TOP LEAGUES" not in [x.upper() for x in req.selected_leagues]:
                match_league = False
                for sel_lg in req.selected_leagues:
                    if sel_lg.lower() in comp_name.lower() or comp_name.lower() in sel_lg.lower():
                        match_league = True
                        break
                    CODE_MAP = {
                        "PL": "Premier League",
                        "PD": "LaLiga",
                        "SA": "Serie A",
                        "BL1": "Bundesliga",
                        "FL1": "Ligue 1",
                        "ELC": "Championship",
                        "DED": "Eredivisie",
                        "PPL": "Liga Portugal",
                    }
                    mapped_name = CODE_MAP.get(sel_lg.upper(), "")
                    if mapped_name and mapped_name.lower() in comp_name.lower():
                        match_league = True
                        break
                if not match_league:
                    continue

            r1x2_ev = {
                "home": ev.get("odds_home", 2.0),
                "draw": ev.get("odds_draw", 3.2),
                "away": ev.get("odds_away", 3.0)
            }

            fixture_pool.append({
                "fixture_id": ev.get("event_id"),
                "event_id": ev.get("event_id"),
                "game_id": ev.get("game_id"),
                "provider_event_id": ev.get("event_id"),
                "external_fixture_id": ev.get("event_id"),
                "home_team": h,
                "away_team": a,
                "competition_code": comp_name,
                "kickoff_datetime": ev.get("kickoff_time") or (match_dt.strftime("%Y-%m-%d %H:%M:%S") if start_ms > 0 else today_str),
                "start_time_ms": start_ms,
                "markets": ev.get("markets", {}),
                "result_1x2": r1x2_ev,
                "ou_lines": [],
                "double_chance": {},
            })


    # Fallback to general upcoming if league filter was too restrictive
    if not fixture_pool:
        raw_sporty_fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=100)
        for ev in raw_sporty_fixtures:
            start_ms = ev.get("start_time_ms") or 0
            if start_ms > 0:
                match_dt = datetime.datetime.fromtimestamp(start_ms / 1000.0, tz=datetime.timezone.utc)
                if (req.date_window or "TODAY").upper() in ("TODAY", "TODAYS_GAMES", "TODAY_ONLY", "DAILY", ""):
                    if match_dt.date() != today_date:
                        continue

            fixture_pool.append({
                "fixture_id": ev.get("event_id"),
                "event_id": ev.get("event_id"),
                "game_id": ev.get("game_id"),
                "provider_event_id": ev.get("event_id"),
                "external_fixture_id": ev.get("event_id"),
                "home_team": ev.get("home_team"),
                "away_team": ev.get("away_team"),
                "competition_code": ev.get("competition") or "Football",
                "kickoff_datetime": ev.get("kickoff_time") or today_str,
                "start_time_ms": start_ms,
                "markets": ev.get("markets", {}),
                "result_1x2": {
                    "home": ev.get("odds_home", 2.0),
                    "draw": ev.get("odds_draw", 3.2),
                    "away": ev.get("odds_away", 3.0)
                },
                "ou_lines": [],
                "double_chance": {},
            })



    # Determine pick limit
    target_games = req.target_games or 5
    max_picks = max(4, (target_games // 2) + 2) if req.target_mode == "GAMES" else 20

    engine = MatchIQPickEngine(use_live_odds=True)
    target_odds_val = req.target_odds if (req.mode.upper() == "ROLLOVER" or req.target_mode == "ODDS") else 999.0
    built_ticket = engine.build_ticket(
        fixture_pool=fixture_pool,
        target_total_odds=target_odds_val,
        mode=req.mode.upper(),
        target_mode=req.target_mode,
        target_games=target_games,
        max_league_picks=max_picks,
        reshuffle_seed=req.reshuffle_seed
    )

    # Trim to exact target_games if in GAMES mode
    if req.target_mode == "GAMES" and len(built_ticket.approved_legs) > target_games:
        built_ticket.approved_legs = built_ticket.approved_legs[:target_games]
        # recalculate accumulated odds
        acc = 1.0
        for leg in built_ticket.approved_legs:
            acc *= float(leg.get("odds", 1.5))
        built_ticket.accumulated_odds = round(acc, 2)


    # Generate genuine SportyBet booking code via SportyBet direct adapter
    booking_code = None
    share_url = None

    if built_ticket.approved_legs:
        try:
            from app.adapters.bookmaker_adapter import SportyBetAdapter
            adapter = SportyBetAdapter()
            code_res = adapter.generate_booking_code(built_ticket.approved_legs, country_code="ng")
            if code_res.get("status") == "SUCCESS" and code_res.get("booking_code"):
                booking_code = code_res.get("booking_code")
                share_url = code_res.get("load_url")
        except Exception as e:
            logger.warning(f"SportyBet booking code generation error: {e}")

    return {
        "status": "SUCCESS",
        "ticket": {
            "mode": built_ticket.mode,
            "target_mode": req.target_mode,
            "target_odds": req.target_odds,
            "target_games": target_games,
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
            "share_url": share_url or (f"https://www.sportybet.com/ng/?shareCode={booking_code}" if booking_code else None),
            "flex_cut": req.flex_cut,
            "date_window": req.date_window,
        }
    }


