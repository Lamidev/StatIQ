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
    Executes MatchIQ 5-Gate Pick Engine on live/historical fixture pool.
    Returns built ticket with decision audit logs, confidence tiers, and SportyBet booking code.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    current_weekday = now.weekday()  # Monday=0, Sunday=6

    fixture_pool = []

    if req.custom_fixtures and len(req.custom_fixtures) > 0:
        fixture_pool = [_normalize_fixture_item(f, req.single_league or "PL") for f in req.custom_fixtures]
    else:
        # 1. Fetch live upcoming fixtures from SportyBet API & today's curated schedule
        try:
            from app.services.ticket_reeditor import _fetch_live_replacements_safe
            live_sporty_events = await asyncio.to_thread(_fetch_live_replacements_safe)
        except Exception:
            live_sporty_events = []

        # Curated Weekend & Week Slate across all major accessible leagues
        from app.api.endpoints.fixtures import get_sportybet_today_fixtures
        today_fixtures_data = await get_sportybet_today_fixtures()
        all_today_matches = []
        for lg in today_fixtures_data.get("leagues", []):
            for m in lg.get("matches", []):
                r1x2 = m.get("result_1x2") or {}
                ou = m.get("ou_lines") or []
                dc = m.get("double_chance") or {}
                all_today_matches.append({
                    "eventId": m.get("event_id"),
                    "homeTeamName": m.get("home_team"),
                    "awayTeamName": m.get("away_team"),
                    "tournamentName": lg.get("league"),
                    "categoryName": lg.get("country"),
                    "estimateStartTime": m.get("kickoff_ts") or int(now.timestamp() * 1000),
                    "result_1x2": r1x2,
                    "ou_lines": ou,
                    "double_chance": dc,
                    "markets": [
                        {
                            "desc": "1X2",
                            "outcomes": [
                                {"desc": "Home", "odds": r1x2.get("home", 2.0)},
                                {"desc": "Draw", "odds": r1x2.get("draw", 3.2)},
                                {"desc": "Away", "odds": r1x2.get("away", 3.0)},
                            ]
                        }
                    ]
                })

        # Always load verified SportyBet matches for today (PSV, Porto, Fenerbahce, Al Nassr, Celtic, Udinese, etc.)
        from app.api.endpoints.fixtures import get_sportybet_today_fixtures
        today_fixtures_data = await get_sportybet_today_fixtures()
        real_sporty_matches = []
        for lg in today_fixtures_data.get("leagues", []):
            for m in lg.get("matches", []):
                real_sporty_matches.append({
                    "eventId": m.get("event_id"),
                    "homeTeamName": m.get("home_team"),
                    "awayTeamName": m.get("away_team"),
                    "tournamentName": lg.get("league"),
                    "categoryName": lg.get("country"),
                    "estimateStartTime": m.get("kickoff_ts"),
                    "result_1x2": m.get("result_1x2") or {},
                    "ou_lines": m.get("ou_lines") or [],
                    "double_chance": m.get("double_chance") or {},
                    "matchStatus": m.get("status", "NOT_STARTED"),
                    "is_verified_top_match": True
                })

        combined_feed = real_sporty_matches + (live_sporty_events or [])
        seen_keys = set()
        now_ts_ms = int(now.timestamp() * 1000)

        for ev in combined_feed:
            h = ev.get("homeTeamName") or "Home"
            a = ev.get("awayTeamName") or "Away"
            k = f"{h.lower()}_{a.lower()}"
            if k in seen_keys:
                continue
            seen_keys.add(k)

            comp_name = ev.get("tournamentName") or ev.get("categoryName") or "League"
            start_ms = ev.get("estimateStartTime") or ev.get("kickoff_ts") or ev.get("startTime")

            # Check match status directly from API - Reject any live or finished match
            ev_status = str(ev.get("matchStatus") or ev.get("status") or "").upper()
            if any(s in ev_status for s in ("LIVE", "IN_PROGRESS", "ONGOING", "H1", "H2", "HT", "CONCLUDED", "FINISHED", "FT", "ENDED", "CANCELLED", "POSTPONED")):
                continue

            # STRICT PRE-MATCH: Match MUST start in the future (at least 2 minutes from right now)
            if not start_ms:
                continue

            try:
                ts_sec = (start_ms / 1000.0) if start_ms > 1e11 else float(start_ms)
                dt = datetime.datetime.fromtimestamp(ts_sec, tz=datetime.timezone.utc)
                dt_date = dt.strftime("%Y-%m-%d")
                diff_sec = (dt - now).total_seconds()

                # STRICT: Game MUST NOT have started yet (must be at least 120s in the future)
                if diff_sec < 120:
                    continue

                if req.date_window == "TODAY":
                    if dt_date != today_str and diff_sec > 86400:
                        continue
                elif req.date_window == "NEXT_24H":
                    if diff_sec > 86400:
                        continue
                elif req.date_window == "WEEKEND":
                    if diff_sec > 259200:
                        continue
                elif req.date_window == "NEXT_7D":
                    if diff_sec > 604800:
                        continue
            except Exception:
                continue

            # League Filter
            if req.selected_leagues and len(req.selected_leagues) > 0 and "ALL" not in req.selected_leagues:
                match_league = False
                for sel_lg in req.selected_leagues:
                    # check code or name match
                    if sel_lg.lower() in comp_name.lower() or comp_name.lower() in sel_lg.lower():
                        match_league = True
                        break
                    # Map common short codes
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

            r1x2_ev = ev.get("result_1x2") or {}
            ou_ev = ev.get("ou_lines") or []
            dc_ev = ev.get("double_chance") or {}

            if not r1x2_ev and ev.get("markets"):
                for mkt in ev.get("markets", []):
                    m_desc = (mkt.get("desc") or mkt.get("name") or "").lower()
                    if "1x2" in m_desc or "match result" in m_desc:
                        for out in mkt.get("outcomes", []):
                            o_desc = (out.get("desc") or out.get("name") or "").lower()
                            try:
                                o_val = float(out.get("odds"))
                                if o_desc in ["1", "home", h.lower()]:
                                    r1x2_ev["home"] = o_val
                                elif o_desc in ["x", "draw"]:
                                    r1x2_ev["draw"] = o_val
                                elif o_desc in ["2", "away", a.lower()]:
                                    r1x2_ev["away"] = o_val
                            except (ValueError, TypeError):
                                pass

            fixture_pool.append({
                "fixture_id": str(ev.get("eventId") or ev.get("gameId") or f"{h}_{a}"),
                "game_id": str(ev.get("eventId") or ev.get("gameId") or ""),
                "external_fixture_id": str(ev.get("eventId") or ev.get("gameId") or ""),
                "home_team": h,
                "away_team": a,
                "competition_code": comp_name,
                "kickoff_datetime": ev.get("estimateStartTime"),
                "markets": ev.get("markets", []),
                "result_1x2": r1x2_ev,
                "ou_lines": ou_ev,
                "double_chance": dc_ev,
            })

    # If pool is still empty, fall back to European scheduled fixtures
    if not fixture_pool:
        fallback_leagues = req.selected_leagues if (req.selected_leagues and "ALL" not in req.selected_leagues) else ["PL", "PD", "SA", "BL1", "FL1"]
        results = await asyncio.gather(*[_fetch_fixtures_for_league(lg) for lg in fallback_leagues], return_exceptions=True)
        for lg, raw_matches in zip(fallback_leagues, results):
            if isinstance(raw_matches, list):
                for m in raw_matches:
                    fixture_pool.append(_normalize_fixture_item(m, lg))

    # Determine pick limit
    target_games = req.target_games or 5
    max_picks = target_games if req.target_mode == "GAMES" else 20

    engine = MatchIQPickEngine(use_live_odds=True)
    target_odds_val = req.target_odds if (req.mode.upper() == "ROLLOVER" or req.target_mode == "ODDS") else 999.0
    built_ticket = engine.build_ticket(
        fixture_pool=fixture_pool,
        target_total_odds=target_odds_val,
        mode=req.mode.upper(),
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


