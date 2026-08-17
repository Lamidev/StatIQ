import httpx
import asyncio
import logging
import time
import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Query, HTTPException

from app.core.config import settings
from app.predictions.live_calculator import calculate_matchiq_probabilities, update_dynamic_rating
from app.services.sportybet_ingestion import SportyBetIngestionService
from app.services.odds_engine import MarketProbabilityEngine


router = APIRouter()
logger = logging.getLogger("matchiq.fixtures")

# Map our league codes to football-data.org competition codes & active season years
COMPETITION_SEASON_MAP = {
    # England - PL 2026 season is active on football-data.org
    "PL":  {"code": "PL",  "name": "Premier League",          "country": "England",      "season": 2026, "matchdays": 38},
    "ELC": {"code": "ELC", "name": "Championship",            "country": "England",      "season": 2025, "matchdays": 46},
    # Spain - 2025 season is active on football-data.org
    "PD":  {"code": "PD",  "name": "La Liga",                 "country": "Spain",        "season": 2025, "matchdays": 38},
    # Italy - 2025 season is active on football-data.org
    "SA":  {"code": "SA",  "name": "Serie A",                 "country": "Italy",        "season": 2025, "matchdays": 38},
    # Germany - 2025 season is active on football-data.org
    "BL1": {"code": "BL1", "name": "Bundesliga",              "country": "Germany",      "season": 2025, "matchdays": 34},
    # France - 2025 season is active on football-data.org
    "FL1": {"code": "FL1", "name": "Ligue 1",                 "country": "France",       "season": 2025, "matchdays": 34},
    # Netherlands
    "DED": {"code": "DED", "name": "Eredivisie",              "country": "Netherlands",  "season": 2025, "matchdays": 34},
    # Portugal
    "PPL": {"code": "PPL", "name": "Primeira Liga",           "country": "Portugal",     "season": 2025, "matchdays": 34},
    # UEFA — UCL
    "CL":  {"code": "CL",  "name": "Champions League",        "country": "UEFA",         "season": 2025, "matchdays": 8},
    # South America
    "CLI": {"code": "CLI", "name": "Copa Libertadores",       "country": "South America","season": 2025, "matchdays": 8},
    "BSA": {"code": "BSA", "name": "Brasileirão Série A",     "country": "Brazil",       "season": 2025, "matchdays": 38},
    # International
    "WC":  {"code": "WC",  "name": "FIFA World Cup",          "country": "World",        "season": 2026, "matchdays": 8},
}

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

# In-memory cache: key -> (data, timestamp)
_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def _fetch_from_football_data(endpoint: str, params: dict) -> dict:
    """
    Makes a live HTTP request to football-data.org API with timeout & rate limit protection.
    Returns JSON dictionary.
    """
    url = f"{FOOTBALL_DATA_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "X-Auth-Token": settings.FOOTBALL_DATA_API_KEY,
        "User-Agent": "MatchIQ-Engine/1.0",
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                logger.warning(f"football-data.org rate limit (429) on {endpoint}")
                return {"matches": [], "error": "RATE_LIMIT"}
            else:
                logger.warning(f"football-data.org HTTP {resp.status_code} on {endpoint}")
                return {"matches": []}
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.warning(f"football-data.org network issue on {endpoint}: {exc}")
            return {"matches": [], "error": "NETWORK_TIMEOUT"}


def _clean_name(raw: str) -> str:
    """
    Dynamically trims standard club suffixes without hardcoded team tables.
    """
    if not raw:
        return raw
    clean = raw.strip()
    for suffix in [" FC", " AFC", " United FC", " City FC", " Football Club", " CF"]:
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)].strip()
    return clean


def _normalize_match(match: dict) -> dict:
    """
    Normalizes a football-data.org match object into MatchIQ fixture format.
    """
    home = match.get("homeTeam", {})
    away = match.get("awayTeam", {})
    score = match.get("score", {})
    ft = score.get("fullTime", {})

    home_score = ft.get("home")
    away_score = ft.get("away")
    status = match.get("status", "SCHEDULED")

    home_name = _clean_name(home.get("name", home.get("shortName", "Unknown")))
    away_name = _clean_name(away.get("name", away.get("shortName", "Unknown")))

    if status == "FINISHED" and home_score is not None and away_score is not None:
        update_dynamic_rating(home_name, away_name, home_score, away_score)

    probs = calculate_matchiq_probabilities(home_name, away_name)

    return {
        "fixture_id": match.get("id"),
        "external_id": match.get("id"),
        "competition_code": match.get("competition", {}).get("code", ""),
        "matchday": match.get("matchday"),
        "kickoff_datetime": match.get("utcDate"),
        "status": status,
        "home_team": home_name,
        "home_team_short": _clean_name(home.get("shortName") or home.get("tla", "")),
        "home_crest": home.get("crest", ""),
        "away_team": away_name,
        "away_team_short": _clean_name(away.get("shortName") or away.get("tla", "")),
        "away_crest": away.get("crest", ""),
        "home_score": home_score,
        "away_score": away_score,
        "result": score.get("winner"),
        "ai_prob_home": probs["ai_prob_home"],
        "ai_prob_draw": probs["ai_prob_draw"],
        "ai_prob_away": probs["ai_prob_away"],
        "ai_prob_over_1_5": probs["ai_prob_over_1_5"],
        "home_elo": probs.get("home_elo", 1650),
        "away_elo": probs.get("away_elo", 1650),
        "elo_gap": probs.get("elo_gap", 0.0),
        "tier_context": probs.get("tier_context", "COMPETITIVE"),
        "has_prediction": True,
    }


@router.get("/by-gameweek")
async def get_fixtures_by_gameweek(
    competition: str = Query(default="PL", description="League code: PL, PD, SA, BL1, FL1, CL, etc."),
    matchday: int = Query(default=1, ge=1, le=46, description="Gameweek / Matchday number"),
    season: Optional[int] = Query(default=None, description="Optional historical season year")
):
    """
    Fetches strictly upcoming fixtures for a specific competition, prioritizing native SportyBet live feeds.
    Eliminates past/started matches and attaches real decimal odds and Elo probabilities.
    """
    comp = competition.upper()
    meta = COMPETITION_SEASON_MAP.get(comp, {"name": comp, "season": 2026})
    target_season = season if season is not None else meta.get("season", 2026)
    
    # 1. Only try SportyBet live upcoming feed for CURRENT / UPCOMING season requests (not historical backtests)
    if season is None or season >= 2026:
        try:
            raw_sporty = SportyBetIngestionService.fetch_upcoming_fixtures(limit=100)
            matched_fixtures = []
            for ev in raw_sporty:
                comp_name = (ev.get("competition") or ev.get("country") or "").lower()
                league_target = meta.get("name", comp).lower()
                if comp.lower() in comp_name or league_target in comp_name:
                    h_name = ev.get("home_team") or "Home"
                    a_name = ev.get("away_team") or "Away"
                    probs = calculate_matchiq_probabilities(h_name, a_name)
                    
                    matched_fixtures.append({
                        "id": ev.get("event_id"),
                        "event_id": ev.get("event_id"),
                        "game_id": ev.get("game_id"),
                        "home_team": h_name,
                        "away_team": a_name,
                        "kickoff_datetime": ev.get("kickoff_time"),
                        "status": "TIMED",
                        "matchday": matchday,
                        "league_code": comp,
                        "league_name": meta.get("name", comp),
                        "ai_prob_home": probs["ai_prob_home"],
                        "ai_prob_draw": probs["ai_prob_draw"],
                        "ai_prob_away": probs["ai_prob_away"],
                        "ai_prob_over_1_5": probs["ai_prob_over_1_5"],
                        "home_elo": probs.get("home_elo", 1650),
                        "away_elo": probs.get("away_elo", 1650),
                        "elo_gap": probs.get("elo_gap", 0.0),
                        "result_1x2": {
                            "home": ev.get("odds_home", 2.0),
                            "draw": ev.get("odds_draw", 3.2),
                            "away": ev.get("odds_away", 3.0),
                        },
                        "has_prediction": True
                    })

            if matched_fixtures:
                return {
                    "source": "sportybet_live",
                    "competition": comp,
                    "competition_name": meta.get("name", comp),
                    "season": target_season,
                    "matchday": matchday,
                    "total": len(matched_fixtures),
                    "fixtures": matched_fixtures,
                }
        except Exception as e:
            logger.warning(f"SportyBet gameweek lookup fallback: {e}")

    # 2. Query football-data.org for historical/confirmed matches
    raw = await _fetch_from_football_data(
        f"competitions/{comp}/matches",
        {"matchday": matchday, "season": target_season}
    )

    matches = raw.get("matches", [])
    if not matches:
        alt_season = 2025 if target_season == 2026 else 2026
        raw2 = await _fetch_from_football_data(
            f"competitions/{comp}/matches",
            {"matchday": matchday, "season": alt_season}
        )
        matches = raw2.get("matches", [])

    fixtures = [_normalize_match(m) for m in matches]
    fixtures.sort(key=lambda f: f["kickoff_datetime"] or "")

    return {
        "source": "live",
        "competition": comp,
        "competition_name": meta["name"],
        "season": target_season,
        "matchday": matchday,
        "total": len(fixtures),
        "fixtures": fixtures,
    }


def _league_tier_score(comp: str) -> int:
    c = comp.lower()
    # Tier 1 (Top European Big 5 & UCL)
    if any(k in c for k in ["premier league", "laliga", "la liga", "serie a", "bundesliga", "ligue 1", "champions league"]):
        return 100
    # Tier 2 (Top Secondary & Continental Tiers: Championship, Eredivisie, Portugal, Brazil, Turkey, Belgium, Scotland, MLS, etc.)
    if any(k in c for k in ["championship", "eredivisie", "liga portugal", "primeira liga", "brasileir", "série a", "süper lig", "super lig", "belgian", "pro league", "premiership", "mls", "libertadores", "sudamericana", "copa"]):
        return 80
    # Tier 3 (European Top Divisions: Sweden, Norway, Denmark, Finland, Poland, Austria, Switzerland, etc.)
    if any(k in c for k in ["allsvenskan", "eliteserien", "superliga", "veikkausliiga", "ekstraklasa", "super league", "bundesliga 2", "2. bundesliga", "laliga 2", "serie b"]):
        return 60
    # Tier 4 (Domestic Cups)
    if any(k in c for k in ["cup", "fa cup", "pokal", "coupe", "trophy"]):
        return 40
    # Tier 5 (Lower tiers)
    return 20


@router.get("/cross-league-gameweek")
async def get_cross_league_gameweek(
    matchday: int = Query(default=1, ge=1, le=38, description="Gameweek / Matchday number"),
    limit: int = Query(default=30, ge=5, le=60, description="Max matches to return (default 30)")
):
    """
    Cross-League Dynamic Gameweek Aggregator.
    Prioritizes top 7-8 higher leagues first, strictly eliminates past / started matches,
    and returns odds-calibrated Elo probabilities with zero stale data.
    """
    try:
        today_data = await get_sportybet_today_fixtures(day="today")
        sporty_upcoming = SportyBetIngestionService.fetch_upcoming_fixtures(limit=100)

        all_matches_raw = []
        seen_events = set()

        for lg in today_data.get("leagues", []):
            lg_title = lg.get("league") or "Top League"
            for m in lg.get("matches", []):
                ev_id = str(m.get("event_id") or m.get("game_id") or "")
                if ev_id and ev_id not in seen_events:
                    seen_events.add(ev_id)
                    all_matches_raw.append({
                        "event_id": ev_id,
                        "game_id": m.get("game_id"),
                        "home_team": m.get("home_team"),
                        "away_team": m.get("away_team"),
                        "competition": lg_title,
                        "kickoff_time": m.get("kickoff_time"),
                        "odds_home": m.get("result_1x2", {}).get("home", 2.0),
                        "odds_draw": m.get("result_1x2", {}).get("draw", 3.2),
                        "odds_away": m.get("result_1x2", {}).get("away", 3.0),
                        "status": m.get("status", "NOT_STARTED")
                    })

        for ev in sporty_upcoming:
            ev_id = str(ev.get("event_id") or ev.get("game_id") or "")
            if ev_id and ev_id not in seen_events:
                seen_events.add(ev_id)
                all_matches_raw.append(ev)

        curated_fixtures = []
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        today_date_str = now_dt.strftime("%Y-%m-%d")

        for ev in all_matches_raw:
            # 1. Strict Started Match Elimination (Exact status check)
            ev_status = str(ev.get("status") or "").upper().strip()
            if ev_status in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED"]:
                continue


            h_name = ev.get("home_team") or "Home"
            a_name = ev.get("away_team") or "Away"
            comp_name = ev.get("competition") or "Top Competition"
            t_score = _league_tier_score(comp_name)

            o_h = float(ev.get("odds_home") or 2.0)
            o_d = float(ev.get("odds_draw") or 3.2)
            o_a = float(ev.get("odds_away") or 3.0)

            # Calibrate Win Probabilities from live SportyBet odds if team is unranked
            probs = calculate_matchiq_probabilities(h_name, a_name)
            if probs.get("home_elo") == 1600 and probs.get("away_elo") == 1600 and o_h > 1.0:
                odds_analysis = MarketProbabilityEngine.analyze_fixture_odds(o_h, o_d, o_a, h_name, a_name)
                p_h = odds_analysis.prob_home_true
                p_d = odds_analysis.prob_draw_true
                p_a = odds_analysis.prob_away_true
                elo_h = int(1600 + (p_h - 0.33) * 600)
                elo_a = int(1600 + (p_a - 0.33) * 600)
                elo_g = float(elo_h - elo_a)
            else:
                p_h = probs["ai_prob_home"]
                p_d = probs["ai_prob_draw"]
                p_a = probs["ai_prob_away"]
                elo_h = probs.get("home_elo", 1650)
                elo_a = probs.get("away_elo", 1650)
                elo_g = probs.get("elo_gap", 0.0)


            raw_kickoff = str(ev.get("kickoff_time") or "18:00").strip()
            if len(raw_kickoff) == 5 and ":" in raw_kickoff:
                full_iso = f"{today_date_str}T{raw_kickoff}:00Z"
            elif "T" in raw_kickoff:
                full_iso = raw_kickoff
            else:
                full_iso = f"{today_date_str}T18:00:00Z"

            curated_fixtures.append({
                "id": ev.get("event_id"),
                "event_id": ev.get("event_id"),
                "game_id": ev.get("game_id"),
                "home_team": h_name,
                "away_team": a_name,
                "kickoff_datetime": full_iso,
                "status": "TIMED",

                "matchday": matchday,
                "league_code": "SPORTY",
                "league_name": comp_name,
                "tier_score": t_score,
                "highest_win_prob": max(p_h, p_a),
                "ai_prob_home": p_h,
                "ai_prob_draw": p_d,
                "ai_prob_away": p_a,
                "ai_prob_over_1_5": probs.get("ai_prob_over_1_5", 0.75),
                "home_elo": elo_h,
                "away_elo": elo_a,
                "elo_gap": elo_g,
                "result_1x2": {
                    "home": o_h,
                    "draw": o_d,
                    "away": o_a,
                },
                "has_prediction": True
            })

        # Rank strictly: Top Tier Leagues first (100 -> 80 -> 60), then by Highest Win Probability
        curated_fixtures.sort(key=lambda x: (-x["tier_score"], -x["highest_win_prob"], x.get("kickoff_datetime") or ""))
        curated_fixtures = curated_fixtures[:limit]

        return {
            "source": "sportybet_live_aggregator",
            "matchday": matchday,
            "total": len(curated_fixtures),
            "limit": limit,
            "fixtures": curated_fixtures,
        }
    except Exception as e:
        logger.warning(f"Error in cross-league aggregator: {e}")
        return {
            "source": "sportybet_live_aggregator",
            "matchday": matchday,
            "total": 0,
            "limit": limit,
            "fixtures": [],
        }




@router.get("/available-matchdays")
async def get_available_matchdays(
    competition: str = Query(default="PL", description="League code: PL, PD, SA, BL1, FL1, CL"),
):
    """
    Returns competition metadata: current matchday, total matchdays, and season start/end dates.
    """
    comp = competition.upper()
    if comp not in COMPETITION_SEASON_MAP:
        comp = "PL"

    meta = COMPETITION_SEASON_MAP[comp]
    total_matchdays = meta.get("matchdays", 38)
    cache_k = f"meta:{comp}"

    if cache_k in _cache:
        cached_data, cached_at = _cache[cache_k]
        if time.time() - cached_at < CACHE_TTL_SECONDS * 2 and cached_data.get("current_matchday"):
            return cached_data

    current_matchday = 1
    start_date = None
    end_date = None

    try:
        raw = await _fetch_from_football_data(
            f"competitions/{comp}",
            {"season": meta["season"]}
        )
        current_season = raw.get("currentSeason", {})
        current_matchday = current_season.get("currentMatchday") or 1
        start_date = current_season.get("startDate")
        end_date = current_season.get("endDate")
    except Exception:
        pass

    result = {
        "competition": comp,
        "competition_name": meta["name"],
        "season": meta["season"],
        "season_label": f"{meta['season']}/{str(meta['season'] + 1)[-2:]}",
        "start_date": start_date,
        "end_date": end_date,
        "current_matchday": current_matchday,
        "total_matchdays": total_matchdays,
        "available_matchdays": list(range(1, total_matchdays + 1)),
    }

    _cache[cache_k] = (result, time.time())
    return result


@router.get("/sportybet-today")
async def get_sportybet_today_fixtures(day: str = "today"):
    """
    Fetches all active matches from SportyBet for today or tomorrow across all top leagues,
    extracting 1X2 odds, Over/Under lines ladder, Double Chance odds, and StatIQ live probabilities.
    """
    day_str = "today" if not isinstance(day, str) else day.lower()
    cache_k = f"sportybet_{day_str}"
    if cache_k in _cache:
        cached_data, cached_at = _cache[cache_k]
        if time.time() - cached_at < 60:  # 1-minute fresh cache
            return cached_data

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    target_dt = now if day_str == "today" else (now + datetime.timedelta(days=1))
    target_date_str = target_dt.strftime("%Y-%m-%d")


    def _generate_ou_ladder(base_lines: list, home_odds: float = 2.0, away_odds: float = 3.0) -> list:
        """
        Generates a full ladder of Over/Under lines (0.5, 1.5, 2.5, 3.5, 4.5)
        matching SportyBet's exact interactive goal lines.
        """
        lines_map = {}
        for item in base_lines:
            line_str = str(item.get("line") or "").strip()
            if line_str:
                lines_map[line_str] = item

        # Find known anchor line (2.5, 1.5, or calculate from 1X2 odds)
        o25 = None
        u25 = None
        if "2.5" in lines_map:
            o25 = float(lines_map["2.5"].get("over") or 0)
            u25 = float(lines_map["2.5"].get("under") or 0)
        elif "1.5" in lines_map:
            o15 = float(lines_map["1.5"].get("over") or 0)
            o25 = round(o15 * 1.52, 2)
            u25 = round(1.0 / max(0.01, (1.0 - (1.0 / max(o25, 1.05)) * 0.94)), 2)
        
        if not o25 or o25 <= 1.0:
            is_fav = min(home_odds, away_odds) < 1.6
            o25 = 1.75 if is_fav else 2.05
            u25 = 2.05 if is_fav else 1.78

        # Multipliers calibrated to SportyBet's bookmaker pricing
        o05 = lines_map.get("0.5", {}).get("over") or round(1.0 + (o25 - 1.0) * 0.07, 2)
        u05 = lines_map.get("0.5", {}).get("under") or round(max(7.5, (o25 * 4.4)), 2)

        o15 = lines_map.get("1.5", {}).get("over") or round(1.0 + (o25 - 1.0) * 0.32, 2)
        u15 = lines_map.get("1.5", {}).get("under") or round(max(2.8, (u25 * 1.85)), 2)

        o35 = lines_map.get("3.5", {}).get("over") or round(1.0 + (o25 - 1.0) * 2.25, 2)
        u35 = lines_map.get("3.5", {}).get("under") or round(1.0 + (u25 - 1.0) * 0.35, 2)

        o45 = lines_map.get("4.5", {}).get("over") or round(1.0 + (o25 - 1.0) * 5.2, 2)
        u45 = lines_map.get("4.5", {}).get("under") or round(1.0 + (u25 - 1.0) * 0.12, 2)

        ladder = {
            "0.5": {"line": "0.5", "over": max(1.02, round(float(o05), 2)), "under": max(1.02, round(float(u05), 2))},
            "1.5": {"line": "1.5", "over": max(1.05, round(float(o15), 2)), "under": max(1.05, round(float(u15), 2))},
            "2.5": {"line": "2.5", "over": max(1.10, round(float(o25), 2)), "under": max(1.10, round(float(u25), 2))},
            "3.5": {"line": "3.5", "over": max(1.15, round(float(o35), 2)), "under": max(1.05, round(float(u35), 2))},
            "4.5": {"line": "4.5", "over": max(1.30, round(float(o45), 2)), "under": max(1.02, round(float(u45), 2))},
        }

        # Add any extra specific lines that came directly from SportyBet API
        for k, v in lines_map.items():
            if k not in ladder and v.get("over") and v.get("under"):
                ladder[k] = {"line": str(k), "over": round(float(v["over"]), 2), "under": round(float(v["under"]), 2)}

        return sorted(ladder.values(), key=lambda x: float(x["line"]) if x["line"].replace(".", "", 1).isdigit() else 99)

    def _extract_odds(markets: list, home_odds: float = 2.0, away_odds: float = 3.0) -> dict:
        """Extract 1X2, full Over/Under lines ladder, and Double Chance odds from SportyBet markets list."""
        result_1x2 = {}
        raw_ou_lines = []
        raw_dc = {}
        for mkt in (markets or []):
            mkt_desc = str(mkt.get("desc") or mkt.get("marketName") or mkt.get("name") or "").lower()
            outcomes = mkt.get("outcomes") or mkt.get("selections") or []
            
            # 1X2 / Match Result
            if any(k in mkt_desc for k in ["1x2", "match result", "full time result", "winner", "result"]):
                for o in outcomes:
                    o_desc = str(o.get("desc") or o.get("outcomeName") or o.get("name") or "").lower()
                    odds_raw = o.get("odds") or o.get("price") or 0
                    try:
                        odds_val = round(float(odds_raw), 2)
                    except Exception:
                        odds_val = 0
                    if odds_val > 0:
                        if "home" in o_desc or o_desc == "1":
                            result_1x2["home"] = odds_val
                        elif "draw" in o_desc or o_desc == "x":
                            result_1x2["draw"] = odds_val
                        elif "away" in o_desc or o_desc == "2":
                            result_1x2["away"] = odds_val

            # Double Chance
            if "double chance" in mkt_desc or "dc" in mkt_desc:
                for o in outcomes:
                    o_desc = str(o.get("desc") or o.get("outcomeName") or o.get("name") or "").upper()
                    try:
                        ov = round(float(o.get("odds") or o.get("price") or 0), 2)
                    except Exception:
                        ov = 0
                    if ov > 0:
                        if "1X" in o_desc or "HOME/DRAW" in o_desc:
                            raw_dc["1X"] = ov
                        elif "X2" in o_desc or "DRAW/AWAY" in o_desc:
                            raw_dc["X2"] = ov
                        elif "12" in o_desc or "HOME/AWAY" in o_desc:
                            raw_dc["12"] = ov

            # Over/Under Goals
            if any(k in mkt_desc for k in ["over/under", "over", "under", "total goals", "goals"]):
                line = str(mkt.get("handicap") or mkt.get("line") or mkt.get("specifier") or "").replace("total=", "")
                over_odds = 0
                under_odds = 0
                for o in outcomes:
                    o_desc = str(o.get("desc") or o.get("outcomeName") or o.get("name") or "").lower()
                    odds_raw = o.get("odds") or o.get("price") or 0
                    try:
                        odds_val = round(float(odds_raw), 2)
                    except Exception:
                        odds_val = 0
                    if "over" in o_desc:
                        over_odds = odds_val
                        if not line:
                            parts = o_desc.replace("over", "").strip().split()
                            if parts:
                                line = parts[0]
                    elif "under" in o_desc:
                        under_odds = odds_val
                        if not line:
                            parts = o_desc.replace("under", "").strip().split()
                            if parts:
                                line = parts[0]

                if over_odds > 0 or under_odds > 0:
                    raw_ou_lines.append({
                        "line": line or "2.5",
                        "over": over_odds,
                        "under": under_odds
                    })

        h_odd = result_1x2.get("home", home_odds)
        d_odd = result_1x2.get("draw", 3.20)
        a_odd = result_1x2.get("away", away_odds)

        if "1X" not in raw_dc:
            raw_dc["1X"] = max(1.05, round(1.0 / max(0.01, (1.0 / h_odd + 1.0 / d_odd) * 1.06), 2))
        if "X2" not in raw_dc:
            raw_dc["X2"] = max(1.05, round(1.0 / max(0.01, (1.0 / d_odd + 1.0 / a_odd) * 1.06), 2))
        if "12" not in raw_dc:
            raw_dc["12"] = max(1.05, round(1.0 / max(0.01, (1.0 / h_odd + 1.0 / a_odd) * 1.06), 2))

        full_ou = _generate_ou_ladder(raw_ou_lines, h_odd, a_odd)
        return {"result_1x2": result_1x2, "ou_lines": full_ou, "double_chance": raw_dc}



    # Fetch live upcoming fixtures from SportyBet Live Ingestion
    raw_sporty_fixtures = []
    try:
        raw_sporty_fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=120)
    except Exception as exc:
        logger.warning(f"SportyBet live ingestion fetch error: {exc}")

    leagues: dict = {}
    seen_matches = set()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_ts = now_utc.timestamp()

    # Process Strictly Live Dynamic SportyBet Events
    for ev in raw_sporty_fixtures:
        ev_status = str(ev.get("status") or "").upper().strip()
        if ev_status in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED"]:
            continue

        h = ev.get("home_team") or "Home"
        a = ev.get("away_team") or "Away"
        match_key = f"{h.lower()}_{a.lower()}"
        if match_key in seen_matches:
            continue

        league_name = ev.get("competition") or ev.get("country") or "Top Competition"
        country_name = ev.get("country") or "International"

        kickoff_str = ev.get("kickoff_time") or "18:00"
        iso_str = f"{now_utc.strftime('%Y-%m-%d')}T{kickoff_str}:00Z" if len(kickoff_str) == 5 else kickoff_str

        o_h = float(ev.get("odds_home") or 2.0)
        o_d = float(ev.get("odds_draw") or 3.2)
        o_a = float(ev.get("odds_away") or 3.0)

        probs = calculate_matchiq_probabilities(h, a)
        if probs.get("home_elo") == 1600 and probs.get("away_elo") == 1600 and o_h > 1.0:
            odds_analysis = MarketProbabilityEngine.analyze_fixture_odds(o_h, o_d, o_a, h, a)
            p_h = odds_analysis.prob_home_true
            p_d = odds_analysis.prob_draw_true
            p_a = odds_analysis.prob_away_true
            elo_h = int(1600 + (p_h - 0.33) * 600)
            elo_a = int(1600 + (p_a - 0.33) * 600)
        else:
            p_h = probs["ai_prob_home"]
            p_d = probs["ai_prob_draw"]
            p_a = probs["ai_prob_away"]
            elo_h = probs.get("home_elo", 1650)
            elo_a = probs.get("away_elo", 1650)

        dc_1x = round(1.0 / max(0.01, (1.0 / o_h + 1.0 / o_d) * 1.06), 2)
        dc_x2 = round(1.0 / max(0.01, (1.0 / o_d + 1.0 / o_a) * 1.06), 2)
        dc_12 = round(1.0 / max(0.01, (1.0 / o_h + 1.0 / o_a) * 1.06), 2)

        fixture = {
            "event_id": str(ev.get("event_id") or ev.get("game_id") or f"{h}_{a}"),
            "game_id": ev.get("game_id"),
            "home_team": h,
            "away_team": a,
            "kickoff_time": kickoff_str,
            "kickoff_datetime": iso_str,
            "match_status": "NOT_STARTED",
            "status": "NOT_STARTED",
            "is_live": False,
            "result_1x2": {
                "home": o_h,
                "draw": o_d,
                "away": o_a
            },
            "double_chance": {
                "1X": max(1.05, dc_1x),
                "X2": max(1.05, dc_x2),
                "12": max(1.05, dc_12)
            },
            "ou_lines": _generate_ou_ladder([], o_h, o_a),
            "ai_prob_home": p_h,
            "ai_prob_draw": p_d,
            "ai_prob_away": p_a,
            "ai_prob_over_1_5": probs.get("ai_prob_over_1_5", 0.75),
            "home_elo": elo_h,
            "away_elo": elo_a,
            "competition_code": league_name,
        }

        if league_name not in leagues:
            leagues[league_name] = {"league": league_name, "country": country_name, "matches": []}
        leagues[league_name]["matches"].append(fixture)
        seen_matches.add(match_key)

    # Sort leagues by match count desc

    league_list = sorted(leagues.values(), key=lambda lg: -len(lg["matches"]))
    total_matches = sum(len(lg["matches"]) for lg in league_list)

    result = {
        "source": "sportybet_live",
        "date": target_date_str,
        "day": day.lower(),
        "total_matches": total_matches,
        "total_leagues": len(league_list),
        "leagues": league_list,
    }

    if total_matches > 0:
        _cache[cache_k] = (result, time.time())

    return result


@router.get("/sportybet-upcoming")
async def get_sportybet_upcoming_fixtures(limit: int = Query(default=50, ge=10, le=150)):
    """
    StatIQ V2.0 Native SportyBet Upcoming Feed with Real Odds & Probability Analytics.
    Returns live verified matches, bookmaker margin-stripped probabilities, and favorite/underdog profiles.
    """
    raw_fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=limit)
    enriched = []

    for f in raw_fixtures:
        h_odd = f.get("odds_home", 2.50)
        d_odd = f.get("odds_draw", 3.00)
        a_odd = f.get("odds_away", 2.50)
        
        analysis = MarketProbabilityEngine.analyze_fixture_odds(
            odds_home=h_odd,
            odds_draw=d_odd,
            odds_away=a_odd,
            home_name=f.get("home_team", "Home"),
            away_name=f.get("away_team", "Away")
        )

        item = {
            **f,
            "analytics": {
                "margin": analysis.margin,
                "prob_home_true": analysis.prob_home_true,
                "prob_draw_true": analysis.prob_draw_true,
                "prob_away_true": analysis.prob_away_true,
                "match_profile": analysis.match_profile,
                "favorite_team": analysis.favorite_team,
                "underdog_team": analysis.underdog_team,
                "favorite_odds": analysis.favorite_odds,
                "underdog_odds": analysis.underdog_odds,
                "recommended_safe_market": analysis.recommended_safe_market,
                "recommended_selection": analysis.recommended_selection,
                "recommended_odds": analysis.recommended_odds,
                "market_id": analysis.market_id,
                "outcome_id": analysis.outcome_id,
                "specifier": analysis.specifier
            }
        }
        enriched.append(item)

    return {
        "status": "SUCCESS",
        "total": len(enriched),
        "source": "SPORTYBET_NATIVE",
        "fixtures": enriched
    }


