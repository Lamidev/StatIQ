"""
MatchIQ H2H Fetcher
====================
Fetches head-to-head historical signals from Football-Data.org API.
Used by the ticket re-editor to bias pick selection based on historical tendencies.

Signals produced:
  - over_15_rate      : fraction of last-N H2H games with 2+ goals
  - over_25_rate      : fraction with 3+ goals
  - both_scored_rate  : fraction where both teams scored
  - home_win_rate     : fraction where home team won
  - away_win_rate     : fraction where away team won
  - draw_rate         : fraction of draws
  - avg_goals         : average goals per game
  - competitive       : True if Elo gap < 100 (triggers H2H lookup)
  - favored_team      : "home" or "away" based on H2H record + Elo
"""

import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("matchiq.h2h_fetcher")

# Football-Data.org API settings (free tier: 10 req/min)
FD_BASE = "https://api.football-data.org/v4"
FD_HEADERS = {"X-Auth-Token": ""}  # Filled from settings at runtime


def _load_api_key() -> str:
    try:
        from app.core.config import settings
        return settings.FOOTBALL_DATA_API_KEY or ""
    except Exception:
        return ""


def _search_team_id(team_name: str, api_key: str) -> Optional[int]:
    """Resolve a team name to a Football-Data.org team ID."""
    if not api_key or not team_name:
        return None
    try:
        url = f"{FD_BASE}/teams"
        headers = {"X-Auth-Token": api_key}
        with httpx.Client(timeout=5.0, headers=headers) as client:
            r = client.get(url, params={"name": team_name, "limit": 5})
            if r.status_code == 200:
                teams = r.json().get("teams", [])
                if teams:
                    # Pick closest name match
                    name_lower = team_name.lower()
                    for t in teams:
                        if name_lower in (t.get("name") or "").lower() or name_lower in (t.get("shortName") or "").lower():
                            return t["id"]
                    return teams[0]["id"]
    except Exception as e:
        logger.debug(f"H2H team search failed for {team_name}: {e}")
    return None


def get_h2h_signals(
    home_team: str,
    away_team: str,
    home_elo: int = 1670,
    away_elo: int = 1670,
    n_matches: int = 10,
) -> Dict[str, Any]:
    """
    Returns H2H signal dict for a fixture. Falls back to Elo-only signals gracefully.
    Only fetches from API when the Elo gap is < 120 (competitive match — H2H matters more).
    """
    elo_gap = abs(home_elo - away_elo)
    competitive = elo_gap < 120

    # Default signals (Elo-based fallback)
    home_stronger = (home_elo + 40) >= away_elo  # +40 home advantage
    default = {
        "source": "ELO_ONLY",
        "competitive": competitive,
        "over_15_rate": 0.78,        # universal base rate
        "over_25_rate": 0.52,
        "both_scored_rate": 0.55,
        "home_win_rate": 0.50 if not home_stronger else 0.58,
        "away_win_rate": 0.20 if home_stronger else 0.35,
        "draw_rate": 0.25,
        "avg_goals": 2.5,
        "favored_team": "home" if home_stronger else "away",
        "h2h_available": False,
    }

    # Only fetch H2H for competitive matches (Elo gap < 120)
    if not competitive:
        default["favored_team"] = "home" if home_stronger else "away"
        return default

    api_key = _load_api_key()
    if not api_key:
        return default

    try:
        # Resolve team IDs (budget: 2 API calls)
        home_id = _search_team_id(home_team, api_key)
        away_id = _search_team_id(away_team, api_key)

        if not home_id or not away_id:
            return default

        # Fetch H2H matches
        url = f"{FD_BASE}/teams/{home_id}/matches"
        headers = {"X-Auth-Token": api_key}
        with httpx.Client(timeout=5.0, headers=headers) as client:
            r = client.get(url, params={
                "status": "FINISHED",
                "limit": n_matches * 3,   # fetch more to filter for H2H
            })
            if r.status_code != 200:
                return default

            all_matches = r.json().get("matches", [])

        # Filter to actual H2H (home vs away, either direction)
        h2h_matches = []
        home_id_str = str(home_id)
        away_id_str = str(away_id)
        for m in all_matches:
            h = str(m.get("homeTeam", {}).get("id", ""))
            a = str(m.get("awayTeam", {}).get("id", ""))
            if (h == home_id_str and a == away_id_str) or (h == away_id_str and a == home_id_str):
                h2h_matches.append(m)
            if len(h2h_matches) >= n_matches:
                break

        if not h2h_matches:
            return default

        # Compute signals from H2H data
        total = len(h2h_matches)
        home_wins = away_wins = draws = over_15 = over_25 = both_scored = total_goals = 0

        for m in h2h_matches:
            score = m.get("score", {}).get("fullTime", {})
            hg = score.get("home") or score.get("homeTeam") or 0
            ag = score.get("away") or score.get("awayTeam") or 0
            try:
                hg, ag = int(hg), int(ag)
            except Exception:
                continue

            goals = hg + ag
            total_goals += goals

            # Determine which team was "home" in this historical match
            is_normal_order = str(m.get("homeTeam", {}).get("id", "")) == home_id_str

            if hg > ag:
                if is_normal_order:
                    home_wins += 1
                else:
                    away_wins += 1
            elif ag > hg:
                if is_normal_order:
                    away_wins += 1
                else:
                    home_wins += 1
            else:
                draws += 1

            if goals >= 2:
                over_15 += 1
            if goals >= 3:
                over_25 += 1
            if hg >= 1 and ag >= 1:
                both_scored += 1

        # Build final signal dict
        hw_rate = home_wins / total
        aw_rate = away_wins / total
        d_rate  = draws / total

        # Combine H2H record with Elo to determine favored team
        # Weight: 60% H2H record + 40% Elo
        h2h_score = hw_rate * 0.6 + (0.4 if home_stronger else 0.2)
        a2h_score = aw_rate * 0.6 + (0.2 if home_stronger else 0.4)
        favored = "home" if h2h_score >= a2h_score else "away"

        return {
            "source": "FOOTBALL_DATA_H2H",
            "competitive": True,
            "n_matches": total,
            "over_15_rate": round(over_15 / total, 3),
            "over_25_rate": round(over_25 / total, 3),
            "both_scored_rate": round(both_scored / total, 3),
            "home_win_rate": round(hw_rate, 3),
            "away_win_rate": round(aw_rate, 3),
            "draw_rate": round(d_rate, 3),
            "avg_goals": round(total_goals / total, 2),
            "favored_team": favored,
            "h2h_available": True,
        }

    except Exception as e:
        logger.debug(f"H2H fetch failed for {home_team} vs {away_team}: {e}")
        return default
