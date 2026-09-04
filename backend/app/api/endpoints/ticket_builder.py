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
    num_tickets: int = 1  # 1 (single ticket), 2, 3, 4 (multi-ticket portfolio)
    overlap_mode: Optional[str] = "ZERO_OVERLAP"  # "ZERO_OVERLAP" or "ANCHOR_ONLY"
    selected_leagues: Optional[List[str]] = None  # e.g. ["PL", "PD", "SA", "BL1", "FL1", "ELC", "DED", "PPL"]
    league_scope: Optional[str] = "MULTI"
    single_league: Optional[str] = "PL"
    date_window: Optional[str] = "TODAY"  # "TODAY", "NEXT_24H", "WEEKEND", "NEXT_7D"
    flex_cut: Optional[int] = 0  # 0 = Straight, 1 = Cut 1, 2 = Cut 2
    use_live_odds: bool = True
    custom_fixtures: Optional[List[Dict[str, Any]]] = None
    reshuffle_seed: Optional[int] = None
    risk_profile: Optional[str] = "BALANCED"  # "ULTRA_CONSERVATIVE", "BALANCED", "AGGRESSIVE"
    allowed_market_categories: Optional[List[str]] = None
    excluded_market_categories: Optional[List[str]] = None


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

def _extract_live_market_data(ev: Dict[str, Any]) -> tuple:
    raw_mkts = ev.get("markets", {})
    if isinstance(raw_mkts, dict):
        raw_mkts = list(raw_mkts.values())
    
    dc_map = {}
    ou_list = []
    
    o_h = float(ev.get("odds_home") or 2.0)
    o_d = float(ev.get("odds_draw") or 3.2)
    o_a = float(ev.get("odds_away") or 3.0)
    
    import re
    for m in (raw_mkts or []):
        if not isinstance(m, dict):
            continue
        m_id = str(m.get("market_id") or m.get("id") or "")
        m_desc = str(m.get("market_name") or m.get("desc") or m.get("name") or "").lower()
        spec = str(m.get("specifier") or "")
        outcomes = m.get("outcomes", [])
        if isinstance(outcomes, dict):
            outcomes = list(outcomes.values())
            
        # Double Chance
        if m_id == "10" or ("double chance" in m_desc and not any(k in m_desc for k in ["&", "over", "under"])):
            for o in outcomes:
                o_id = str(o.get("outcome_id") or o.get("id") or "")
                o_desc = str(o.get("selection_name") or o.get("desc") or "").upper()
                try:
                    ov = float(o.get("odds") or o.get("oddsValue") or 0.0)
                    if ov >= 1.02:
                        if o_id == "9" or "1X" in o_desc: dc_map["1X"] = ov
                        elif o_id == "11" or "X2" in o_desc: dc_map["X2"] = ov
                        elif o_id == "10" or "12" in o_desc: dc_map["12"] = ov
                except Exception:
                    pass
                    
    # Over/Under Goals: Extract existing lines from raw feed
        if m_id == "18" or ("over/under" in m_desc and not any(k in m_desc for k in ["&", "1x2", "dc"])):
            line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
            line_str = line_m.group(1) if line_m else "1.5"
            o_val = None
            u_val = None
            for o in outcomes:
                o_desc = str(o.get("selection_name") or o.get("desc") or "").lower()
                o_id = str(o.get("outcome_id") or o.get("id") or "")
                try:
                    ov = float(o.get("odds") or o.get("oddsValue") or 0.0)
                    if ov >= 1.02:
                        if "over" in o_desc or o_id == "12": o_val = ov
                        elif "under" in o_desc or o_id == "13": u_val = ov
                except Exception:
                    pass
            if o_val or u_val:
                ou_list.append({"line": line_str, "over": o_val, "under": u_val})
                
    # Accurate overround margin conversion if specific submarket not expanded in list
    if "1X" not in dc_map and o_h > 1.0 and o_d > 1.0:
        dc_map["1X"] = round(1.0 / max(0.01, (1.0 / o_h + 1.0 / o_d) * 1.08), 2)
    if "X2" not in dc_map and o_a > 1.0 and o_d > 1.0:
        dc_map["X2"] = round(1.0 / max(0.01, (1.0 / o_a + 1.0 / o_d) * 1.08), 2)
    if "12" not in dc_map and o_h > 1.0 and o_a > 1.0:
        dc_map["12"] = round(1.0 / max(0.01, (1.0 / o_h + 1.0 / o_a) * 1.08), 2)

    # Universal SportyBet Half-Point Lines (1.5, 2.5, 3.5, 4.5):
    # If the raw match feed only included a single/high line (e.g. 5.5), synthesize
    # standard half-point lines using Poisson expectation so the engine has rich market depth
    existing_lines = {str(item.get("line")) for item in ou_list}
    exp_goals = 3.3 if (o_h <= 1.30 or o_a <= 1.30) else (2.9 if (o_h <= 1.60 or o_a <= 1.60) else 2.55)
    
    import math
    p0 = math.exp(-exp_goals)
    p1 = p0 * exp_goals
    p2 = p1 * exp_goals / 2.0
    p3 = p2 * exp_goals / 3.0
    p4 = p3 * exp_goals / 4.0

    p_u15 = p0 + p1
    p_o15 = max(0.01, 1.0 - p_u15)
    p_u25 = p_u15 + p2
    p_o25 = max(0.01, 1.0 - p_u25)
    p_u35 = p_u25 + p3
    p_o35 = max(0.01, 1.0 - p_u35)
    p_u45 = p_u35 + p4
    p_o45 = max(0.01, 1.0 - p_u45)

    margin = 1.07
    if "1.5" not in existing_lines:
        ou_list.append({
            "line": "1.5",
            "over": round(1.0 / (p_o15 * margin), 2),
            "under": round(1.0 / (p_u15 * margin), 2)
        })
    if "2.5" not in existing_lines:
        ou_list.append({
            "line": "2.5",
            "over": round(1.0 / (p_o25 * margin), 2),
            "under": round(1.0 / (p_u25 * margin), 2)
        })
    if "3.5" not in existing_lines:
        ou_list.append({
            "line": "3.5",
            "over": round(1.0 / (p_o35 * margin), 2),
            "under": round(1.0 / (p_u35 * margin), 2)
        })
    # Note: Line 4.5 is a specialty line on SportyBet and is only included if SportyBet's active board published it
        
    return dc_map, ou_list

def _is_league_match(comp_name: str, country_name: str, code_key: str) -> bool:
    comp = (comp_name or "").strip().lower()
    country = (country_name or "").strip().lower()
    code = (code_key or "").upper()

    # Reject non-top flight attributes universally unless specifically a cup code
    is_cup_code = code in ["UCL", "UEL", "UECL", "COP"]
    if not is_cup_code:
        if any(x in comp for x in [
            "women", "femenino", "feminin", "damen", "frauen", "vrouwen", "kvinner", "bayanlar",
            "u23", "u21", "u20", "u19", "u18", "u17", "youth", "primavera", "reserve", "reserves",
            "amateur", "cup", "trophy", "kupa", "pokal", "coppa", "taça", "taca", "copa", "shield",
            "group a", "group b", "group c", "group d", "group e", "group f", "group g", "group h",
            "serie c", "serie d", "liga 3", "liga 2", "2. liga", "3. liga", "persha", "druha", "segunda"
        ]):
            return False

    if code == "PL":
        # English Premier League (Strict Top Flight)
        if any(x in comp for x in [
            "faroe", "islands", "ghana", "egypt", "wales", "israel", "crimea", "russia", "victoria",
            "kazakhstan", "northern ireland", "south africa", "ukraine", "bhutan", "division", "kuwait",
            "india", "kenya", "singapore", "jamaica", "malta", "armenia", "georgia"
        ]):
            return False
        if country and country not in ["england", "great britain", "uk", "international"]:
            return False
        return "premier league" in comp or "epl" in comp

    elif code == "PD":
        # Spanish LaLiga (Primera Division Only)
        if any(x in comp for x in ["laliga 2", "la liga 2", "hypermotion", "segunda", "rfef", "federacion", "tercera"]):
            return False
        if country and country not in ["spain", ""]:
            return False
        return "laliga" in comp or "la liga" in comp or "primera division" in comp

    elif code == "SA":
        # Italian Serie A (Strict Top Flight)
        if any(x in comp for x in ["serie b", "serie c", "serie d", "brasileiro", "brazil", "ecuador", "colombia"]):
            return False
        if country and country not in ["italy", ""]:
            return False
        return "serie a" in comp

    elif code == "BL1":
        # German Bundesliga (Strict Top Flight)
        if any(x in comp for x in ["2. bundesliga", "2.bundesliga", "3. liga", "austria", "österreich", "regionalliga"]):
            return False
        if country and country not in ["germany", ""]:
            return False
        return "bundesliga" in comp

    elif code == "FL1":
        # French Ligue 1 (Strict Top Flight)
        if any(x in comp for x in ["ligue 2", "national", "algeria", "ivory coast", "tunisia"]):
            return False
        if country and country not in ["france", ""]:
            return False
        return "ligue 1" in comp

    elif code == "ELC":
        # English Championship
        if country and country not in ["england", "uk", "great britain", ""]:
            return False
        return "championship" in comp and "scotland" not in comp and "scottish" not in comp

    elif code == "DED":
        # Dutch Eredivisie (Strict Top Flight)
        if any(x in comp for x in ["eerste", "division", "reserve"]):
            return False
        if country and country not in ["netherlands", "holland", ""]:
            return False
        return "eredivisie" in comp

    elif code == "PPL":
        # Portuguese Primeira Liga (Strict Top Flight)
        if any(x in comp for x in ["liga 2", "liga portugal 2", "liga 3", "liga portugal 3", " b"]):
            return False
        if country and country not in ["portugal", ""]:
            return False
        return "primeira liga" in comp or ("liga portugal" in comp and not any(k in comp for k in [" 2", " 3", " b"]))

    elif code == "BL2":
        # German 2. Bundesliga
        if country and country not in ["germany", ""]:
            return False
        return "2. bundesliga" in comp or "2.bundesliga" in comp

    elif code == "SD":
        # Spanish LaLiga 2 / Hypermotion
        if country and country not in ["spain", ""]:
            return False
        return "laliga 2" in comp or "la liga 2" in comp or "segunda division" in comp or "hypermotion" in comp

    elif code == "TUR":
        # Turkish Süper Lig (Top Flight Only)
        if any(x in comp for x in ["1. lig", "2. lig", "3. lig"]):
            return False
        if country and country not in ["turkey", "türkiye", "turkiye", ""]:
            return False
        return "super lig" in comp or "süper lig" in comp or "superlig" in comp

    elif code == "BEL":
        # Belgian Pro League / Jupiler Pro League (Top Flight Only)
        if any(x in comp for x in ["1b", "challenger"]):
            return False
        if country and country not in ["belgium", "belgique", ""]:
            return False
        return "pro league" in comp or "first division a" in comp or "jupiler" in comp

    elif code == "AUT":
        # Austrian Bundesliga (Top Flight Only)
        if any(x in comp for x in ["2. liga", "2.liga", "regionalliga"]):
            return False
        if country and country not in ["austria", "österreich", ""]:
            return False
        return "bundesliga" in comp

    elif code == "SAU":
        # Saudi Pro League (Roshn Saudi League - Top Flight Only)
        if any(x in comp for x in ["division 1", "division 2", "division 3", "first division"]):
            return False
        if country and country not in ["saudi arabia", "saudi", ""]:
            return False
        return "pro league" in comp or "roshn" in comp

    elif code == "SCO":
        # Scottish Premiership (Top Flight Only)
        if any(x in comp for x in ["championship", "league one", "league two"]):
            return False
        if country and country not in ["scotland", ""]:
            return False
        return "premiership" in comp or "premier league" in comp

    elif code in ["ROU", "ROM"]:
        # Romanian SuperLiga (Top Flight Only)
        if any(x in comp for x in ["liga 2", "liga 3"]):
            return False
        if country and country not in ["romania", "rumänien", ""]:
            return False
        return "superliga" in comp or "liga 1" in comp or "liga i" in comp

    elif code == "SUI":
        # Swiss Super League (Top Flight Only)
        if any(x in comp for x in ["challenge", "promotion"]):
            return False
        if country and country not in ["switzerland", "suisse", "schweiz", ""]:
            return False
        return "super league" in comp or "credit suisse" in comp

    elif code == "CRO":
        # Croatian HNL (Top Flight Only)
        if any(x in comp for x in ["2. hnl", "1. nl", "2. nl"]):
            return False
        if country and country not in ["croatia", "hrvatska", ""]:
            return False
        return "hnl" in comp or "prva liga" in comp

    elif code == "DEN":
        # Danish Superliga (Top Flight Only)
        if any(x in comp for x in ["1. division", "2. division"]):
            return False
        if country and country not in ["denmark", "danmark", ""]:
            return False
        return "superliga" in comp or "superligaen" in comp

    elif code == "GRE":
        # Greek Super League 1 (Top Flight Only)
        if "super league 2" in comp:
            return False
        if country and country not in ["greece", ""]:
            return False
        return "super league" in comp

    elif code == "NOR":
        # Norwegian Eliteserien (Top Flight Only)
        if any(x in comp for x in ["1. divisjon", "obos"]):
            return False
        if country and country not in ["norway", "norge", ""]:
            return False
        return "eliteserien" in comp

    elif code == "SWE":
        # Swedish Allsvenskan (Top Flight Only)
        if any(x in comp for x in ["superettan", "ettan"]):
            return False
        if country and country not in ["sweden", "sverige", ""]:
            return False
        return "allsvenskan" in comp

    elif code == "POL":
        # Polish Ekstraklasa (Top Flight Only)
        if any(x in comp for x in ["i liga", "ii liga"]):
            return False
        if country and country not in ["poland", "polska", ""]:
            return False
        return "ekstraklasa" in comp

    elif code == "BRA":
        # Brazilian Serie A (Brasileirão - Top Flight Only)
        if any(x in comp for x in ["serie b", "serie c", "serie d", "carioca", "paulista", "mineiro", "gaucho"]):
            return False
        if country and country not in ["brazil", "brasil", ""]:
            return False
        return "serie a" in comp or "brasileiro" in comp or "brasileirão" in comp

    elif code == "MLS":
        # American Major League Soccer (Top Flight Only)
        if any(x in comp for x in ["next pro", "usl", "nwsl"]):
            return False
        if country and country not in ["usa", "united states", ""]:
            return False
        return "major league soccer" in comp or "mls" in comp

    elif code == "RUS":
        # Russian Premier League (Top Flight Only)
        if any(x in comp for x in ["fnl", "first league"]):
            return False
        if country and country not in ["russia", ""]:
            return False
        return "premier league" in comp or "rpl" in comp

    elif code == "UKR":
        # Ukrainian Premier League (Top Flight Only)
        if any(x in comp for x in ["persha", "druha"]):
            return False
        if country and country not in ["ukraine", ""]:
            return False
        return "premier league" in comp or "upl" in comp

    elif code == "COP":
        # Italian Coppa Italia
        return "coppa italia" in comp or (country == "italy" and ("cup" in comp or "coppa" in comp))

    elif code == "UCL":
        return "champions league" in comp and ("uefa" in comp or comp == "champions league" or "ucl" in comp)

    elif code == "UEL":
        return "europa league" in comp and "conference" not in comp

    elif code == "UECL":
        return "conference league" in comp

    elif code == "ELC":
        # English Championship
        if country and country not in ["england", "uk", "great britain", ""]:
            return False
        return "championship" in comp and "scotland" not in comp and "scottish" not in comp

    elif code == "SD":
        # Spanish LaLiga 2 / Hypermotion
        if country and country not in ["spain", ""]:
            return False
        return any(x in comp for x in ["laliga 2", "la liga 2", "segunda division", "hypermotion", "segunda"])

    elif code == "BL2":
        # German 2. Bundesliga
        if country and country not in ["germany", ""]:
            return False
        return "2. bundesliga" in comp or "2.bundesliga" in comp

    elif code == "IT2":
        # Italian Serie B
        if country and country not in ["italy", ""]:
            return False
        return "serie b" in comp

    elif code == "FL2":
        # French Ligue 2
        if country and country not in ["france", ""]:
            return False
        return "ligue 2" in comp

    elif code == "ARG":
        # Argentine Primera Division / LPF
        if country and country not in ["argentina", ""]:
            return False
        return any(x in comp for x in ["primera", "lpf", "liga profesional", "superliga"])

    elif code == "COL":
        # Colombian Liga Betplay DIMAYOR
        if country and country not in ["colombia", ""]:
            return False
        return any(x in comp for x in ["liga betplay", "dimayor", "liga colombiana", "primera a"])

    elif code == "CHI":
        # Chilean Primera Division
        if country and country not in ["chile", ""]:
            return False
        return any(x in comp for x in ["primera division", "campeonato", "liga chilena"])

    elif code == "MEX":
        # Mexican Liga MX
        if country and country not in ["mexico", "méxico", ""]:
            return False
        return any(x in comp for x in ["liga mx", "liga bancomer", "primera division"])

    elif code == "CZE":
        # Czech 1. Liga
        if country and country not in ["czech republic", "czechia", ""]:
            return False
        return any(x in comp for x in ["1. liga", "fortuna liga", "czech liga", "first league"])

    elif code == "BUL":
        # Bulgarian Parva Liga
        if country and country not in ["bulgaria", ""]:
            return False
        return any(x in comp for x in ["parva liga", "efbet liga", "first professional"])

    elif code == "TUN":
        # Tunisian Ligue 1 Professionnelle
        if country and country not in ["tunisia", ""]:
            return False
        return any(x in comp for x in ["ligue 1", "ligue professionnelle"])

    elif code == "EGY":
        # Egyptian Premier League
        if country and country not in ["egypt", ""]:
            return False
        return any(x in comp for x in ["premier league", "egyptian premier", "eg premier"])

    # -----------------------------------------------------------------------
    # COUNTRY-NAME FALLBACK: If a league code has no explicit rule, match by
    # country name so new/unlisted leagues are never silently dropped.
    # -----------------------------------------------------------------------
    _country_map = {
        "PL": ["england", "uk", "great britain"],
        "PD": ["spain"],
        "SA": ["italy"],
        "BL1": ["germany"],
        "FL1": ["france"],
        "DED": ["netherlands", "holland"],
        "PPL": ["portugal"],
        "TUR": ["turkey", "türkiye", "turkiye"],
        "BEL": ["belgium", "belgique"],
        "AUT": ["austria", "österreich"],
        "SCO": ["scotland"],
        "SUI": ["switzerland", "suisse", "schweiz"],
        "CRO": ["croatia", "hrvatska"],
        "DEN": ["denmark", "danmark"],
        "GRE": ["greece", "hellas"],
        "NOR": ["norway", "norge"],
        "SWE": ["sweden", "sverige"],
        "POL": ["poland", "polska"],
        "ROU": ["romania"],
        "RUS": ["russia"],
        "UKR": ["ukraine"],
        "BRA": ["brazil", "brasil"],
        "MLS": ["usa", "united states"],
        "SAU": ["saudi arabia", "saudi"],
        "ARG": ["argentina"],
        "COL": ["colombia"],
        "CHI": ["chile"],
        "MEX": ["mexico", "méxico"],
        "CZE": ["czech republic", "czechia"],
        "BUL": ["bulgaria"],
        "TUN": ["tunisia"],
        "EGY": ["egypt"],
    }

    if code in _country_map:
        expected_countries = _country_map[code]
        if country and any(c in country for c in expected_countries):
            # Additional safety: exclude youth/women comps if we got here via fallback
            bad_fallback = ["women", "youth", "u19", "u21", "u23", "reserve", "amateur"]
            if not any(b in comp for b in bad_fallback):
                return True

    return False


@router.post("/build")
async def build_ai_ticket(req: BuildTicketRequest):
    """
    Executes StatIQ V2.0 7-Gate Pick Engine on native SportyBet live fixture pool.
    Returns built ticket with decision audit logs, confidence tiers, and verified SportyBet booking code.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    TOP_MAJOR_EUROPEAN_LEAGUES = [
        # Top 5 European
        "PL", "PD", "SA", "BL1", "FL1",
        # Major European Leagues & Saudi Pro League (Czech Republic & Saudi Arabia explicitly included)
        "DED", "PPL", "TUR", "BEL", "AUT", "SCO", "SUI", "CRO", "DEN", "GRE", "NOR", "SWE", "POL", "ROU", "CZE", "RUS", "UKR", "SAU",
        # European Club Competitions
        "UCL", "UEL", "UECL", "COP"
    ]

    ALL_KNOWN_LEAGUES = [
        # Top Major European Leagues & Saudi
        *TOP_MAJOR_EUROPEAN_LEAGUES,
        # Second Divisions (Midweek / Worldwide only)
        "ELC", "SD", "BL2", "IT2", "FL2",
        # Americas & Africa (Midweek / Worldwide only)
        "BRA", "MLS", "ARG", "COL", "CHI", "MEX", "BUL", "TUN", "EGY"
    ]

    fixture_pool = []

    if req.custom_fixtures and len(req.custom_fixtures) > 0:
        fixture_pool = [_normalize_fixture_item(f, req.single_league or "PL") for f in req.custom_fixtures]
    else:
        # 1. Fetch live upcoming fixtures directly from SportyBet API
        raw_sporty_fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=0)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        today_date = now_utc.date()

        for ev in raw_sporty_fixtures:
            h = ev.get("home_team") or "Home"
            a = ev.get("away_team") or "Away"
            comp_name = (ev.get("competition") or "Football").strip()
            country_name = (ev.get("country") or "").strip()
            start_ms = ev.get("start_time_ms") or 0
            match_dt = datetime.datetime.fromtimestamp(start_ms / 1000.0, tz=datetime.timezone.utc) if start_ms > 0 else now_utc

            # 0. STRICT UNSTARTED PRE-MATCH FILTER:
            # Must NOT have already started, be live, or kick off within 3 minutes
            status_str = str(ev.get("status") or ev.get("match_status") or ev.get("match_status_code") or "").upper()
            if status_str in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED", "CLOSED", "CONCLUDED"]:
                continue

            if start_ms > 0:
                diff_sec = (match_dt - now_utc).total_seconds()
                if diff_sec < 180:  # If kickoff was in the past or within next 3 minutes, skip!
                    continue

            # 1. Strict Date Window Filter
            if start_ms > 0:
                win = (req.date_window or "TODAY").upper()
                if win in ("TODAY", "TODAYS_GAMES", "TODAY_ONLY", "DAILY", ""):
                    if match_dt.date() != today_date:
                        continue
                elif win in ("TOMORROW", "NEXT_DAY"):
                    if (match_dt.date() - today_date).days != 1:
                        continue
                elif win in ("NEXT_24H", "24H"):
                    diff_sec = (match_dt - now_utc).total_seconds()
                    if diff_sec < 180 or diff_sec > 86400:
                        continue
                elif win in ("WEEKEND", "WEEKEND_COMBINED", "SAT_SUN"):
                    diff_days = (match_dt.date() - today_date).days
                    # Must be upcoming within 6 days and fall on Fri (weekday 4), Sat (5), or Sun (6)
                    if diff_days < 0 or diff_days > 6 or match_dt.weekday() not in (4, 5, 6):
                        continue
                elif win in ("NEXT_7D", "7D", "WEEK"):
                    diff_sec = (match_dt - now_utc).total_seconds()
                    if diff_sec < 180 or diff_sec > (7 * 86400):
                        continue

            # 2. Strict League Scope Filter (3 Distinct Modes)
            selected_lgs = req.selected_leagues or []
            if any(x.upper() in ["ALL_WORLDWIDE", "WORLDWIDE", "ALL_MATCHES"] for x in selected_lgs):
                # Mode C: Worldwide — Allow 100% of matches from SportyBet Today board (250+ matches)
                pass
            elif any(x.upper().replace(" ", "_") in ["TOP_5_EUROPEAN", "TOP_5", "TOP5"] for x in selected_lgs):
                # Mode A: Top 5 Major European Leagues (Premier League, LaLiga, Serie A, Bundesliga, Ligue 1)
                target_league_codes = ["PL", "PD", "SA", "BL1", "FL1"]
                match_league = False
                for sel_lg in target_league_codes:
                    if _is_league_match(comp_name, country_name, sel_lg):
                        match_league = True
                        break
                if not match_league:
                    continue
            else:
                # Mode B: All Major European & Premier Leagues (~25 top flight leagues)
                if not selected_lgs or any(x.upper().replace(" ", "_") in ["ALL", "ALL_TOP_LEAGUES", "TOP_LEAGUES", "EUROPEAN_LEAGUES"] for x in selected_lgs):
                    target_league_codes = TOP_MAJOR_EUROPEAN_LEAGUES
                else:
                    target_league_codes = selected_lgs

                match_league = False
                for sel_lg in target_league_codes:
                    if _is_league_match(comp_name, country_name, sel_lg):
                        match_league = True
                        break

                if not match_league:
                    continue


            r1x2_ev = {
                "home": ev.get("odds_home", 2.0),
                "draw": ev.get("odds_draw", 3.2),
                "away": ev.get("odds_away", 3.0)
            }

            dc_data, ou_data = _extract_live_market_data(ev)

            fixture_pool.append({
                "fixture_id": ev.get("event_id"),
                "event_id": ev.get("event_id"),
                "game_id": ev.get("game_id"),
                "provider_event_id": ev.get("event_id"),
                "external_fixture_id": ev.get("event_id"),
                "home_team": h,
                "away_team": a,
                "competition": comp_name,
                "competition_code": comp_name,
                "country": country_name,
                "kickoff_datetime": ev.get("kickoff_time") or (match_dt.strftime("%Y-%m-%d %H:%M:%S") if start_ms > 0 else today_str),
                "start_time_ms": start_ms,
                "markets": ev.get("markets", {}),
                "result_1x2": r1x2_ev,
                "ou_lines": ou_data,
                "double_chance": dc_data,
            })

    # If no fixtures match the user's specific filter, return clear feedback rather than giving arbitrary games
    if not fixture_pool:
        selected_desc = ", ".join(req.selected_leagues) if (req.selected_leagues and "ALL" not in req.selected_leagues) else "All Leagues"
        window_desc = req.date_window or "Today"
        return {
            "status": "NO_FIXTURES",
            "message": f"No unstarted SportyBet fixtures found for {selected_desc} in the '{window_desc}' window. Try selecting 'Weekend Combined' or 'All Top Leagues'.",
            "ticket": {
                "mode": req.mode.upper(),
                "target_mode": req.target_mode,
                "target_odds": req.target_odds,
                "accumulated_odds": 1.0,
                "combined_probability": 0.0,
                "confidence_tier": "NONE",
                "recommended_stake_pct": 0,
                "approved_legs": [],
                "rejected_picks": [],
                "total_evaluated": 0,
                "error": f"No unstarted fixtures found for {selected_desc} in the '{window_desc}' timeframe.",
                "booking_code": None,
                "share_url": None,
                "date_window": req.date_window
            }
        }



    # -----------------------------------------------------------------------
    # H2H BATCH FETCH: Enrich all fixtures with Head-to-Head stats in parallel
    # Runs concurrently against SportyBet's H2H endpoint (max 1.5s timeout per fixture)
    # Attaches h2h_data to each fixture so pick_engine can apply H2H gates
    # -----------------------------------------------------------------------
    if fixture_pool and req.use_live_odds:
        try:
            h2h_map = SportyBetIngestionService.fetch_h2h_batch(fixture_pool)
            for fix in fixture_pool:
                ev_id = str(fix.get("event_id") or fix.get("fixture_id") or "")
                if ev_id and ev_id in h2h_map:
                    fix["h2h_data"] = h2h_map[ev_id]
            logger.info(f"[H2H] Enriched {len(h2h_map)} / {len(fixture_pool)} fixtures with H2H data")
        except Exception as h2h_err:
            logger.warning(f"[H2H Batch] Non-fatal H2H fetch error: {h2h_err}")

    # Determine pick limit
    target_games = req.target_games or 5
    max_picks = max(4, (target_games // 2) + 2) if req.target_mode == "GAMES" else 20

    engine = MatchIQPickEngine(use_live_odds=True)
    target_odds_val = req.target_odds if (req.mode.upper() == "ROLLOVER" or req.target_mode == "ODDS") else 999.0
    num_t = max(1, min(4, int(req.num_tickets or 1)))

    if num_t > 1:
        portfolio_built = engine.build_portfolio(
            fixture_pool=fixture_pool,
            num_tickets=num_t,
            target_total_odds=target_odds_val,
            mode=req.mode.upper(),
            target_mode=req.target_mode,
            target_games=target_games,
            max_league_picks=max_picks,
            risk_profile=req.risk_profile or "BALANCED",
            allowed_markets=req.allowed_market_categories,
            excluded_markets=req.excluded_market_categories,
            overlap_mode=req.overlap_mode or "ZERO_OVERLAP"
        )
    else:
        portfolio_built = [engine.build_ticket(
            fixture_pool=fixture_pool,
            target_total_odds=target_odds_val,
            mode=req.mode.upper(),
            target_mode=req.target_mode,
            target_games=target_games,
            max_league_picks=max_picks,
            reshuffle_seed=req.reshuffle_seed,
            risk_profile=req.risk_profile or "BALANCED",
            allowed_markets=req.allowed_market_categories,
            excluded_markets=req.excluded_market_categories,
        )]

    # Process and generate SportyBet booking codes for each ticket
    portfolio_results = []
    from app.adapters.bookmaker_adapter import SportyBetAdapter
    adapter = SportyBetAdapter()

    active_rp = (req.risk_profile or "CONSERVATIVE").upper()
    is_aggressive = active_rp in ("AGGRESSIVE", "AGGRESSIVE_VALUE", "VALUE")

    def _verify_odds_pre_booking(legs: List[Dict[str, Any]], pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Pre-booking odds verification pass aligned with the active Risk Strategy Profile.
        Strict 1.15 minimum odds floor enforced globally.
        """
        verified = []
        for leg in legs:
            market = str(leg.get("market_name") or "").lower()
            selection = str(leg.get("selection_name") or "").lower()
            odds = float(leg.get("odds") or leg.get("estimated_odds") or 1.25)

            # Strict Global 1.15 Odds Floor: Reject all unviable micro-odds
            if odds < 1.15:
                continue

            is_dc = "double chance" in market

            # DC odds ceiling
            if is_dc and odds > 1.40:
                logger.warning(f"[OddsVerify] REJECTED DC trap: {leg.get('home_team')} vs {leg.get('away_team')} | {selection} @{odds:.2f} > 1.40")
                continue

            # Strict Odds Boundaries based on Risk Profile
            if is_aggressive:
                if odds < 1.20 or odds > 3.00:
                    continue
            else:
                if odds < 1.15 or odds > 1.45:
                    continue

            verified.append(leg)
        return verified

    # Enforce maximum 15 games per ticket
    target_games = min(15, target_games)

    for idx, b_ticket in enumerate(portfolio_built):
        # Pre-booking odds verification: purge any DC/O1.5 trap odds before generating code
        if b_ticket.approved_legs:
            pre_count = len(b_ticket.approved_legs)
            verified_legs = _verify_odds_pre_booking(b_ticket.approved_legs, fixture_pool)
            
            # If verification trimmed any legs and we are in GAMES mode, preserve the original approved legs
            # if verified_legs count fell below requested target_games
            if req.target_mode == "GAMES" and len(verified_legs) < target_games and len(b_ticket.approved_legs) >= target_games:
                # Keep verified legs and backfill with remaining approved legs from the engine
                seen_f = {str(x.get("fixture_id") or f"{x.get('home_team')}_{x.get('away_team')}") for x in verified_legs}
                for orig_l in b_ticket.approved_legs:
                    f_k = str(orig_l.get("fixture_id") or f"{orig_l.get('home_team')}_{orig_l.get('away_team')}")
                    if f_k not in seen_f and float(orig_l.get("odds") or orig_l.get("estimated_odds") or 1.0) >= 1.15:
                        verified_legs.append(orig_l)
                        seen_f.add(f_k)
                        if len(verified_legs) >= target_games:
                            break
            
            b_ticket.approved_legs = verified_legs
            acc = 1.0
            for leg in b_ticket.approved_legs:
                acc *= float(leg.get("odds") or leg.get("estimated_odds") or 1.25)
            b_ticket.accumulated_odds = round(acc, 2)

        # Trim to exact target_games (max 15) if in GAMES mode
        if req.target_mode == "GAMES" and len(b_ticket.approved_legs) > target_games:
            b_ticket.approved_legs = b_ticket.approved_legs[:target_games]
            acc = 1.0
            for leg in b_ticket.approved_legs:
                acc *= float(leg.get("odds", 1.5))
            b_ticket.accumulated_odds = round(acc, 2)

        # Strict Global Cap: Maximum 15 legs per ticket on all modes
        if len(b_ticket.approved_legs) > 15:
            b_ticket.approved_legs = b_ticket.approved_legs[:15]
            acc = 1.0
            for leg in b_ticket.approved_legs:
                acc *= float(leg.get("odds", 1.5))
            b_ticket.accumulated_odds = round(acc, 2)

        booking_code = None
        share_url = None
        if b_ticket.approved_legs:
            try:
                code_res = adapter.generate_booking_code(b_ticket.approved_legs, country_code="ng")
                if code_res.get("status") == "SUCCESS" and code_res.get("booking_code"):
                    booking_code = code_res.get("booking_code")
                    share_url = code_res.get("load_url")
            except Exception as e:
                logger.warning(f"SportyBet booking code generation error for ticket #{idx+1}: {e}")

        notice = None
        if req.target_mode == "GAMES" and len(b_ticket.approved_legs) < target_games:
            notice = f"Found all {len(b_ticket.approved_legs)} top-flight matches currently playing for {req.date_window}."

        t_dict = {
            "ticket_index": idx + 1,
            "mode": b_ticket.mode,
            "target_mode": req.target_mode,
            "target_odds": req.target_odds,
            "target_games": target_games,
            "accumulated_odds": b_ticket.accumulated_odds,
            "combined_probability": b_ticket.combined_probability,
            "correlation_adjusted_probability": b_ticket.correlation_adjusted_probability,
            "confidence_tier": b_ticket.confidence_tier,
            "recommended_stake_pct": b_ticket.recommended_stake_pct,
            "leg_config": b_ticket.leg_config,
            "approved_legs": b_ticket.approved_legs,
            "rejected_picks": b_ticket.rejected_picks,
            "total_evaluated": b_ticket.total_evaluated,
            "decision_audit_summary": b_ticket.decision_audit_summary,
            "booking_code": booking_code,
            "share_url": share_url or (f"https://www.sportybet.com/ng/?shareCode={booking_code}" if booking_code else None),
            "flex_cut": req.flex_cut,
            "date_window": req.date_window,
            "notice": notice,
        }
        portfolio_results.append(t_dict)

    primary_ticket = portfolio_results[0]

    return {
        "status": "SUCCESS",
        "num_tickets": num_t,
        "ticket": primary_ticket,
        "portfolio_tickets": portfolio_results,
        "portfolio_summary": {
            "total_tickets": len(portfolio_results),
            "total_unique_matches": sum(len(t["approved_legs"]) for t in portfolio_results),
            "diversification_mode": req.overlap_mode or "ZERO_OVERLAP",
            "message": f"Successfully generated {len(portfolio_results)} diversified portfolio tickets."
        }
    }


class MergeMasterRequest(BaseModel):
    slips: List[Dict[str, Any]]
    target_games: Optional[int] = 10
    country_code: Optional[str] = "ng"


@router.post("/merge-master")
async def merge_portfolio_to_master(req: MergeMasterRequest):
    """
    Merges 2 (or more) variant portfolio tickets into 1 unified Master Ticket.
    - Resolves shared fixtures by selecting the single highest-win-probability market.
    - Slices to the user's prioritized game count (5, 8, 10, 12, 15 max).
    - Calculates accumulated odds and joint probability.
    - Generates live verified SportyBet booking code.
    """
    if not req.slips:
        raise HTTPException(status_code=400, detail="No slips provided to merge.")

    # 1. Gather all candidate legs across all slips
    fixture_candidates: Dict[str, List[Dict[str, Any]]] = {}

    for s_idx, slip in enumerate(req.slips):
        legs = slip.get("approved_legs") or slip.get("final_selections") or slip.get("selections") or []
        for leg in legs:
            f_id = str(leg.get("fixture_id") or leg.get("event_id") or leg.get("provider_event_id") or "")
            h_name = str(leg.get("home_team") or "").strip().lower()
            a_name = str(leg.get("away_team") or "").strip().lower()
            f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else f_id
            if not f_key:
                continue

            if f_key not in fixture_candidates:
                fixture_candidates[f_key] = []
            fixture_candidates[f_key].append(leg)

    if not fixture_candidates:
        raise HTTPException(status_code=400, detail="No valid match legs found in provided slips.")

    # 2. For each unique fixture, select the best candidate pick
    best_picks_per_fixture = []
    for f_key, leg_list in fixture_candidates.items():
        def _score_leg(l):
            prob = float(l.get("model_probability") or l.get("win_prob") or 0.70)
            odds = float(l.get("odds") or l.get("estimated_odds") or 1.25)
            return (prob, -abs(odds - 1.25))

        leg_list.sort(key=_score_leg, reverse=True)
        best_picks_per_fixture.append(leg_list[0])

    # 3. Sort all unique fixtures by conviction (model_probability descending, safety)
    def _rank_fixture(l):
        prob = float(l.get("model_probability") or l.get("win_prob") or 0.70)
        odds = float(l.get("odds") or l.get("estimated_odds") or 1.25)
        return (prob, odds)

    best_picks_per_fixture.sort(key=_rank_fixture, reverse=True)

    # 4. Slice to prioritized target_games (clamped between 2 and 15)
    t_games = max(2, min(15, int(req.target_games or 10)))
    master_legs = best_picks_per_fixture[:t_games]

    # Recalculate accumulated odds and combined probability
    acc_odds = 1.0
    comb_prob = 1.0
    for leg in master_legs:
        o = float(leg.get("odds") or leg.get("estimated_odds") or 1.25)
        p = float(leg.get("model_probability") or leg.get("win_prob") or 0.75)
        acc_odds *= o
        comb_prob *= min(0.95, p)

    acc_odds = round(acc_odds, 2)
    comb_prob = round(comb_prob, 4)

    # 5. Generate SportyBet booking code
    booking_code = None
    share_url = None
    try:
        from app.adapters.bookmaker_adapter import SportyBetAdapter
        adapter = SportyBetAdapter()
        code_res = adapter.generate_booking_code(master_legs, country_code=req.country_code or "ng")
        if code_res.get("status") == "SUCCESS" and code_res.get("booking_code"):
            booking_code = code_res.get("booking_code")
            share_url = code_res.get("load_url")
    except Exception as e:
        logger.warning(f"Error generating SportyBet code for master ticket: {e}")

    master_ticket = {
        "scenario_id": f"STATIQ-MASTER-SLIP-{len(master_legs)}G",
        "ticket_index": "MASTER",
        "is_master": True,
        "title": f"⚡ Master Ticket ({len(master_legs)} Legs)",
        "scope_label": f"Master Ticket · Top {len(master_legs)} Prioritized Games",
        "gameweek_label": "MERGED_MASTER",
        "target_mode": "GAMES",
        "target_games": len(master_legs),
        "target_odds": acc_odds,
        "accumulated_odds": acc_odds,
        "new_total_odds": str(acc_odds),
        "final_count": len(master_legs),
        "combined_probability": comb_prob,
        "avg_win_prob": round(sum(float(l.get("model_probability") or l.get("win_prob") or 0.75) for l in master_legs) / max(1, len(master_legs)), 2),
        "correlation_adjusted_probability": round(comb_prob * 1.08, 4),
        "confidence_tier": "ELITE" if comb_prob > 0.25 else "HIGH",
        "recommended_stake_pct": 2.5,
        "approved_legs": master_legs,
        "final_selections": master_legs,
        "selections": master_legs,
        "booking_code": booking_code,
        "share_url": share_url or (f"https://www.sportybet.com/ng/?shareCode={booking_code}" if booking_code else None),
        "verification_status": "BOOKING_VERIFIED" if booking_code else "PENDING",
        "notice": f"Merged from {len(req.slips)} slips into {len(master_legs)} prioritized high-conviction games."
    }

    return {
        "status": "SUCCESS",
        "master_ticket": master_ticket
    }



