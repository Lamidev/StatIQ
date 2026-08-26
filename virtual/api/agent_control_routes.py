"""
Virtual Agent Controller & Live vFootball API Routes.

Architecture:
  - /vfootball/live   → Fetches directly from SportyBet vFootball API (real-time)
  - /state            → Agent on/off + current generated ticket
  - /config           → Update agent settings
  - /generate-ticket  → Manually trigger ticket generation from live fixtures
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging

from virtual.core.db import get_db
from virtual.models.virtual_models import VirtualLeague, VirtualEvent, VirtualOddsSnapshot, VirtualBankroll
from virtual.ingestion.virtual_sportybet_client import VirtualSportyBetClient
from virtual.paper.paper_trader import PaperTrader

logger = logging.getLogger("statiq.virtual.agent_control")
router = APIRouter()

# ---------------------------------------------------------------
# In-memory Agent Control State
# ---------------------------------------------------------------
AGENT_STATE = {
    "is_active": True,
    "target_odds": 2.0,
    "num_games": 2,
    "stake_amount": 1000.0,
    "preferred_market": "ALL",   # ALL | 1X2_HOME | 1X2_AWAY | OVER_1.5 | OVER_2.5 | DOUBLE_CHANCE
    "last_generated_ticket": None,
    "last_ticket_timestamp": None,
}


class AgentConfigUpdate(BaseModel):
    is_active: Optional[bool] = None
    target_odds: Optional[float] = None
    num_games: Optional[int] = None
    stake_amount: Optional[float] = None
    preferred_market: Optional[str] = None


# ---------------------------------------------------------------
# LIVE vFootball Fixtures from SportyBet API
# ---------------------------------------------------------------

@router.get("/vfootball/live")
def get_live_vfootball_fixtures(
    league: Optional[str] = Query(None, description="Filter by league: england, spain, italy, germany, france, turkey")
):
    """
    Fetches current vFootball fixtures DIRECTLY from the SportyBet API.
    Returns real team names, real odds, real gameIds — exactly as on the site.
    Auto-polls fresh data every call.
    """
    try:
        raw_events = VirtualSportyBetClient.fetch_upcoming_virtual_events()
    except Exception as e:
        logger.error(f"[LiveFixtures] Error fetching from SportyBet: {e}")
        raise HTTPException(status_code=503, detail=f"Could not reach SportyBet API: {e}")

    fixtures = []
    for ev in raw_events:
        sport = ev.get("sport", {})
        cat = sport.get("category", {}) if isinstance(sport, dict) else {}
        cat_name = cat.get("name", "Virtual")  # England / Spain / Italy etc.

        # Apply league filter
        if league and cat_name.lower() != league.lower():
            continue

        home = ev.get("homeTeamName", "?")
        away = ev.get("awayTeamName", "?")
        game_id = str(ev.get("gameId", ""))
        event_id = ev.get("eventId", "")
        start_ms = ev.get("estimateStartTime", 0)
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat() if start_ms else None

        markets = ev.get("markets", [])
        odds_1x2 = _extract_1x2(markets)
        odds_ou_list = _extract_ou_markets(markets)

        fixtures.append({
            "game_id": game_id,
            "event_id": event_id,
            "league": f"{cat_name} Virtual",
            "country": cat_name,
            "home_team": home,
            "away_team": away,
            "kick_off": start_dt,
            "kick_off_display": datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%H:%M") if start_ms else "--:--",
            "status": ev.get("matchStatus", "Not start"),
            "odds_1x2": odds_1x2,
            "odds_ou": odds_ou_list,
            "market_count": len(markets),
        })

    # Group by league for display
    leagues: Dict[str, List] = {}
    for f in fixtures:
        key = f["country"]
        if key not in leagues:
            leagues[key] = []
        leagues[key].append(f)

    return {
        "total": len(fixtures),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "leagues": leagues,
        "fixtures": fixtures,
    }


@router.get("/vfootball/event/{game_id}")
def get_vfootball_event(game_id: str):
    """Fetch full detail for a single vFootball event by its gameId."""
    ev = VirtualSportyBetClient.fetch_event_by_game_id(game_id)
    if not ev:
        raise HTTPException(status_code=404, detail=f"vFootball event gameId={game_id} not found or not upcoming")

    sport = ev.get("sport", {})
    cat = sport.get("category", {}) if isinstance(sport, dict) else {}
    return {
        "game_id": game_id,
        "event_id": ev.get("eventId"),
        "league": f"{cat.get('name', 'Virtual')} Virtual",
        "home_team": ev.get("homeTeamName"),
        "away_team": ev.get("awayTeamName"),
        "kick_off": datetime.fromtimestamp(ev.get("estimateStartTime", 0) / 1000, tz=timezone.utc).isoformat(),
        "status": ev.get("matchStatus"),
        "markets": ev.get("markets", []),
    }


# ---------------------------------------------------------------
# Agent State & Control
# ---------------------------------------------------------------

@router.get("/state")
def get_agent_state(db: Session = Depends(get_db)):
    """Returns agent ON/OFF status, config, bankroll, and current ticket immediately."""
    bankroll = PaperTrader.get_bankroll_summary(db)
    return {
        "agent": AGENT_STATE,
        "bankroll": bankroll,
    }



@router.post("/config")
def update_agent_config(config: AgentConfigUpdate, db: Session = Depends(get_db)):
    """Update agent ON/OFF, Target Odds, Game Count, Stake, or Market preference."""
    if config.is_active is not None:
        AGENT_STATE["is_active"] = config.is_active
    if config.target_odds is not None:
        AGENT_STATE["target_odds"] = config.target_odds
    if config.num_games is not None:
        AGENT_STATE["num_games"] = config.num_games
    if config.stake_amount is not None:
        AGENT_STATE["stake_amount"] = config.stake_amount
    if config.preferred_market is not None:
        AGENT_STATE["preferred_market"] = config.preferred_market

    # Regenerate ticket with new settings
    if AGENT_STATE["is_active"]:
        _auto_generate_ticket(db)

    return {"message": "Agent configuration updated.", "agent": AGENT_STATE}


@router.post("/generate-ticket")
def generate_ticket_from_live(
    target_odds: Optional[float] = Query(None),
    num_games: Optional[int] = Query(None),
    stake_amount: Optional[float] = Query(None),
    market: Optional[str] = Query(None, description="1X2_HOME | 1X2_AWAY | OVER_1.5 | OVER_2.5 | DOUBLE_CHANCE | ALL"),
    db: Session = Depends(get_db)
):
    """
    Fetch live vFootball fixtures and generate a betting ticket
    that meets the target odds / number of games criteria.
    Returns the booking code and selections.
    """
    odds_target = target_odds or AGENT_STATE["target_odds"]
    games = num_games or AGENT_STATE["num_games"]
    stake = stake_amount or AGENT_STATE["stake_amount"]
    mkt = market or AGENT_STATE["preferred_market"]

    # Fetch live fixtures
    try:
        raw_events = VirtualSportyBetClient.fetch_upcoming_virtual_events()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not reach SportyBet: {e}")

    if not raw_events:
        return {"status": "NO_FIXTURES", "message": "No upcoming vFootball fixtures available right now."}

    # Build selections from live events
    selections = _pick_selections(raw_events, mkt, games, odds_target)

    if not selections:
        return {
            "status": "NO_MATCH",
            "message": f"Could not find {games} selections meeting target odds {odds_target}x with market '{mkt}'.",
        }

    # Calculate totals
    total_odds = 1.0
    for s in selections:
        total_odds *= s["odds"]
    potential_return = round(stake * total_odds, 2)
    profit = round(potential_return - stake, 2)

    ticket = {
        "selections": selections,
        "num_selections": len(selections),
        "total_odds": round(total_odds, 2),
        "stake_ngn": stake,
        "potential_return_ngn": potential_return,
        "profit_ngn": profit,
        "booking_code": _build_booking_code(selections),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sportybet_url": "https://www.sportybet.com/ng/sport/vFootball/",
    }

    AGENT_STATE["last_generated_ticket"] = ticket
    AGENT_STATE["last_ticket_timestamp"] = ticket["generated_at"]

    return {"status": "SUCCESS", "ticket": ticket}


@router.post("/reset-ledger")
def reset_fronttest_ledger(db: Session = Depends(get_db)):
    """
    Clears all front-testing slips and match history from the database to start afresh.
    """
    from virtual.models.virtual_models import VirtualFrontTestSlip, VirtualMatchHistory
    deleted_slips = db.query(VirtualFrontTestSlip).delete()
    deleted_history = db.query(VirtualMatchHistory).delete()
    db.commit()
    return {
        "status": "SUCCESS",
        "message": f"Ledger reset. Cleared {deleted_slips} slips and {deleted_history} history records."
    }



# ---------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------

def _extract_1x2(markets: List[Dict]) -> Dict:
    for m in markets:
        if m.get("desc") == "1X2" or str(m.get("id")) == "1":
            m_id = str(m.get("id") or "1")
            outcomes = m.get("outcomes", [])
            h_val, d_val, a_val = None, None, None
            h_oid, d_oid, a_oid = "1", "2", "3"
            for o in outcomes:
                desc = str(o.get("desc") or "").upper()
                val = float(o.get("odds") or 0.0)
                oid = str(o.get("id") or "")
                if desc in ["HOME", "1"] or oid == "1":
                    h_val = val
                    h_oid = oid or "1"
                elif desc in ["DRAW", "X"] or oid == "2":
                    d_val = val
                    d_oid = oid or "2"
                elif desc in ["AWAY", "2"] or oid == "3":
                    a_val = val
                    a_oid = oid or "3"
            return {
                "home": h_val,
                "draw": d_val,
                "away": a_val,
                "home_outcome_id": h_oid,
                "draw_outcome_id": d_oid,
                "away_outcome_id": a_oid,
                "market_id": m_id,
            }
    return {"home": None, "draw": None, "away": None, "market_id": "1", "home_outcome_id": "1", "away_outcome_id": "3"}


def _extract_ou_markets(markets: List[Dict]) -> List[Dict]:
    ou = []
    for m in markets:
        desc = str(m.get("desc") or "").upper()
        m_id = str(m.get("id") or "18")
        specifier = str(m.get("specifier") or "")
        if ("O/U" in desc or "OVER" in desc or m_id == "18") and "total=" in specifier:
            line = specifier.replace("total=", "")
            outcomes = m.get("outcomes", [])
            o_val, u_val = None, None
            o_oid, u_oid = "12", "13"
            for o in outcomes:
                o_desc = str(o.get("desc") or "").upper()
                val = float(o.get("odds") or 0.0)
                oid = str(o.get("id") or "")
                if "OVER" in o_desc or oid == "12":
                    o_val = val
                    o_oid = oid or "12"
                elif "UNDER" in o_desc or oid == "13":
                    u_val = val
                    u_oid = oid or "13"
            if o_val or u_val:
                ou.append({
                    "line": line,
                    "over": o_val,
                    "under": u_val,
                    "over_outcome_id": o_oid,
                    "under_outcome_id": u_oid,
                    "market_id": m_id,
                    "specifier": specifier,
                })
    ou.sort(key=lambda x: float(x["line"]) if x["line"] not in ("?", "") else 0)
    return ou


def _extract_double_chance(markets: List[Dict]) -> Dict:
    for m in markets:
        desc = str(m.get("desc") or "").upper()
        m_id = str(m.get("id") or "")
        if "DOUBLE CHANCE" in desc or m_id == "10":
            outcomes = m.get("outcomes", [])
            dc_1x, dc_12, dc_x2 = None, None, None
            for o in outcomes:
                o_desc = str(o.get("desc") or "").upper()
                val = float(o.get("odds") or 0.0)
                oid = str(o.get("id") or "")
                if "1X" in o_desc or "HOME OR DRAW" in o_desc or oid == "9":
                    dc_1x = val
                elif "12" in o_desc or "HOME OR AWAY" in o_desc or oid == "10":
                    dc_12 = val
                elif "X2" in o_desc or "DRAW OR AWAY" in o_desc or oid == "11":
                    dc_x2 = val
            return {
                "1x": dc_1x,
                "12": dc_12,
                "x2": dc_x2,
                "market_id": m_id or "10"
            }
    return {"1x": None, "12": None, "x2": None, "market_id": "10"}


def _pick_selections(events: List[Dict], market: str, count: int, target_odds: float, db: Optional[Session] = None) -> List[Dict]:
    """
    Assembles 2 to 3 safe selections (max 3) to reach ~target_odds.
    STRICTLY NO STRAIGHT 1X2 WINS: Uses Double Chance (1X/X2) and Over 1.5 Goals only.
    Enriched with rolling team goal distributions and cold-trap elimination.
    """
    from virtual.services.virtual_stats_enricher import VirtualStatsEnricher

    candidates = []

    for ev in events:
        sport = ev.get("sport", {})
        cat = sport.get("category", {}) if isinstance(sport, dict) else {}
        league = f"{cat.get('name', 'Virtual')} Virtual"
        home = ev.get("homeTeamName", "?")
        away = ev.get("awayTeamName", "?")
        game_id = str(ev.get("gameId", ""))
        event_id = str(ev.get("eventId") or f"sr:match:{game_id}")
        markets = ev.get("markets", [])

        # Evaluate statistical safety if DB session provided
        safety_meta = {}
        if db:
            safety_meta = VirtualStatsEnricher.evaluate_fixture_safety(db, home, away, league)
            # Skip cold-trap matches (low goal frequency)
            if safety_meta.get("is_cold_trap"):
                continue

        # 1. Double Chance (1X / X2) — Draw-Protected
        dc = _extract_double_chance(markets)
        if dc["1x"] and 1.15 <= float(dc["1x"]) <= 1.45:
            dc_safety = safety_meta.get("dc_1x_safety", 0.75)
            candidates.append({
                "game_id": game_id,
                "event_id": event_id,
                "league": league,
                "match": f"{home} vs {away}",
                "pick": f"{home} or Draw (1X)",
                "pick_code": "1x",
                "market_type": "DC",
                "market_id": dc.get("market_id", "10"),
                "outcome_id": "9",
                "specifier": None,
                "odds": float(dc["1x"]),
                "safety_score": (1.0 / float(dc["1x"])) * (1.0 + (dc_safety * 0.2)),
            })
        elif dc["x2"] and 1.15 <= float(dc["x2"]) <= 1.45:
            dc_safety = safety_meta.get("dc_x2_safety", 0.75)
            candidates.append({
                "game_id": game_id,
                "event_id": event_id,
                "league": league,
                "match": f"{home} vs {away}",
                "pick": f"Draw or {away} (X2)",
                "pick_code": "x2",
                "market_type": "DC",
                "market_id": dc.get("market_id", "10"),
                "outcome_id": "11",
                "specifier": None,
                "odds": float(dc["x2"]),
                "safety_score": (1.0 / float(dc["x2"])) * (1.0 + (dc_safety * 0.2)),
            })

        # 2. Over 1.5 Total Goals
        for ou in _extract_ou_markets(markets):
            if ou["line"] == "1.5" and ou["over"] and 1.15 <= float(ou["over"]) <= 1.48:
                o_odds = float(ou["over"])
                exp_g = safety_meta.get("expected_goals", 2.9)
                prob = safety_meta.get("over_15_prob", 0.80)
                candidates.append({
                    "game_id": game_id,
                    "event_id": event_id,
                    "league": league,
                    "match": f"{home} vs {away}",
                    "pick": "Over 1.5 Goals",
                    "pick_code": "over_1.5",
                    "market_type": "OU",
                    "market_id": ou.get("market_id", "18"),
                    "outcome_id": ou.get("over_outcome_id", "12"),
                    "specifier": ou.get("specifier", "total=1.5"),
                    "odds": o_odds,
                    "safety_score": (1.0 / o_odds) * (1.0 + (prob * 0.2)),
                })


    if not candidates:
        return []

    if not candidates:
        return []

    # Sort candidates by safety score descending
    candidates.sort(key=lambda x: x["safety_score"], reverse=True)

    # Consider top 8 highest-safety candidate picks for combination search
    pool = candidates[:8]

    best_combo = []
    best_score = float("inf")
    target = float(target_odds or 2.0)
    min_bracket = target * 0.90  # e.g., 1.80x for 2.0x target
    max_bracket = target * 1.15  # e.g., 2.30x for 2.0x target

    # 1. Search 2-leg combinations
    from itertools import combinations
    for combo in combinations(pool, 2):
        if combo[0]["game_id"] == combo[1]["game_id"]:
            continue
        tot_odds = round(combo[0]["odds"] * combo[1]["odds"], 2)
        dist = abs(tot_odds - target)
        
        # Prefer combos within bracket
        bracket_penalty = 0.0 if (min_bracket <= tot_odds <= max_bracket) else (2.0 + dist)
        avg_safety = (combo[0]["safety_score"] + combo[1]["safety_score"]) / 2.0
        score = bracket_penalty + (dist * 1.5) - (avg_safety * 0.3)

        if score < best_score:
            best_score = score
            best_combo = list(combo)

    # 2. Search 3-leg combinations
    for combo in combinations(pool, 3):
        gids = {c["game_id"] for c in combo}
        if len(gids) < 3:
            continue
        tot_odds = round(combo[0]["odds"] * combo[1]["odds"] * combo[2]["odds"], 2)
        dist = abs(tot_odds - target)

        bracket_penalty = 0.0 if (min_bracket <= tot_odds <= max_bracket) else (2.0 + dist)
        avg_safety = (combo[0]["safety_score"] + combo[1]["safety_score"] + combo[2]["safety_score"]) / 3.0
        score = bracket_penalty + (dist * 1.5) - (avg_safety * 0.3)

        if score < best_score:
            best_score = score
            best_combo = list(combo)

    return best_combo if best_combo else candidates[:2]




def _build_booking_code(selections: List[Dict]) -> str:
    """
    Generates a live, verified SportyBet booking code for vFootball selections.
    """
    import httpx
    share_payload = []
    for s in selections:
        item = {
            "eventId": str(s.get("event_id") or f"sr:match:{s.get('game_id')}"),
            "marketId": str(s.get("market_id") or "1"),
            "outcomeId": str(s.get("outcome_id") or "1"),
        }
        if s.get("specifier"):
            item["specifier"] = str(s["specifier"])
        share_payload.append(item)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sportybet.com/ng/sport/vFootball/",
        "Origin": "https://www.sportybet.com"
    }

    try:
        with httpx.Client(timeout=5.0, headers=headers, verify=False) as client:
            r = client.post("https://www.sportybet.com/api/ng/orders/share", json={"selections": share_payload})
            if r.status_code == 200:
                d = r.json()
                if d.get("bizCode") == 10000:
                    code = d.get("data", {}).get("shareCode")
                    if code:
                        logger.info(f"[vFootball] Generated live SportyBet booking code: {code}")
                        return code
    except Exception as e:
        logger.warning(f"[vFootball] Live booking code error: {e}")

    # Fallback readable identifier
    import random, string
    return "VF" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


def _auto_generate_ticket(db: Session):
    """Internal: generate ticket with current agent config."""
    try:
        raw_events = VirtualSportyBetClient.fetch_upcoming_virtual_events()
        if not raw_events:
            return
        selections = _pick_selections(
            raw_events,
            AGENT_STATE["preferred_market"],
            AGENT_STATE["num_games"],
            AGENT_STATE["target_odds"]
        )
        if selections:
            total_odds = 1.0
            for s in selections:
                total_odds *= s["odds"]
            stake = AGENT_STATE["stake_amount"]
            AGENT_STATE["last_generated_ticket"] = {
                "selections": selections,
                "total_odds": round(total_odds, 2),
                "stake_ngn": stake,
                "potential_return_ngn": round(stake * total_odds, 2),
                "profit_ngn": round(stake * total_odds - stake, 2),
                "booking_code": _build_booking_code(selections),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sportybet_url": "https://www.sportybet.com/ng/sport/vFootball/",
            }
            AGENT_STATE["last_ticket_timestamp"] = AGENT_STATE["last_generated_ticket"]["generated_at"]
    except Exception as e:
        logger.error(f"[AutoTicket] Error: {e}")
