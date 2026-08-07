import httpx
import asyncio
import logging
from functools import lru_cache
from typing import Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException

from app.core.config import settings
from app.predictions.live_calculator import calculate_matchiq_probabilities, update_dynamic_rating

router = APIRouter()
logger = logging.getLogger("matchiq.fixtures")

# Map our league codes to football-data.org competition codes
# season=2026 targets the 2026/2027 season (football-data.org uses the start year)
# These are ALL competitions available on this API key's subscription tier.
COMPETITION_SEASON_MAP = {
    # England
    "PL":  {"code": "PL",  "name": "Premier League",          "country": "England",      "season": 2026, "matchdays": 38},
    "ELC": {"code": "ELC", "name": "Championship",            "country": "England",      "season": 2026, "matchdays": 46},
    # Spain
    "PD":  {"code": "PD",  "name": "La Liga",                 "country": "Spain",        "season": 2026, "matchdays": 38},
    # Italy
    "SA":  {"code": "SA",  "name": "Serie A",                 "country": "Italy",        "season": 2026, "matchdays": 38},
    # Germany
    "BL1": {"code": "BL1", "name": "Bundesliga",              "country": "Germany",      "season": 2026, "matchdays": 34},
    # France
    "FL1": {"code": "FL1", "name": "Ligue 1",                 "country": "France",       "season": 2026, "matchdays": 34},
    # Netherlands
    "DED": {"code": "DED", "name": "Eredivisie",              "country": "Netherlands",  "season": 2026, "matchdays": 34},
    # Portugal
    "PPL": {"code": "PPL", "name": "Primeira Liga",           "country": "Portugal",     "season": 2026, "matchdays": 34},
    # UEFA — UCL 2026/27 not yet scheduled, use 2025/26 season
    "CL":  {"code": "CL",  "name": "Champions League",        "country": "UEFA",         "season": 2025, "matchdays": 8},
    # South America
    "CLI": {"code": "CLI", "name": "Copa Libertadores",       "country": "South America","season": 2026, "matchdays": 8},
    "BSA": {"code": "BSA", "name": "Brasileirão Série A",     "country": "Brazil",       "season": 2026, "matchdays": 38},
    # International
    "WC":  {"code": "WC",  "name": "FIFA World Cup",          "country": "World",        "season": 2026, "matchdays": 8},
}

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

# In-memory cache: key -> (data, timestamp)
_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def _fetch_from_football_data(endpoint: str, params: dict) -> dict:
    """
    Makes a live HTTP request to football-data.org API.
    Returns the JSON response or raises HTTPException on failure.
    """
    url = f"{FOOTBALL_DATA_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "X-Auth-Token": settings.FOOTBALL_DATA_API_KEY,
        "User-Agent": "MatchIQ-Engine/1.0",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                raise HTTPException(status_code=403, detail="football-data.org: Access restricted. Check API subscription tier.")
            elif resp.status_code == 429:
                raise HTTPException(status_code=429, detail="football-data.org: Rate limit hit. Try again shortly.")
            elif resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"football-data.org: Resource not found ({endpoint})")
            else:
                raise HTTPException(status_code=502, detail=f"football-data.org error: HTTP {resp.status_code}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="football-data.org request timed out.")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Could not reach football-data.org: {exc}")


def _cache_key(competition: str, matchday: int) -> str:
    return f"{competition}:{matchday}"


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
    # Strip common suffixes for a clean short display
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

    # Update dynamic Elo rating if match is finished
    if status == "FINISHED" and home_score is not None and away_score is not None:
        update_dynamic_rating(home_name, away_name, home_score, away_score)

    # Compute MatchIQ calibrated quantitative probabilities
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
        "result": score.get("winner"),  # HOME_TEAM / AWAY_TEAM / DRAW / null
        # AI probabilities & dynamic Elo ratings calculated by MatchIQ Quantitative Engine
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
    season: Optional[int] = Query(default=None, description="Optional historical season year e.g. 2024, 2023, 2022, 2021 for backtesting")
):
    """
    Fetches fixtures for a specific competition, matchday, and season.
    Supports querying past finished seasons (2024, 2023, 2022, 2021) for historical backtesting.
    """
    comp = competition.upper()
    if comp not in COMPETITION_SEASON_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown competition code: {competition}. Valid: {list(COMPETITION_SEASON_MAP.keys())}")

    meta = COMPETITION_SEASON_MAP[comp]
    target_season = season if season is not None else meta["season"]
    cache_k = f"{comp}:{matchday}:{target_season}"

    import time
    if cache_k in _cache:
        cached_data, cached_at = _cache[cache_k]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return cached_data

    raw = await _fetch_from_football_data(
        f"competitions/{comp}/matches",
        {"matchday": matchday, "season": target_season}
    )

    matches = raw.get("matches", [])
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

    _cache[cache_k] = (result, time.time())
    return result


@router.get("/cross-league-gameweek")
async def get_cross_league_gameweek(
    matchday: int = Query(default=1, ge=1, le=38, description="Gameweek / Matchday number"),
    limit: int = Query(default=20, ge=5, le=50, description="Max matches to return")
):
    """
    Cross-League Dynamic Gameweek Aggregator.
    Fetches fixtures across PL, PD, SA, BL1, FL1, CL for the given matchday,
    combining domestic weekend matches (Fri-Mon) and mid-week ties (Tue-Wed).
    Returns top N matches sorted by kickoff date/time.
    """
    major_leagues = ["PL", "PD", "SA", "BL1", "FL1", "CL"]
    all_fixtures = []

    tasks = [
        _fetch_from_football_data(
            f"competitions/{comp}/matches",
            {"matchday": matchday, "season": COMPETITION_SEASON_MAP[comp]["season"]}
        )
        for comp in major_leagues
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, res in enumerate(results):
        if isinstance(res, dict):
            matches = res.get("matches", [])
            for m in matches:
                st = (m.get("status") or "").upper()
                # Exclude finished or awarded past matches — keep ONLY upcoming/scheduled fixtures
                if st in ("FINISHED", "AWARDED", "CANCELLED", "POSTPONED"):
                    continue
                norm = _normalize_match(m)
                norm["league_code"] = major_leagues[i]
                norm["league_name"] = COMPETITION_SEASON_MAP[major_leagues[i]]["name"]
                all_fixtures.append(norm)

    # Fallback: if selected matchday has no upcoming matches left, fetch future scheduled fixtures
    if not all_fixtures and matchday < 38:
        next_tasks = [
            _fetch_from_football_data(
                f"competitions/{comp}/matches",
                {"matchday": matchday + 1, "season": COMPETITION_SEASON_MAP[comp]["season"]}
            )
            for comp in major_leagues
        ]
        next_results = await asyncio.gather(*next_tasks, return_exceptions=True)
        for i, res in enumerate(next_results):
            if isinstance(res, dict):
                matches = res.get("matches", [])
                for m in matches:
                    st = (m.get("status") or "").upper()
                    if st in ("FINISHED", "AWARDED", "CANCELLED", "POSTPONED"):
                        continue
                    norm = _normalize_match(m)
                    norm["league_code"] = major_leagues[i]
                    norm["league_name"] = COMPETITION_SEASON_MAP[major_leagues[i]]["name"]
                    all_fixtures.append(norm)

    all_fixtures.sort(key=lambda f: f["kickoff_datetime"] or "")
    curated = all_fixtures[:limit]

    return {
        "source": "cross_league_aggregator",
        "matchday": matchday,
        "total": len(curated),
        "limit": limit,
        "fixtures": curated,
    }


@router.get("/available-matchdays")
async def get_available_matchdays(
    competition: str = Query(default="PL", description="League code: PL, PD, SA, BL1, FL1, CL"),
):
    """
    Returns competition metadata for the 2026/27 season:
    current matchday, total matchdays, and season start/end dates.
    Fetches live from football-data.org.
    """
    comp = competition.upper()
    if comp not in COMPETITION_SEASON_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown competition code: {competition}")

    meta = COMPETITION_SEASON_MAP[comp]
    total_matchdays = meta.get("matchdays", 38)

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
        current_matchday = 1
        start_date = None
        end_date = None

    return {
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
