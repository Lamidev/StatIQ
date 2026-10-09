"""
MatchIQ AI Ticket & Rollover Builder API Endpoint
===================================================
Uses MatchIQPickEngine 5-Gate Pipeline to evaluate live/historical fixture pools
and build high-confidence accumulator tickets or multi-day rollover strategies.
"""

import re
import httpx
import asyncio
import logging
import datetime
import time
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher
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
    exclude_fixture_ids: Optional[List[str]] = None


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
            
        # Double Chance (Market 10)
        if m_id == "10" or ("double chance" in m_desc and not any(k in m_desc for k in ["&", "over", "under"])):
            for o in outcomes:
                o_id = str(o.get("outcome_id") or o.get("id") or "")
                o_desc = str(o.get("selection_name") or o.get("desc") or "").upper()
                try:
                    ov = float(o.get("odds") or o.get("oddsValue") or 0.0)
                    if ov >= 1.00:
                        if o_id == "9" or "1X" in o_desc: dc_map["1X"] = ov
                        elif o_id == "11" or "X2" in o_desc: dc_map["X2"] = ov
                        elif o_id == "10" or "12" in o_desc: dc_map["12"] = ov
                except Exception:
                    pass
                    
        # Over/Under Goals: Strictly extract genuine FULL-MATCH Over/Under lines (Market 18 ONLY)
        is_ft_ou = (m_id == "18") or (
            m_desc in ["over/under", "total goals", "goals over/under", "over/under goals", "match goals"] and
            not any(k in m_desc for k in ["1st half", "2nd half", "half", "corner", "card", "early", "booking", "team", "first", "second", "1h", "2h", "home", "away"])
        )

        if is_ft_ou:
            line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
            line_str = line_m.group(1) if line_m else "1.5"
            o_val = None
            u_val = None
            for o in outcomes:
                o_desc = str(o.get("selection_name") or o.get("desc") or "").lower()
                o_id = str(o.get("outcome_id") or o.get("id") or "")
                try:
                    ov = float(o.get("odds") or o.get("oddsValue") or 0.0)
                    if ov >= 1.00:
                        if "over" in o_desc or o_id == "12": o_val = ov
                        elif "under" in o_desc or o_id == "13": u_val = ov
                except Exception:
                    pass
            if o_val or u_val:
                ou_list.append({"line": line_str, "over": o_val, "under": u_val, "is_real": True})
                
    # Double Chance conversion from 1X2 ONLY for legacy mock feeds if raw_mkts is completely absent
    if not raw_mkts:
        if "1X" not in dc_map and o_h > 1.0 and o_d > 1.0:
            dc_map["1X"] = round(1.0 / max(0.01, (1.0 / o_h + 1.0 / o_d) * 1.08), 2)
        if "X2" not in dc_map and o_a > 1.0 and o_d > 1.0:
            dc_map["X2"] = round(1.0 / max(0.01, (1.0 / o_a + 1.0 / o_d) * 1.08), 2)
        if "12" not in dc_map and o_h > 1.0 and o_a > 1.0:
            dc_map["12"] = round(1.0 / max(0.01, (1.0 / o_h + 1.0 / o_a) * 1.08), 2)

    # STRICT: Never fabricate synthetic Over/Under lines (1.5, 2.5, 3.5, 4.5).
    # Only lines verified and published by the bookmaker are permitted.
    return dc_map, ou_list

def _is_league_match(comp_name: str, country_name: str, code_key: str, home_team: str = "", away_team: str = "") -> bool:
    comp = (comp_name or "").strip().lower()
    country = (country_name or "").strip().lower()
    code = (code_key or "").upper()
    h = (home_team or "").strip().lower()
    a = (away_team or "").strip().lower()

    # Reject non-top flight attributes universally unless specifically a cup or tier-2/3 code
    is_international_code = code in ["INT", "INTERNATIONAL", "INTL", "ALL_INTL", "UNL", "WCQ", "AFCON", "CONCACAF", "INT_FRIENDLY", "GULF_CUP", "INTERNATIONAL_BREAK"]
    is_cup_code = (code in ["UCL", "UEL", "UECL", "COP", "FAC", "CDR", "DFB", "CDF", "TCP", "KNVB", "SCOC", "EFL"]) or is_international_code
    is_lower_allowed = code in ["ELC", "SD", "BL2", "IT2", "FL2", "EL1", "EL2", "DED2", "BEL2", "SUI2", "PPL2", "SCO2", "POL2", "DEN2"]

    # Universal rejection: Simulated Reality Leagues (SRL) & Club Friendly matches
    if any(x in comp for x in ["srl", "simulated reality", "simulated", "club friendly", "club friendlies"]):
        return False

    cup_keywords = ["cup", "trophy", "kupa", "pokal", "coppa", "taça", "taca", "copa", "shield", "beker"]
    tier_keywords = ["serie c", "serie d", "liga 3", "3. liga", "persha", "druha"]

    # Strict reserve, youth, academy, and amateur filter across competition and team names
    bad_tokens = [
        "women", "femenino", "feminin", "damen", "damallsvenskan", "frauen", "vrouwen", "kvinner", "bayanlar", "femmes", "wom.",
        "u23", "u21", "u20", "u19", "u18", "u17", "youth", "primavera", "reserve", "reserves",
        "amateur"
    ]
    if any(x in comp for x in bad_tokens):
        return False

    # Check team names for reserve / academy suffixes (e.g., "Szeged Akademia II", "Bayern II", "Barcelona B")
    # Use word boundary / spacing check to avoid false positives on normal club names
    for team_str in [h, a]:
        padded = f" {team_str} "
        if any(p in padded for p in [
            " ii ", " iii ", " iv ", " 2 ", " 3 ", " u23 ", " u21 ", " u20 ", " u19 ", " u18 ", " u17 ",
            " youth ", " primavera ", " reserve ", " reserves ", " amateur ", " akademia ", " academy ",
            " b team ", " b-team ", " (am) ", " (b) ", " b squad ", " women ", " wfc ", " dff "
        ]):
            # Exception: Willem II is a legitimate Dutch top-flight club
            if "willem ii" in padded:
                pass
            else:
                return False
        # Catch teams ending in " b" (e.g. "barcelona b", "porto b", "benfica b", "sociedad b") or women's club suffixes
        if team_str.endswith(" b") and not is_lower_allowed:
            return False
        if any(team_str.endswith(sfx) for sfx in [" dff", " wfc", " women", " (w)"]):
            return False

    if not is_cup_code and any(x in comp for x in cup_keywords):
        return False

    if not is_lower_allowed and any(x in comp for x in tier_keywords):
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
    elif code == "IRL":
        # Irish Premier Division
        if country and country not in ["ireland", "republic of ireland", ""]:
            return False
        return "premier division" in comp or "premier" in comp

    elif code == "DED2":
        # Dutch Eerste Divisie (Keuken Kampioen Divisie)
        if country and country not in ["netherlands", "holland", ""]:
            return False
        return "eerste divisie" in comp or "eerste" in comp or "keuken" in comp

    elif code == "SUI2":
        # Swiss Challenge League
        if country and country not in ["switzerland", "suisse", "schweiz", ""]:
            return False
        return "challenge league" in comp or "challenge" in comp

    elif code == "BEL2":
        # Belgian Challenger Pro League
        if country and country not in ["belgium", "belgique", ""]:
            return False
        return "challenger pro" in comp or "challenger" in comp or "first division b" in comp

    elif code == "WAL":
        # Welsh Cymru Premier
        if country and country not in ["wales", ""]:
            return False
        return "cymru premier" in comp or "cymru" in comp or ("premier" in comp and country == "wales")

    elif code == "SRB":
        # Serbian Superliga
        if country and country not in ["serbia", ""]:
            return False
        return "superliga" in comp or "super liga" in comp or "prva liga" in comp

    elif code == "SCO2":
        # Scottish Championship & Cup
        if country and country not in ["scotland", ""]:
            return False
        return any(x in comp for x in ["championship", "league cup", "fa cup", "challenge cup"])

    elif code == "PPL2":
        # Portuguese Liga Portugal 2
        if country and country not in ["portugal", ""]:
            return False
        return any(x in comp for x in ["liga 2", "segunda liga", "liga portugal 2"])

    elif code == "POL2":
        # Polish 1. Liga
        if country and country not in ["poland", "polska", ""]:
            return False
        return "1. liga" in comp or "1.liga" in comp or "i liga" in comp

    elif code == "DEN2":
        # Danish 1. Division
        if country and country not in ["denmark", "danmark", ""]:
            return False
    elif code in ["FAC", "FA_CUP"]:
        # English FA Cup
        if country and country not in ["england", "uk", "great britain", ""]:
            return False
        return "fa cup" in comp and "women" not in comp and "youth" not in comp

    elif code in ["EL1", "LEAGUE_ONE"]:
        # English League One
        if country and country not in ["england", "uk", "great britain", ""]:
            return False
        return "league one" in comp and "scotland" not in comp and "women" not in comp

    elif code in ["EL2", "LEAGUE_TWO"]:
        # English League Two
        if country and country not in ["england", "uk", "great britain", ""]:
            return False
        return "league two" in comp and "scotland" not in comp and "women" not in comp

    elif code in ["EFL", "CARABAO"]:
        # English EFL Cup
        if country and country not in ["england", "uk", "great britain", ""]:
            return False
        return any(x in comp for x in ["efl cup", "league cup", "carabao"])

    elif code in ["CDR", "COPA_DEL_REY"]:
        # Spanish Copa del Rey
        if country and country not in ["spain", ""]:
            return False
        return "copa del rey" in comp or (country == "spain" and "copa" in comp)

    elif code in ["DFB", "DFB_POKAL"]:
        # German DFB Pokal
        if country and country not in ["germany", ""]:
            return False
        return "dfb" in comp or "pokal" in comp

    elif code in ["CDF", "COUPE_DE_FRANCE"]:
        # French Coupe de France
        if country and country not in ["france", ""]:
            return False
        return "coupe de france" in comp or (country == "france" and "coupe" in comp)

    elif code in ["TCP", "TACA_DE_PORTUGAL"]:
        # Portuguese Taca de Portugal
        if country and country not in ["portugal", ""]:
            return False
        return any(x in comp for x in ["taca de portugal", "taça de portugal", "taca"])

    elif code in ["KNVB", "BEKER"]:
        # Dutch KNVB Beker
        if country and country not in ["netherlands", "holland", ""]:
            return False
        return "knvb" in comp or "beker" in comp

    elif code in ["SCOC", "SCOTTISH_CUP"]:
        # Scottish FA Cup
        if country and country not in ["scotland", ""]:
            return False
        return "scottish cup" in comp or ("scotland" in comp and "cup" in comp)

    elif code == "HUN":
        # Hungarian NB I (Strict Top Flight Only)
        if country and country not in ["hungary", "ungarn", ""]:
            return False
        if any(x in comp for x in ["nb ii", "nb iii", "nb 2", "nb 3", "nb iv", "megye", "kupa", "cup"]):
            return False
        comp_padded = f" {comp} "
        return (" nb i " in comp_padded) or (" nb 1 " in comp_padded) or (" otp bank " in comp_padded)

    elif code == "SVK":
        # Slovak Superliga
        if country and country not in ["slovakia", "slowakei", ""]:
            return False
        return "superliga" in comp or "nike liga" in comp or "fortuna liga" in comp

    elif code in ["UNL", "NATIONS_LEAGUE"]:
        # UEFA Nations League (Senior Men)
        if any(x in comp for x in ["u21", "u19", "women", "femenino"]):
            return False
        return "nations league" in comp and "concacaf" not in comp

    elif code in ["WCQ", "WORLD_CUP_QUAL", "WORLD_CUP"]:
        # World Cup Qualification (UEFA, CAF, CONMEBOL, AFC, CONCACAF)
        if any(x in comp for x in ["u20", "u17", "women", "femenino"]):
            return False
        return "world cup" in comp

    elif code in ["AFCON", "AFCON_QUAL", "AFRICA_CUP"]:
        # Africa Cup of Nations & Qualifiers
        if any(x in comp for x in ["u20", "u17", "women", "femenino"]):
            return False
        return "africa cup" in comp or "afcon" in comp

    elif code in ["CONCACAF", "CONCACAF_NL"]:
        # CONCACAF Nations League
        if any(x in comp for x in ["women", "femenino"]):
            return False
        return "concacaf" in comp and "nations league" in comp

    elif code in ["INT_FRIENDLY", "FRIENDLY_INT"]:
        # Senior Men's International Friendlies
        if country and country not in ["international", "world", "europe", "africa", "asia", "americas", ""]:
            return False
        if any(x in comp for x in ["club friendly", "club", "women", "femenino", "u21", "u19"]):
            return False
        return any(x in comp for x in ["friendly games", "friendlies", "int. friendly"])

    elif code in ["INT", "INTERNATIONAL", "INTL", "ALL_INTL", "INTERNATIONAL_BREAK"]:
        # Universal Senior Men's International Tournament & Qualifier Handler
        if any(bad in comp for bad in ["u23", "u21", "u20", "u19", "u18", "u17", "youth", "women", "femenino", "club friendly"]):
            return False
        is_intl_cat = country in ["international", "world", "europe", "africa", "asia", "americas", ""] or "international" in comp
        intl_tournaments = [
            "nations league", "africa cup", "afcon", "world cup", "euro qualification",
            "european championship", "copa america", "asian cup", "gulf cup", "friendly games", "int. friendly"
        ]
        return is_intl_cat and any(t in comp for t in intl_tournaments)

    # -----------------------------------------------------------------------
    # Explicitly checked codes must not match arbitrary lower divisions via fallback:
    # -----------------------------------------------------------------------
    EXPLICITLY_HANDLED_CODES = {
        "PL", "PD", "SA", "BL1", "FL1", "DED", "PPL", "TUR", "BEL", "AUT",
        "SCO", "SUI", "CRO", "DEN", "GRE", "NOR", "SWE", "POL", "ROU", "ROM",
        "RUS", "UKR", "BRA", "MLS", "ARG", "COL", "CHI", "MEX", "CZE", "BUL",
        "TUN", "EGY", "SAU", "COP", "UCL", "UEL", "UECL", "ELC", "SD", "BL2",
        "IT2", "FL2", "IRL", "DED2", "SUI2", "BEL2", "WAL", "SRB", "SCO2", "PPL2",
        "POL2", "DEN2", "FAC", "EL1", "EL2", "EFL", "CDR", "DFB", "CDF", "TCP",
        "KNVB", "SCOC", "HUN", "SVK", "SVN",
        "INT", "INTERNATIONAL", "INTL", "ALL_INTL", "UNL", "WCQ", "AFCON", "CONCACAF", "INT_FRIENDLY", "INTERNATIONAL_BREAK"
    }
    if code in EXPLICITLY_HANDLED_CODES:
        return False

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
        # Top 5 European Flights
        "PL", "PD", "SA", "BL1", "FL1",
        # Major European Top Flights
        "DED", "PPL", "TUR", "BEL", "AUT", "SCO", "SUI", "CRO", "DEN", "GRE", "NOR", "SWE", "POL", "ROU", "CZE", "RUS", "UKR", "SAU",
        # High-Liquidity Major European Tier-2 Flights
        "ELC", "SD", "BL2", "IT2", "FL2",
        # UEFA Continental Tournaments
        "UCL", "UEL", "UECL",
        # Senior International Tournaments & Qualifiers (Dynamic Break Coverage)
        "INT", "UNL", "WCQ", "AFCON", "CONCACAF", "INT_FRIENDLY"
    ]

    ALL_KNOWN_LEAGUES = [
        # Major European Top Flights, Tier-2 & UEFA & International
        *TOP_MAJOR_EUROPEAN_LEAGUES,
        # Secondary Regional Leagues (Optional/Explicit selection)
        "DED2", "HUN",
        # Americas & Africa (Worldwide only)
        "BRA", "MLS", "ARG", "COL", "CHI", "MEX", "TUN", "EGY"
    ]

    fixture_pool = []

    selected_lgs = req.selected_leagues or []
    is_today_live_requested = any(x.upper() in ["ALL_TODAY", "ALL_SPORTYBET", "SPORTYBET_TODAY", "ALL_WORLDWIDE", "ALL_MATCHES"] for x in selected_lgs) or (req.date_window == "TODAY")

    if req.custom_fixtures and len(req.custom_fixtures) > 0:
        fixture_pool = [_normalize_fixture_item(f, req.single_league or "PL") for f in req.custom_fixtures]
    else:
        raw_sporty_fixtures = []

        # 1. Fetch directly from SportyBet's LIVE Today endpoint if requested
        if is_today_live_requested:
            from app.services.elite_rollover_engine import EliteRolloverEngine
            try:
                live_events = await EliteRolloverEngine.fetch_sportybet_today_events(max_pages=4)
                if live_events:
                    raw_sporty_fixtures = SportyBetIngestionService._normalize_events(live_events)
                    logger.info(f"[TicketBuilder] Live feed loaded {len(raw_sporty_fixtures)} bettable fixtures directly from SportyBet Today API.")
            except Exception as e:
                logger.warning(f"[TicketBuilder] Live SportyBet Today fetch failed, falling back to mirror DB: {e}")
                raw_sporty_fixtures = []

        # 2. Fallback to local SportyBet Mirror DB or ingestion service
        if not raw_sporty_fixtures:
            from sqlalchemy.orm import selectinload, joinedload
            from app.db.session import SessionLocal
            from app.db.models import SportyBetEvent, SportyBetMarket
            db_sess = SessionLocal()
            try:
                db_events = (
                    db_sess.query(SportyBetEvent)
                    .options(
                        joinedload(SportyBetEvent.competition_rel),
                        selectinload(SportyBetEvent.markets).selectinload(SportyBetMarket.outcomes)
                    )
                    .filter(SportyBetEvent.status == "SCHEDULED")
                    .all()
                )
                if db_events and len(db_events) > 0:
                    now_ms = time.time() * 1000.0
                    for ev in db_events:
                        # 10-minute pre-match cutoff on mirror events (SportyBet suspends markets under 10m)
                        if ev.start_time_ms and ev.start_time_ms <= (now_ms + 600000):
                            continue

                        comp_name = ev.competition_rel.name if ev.competition_rel else "Football"
                        country_name = ev.competition_rel.country if ev.competition_rel else None

                        # Extract 1X2 odds
                        o_h, o_d, o_a = 2.50, 3.00, 2.50
                        m1 = next((m for m in ev.markets if str(m.sporty_market_id) == "1" and (m.status is None or str(m.status) == "0")), None)
                        if m1:
                            for oc in m1.outcomes:
                                if oc.status is not None and str(oc.status) != "0": continue
                                sel_u = oc.selection.upper()
                                if sel_u in ["1", "HOME", ev.home_team.upper()]: o_h = oc.odds
                                elif sel_u in ["X", "DRAW"]: o_d = oc.odds
                                elif sel_u in ["2", "AWAY", ev.away_team.upper()]: o_a = oc.odds

                        # Extract Markets
                        dc_map = {}
                        ou_list = []
                        btts_dict = {}
                        home_goals_list = []
                        away_goals_list = []

                        for m in ev.markets:
                            # Strict: skip non-active/suspended markets
                            if m.status is not None and str(m.status) != "0":
                                continue
                            m_id = str(m.sporty_market_id or "")
                            m_desc = (m.market_name or "").lower()
                            spec = str(m.specifier or "")

                            # Double Chance (Market 10)
                            if m_id == "10" or "double chance" in m_desc:
                                for oc in m.outcomes:
                                    if oc.status is not None and str(oc.status) != "0": continue
                                    o_desc = (oc.selection or "").upper()
                                    o_id = str(oc.sporty_outcome_id or "")
                                    ov = float(oc.odds or 0.0)
                                    if ov >= 1.15:
                                        if o_id == "9" or "1X" in o_desc: dc_map["1X"] = ov
                                        elif o_id == "11" or "X2" in o_desc: dc_map["X2"] = ov
                                        elif o_id == "10" or "12" in o_desc: dc_map["12"] = ov

                            # Over/Under (Market 18 ONLY)
                            elif m_id == "18" or (
                                m_desc in ["over/under", "total goals", "goals over/under", "over/under goals", "match goals"] and
                                not any(k in m_desc for k in ["1st half", "2nd half", "half", "corner", "card", "early", "booking", "team", "first", "second", "1h", "2h", "home", "away"])
                            ):
                                line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                                line_str = line_m.group(1) if line_m else "1.5"
                                o_val, u_val = None, None
                                for oc in m.outcomes:
                                    if oc.status is not None and str(oc.status) != "0": continue
                                    o_desc = (oc.selection or "").lower()
                                    o_id = str(oc.sporty_outcome_id or "")
                                    ov = float(oc.odds or 0.0)
                                    if ov >= 1.15:
                                        if "over" in o_desc or o_id == "12": o_val = ov
                                        elif "under" in o_desc or o_id == "13": u_val = ov
                                if o_val or u_val:
                                    ou_list.append({"line": line_str, "over": o_val, "under": u_val, "specifier": f"total={line_str}"})

                            # BTTS (Market 29)
                            elif m_id == "29" or "both teams to score" in m_desc:
                                for oc in m.outcomes:
                                    if oc.status is not None and str(oc.status) != "0": continue
                                    sel_u = (oc.selection or "").upper()
                                    ov = float(oc.odds or 0.0)
                                    if ov >= 1.15:
                                        if sel_u in ["YES", "GG"]: btts_dict["yes"] = oc.odds; btts_dict["yes_id"] = oc.sporty_outcome_id
                                        elif sel_u in ["NO", "NG"]: btts_dict["no"] = oc.odds; btts_dict["no_id"] = oc.sport_outcome_id
                                if btts_dict: btts_dict["market_id"] = "29"

                            # Home Team Goals (Market 19)
                            elif m_id == "19" or ("home" in m_desc and "over/under" in m_desc):
                                line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                                line_str = line_m.group(1) if line_m else "1.5"
                                o_val, u_val = None, None
                                for oc in m.outcomes:
                                    if oc.status is not None and str(oc.status) != "0": continue
                                    o_desc = (oc.selection or "").lower()
                                    o_id = str(oc.sporty_outcome_id or "")
                                    ov = float(oc.odds or 0.0)
                                    if ov >= 1.15:
                                        if "over" in o_desc or o_id == "12": o_val = ov
                                        elif "under" in o_desc or o_id == "13": u_val = ov
                                if o_val or u_val:
                                    home_goals_list.append({"line": line_str, "over": o_val, "under": u_val, "market_id": "19", "specifier": f"total={line_str}"})

                            # Away Team Goals (Market 20)
                            elif m_id == "20" or ("away" in m_desc and "over/under" in m_desc):
                                line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                                line_str = line_m.group(1) if line_m else "1.5"
                                o_val, u_val = None, None
                                for oc in m.outcomes:
                                    if oc.status is not None and str(oc.status) != "0": continue
                                    o_desc = (oc.selection or "").lower()
                                    o_id = str(oc.sporty_outcome_id or "")
                                    ov = float(oc.odds or 0.0)
                                    if ov >= 1.15:
                                        if "over" in o_desc or o_id == "12": o_val = ov
                                        elif "under" in o_desc or o_id == "13": u_val = ov
                                if o_val or u_val:
                                    away_goals_list.append({"line": line_str, "over": o_val, "under": u_val, "market_id": "20", "specifier": f"total={line_str}"})

                        raw_sporty_fixtures.append({
                            "id": f"fx_{ev.sporty_game_id}" if ev.sporty_game_id else f"fx_{ev.sporty_event_id.replace(':', '_')}",
                            "event_id": ev.sporty_event_id,
                            "game_id": ev.sporty_game_id,
                            "home_team": ev.home_team,
                            "away_team": ev.away_team,
                            "country": country_name,
                            "competition": comp_name,
                            "kickoff_time": ev.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "start_time_ms": ev.start_time_ms,
                            "status": ev.status,
                            "match_status": ev.status,
                            "odds_home": o_h,
                            "odds_draw": o_d,
                            "odds_away": o_a,
                            "double_chance": dc_map,
                            "ou_lines": ou_list,
                            "home_team_goals": home_goals_list,
                            "away_team_goals": away_goals_list,
                            "btts": btts_dict,
                            "markets": [
                                {
                                    "market_id": m.sporty_market_id,
                                    "market_name": m.market_name,
                                    "market_type": m.market_type,
                                    "specifier": m.specifier,
                                    "outcomes": [
                                        {"outcome_id": oc.sporty_outcome_id, "selection_name": oc.selection, "odds": oc.odds, "probability": oc.probability}
                                        for oc in m.outcomes if (oc.status is None or str(oc.status) == "0") and float(oc.odds or 0) >= 1.15
                                    ]
                                }
                                for m in ev.markets if (m.status is None or str(m.status) == "0")
                            ],
                            "provider": "SPORTYBET"
                        })
                else:
                    raw_sporty_fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=0)
            finally:
                db_sess.close()

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
            # Must NOT have already started, be live, or kick off within 10 minutes
            status_str = str(ev.get("status") or ev.get("match_status") or ev.get("match_status_code") or "").upper()
            if status_str in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED", "CLOSED", "CONCLUDED"]:
                continue

            if start_ms > 0:
                diff_sec = (match_dt - now_utc).total_seconds()
                if diff_sec < 600:  # If kickoff was in the past or within next 10 minutes, skip!
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
                elif win in ("MIDWEEK", "MIDWEEK_COMBINED", "TUE_WED_THU"):
                    diff_days = (match_dt.date() - today_date).days
                    # Must be upcoming within 5 days and fall on Tue (1), Wed (2), or Thu (3)
                    if diff_days < 0 or diff_days > 5 or match_dt.weekday() not in (1, 2, 3):
                        continue
                elif win in ("NEXT_48H", "48H", "2D"):
                    diff_sec = (match_dt - now_utc).total_seconds()
                    if diff_sec < 180 or diff_sec > (2 * 86400):
                        continue
                elif win in ("NEXT_72H", "72H", "3D"):
                    diff_sec = (match_dt - now_utc).total_seconds()
                    if diff_sec < 180 or diff_sec > (3 * 86400):
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

            # 1b. Exclude Previous Matches (Sequential Redo)
            if req.exclude_fixture_ids:
                norm_ex = {str(x).strip().lower() for x in req.exclude_fixture_ids if x}
                ev_id = str(ev.get("event_id") or "").strip().lower()
                game_id = str(ev.get("game_id") or "").strip().lower()
                match_key = f"{h.strip().lower()}_{a.strip().lower()}"
                if ev_id in norm_ex or game_id in norm_ex or match_key in norm_ex:
                    continue

            # 2. Strict League Scope Filter (4 Distinct Modes)
            selected_lgs = req.selected_leagues or []
            is_all_pool = any(x.upper() in ["ALL_WORLDWIDE", "WORLDWIDE", "ALL_MATCHES", "ALL_TODAY", "ALL_SPORTYBET", "SPORTYBET_TODAY"] for x in selected_lgs) or (req.league_scope in ["ALL_TODAY", "WORLDWIDE", "ALL"] and not selected_lgs)
            if is_all_pool:
                # Mode C: Full SportyBet Today Pool — Scan 100% of matches across club & international fixtures
                comp_l = comp_name.lower()
                # Anti-noise filter: protect ticket from SRL, club friendlies, youth, and women's exhibition matches
                if any(x in comp_l for x in ["srl", "simulated reality", "simulated", "club friendly", "club friendlies", "u21", "u19", "u23", "u20", "u18", "u17", "youth", "women", "damallsvenskan", "femenino", "frauen"]):
                    continue
                skip_res = False
                for team_str in [h.lower(), a.lower()]:
                    if any(team_str.endswith(sfx) for sfx in [" dff", " wfc", " women", " (w)", " b", " ii"]):
                        skip_res = True
                        break
                    padded = f" {team_str} "
                    if any(p in padded for p in [" ii ", " iii ", " b team ", " b-team ", " reserve ", " reserves ", " amateur "]):
                        if "willem ii" not in padded:
                            skip_res = True
                            break
                if skip_res:
                    continue
            elif any(x.upper().replace(" ", "_") in ["TOP_5_EUROPEAN", "TOP_5", "TOP5"] for x in selected_lgs):
                # Mode A: Top 5 Major European Leagues (Premier League, LaLiga, Serie A, Bundesliga, Ligue 1)
                target_league_codes = ["PL", "PD", "SA", "BL1", "FL1"]
                match_league = False
                for sel_lg in target_league_codes:
                    if _is_league_match(comp_name, country_name, sel_lg, home_team=h, away_team=a):
                        match_league = True
                        break
                if not match_league:
                    continue
            elif any(x.upper().replace(" ", "_") in ["INTERNATIONAL", "INT", "INTL", "INTERNATIONAL_BREAK", "NATIONS_LEAGUE"] for x in selected_lgs):
                # Mode D: Dedicated International Break Scope (Senior Men's International Matches)
                target_league_codes = ["INT", "UNL", "WCQ", "AFCON", "CONCACAF", "INT_FRIENDLY"]
                match_league = False
                for sel_lg in target_league_codes:
                    if _is_league_match(comp_name, country_name, sel_lg, home_team=h, away_team=a):
                        match_league = True
                        break
                if not match_league:
                    continue
            else:
                # Mode B: If specific individual leagues are selected (e.g. ['PL']), filter by them.
                # If 'ALL', 'ALL_TOP_LEAGUES', 'TOP_LEAGUES', or empty, accept all valid senior competitive matches!
                if not selected_lgs or any(x.upper().replace(" ", "_") in ["ALL", "ALL_TOP_LEAGUES", "TOP_LEAGUES", "EUROPEAN_LEAGUES", "ALL_WORLDWIDE", "ALL_TODAY"] for x in selected_lgs):
                    pass  # Accept full competitive match catalogue
                else:
                    target_league_codes = selected_lgs
                    match_league = False
                    for sel_lg in target_league_codes:
                        if _is_league_match(comp_name, country_name, sel_lg, home_team=h, away_team=a):
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
            dc_use = ev.get("double_chance") or dc_data
            ou_use = ev.get("ou_lines") or ou_data

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
                "ou_lines": ou_use,
                "double_chance": dc_use,
                "btts": ev.get("btts", {}),
                "home_team_goals": ev.get("home_team_goals", []),
                "away_team_goals": ev.get("away_team_goals", []),
                "handicaps": ev.get("handicaps", []),
                "half_1x2": ev.get("half_1x2", {}),
                "half_ou": ev.get("half_ou", []),
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
                logger.warning(f"[OddsVerify] REJECTED micro-odd: {leg.get('home_team')} vs {leg.get('away_team')} | {selection} @{odds:.2f} < 1.15")
                continue

            # Strict Guardrail: Reject volatile Over 2.5+ or Under <= 2.5 goals
            if "over" in selection and any(x in selection for x in ["over 2.5", "over 3.5", "over 4.5", "over 5.5"]):
                logger.warning(f"[OddsVerify] REJECTED volatile high over: {leg.get('home_team')} vs {leg.get('away_team')} | {selection}")
                continue
            if "under" in selection and any(x in selection for x in ["under 0.5", "under 1.5", "under 2.5"]):
                logger.warning(f"[OddsVerify] REJECTED volatile low under: {leg.get('home_team')} vs {leg.get('away_team')} | {selection}")
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
                if odds < 1.15 or odds > 1.50:
                    continue

            verified.append(leg)
        return verified

    # Enforce maximum 40 games per ticket (SportyBet accumulator limit)
    target_games = min(40, target_games)

    for idx, b_ticket in enumerate(portfolio_built):
        # Pre-booking odds verification: purge any DC/O1.5 trap odds before generating code
        if b_ticket.approved_legs:
            verified_legs = _verify_odds_pre_booking(b_ticket.approved_legs, fixture_pool)
            b_ticket.approved_legs = verified_legs

            # Backfill pass if verified_legs is below target_games in GAMES mode
            if req.target_mode == "GAMES" and len(b_ticket.approved_legs) < target_games:
                used_fix_ids = {str(l.get("event_id") or l.get("fixture_id")) for l in b_ticket.approved_legs}
                for candidate_fix in fixture_pool:
                    if len(b_ticket.approved_legs) >= target_games:
                        break
                    cf_id = str(candidate_fix.get("event_id") or candidate_fix.get("fixture_id") or "")
                    if cf_id in used_fix_ids:
                        continue
                    cands = engine.evaluate_fixture_all_candidates(
                        fixture=candidate_fix,
                        per_leg_target_odds=1.35,
                        min_prob_threshold=0.58,
                        risk_profile=req.risk_profile or "BALANCED",
                        allowed_markets=req.allowed_market_categories,
                        excluded_markets=req.excluded_market_categories,
                    )
                    valid_c = [c for c in (cands or []) if c.approved and float(c.estimated_odds or 0) >= 1.15]
                    if valid_c:
                        best_pick = max(valid_c, key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))))
                        ev_id = str((best_pick.raw_match_data or {}).get("event_id") or best_pick.fixture_id)
                        b_ticket.approved_legs.append({
                            "fixture_id": best_pick.fixture_id,
                            "event_id": ev_id,
                            "provider_event_id": ev_id,
                            "game_id": best_pick.fixture_id,
                            "home_team": best_pick.home_team,
                            "away_team": best_pick.away_team,
                            "competition": best_pick.competition,
                            "country": (best_pick.raw_match_data or {}).get("country") or "",
                            "kickoff_datetime": best_pick.kickoff_datetime,
                            "market_name": best_pick.market_name,
                            "selection_name": best_pick.selection_name,
                            "model_probability": best_pick.model_probability,
                            "estimated_odds": best_pick.estimated_odds,
                            "odds": best_pick.estimated_odds,
                            "confidence_tier": best_pick.confidence_tier,
                            "elo_gap": best_pick.elo_gap,
                            "tier_context": best_pick.tier_context,
                            "market_id": best_pick.market_id,
                            "outcome_id": best_pick.outcome_id,
                            "specifier": best_pick.specifier,
                            "tactical_reason": getattr(best_pick, "tactical_reason", ""),
                        })
                        used_fix_ids.add(cf_id)

            acc = 1.0
            for leg in b_ticket.approved_legs:
                acc *= float(leg.get("odds") or leg.get("estimated_odds") or 1.25)
            b_ticket.accumulated_odds = round(acc, 2)

        # Trim to exact target_games if in GAMES mode
        if req.target_mode == "GAMES" and len(b_ticket.approved_legs) > target_games:
            b_ticket.approved_legs = b_ticket.approved_legs[:target_games]
            acc = 1.0
            for leg in b_ticket.approved_legs:
                acc *= float(leg.get("odds", 1.5))
            b_ticket.accumulated_odds = round(acc, 2)

        # Strict Global Cap: Maximum 40 legs per ticket on all modes
        if len(b_ticket.approved_legs) > 40:
            b_ticket.approved_legs = b_ticket.approved_legs[:40]
            acc = 1.0
            for leg in b_ticket.approved_legs:
                acc *= float(leg.get("odds", 1.5))
            b_ticket.accumulated_odds = round(acc, 2)

    # Parallel Verified Booking Code Generation across all portfolio tickets
    import concurrent.futures

    def _gen_code_for_ticket(b_t):
        if not b_t.approved_legs:
            return None, None, b_t.approved_legs
        try:
            c_res = adapter.generate_booking_code(b_t.approved_legs, country_code="ng")
            if c_res.get("status") == "SUCCESS" and c_res.get("booking_code"):
                final_legs = c_res.get("booked_selections") or b_t.approved_legs
                if req.target_mode == "GAMES" and len(final_legs) < target_games:
                    used_ids = {str(l.get("event_id") or l.get("fixture_id")) for l in final_legs}
                    backfill_legs = list(final_legs)
                    for candidate_fix in fixture_pool:
                        if len(backfill_legs) >= target_games:
                            break
                        cf_id = str(candidate_fix.get("event_id") or candidate_fix.get("fixture_id") or "")
                        if cf_id in used_ids:
                            continue
                        cands = engine.evaluate_fixture_all_candidates(
                            fixture=candidate_fix,
                            per_leg_target_odds=1.35,
                            min_prob_threshold=0.58,
                            risk_profile=req.risk_profile or "BALANCED",
                            allowed_markets=req.allowed_market_categories,
                            excluded_markets=req.excluded_market_categories,
                        )
                        valid_c = [c for c in (cands or []) if c.approved and float(c.estimated_odds or 0) >= 1.15]
                        if valid_c:
                            best_p = max(valid_c, key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))))
                            ev_id = str((best_p.raw_match_data or {}).get("event_id") or best_p.fixture_id)
                            backfill_legs.append({
                                "fixture_id": best_p.fixture_id,
                                "event_id": ev_id,
                                "provider_event_id": ev_id,
                                "game_id": best_p.fixture_id,
                                "home_team": best_p.home_team,
                                "away_team": best_p.away_team,
                                "competition": best_p.competition,
                                "country": (best_p.raw_match_data or {}).get("country") or "",
                                "kickoff_datetime": best_p.kickoff_datetime,
                                "market_name": best_p.market_name,
                                "selection_name": best_p.selection_name,
                                "model_probability": best_p.model_probability,
                                "estimated_odds": best_p.estimated_odds,
                                "odds": best_p.estimated_odds,
                                "confidence_tier": best_p.confidence_tier,
                                "elo_gap": best_p.elo_gap,
                                "tier_context": best_p.tier_context,
                                "market_id": best_p.market_id,
                                "outcome_id": best_p.outcome_id,
                                "specifier": best_p.specifier,
                                "tactical_reason": getattr(best_p, "tactical_reason", ""),
                            })
                            used_ids.add(cf_id)
                    if len(backfill_legs) > len(final_legs):
                        c_res2 = adapter.generate_booking_code(backfill_legs, country_code="ng")
                        if c_res2.get("status") == "SUCCESS" and c_res2.get("booking_code"):
                            return c_res2.get("booking_code"), c_res2.get("load_url"), (c_res2.get("booked_selections") or backfill_legs)
                return c_res.get("booking_code"), c_res.get("load_url"), final_legs
        except Exception as e:
            logger.warning(f"SportyBet booking code generation error: {e}")
        return None, None, b_t.approved_legs

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(portfolio_built))) as tpool:
        booking_results = list(tpool.map(_gen_code_for_ticket, portfolio_built))

    for idx, b_ticket in enumerate(portfolio_built):
        booking_code, share_url, final_legs = booking_results[idx] if idx < len(booking_results) else (None, None, b_ticket.approved_legs)
        b_ticket.approved_legs = final_legs
        acc = 1.0
        for leg in final_legs:
            acc *= float(leg.get("odds") or leg.get("estimated_odds") or 1.25)
        b_ticket.accumulated_odds = round(acc, 2)

        notice = None
        if req.target_mode == "GAMES" and len(final_legs) < target_games:
            notice = f"Found all {len(final_legs)} top-flight matches currently playing for {req.date_window}."

        t_dict = {
            "ticket_index": idx + 1,
            "title": f"Ticket {idx+1} ({len(final_legs)} Legs)" if num_t > 1 else f"Accumulator ({len(final_legs)} Legs)",
            "mode": b_ticket.mode,
            "target_mode": req.target_mode,
            "target_odds": req.target_odds,
            "target_games": len(final_legs) if req.target_mode == "GAMES" else target_games,
            "accumulated_odds": b_ticket.accumulated_odds,
            "combined_probability": b_ticket.combined_probability,
            "correlation_adjusted_probability": b_ticket.correlation_adjusted_probability,
            "confidence_tier": b_ticket.confidence_tier,
            "recommended_stake_pct": b_ticket.recommended_stake_pct,
            "leg_config": b_ticket.leg_config,
            "approved_legs": final_legs,
            "selections": final_legs,
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

    # 1. Gather and rank legs per slip by conviction (model_probability descending)
    slips_legs = []
    for slip in req.slips:
        legs = slip.get("approved_legs") or slip.get("final_selections") or slip.get("selections") or []
        sorted_slip_legs = sorted(
            legs,
            key=lambda l: (
                float(l.get("model_probability") or l.get("win_prob") or 0.70),
                -abs(float(l.get("odds") or l.get("estimated_odds") or 1.25) - 1.25)
            ),
            reverse=True
        )
        if sorted_slip_legs:
            slips_legs.append(sorted_slip_legs)

    if not slips_legs:
        raise HTTPException(status_code=400, detail="No valid match legs found in provided slips.")

    # 2. Select evenly from both variant slips (alternating round-robin)
    t_games = max(2, min(15, int(req.target_games or 10)))
    master_legs = []
    seen_fixtures = set()

    max_iter = max(len(l) for l in slips_legs)
    for round_idx in range(max_iter):
        for s_idx in range(len(slips_legs)):
            if len(master_legs) >= t_games:
                break
            if round_idx < len(slips_legs[s_idx]):
                leg = slips_legs[s_idx][round_idx]
                h_name = str(leg.get("home_team") or "").strip().lower()
                a_name = str(leg.get("away_team") or "").strip().lower()
                f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else str(leg.get("fixture_id") or leg.get("event_id") or "")
                if not f_key or f_key in seen_fixtures:
                    continue
                seen_fixtures.add(f_key)
                master_legs.append(leg)
        if len(master_legs) >= t_games:
            break

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
            if code_res.get("booked_selections"):
                master_legs = code_res.get("booked_selections")
                acc_odds = 1.0
                for leg in master_legs:
                    acc_odds *= float(leg.get("odds") or leg.get("estimated_odds") or 1.25)
                acc_odds = round(acc_odds, 2)
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


# =========================================================================
# Custom Fixture Shortlist Ingestion & Auto-Prediction Engine
# =========================================================================

class ShortlistBuildRequest(BaseModel):
    raw_text: Optional[str] = None
    matches_text: Optional[str] = None
    match_pairs: Optional[List[Dict[str, str]]] = None  # [{"home": "...", "away": "..."}]
    target_odds: Optional[float] = 5.0
    target_games: Optional[int] = 5
    target_mode: Optional[str] = "GAMES"  # "ODDS" or "GAMES"
    num_tickets: Optional[int] = 1  # 1, 2, 3 portfolio variants
    risk_profile: Optional[str] = "BALANCED"
    country_code: Optional[str] = "ng"
    reshuffle_seed: Optional[int] = None
    min_odds: Optional[float] = 1.15
    allowed_market_categories: Optional[List[str]] = None
    excluded_market_categories: Optional[List[str]] = None


def parse_shortlist_text(text: str) -> List[Tuple[str, str]]:
    """
    Parses user-pasted match text into (home_team, away_team) pairs.
    Supports:
      1. Delimited lines: 'Team A vs Team B', 'Team A - Team B', 'Team A v Team B', 'Team A, Team B'
      2. SportyBet / Flashscore multi-line copied blocks
    """
    if not text or not text.strip():
        return []

    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    pairs = []

    # Strategy 1: Check for explicit delimiters per line
    delims = [r"\s+vs\.?\s+", r"\s+v\.?\s+", r"\s*-\s*", r"\s*,\s*"]
    for line in lines:
        for d in delims:
            parts = re.split(d, line, flags=re.IGNORECASE)
            if len(parts) == 2 and len(parts[0].strip()) >= 2 and len(parts[1].strip()) >= 2:
                # Exclude pure numbers/odds
                if not re.match(r"^[\d\.\s]+$", parts[0]) and not re.match(r"^[\d\.\s]+$", parts[1]):
                    pairs.append((parts[0].strip(), parts[1].strip()))
                    break

    if pairs:
        return pairs

    # Strategy 2: Block / Multiline copy-paste from betting websites
    noise_keywords = [
        "way", "o/u", "double chance", "gg/ng", "draw no bet", "other markets",
        "goals", "over", "under", "matches", "outrights", "saturday", "sunday",
        "monday", "tuesday", "wednesday", "thursday", "friday", "today", "tomorrow"
    ]
    candidate_tokens = []
    for line in lines:
        l_low = line.lower()
        if re.match(r"^[\d\.\:\+\s\-]+$", line):
            continue
        if re.match(r"^id\s*:\s*\d+", l_low):
            continue
        if any(k in l_low for k in noise_keywords) and len(line.split()) <= 4:
            continue
        if line.strip().upper() in ["1", "X", "2", "1X", "X2", "12"]:
            continue
        candidate_tokens.append(line.strip())

    i = 0
    while i < len(candidate_tokens) - 1:
        pairs.append((candidate_tokens[i], candidate_tokens[i+1]))
        i += 2

    return pairs


def _normalize_name_for_match(name: str) -> str:
    s = str(name or "").lower().strip()
    aliases = {
        "czech republic": "czechia",
        "usa": "united states",
        "south korea": "korea republic",
        "ivory coast": "cote divoire",
        "cape verde": "cabo verde",
        "bosnia": "bosnia and herzegovina",
        "man utd": "manchester united",
        "man city": "manchester city",
        "wolves": "wolverhampton",
        "spurs": "tottenham",
        "psg": "paris saint germain",
        "atletico": "atletico madrid",
        "real": "real madrid"
    }
    for a, r in aliases.items():
        if s == a:
            s = r
            break

    s = re.sub(r"[^\w\s]", " ", s)
    stop = {"fc", "cf", "sc", "cd", "ec", "fk", "sk", "bk", "afc", "ac", "as", "club", "united", "city", "town"}
    filtered = [t for t in s.split() if t not in stop]
    return " ".join(filtered) if filtered else s


@router.post("/build-from-shortlist")
async def build_from_custom_shortlist(req: ShortlistBuildRequest):
    """
    Evaluates user-submitted custom shortlist of fixtures against live SportyBet markets.
    Applies StatIQ 5-Gate Pick Engine and generates genuine SportyBet booking codes.
    """
    # 1. Parse matches from input
    parsed_pairs = []
    raw_input_text = req.matches_text or req.raw_text
    if req.match_pairs and len(req.match_pairs) > 0:
        for p in req.match_pairs:
            h = str(p.get("home") or "").strip()
            a = str(p.get("away") or "").strip()
            if h and a:
                parsed_pairs.append((h, a))
    elif raw_input_text:
        parsed_pairs = parse_shortlist_text(raw_input_text)

    if not parsed_pairs:
        raise HTTPException(
            status_code=400,
            detail="No fixtures detected. Please paste your matches (e.g. 'Team A vs Team B' on separate lines)."
        )

    # 2. Fetch live SportyBet fixture pool (Fast Live Today API with Mirror DB fallback)
    from app.services.elite_rollover_engine import EliteRolloverEngine
    from app.services.form_h2h_service import evaluate_fixture_3pillar_metrics
    from app.predictions.live_calculator import get_team_rating

    raw_sporty_fixtures = []
    try:
        live_events = await EliteRolloverEngine.fetch_sportybet_today_events(max_pages=4)
        if live_events:
            raw_sporty_fixtures = SportyBetIngestionService._normalize_events(live_events)
            logger.info(f"[Shortlist] Live feed loaded {len(raw_sporty_fixtures)} bettable fixtures directly from SportyBet Today API.")
    except Exception as e:
        logger.warning(f"[Shortlist] Live SportyBet Today fetch fallback: {e}")
        raw_sporty_fixtures = []

    if not raw_sporty_fixtures:
        from sqlalchemy.orm import selectinload, joinedload
        from app.db.session import SessionLocal
        from app.db.models import SportyBetEvent, SportyBetMarket
        db_sess = SessionLocal()
        db_events = []
        try:
            db_events = (
                db_sess.query(SportyBetEvent)
                .options(
                    joinedload(SportyBetEvent.competition_rel),
                    selectinload(SportyBetEvent.markets).selectinload(SportyBetMarket.outcomes)
                )
                .filter(SportyBetEvent.status == "SCHEDULED")
                .all()
            )
        except Exception as e:
            logger.warning(f"[Shortlist] DB events query error: {e}")
        finally:
            db_sess.close()

        if db_events and len(db_events) > 0:
            now_ms = time.time() * 1000.0
            for ev in db_events:
                if ev.start_time_ms and ev.start_time_ms <= (now_ms + 600000):
                    continue

                comp_name = ev.competition_rel.name if ev.competition_rel else "Football"
                country_name = ev.competition_rel.country if ev.competition_rel else None

                # Extract real 1X2 odds
                o_h, o_d, o_a = 2.50, 3.00, 2.50
                m1 = next((m for m in ev.markets if str(m.sporty_market_id) == "1" and (m.status is None or str(m.status) in ("0", "ACTIVE"))), None)
                if m1:
                    for oc in m1.outcomes:
                        if oc.status is not None and str(oc.status) not in ("0", "ACTIVE"):
                            continue
                        sel_u = (oc.selection or "").upper()
                        if sel_u in ["1", "HOME", ev.home_team.upper()]:
                            o_h = float(oc.odds or 2.50)
                        elif sel_u in ["X", "DRAW"]:
                            o_d = float(oc.odds or 3.00)
                        elif sel_u in ["2", "AWAY", ev.away_team.upper()]:
                            o_a = float(oc.odds or 2.50)

                # Extract markets dictionary and structured market lists
                dc_map = {}
                ou_list = []
                btts_dict = {}
                home_goals_list = []
                away_goals_list = []
                markets_dict = {}

                for m in ev.markets:
                    m_stat = str(m.status or "")
                    if m_stat in ("1", "2", "SUSPENDED", "INACTIVE", "CLOSED"):
                        continue
                    m_id = str(m.sporty_market_id or "")
                    m_desc = (m.market_name or "").lower()
                    spec = str(m.specifier or "")

                    outcomes_clean = []
                    for oc in m.outcomes:
                        oc_stat = str(oc.status or "")
                        if oc_stat in ("1", "2", "SUSPENDED", "INACTIVE"):
                            continue
                        ov = float(oc.odds or 0.0)
                        if ov < 1.05:
                            continue
                        outcomes_clean.append({
                            "outcome_id": str(oc.sporty_outcome_id or ""),
                            "id": str(oc.sporty_outcome_id or ""),
                            "selection_name": oc.selection or "",
                            "desc": oc.selection or "",
                            "odds": ov,
                            "probability": oc.probability
                        })

                    if not outcomes_clean:
                        continue

                    markets_dict[f"{m_id}_{spec}"] = {
                        "market_id": m_id,
                        "market_name": m.market_name,
                        "specifier": spec,
                        "outcomes": outcomes_clean
                    }

                    # Double Chance (10)
                    if m_id == "10" or "double chance" in m_desc:
                        for oc in outcomes_clean:
                            o_desc = oc["selection_name"].upper()
                            o_id = oc["outcome_id"]
                            ov = oc["odds"]
                            if ov >= 1.15:
                                if o_id == "9" or "1X" in o_desc: dc_map["1X"] = ov
                                elif o_id == "11" or "X2" in o_desc: dc_map["X2"] = ov
                                elif o_id == "10" or "12" in o_desc: dc_map["12"] = ov

                    # Over/Under (18)
                    elif m_id == "18" or "over/under" in m_desc:
                        line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                        line_str = line_m.group(1) if line_m else "1.5"
                        o_val, u_val = None, None
                        for oc in outcomes_clean:
                            o_desc = oc["selection_name"].lower()
                            o_id = oc["outcome_id"]
                            ov = oc["odds"]
                            if ov >= 1.15:
                                if "over" in o_desc or o_id == "12": o_val = ov
                                elif "under" in o_desc or o_id == "13": u_val = ov
                        if o_val or u_val:
                            ou_list.append({"line": line_str, "over": o_val, "under": u_val, "specifier": f"total={line_str}"})

                    # BTTS (29)
                    elif m_id == "29" or "both teams to score" in m_desc:
                        for oc in outcomes_clean:
                            sel_u = oc["selection_name"].upper()
                            ov = oc["odds"]
                            if ov >= 1.15:
                                if sel_u in ["YES", "GG"]: btts_dict["yes"] = ov; btts_dict["yes_id"] = oc["outcome_id"]
                                elif sel_u in ["NO", "NG"]: btts_dict["no"] = ov; btts_dict["no_id"] = oc["outcome_id"]
                        if btts_dict: btts_dict["market_id"] = "29"

                    # Home Team Goals (19)
                    elif m_id == "19" or ("home" in m_desc and "over/under" in m_desc):
                        line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                        line_str = line_m.group(1) if line_m else "1.5"
                        o_val, u_val = None, None
                        for oc in outcomes_clean:
                            o_desc = oc["selection_name"].lower()
                            o_id = oc["outcome_id"]
                            ov = oc["odds"]
                            if ov >= 1.15:
                                if "over" in o_desc or o_id == "12": o_val = ov
                                elif "under" in o_desc or o_id == "13": u_val = ov
                        if o_val or u_val:
                            home_goals_list.append({"line": line_str, "over": o_val, "under": u_val, "market_id": "19", "specifier": f"total={line_str}"})

                    # Away Team Goals (20)
                    elif m_id == "20" or ("away" in m_desc and "over/under" in m_desc):
                        line_m = re.search(r"total=(\d+\.?\d*)", spec) or re.search(r"(\d+\.?\d*)", m_desc)
                        line_str = line_m.group(1) if line_m else "1.5"
                        o_val, u_val = None, None
                        for oc in outcomes_clean:
                            o_desc = oc["selection_name"].lower()
                            o_id = oc["outcome_id"]
                            ov = oc["odds"]
                            if ov >= 1.15:
                                if "over" in o_desc or o_id == "12": o_val = ov
                                elif "under" in o_desc or o_id == "13": u_val = ov
                        if o_val or u_val:
                            away_goals_list.append({"line": line_str, "over": o_val, "under": u_val, "market_id": "20", "specifier": f"total={line_str}"})

                raw_sporty_fixtures.append({
                    "id": f"fx_{ev.sporty_game_id}" if ev.sporty_game_id else f"fx_{ev.sporty_event_id.replace(':', '_')}",
                    "event_id": ev.sporty_event_id,
                    "game_id": ev.sporty_game_id,
                    "home_team": ev.home_team,
                    "away_team": ev.away_team,
                    "country": country_name,
                    "competition": comp_name,
                    "kickoff_time": ev.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "start_time_ms": ev.start_time_ms,
                    "odds_home": o_h,
                    "odds_draw": o_d,
                    "odds_away": o_a,
                    "double_chance": dc_map,
                    "ou_lines": ou_list,
                    "home_team_goals": home_goals_list,
                    "away_team_goals": away_goals_list,
                    "btts": btts_dict,
                    "markets": markets_dict,
                    "provider": "SPORTYBET"
                })
        else:
            raw_sporty_fixtures = []

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_ms = now_utc.timestamp() * 1000.0

    resolved_pool = []
    seen_event_ids = set()
    unmatched_items = []

    for req_h, req_a in parsed_pairs:
        h_norm = _normalize_name_for_match(req_h)
        a_norm = _normalize_name_for_match(req_a)

        best_match = None
        best_score = 0.0

        for ev in raw_sporty_fixtures:
            ev_id = str(ev.get("event_id") or ev.get("game_id") or "")
            if ev_id in seen_event_ids:
                continue

            # Must not have started
            start_ms = ev.get("start_time_ms") or 0
            if start_ms > 0 and start_ms <= (now_ms + 180000):
                continue

            ev_status = str(ev.get("status") or "").upper()
            if ev_status in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED"]:
                continue

            sb_h = str(ev.get("home_team") or "")
            sb_a = str(ev.get("away_team") or "")
            sb_h_norm = _normalize_name_for_match(sb_h)
            sb_a_norm = _normalize_name_for_match(sb_a)

            # Check standard order (Home vs Away)
            score_h = SequenceMatcher(None, h_norm, sb_h_norm).ratio()
            score_a = SequenceMatcher(None, a_norm, sb_a_norm).ratio()

            # Substring boost
            if h_norm and (h_norm in sb_h_norm or sb_h_norm in h_norm):
                score_h = max(score_h, 0.90)
            if a_norm and (a_norm in sb_a_norm or sb_a_norm in a_norm):
                score_a = max(score_a, 0.90)

            # Check reverse order (in case user pasted Away vs Home)
            score_h_rev = SequenceMatcher(None, h_norm, sb_a_norm).ratio()
            score_a_rev = SequenceMatcher(None, a_norm, sb_h_norm).ratio()
            if h_norm and (h_norm in sb_a_norm or sb_a_norm in h_norm):
                score_h_rev = max(score_h_rev, 0.90)
            if a_norm and (a_norm in sb_a_norm or sb_a_norm in a_norm):
                score_a_rev = max(score_a_rev, 0.90)

            combined_std = (score_h + score_a) / 2.0
            combined_rev = (score_h_rev + score_a_rev) / 2.0
            combined = max(combined_std, combined_rev)

            if combined >= 0.65 and min(score_h, score_a) >= 0.50 and combined > best_score:
                best_score = combined
                best_match = ev

        if best_match:
            ev_id = str(best_match.get("event_id") or best_match.get("game_id") or "")
            seen_event_ids.add(ev_id)
            h_act = best_match.get("home_team") or req_h
            a_act = best_match.get("away_team") or req_a
            comp_name = (best_match.get("competition") or "Football").strip()
            country_name = (best_match.get("country") or "").strip()
            start_ms = best_match.get("start_time_ms") or 0
            match_dt = datetime.datetime.fromtimestamp(start_ms / 1000.0, tz=datetime.timezone.utc) if start_ms > 0 else now_utc

            r1x2_ev = {
                "home": float(best_match.get("odds_home") or 2.50),
                "draw": float(best_match.get("odds_draw") or 3.00),
                "away": float(best_match.get("odds_away") or 2.50)
            }
            dc_data = best_match.get("double_chance") or {}
            ou_data = best_match.get("ou_lines") or []

            # 3-Pillar Safety Metrics & Elo Intelligence (Instant calculation)
            r_h = get_team_rating(h_act) + 40
            r_a = get_team_rating(a_act)
            elo_gap = round(r_h - r_a, 1)

            fav_is_home = r1x2_ev["home"] <= r1x2_ev["away"]
            fav_team = h_act if fav_is_home else a_act
            fav_odds = r1x2_ev["home"] if fav_is_home else r1x2_ev["away"]

            pillar_eval = evaluate_fixture_3pillar_metrics(h_act, a_act, "1X2", fav_team, fav_odds)
            h2h_info = {
                "home_win_pct": round((1.0 / max(1.05, r1x2_ev["home"])) / (1.0/r1x2_ev["home"] + 1.0/r1x2_ev["away"]), 3),
                "away_win_pct": round((1.0 / max(1.05, r1x2_ev["away"])) / (1.0/r1x2_ev["home"] + 1.0/r1x2_ev["away"]), 3),
                "draw_pct": 0.25,
                "total_meetings": 5,
                "avg_total_goals": 2.6,
                "summary": pillar_eval.get("h2h_summary"),
                "form_summary": pillar_eval.get("form_summary"),
                "safety_score": pillar_eval.get("composite_safety_score"),
                "is_safe": pillar_eval.get("is_safe")
            }

            resolved_pool.append({
                "fixture_id": ev_id,
                "event_id": ev_id,
                "game_id": best_match.get("game_id"),
                "provider_event_id": ev_id,
                "external_fixture_id": ev_id,
                "home_team": h_act,
                "away_team": a_act,
                "competition": comp_name,
                "competition_code": comp_name,
                "country": country_name,
                "kickoff_datetime": best_match.get("kickoff_time") or match_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "start_time_ms": start_ms,
                "markets": best_match.get("markets", {}),
                "result_1x2": r1x2_ev,
                "odds_home": r1x2_ev["home"],
                "odds_draw": r1x2_ev["draw"],
                "odds_away": r1x2_ev["away"],
                "ou_lines": ou_data,
                "double_chance": dc_data,
                "home_team_goals": best_match.get("home_team_goals", []),
                "away_team_goals": best_match.get("away_team_goals", []),
                "btts": best_match.get("btts", {}),
                "elo_gap": elo_gap,
                "h2h_data": h2h_info,
                "matched_from_input": f"{req_h} vs {req_a}",
            })
        else:
            unmatched_items.append(f"{req_h} vs {req_a}")

    if not resolved_pool:
        return {
            "status": "NO_MATCHES_RESOLVED",
            "message": f"Could not find any of the {len(parsed_pairs)} submitted matches on SportyBet's active today board. Ensure match names are accurate and matches haven't kicked off yet.",
            "total_submitted": len(parsed_pairs),
            "total_resolved": 0,
            "unmatched_items": unmatched_items,
        }

    # 4. Pick Engine
    t_games = req.target_games or min(len(resolved_pool), 15)
    t_games = min(40, max(1, t_games))
    t_odds = req.target_odds if req.target_mode == "ODDS" else 999.0
    num_t = max(1, min(3, int(req.num_tickets or 1)))

    engine = MatchIQPickEngine(use_live_odds=True)

    if num_t > 1:
        portfolio_built = engine.build_portfolio(
            fixture_pool=resolved_pool,
            num_tickets=num_t,
            target_total_odds=t_odds,
            mode="ACCUMULATOR",
            target_mode=req.target_mode,
            target_games=t_games,
            max_league_picks=40,
            risk_profile=req.risk_profile or "BALANCED",
            overlap_mode="ZERO_OVERLAP"
        )
    else:
        portfolio_built = [engine.build_ticket(
            fixture_pool=resolved_pool,
            target_total_odds=t_odds,
            mode="ACCUMULATOR",
            target_mode=req.target_mode,
            target_games=t_games,
            max_league_picks=40,
            reshuffle_seed=req.reshuffle_seed,
            risk_profile=req.risk_profile or "BALANCED",
        )]

    # 5. Book on SportyBet
    from app.adapters.bookmaker_adapter import SportyBetAdapter
    adapter = SportyBetAdapter()
    portfolio_results = []

    for idx, b_ticket in enumerate(portfolio_built):
        # Enforce minimum odds floor 1.15
        valid_legs = [l for l in b_ticket.approved_legs if float(l.get("odds") or l.get("estimated_odds") or 1.0) >= 1.15]

        # Backfill pass from resolved_pool if valid_legs is below requested t_games
        if req.target_mode == "GAMES" and len(valid_legs) < t_games:
            used_ev_ids = {str(l.get("event_id") or l.get("fixture_id")) for l in valid_legs}
            for fix in resolved_pool:
                if len(valid_legs) >= t_games:
                    break
                f_id = str(fix.get("event_id") or fix.get("fixture_id") or "")
                if f_id in used_ev_ids:
                    continue
                cands = engine.evaluate_fixture_all_candidates(
                    fixture=fix,
                    per_leg_target_odds=1.35,
                    min_prob_threshold=0.58,
                    risk_profile=req.risk_profile or "BALANCED",
                )
                valid_c = [c for c in (cands or []) if c.approved and float(c.estimated_odds or 0) >= 1.15]
                if valid_c:
                    best_pick = max(valid_c, key=lambda x: (x.model_probability, float(getattr(x, "tactical_score", 0.0))))
                    ev_id = str((best_pick.raw_match_data or {}).get("event_id") or best_pick.fixture_id)
                    valid_legs.append({
                        "fixture_id": best_pick.fixture_id,
                        "event_id": ev_id,
                        "provider_event_id": ev_id,
                        "game_id": best_pick.fixture_id,
                        "home_team": best_pick.home_team,
                        "away_team": best_pick.away_team,
                        "competition": best_pick.competition,
                        "country": (best_pick.raw_match_data or {}).get("country") or "",
                        "kickoff_datetime": best_pick.kickoff_datetime,
                        "market_name": best_pick.market_name,
                        "selection_name": best_pick.selection_name,
                        "model_probability": best_pick.model_probability,
                        "estimated_odds": best_pick.estimated_odds,
                        "odds": best_pick.estimated_odds,
                        "confidence_tier": best_pick.confidence_tier,
                        "elo_gap": best_pick.elo_gap,
                        "tier_context": best_pick.tier_context,
                        "market_id": best_pick.market_id,
                        "outcome_id": best_pick.outcome_id,
                        "specifier": best_pick.specifier,
                        "tactical_reason": getattr(best_pick, "tactical_reason", ""),
                    })
                    used_ev_ids.add(f_id)

        if req.target_mode == "GAMES" and len(valid_legs) > t_games:
            valid_legs = valid_legs[:t_games]
        elif len(valid_legs) > 40:
            valid_legs = valid_legs[:40]

        b_ticket.approved_legs = valid_legs

        acc = 1.0
        for l in valid_legs:
            acc *= float(l.get("odds", 1.5))
        b_ticket.accumulated_odds = round(acc, 2)

        booking_code = None
        share_url = None
        if valid_legs:
            try:
                c_res = adapter.generate_booking_code(valid_legs, country_code=req.country_code or "ng")
                if c_res.get("status") == "SUCCESS" and c_res.get("booking_code"):
                    booking_code = c_res.get("booking_code")
                    share_url = c_res.get("load_url")
                    if c_res.get("booked_selections"):
                        valid_legs = c_res.get("booked_selections")
                        acc = 1.0
                        for l in valid_legs:
                            acc *= float(l.get("odds", 1.25))
                        b_ticket.accumulated_odds = round(acc, 2)
            except Exception as exc:
                logger.warning(f"[Shortlist] Booking code error for variant {idx+1}: {exc}")

        t_dict = {
            "scenario_id": f"SHORTLIST-V{idx+1}-{len(valid_legs)}G",
            "ticket_index": idx + 1,
            "title": f"Ticket {idx+1} ({len(valid_legs)} Legs)" if num_t > 1 else f"Shortlist Ticket ({len(valid_legs)} Legs)",
            "target_mode": req.target_mode,
            "target_games": t_games,
            "target_odds": req.target_odds,
            "accumulated_odds": b_ticket.accumulated_odds,
            "combined_probability": b_ticket.combined_probability,
            "confidence_tier": b_ticket.confidence_tier,
            "recommended_stake_pct": b_ticket.recommended_stake_pct,
            "approved_legs": valid_legs,
            "selections": valid_legs,
            "rejected_picks": b_ticket.rejected_picks,
            "booking_code": booking_code,
            "share_url": share_url or (f"https://www.sportybet.com/ng/?shareCode={booking_code}" if booking_code else None),
            "total_evaluated": len(resolved_pool)
        }
        portfolio_results.append(t_dict)

    primary_ticket = portfolio_results[0] if portfolio_results else {}

    return {
        "status": "SUCCESS",
        "total_submitted": len(parsed_pairs),
        "total_resolved": len(resolved_pool),
        "unmatched_items": unmatched_items,
        "ticket": primary_ticket,
        "scenarios": portfolio_results,
        "portfolio_tickets": portfolio_results if num_t > 1 else None
    }



