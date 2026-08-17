"""
StatIQ API-Football Stats Fetcher
==================================
Fetches real match statistics (corners, halftime scores) from api-football.com.
Only called for picks that CANNOT be verified from score data alone:
  - Total Corners Over 7.5
  - 1st Half Over 0.5 Goals
  - Win Either Half

Usage:
  stats = await fetch_match_stats("FC Thun", "Vikingur Reykjavik", "2025-08-01")
  # → { "ht_home": 1, "ht_away": 0, "home_corners": 5, "away_corners": 3 }
"""

import asyncio
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

# In-memory caches
_stats_cache: Dict[str, Dict[str, Any]] = {}
_team_id_cache: Dict[str, int] = {}


def _norm(name: str) -> str:
    """Normalize team name for fuzzy matching."""
    if not name:
        return ""
    return (
        name.lower()
        .replace("fc", "").replace("afc", "").replace("sc", "")
        .replace(".", "").replace("-", " ").replace("'", "")
        .strip()
    )


async def _resolve_team_id(team_name: str, client: httpx.AsyncClient, headers: dict) -> Optional[int]:
    """Resolves a team name string to API-Football numeric team ID."""
    clean = _norm(team_name).replace(" women", "").replace(" w", "").strip()
    if not clean:
        return None
    if clean in _team_id_cache:
        return _team_id_cache[clean]

    # Clean team search query (take first 2 words max)
    words = clean.split()
    search_q = words[0] if len(words) > 0 else clean

    try:
        resp = await client.get(
            f"{API_FOOTBALL_BASE}/teams",
            params={"search": search_q},
            headers=headers
        )
        if resp.status_code == 200:
            teams = resp.json().get("response", [])
            for t in teams:
                info = t.get("team", {})
                t_name_norm = _norm(info.get("name", ""))
                if clean in t_name_norm or t_name_norm in clean or words[0] in t_name_norm:
                    tid = info.get("id")
                    _team_id_cache[clean] = tid
                    return tid
            # Fallback to first result if available
            if teams:
                tid = teams[0].get("team", {}).get("id")
                _team_id_cache[clean] = tid
                return tid
    except Exception as e:
        logger.warning(f"Error resolving team ID for {team_name}: {e}")
    return None


async def fetch_match_stats(
    home_team: str,
    away_team: str,
    match_date: Optional[str],  # "YYYY-MM-DD" or None
    api_key: str,
) -> Dict[str, Any]:
    """
    Fetches halftime score and corner statistics for a specific match from api-football.com.
    Supports regular league matches, Club Friendlies, International Friendlies, and Preseason games.
    Returns a dict with keys: ht_home, ht_away, home_corners, away_corners, found (bool)
    """
    NOT_FOUND = {"found": False, "ht_home": None, "ht_away": None, "home_corners": None, "away_corners": None}

    if not api_key or api_key.strip() == "":
        logger.warning("API_FOOTBALL_KEY not configured — cannot fetch real match stats.")
        return NOT_FOUND

    home_norm = _norm(home_team)
    away_norm = _norm(away_team)
    cache_k = f"{home_norm}|{away_norm}|{match_date or 'any'}"
    if cache_k in _stats_cache:
        return _stats_cache[cache_k]

    headers = {
        "x-apisports-key": api_key,
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": api_key,
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            # Step 1: Resolve home team ID
            team_id = await _resolve_team_id(home_team, client, headers)
            if not team_id:
                team_id = await _resolve_team_id(away_team, client, headers)

            fixtures = []
            if team_id:
                # Fetch recent fixtures for this team ID (covers friendlies, preseason, and league matches)
                fix_params = {"team": team_id, "last": 15}
                fix_resp = await client.get(f"{API_FOOTBALL_BASE}/fixtures", params=fix_params, headers=headers)
                if fix_resp.status_code == 200:
                    fixtures = fix_resp.json().get("response", [])
            elif match_date:
                # Fallback to date search
                fix_resp = await client.get(f"{API_FOOTBALL_BASE}/fixtures", params={"date": match_date}, headers=headers)
                if fix_resp.status_code == 200:
                    fixtures = fix_resp.json().get("response", [])

            # Step 2: Find best-matching fixture by team names
            fixture_id = None
            ht_home = None
            ht_away = None

            for fix in fixtures:
                fx_home = _norm(fix.get("teams", {}).get("home", {}).get("name", ""))
                fx_away = _norm(fix.get("teams", {}).get("away", {}).get("name", ""))

                home_match = home_norm in fx_home or fx_home in home_norm or home_norm[:4] in fx_home
                away_match = away_norm in fx_away or fx_away in away_norm or away_norm[:4] in fx_away

                if home_match and away_match:
                    fixture_id = fix.get("fixture", {}).get("id")
                    ht = fix.get("score", {}).get("halftime", {})
                    ht_home = ht.get("home")
                    ht_away = ht.get("away")
                    break

            if not fixture_id:
                _stats_cache[cache_k] = NOT_FOUND
                return NOT_FOUND

            # Step 3: Fetch match statistics (corners)
            stats_resp = await client.get(
                f"{API_FOOTBALL_BASE}/fixtures/statistics",
                params={"fixture": fixture_id},
                headers=headers,
            )
            home_corners = None
            away_corners = None

            if stats_resp.status_code == 200:
                stat_teams = stats_resp.json().get("response", [])
                for team_stats in stat_teams:
                    team_name = _norm(team_stats.get("team", {}).get("name", ""))
                    is_home = home_norm in team_name or team_name in home_norm

                    for stat in team_stats.get("statistics", []):
                        if stat.get("type") == "Corner Kicks":
                            val = stat.get("value")
                            try:
                                val = int(val) if val is not None else 0
                            except (TypeError, ValueError):
                                val = 0

                            if is_home:
                                home_corners = val
                            else:
                                away_corners = val

            result = {
                "found": True,
                "fixture_id": fixture_id,
                "ht_home": ht_home,
                "ht_away": ht_away,
                "home_corners": home_corners,
                "away_corners": away_corners,
            }

            _stats_cache[cache_k] = result
            logger.info(
                f"[APIFootball] Resolved fixture {fixture_id}: {home_team} vs {away_team} -> "
                f"HT: {ht_home}-{ht_away}, Corners: {home_corners}+{away_corners}"
            )
            return result

        except Exception as e:
            logger.warning(f"[APIFootball] Error fetching match stats for {home_team} vs {away_team}: {e}")

    return NOT_FOUND


async def batch_fetch_match_stats(
    matches: list,  # list of {home_team, away_team, match_date, pick}
    api_key: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch stats only for picks that require real stat verification:
      - picks containing 'corners'
      - picks containing '1st half over' or 'ht over'
      - picks containing 'win either half'

    Returns a dict keyed by match index → stats dict.
    Skips all other picks to conserve API call budget.
    """
    STAT_PICKS = ["corners", "1st half over", "ht over", "win either half", "weh"]

    tasks = {}
    for i, m in enumerate(matches):
        pick_lower = (m.get("pick") or m.get("prediction") or "").lower()
        needs_stats = any(kw in pick_lower for kw in STAT_PICKS)

        if needs_stats:
            tasks[i] = fetch_match_stats(
                m.get("home_team") or m.get("home", ""),
                m.get("away_team") or m.get("away", ""),
                m.get("match_date"),
                api_key,
            )

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return {
        idx: (res if isinstance(res, dict) else {"found": False})
        for idx, res in zip(tasks.keys(), results)
    }
