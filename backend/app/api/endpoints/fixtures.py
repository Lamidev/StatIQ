import httpx
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Query, HTTPException

from app.core.config import settings
from app.predictions.live_calculator import calculate_matchiq_probabilities, update_dynamic_rating

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


TEAM_NAME_OVERRIDES = {
    "Brighton & Hove Albion FC": "Brighton",
    "Brighton Hove": "Brighton",
    "Manchester United FC": "Manchester Utd",
    "Manchester City FC": "Manchester City",
    "Tottenham Hotspur FC": "Tottenham",
    "Newcastle United FC": "Newcastle",
    "Nottingham Forest FC": "Nottingham Forest",
    "Hull City AFC": "Hull City",
    "AFC Bournemouth": "Bournemouth",
    "Wolverhampton Wanderers FC": "Wolves",
    "West Ham United FC": "West Ham",
    "Leicester City FC": "Leicester City",
    "Crystal Palace FC": "Crystal Palace",
    "Coventry City FC": "Coventry City",
    "Sunderland AFC": "Sunderland",
    "Ipswich Town FC": "Ipswich Town",
    "Leeds United FC": "Leeds United",
    "Aston Villa FC": "Aston Villa",
    "Brentford FC": "Brentford",
    "Everton FC": "Everton",
    "Fulham FC": "Fulham",
    "Chelsea FC": "Chelsea",
    "Liverpool FC": "Liverpool",
    "Arsenal FC": "Arsenal",
}

def _clean_name(raw: str) -> str:
    if not raw:
        return raw
    if raw in TEAM_NAME_OVERRIDES:
        return TEAM_NAME_OVERRIDES[raw]
    for suffix in [" FC", " AFC", " United FC", " City FC"]:
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    return raw


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
    Fetches fixtures for a specific competition, matchday, and season directly from football-data.org.
    Uses intelligent season fallback (2026 -> 2025) to ensure real live fixtures are always returned.
    """
    comp = competition.upper()
    if comp not in COMPETITION_SEASON_MAP:
        comp = "PL"

    meta = COMPETITION_SEASON_MAP[comp]
    target_season = season if season is not None else meta["season"]
    cache_k = f"{comp}:{matchday}:{target_season}"

    if cache_k in _cache:
        cached_data, cached_at = _cache[cache_k]
        if time.time() - cached_at < CACHE_TTL_SECONDS and cached_data.get("total", 0) > 0:
            return cached_data

    raw = await _fetch_from_football_data(
        f"competitions/{comp}/matches",
        {"matchday": matchday, "season": target_season}
    )

    matches = raw.get("matches", [])
    # If primary season returns empty, query alternative season year from football-data.org
    if not matches:
        alt_season = 2025 if target_season == 2026 else 2026
        raw2 = await _fetch_from_football_data(
            f"competitions/{comp}/matches",
            {"matchday": matchday, "season": alt_season}
        )
        matches = raw2.get("matches", [])

    fixtures = [_normalize_match(m) for m in matches]
    fixtures.sort(key=lambda f: f["kickoff_datetime"] or "")

    result = {
        "source": "live",
        "competition": comp,
        "competition_name": meta["name"],
        "season": target_season,
        "matchday": matchday,
        "total": len(fixtures),
        "fixtures": fixtures,
    }

    if len(fixtures) > 0:
        _cache[cache_k] = (result, time.time())
        
    return result


@router.get("/cross-league-gameweek")
async def get_cross_league_gameweek(
    matchday: int = Query(default=1, ge=1, le=38, description="Gameweek / Matchday number"),
    limit: int = Query(default=25, ge=5, le=50, description="Max matches to return")
):
    """
    Cross-League Dynamic Gameweek Aggregator.
    Fetches real live fixtures across major European leagues for the given matchday.
    """
    cache_k = f"cross_league:{matchday}:{limit}"
    if cache_k in _cache:
        cached_data, cached_at = _cache[cache_k]
        if time.time() - cached_at < CACHE_TTL_SECONDS and cached_data.get("total", 0) > 0:
            return cached_data

    major_leagues = ["PL", "PD", "SA", "BL1", "FL1", "CL"]
    
    # Fetch all major leagues concurrently in parallel
    results = await asyncio.gather(
        *[get_fixtures_by_gameweek(competition=comp, matchday=matchday) for comp in major_leagues],
        return_exceptions=True
    )

    all_fixtures = []
    for comp, res in zip(major_leagues, results):
        if isinstance(res, dict):
            fixtures = res.get("fixtures", [])
            for f in fixtures:
                f_copy = dict(f)
                f_copy["league_code"] = comp
                f_copy["league_name"] = COMPETITION_SEASON_MAP.get(comp, {}).get("name", comp)
                all_fixtures.append(f_copy)

    all_fixtures.sort(key=lambda f: f.get("kickoff_datetime") or "")
    curated = all_fixtures[:limit]

    result = {
        "source": "cross_league_aggregator",
        "matchday": matchday,
        "total": len(curated),
        "limit": limit,
        "fixtures": curated,
    }

    if len(curated) > 0:
        _cache[cache_k] = (result, time.time())
        
    return result


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
