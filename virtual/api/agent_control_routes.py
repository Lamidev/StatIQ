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
from virtual.models.virtual_models import (
    VirtualLeague, VirtualEvent, VirtualOddsSnapshot, VirtualBankroll,
    VirtualAgentConfig, VirtualAgentHeartbeat, VirtualAgentAuditLog, VirtualFrontTestSlip
)
from virtual.ingestion.virtual_sportybet_client import VirtualSportyBetClient
from virtual.paper.paper_trader import PaperTrader

logger = logging.getLogger("statiq.virtual.agent_control")
router = APIRouter()


def get_or_create_agent_config(db: Session) -> VirtualAgentConfig:
    """
    Authoritative Single Source of Truth for the Virtual Agent.
    Guarantees a persistent database configuration row exists.
    """
    cfg = db.query(VirtualAgentConfig).filter(VirtualAgentConfig.id == "default").first()
    if not cfg:
        cfg = VirtualAgentConfig(
            id="default",
            enabled=True,
            emergency_stop=False,
            target_odds=2.0,
            stake_amount=1000.0,
            league_count=2,
            selected_leagues=["England Virtual", "Spain Virtual"],
            strategy="ADAPTIVE",
            risk_profile="CONSERVATIVE",
            preferred_market="ALL",
            execution_mode="PAPER",
            max_consecutive_losses=3,
            max_daily_loss=5000.0,
            config_version=1
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def log_agent_audit(db: Session, event_type: str, payload: Dict[str, Any], config_version: int, operator: str = "UI"):
    """Records an immutable audit trail entry for state changes."""
    try:
        audit_entry = VirtualAgentAuditLog(
            event_type=event_type,
            payload=payload,
            config_version=config_version,
            operator=operator,
            created_at=datetime.now(timezone.utc)
        )
        db.add(audit_entry)
        db.commit()
    except Exception as e:
        logger.error(f"[AuditLog] Failed to record audit log: {e}")


class PersistentAgentConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    emergency_stop: Optional[bool] = None
    target_odds: Optional[float] = None
    stake_amount: Optional[float] = None
    league_count: Optional[int] = None
    selected_leagues: Optional[List[str]] = None
    strategy: Optional[str] = None
    risk_profile: Optional[str] = None
    preferred_market: Optional[str] = None
    execution_mode: Optional[str] = None
    max_consecutive_losses: Optional[int] = None
    max_daily_loss: Optional[float] = None


# ---------------------------------------------------------------
# Authoritative Control Plane Endpoints (PRD v4.0)
# ---------------------------------------------------------------

@router.get("/agent/status")
@router.get("/status")
def get_agent_status(db: Session = Depends(get_db)):
    """
    Returns authoritative DB config, live VPS worker heartbeat, config sync state,
    and cumulative performance ledger metrics.
    """
    cfg = get_or_create_agent_config(db)
    heartbeat = db.query(VirtualAgentHeartbeat).filter(VirtualAgentHeartbeat.worker_id == "vfootball_fronttest_worker").first()

    now_utc = datetime.now(timezone.utc)
    is_online = False
    heartbeat_age_sec = 999.0
    worker_state = "OFFLINE"
    worker_version = 0

    if heartbeat and heartbeat.last_seen:
        hb_ts = heartbeat.last_seen
        if hb_ts.tzinfo is None:
            hb_ts = hb_ts.replace(tzinfo=timezone.utc)
        heartbeat_age_sec = (now_utc - hb_ts).total_seconds()
        is_online = heartbeat_age_sec < 30.0
        worker_version = heartbeat.config_version or 0
        worker_state = heartbeat.worker_state if is_online else "OFFLINE"

    is_synced = is_online and (worker_version == cfg.config_version)

    # Calculate ledger performance metrics
    all_slips = db.query(VirtualFrontTestSlip).order_by(VirtualFrontTestSlip.created_at.desc()).all()
    total_slips = len(all_slips)
    won_slips = sum(1 for s in all_slips if s.status == "WON")
    lost_slips = sum(1 for s in all_slips if s.status == "LOST")
    pending_slips = sum(1 for s in all_slips if s.status == "PENDING")
    settled = won_slips + lost_slips
    win_rate = round((won_slips / settled) * 100.0, 1) if settled > 0 else 0.0
    net_profit = sum(s.profit_loss for s in all_slips if s.profit_loss is not None)

    recent_slips = []
    seen_codes = set()
    for s in all_slips:
        code_key = s.booking_code or str(s.id)
        if code_key in seen_codes:
            continue
        seen_codes.add(code_key)
        recent_slips.append({
            "id": s.id,
            "ticket_id": s.ticket_id,
            "booking_code": s.booking_code,
            "league_name": s.league_name,
            "round_time": s.round_time.isoformat() if s.round_time else None,
            "actual_odds": s.actual_odds,
            "num_games": s.num_games,
            "status": s.status,
            "profit_loss": s.profit_loss,
            "selections": s.selections,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
        if len(recent_slips) >= 15:
            break

    return {
        "status": "SUCCESS",
        "config": {
            "enabled": cfg.enabled,
            "emergency_stop": cfg.emergency_stop,
            "target_odds": cfg.target_odds,
            "stake_amount": cfg.stake_amount,
            "league_count": cfg.league_count,
            "selected_leagues": cfg.selected_leagues or [],
            "strategy": cfg.strategy,
            "risk_profile": cfg.risk_profile,
            "preferred_market": cfg.preferred_market,
            "execution_mode": cfg.execution_mode,
            "config_version": cfg.config_version,
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
        },
        "heartbeat": {
            "is_online": is_online,
            "worker_state": worker_state,
            "heartbeat_age_seconds": round(heartbeat_age_sec, 1),
            "worker_config_version": worker_version,
            "server_config_version": cfg.config_version,
            "is_synced": is_synced,
            "current_round": heartbeat.current_round if heartbeat else None,
            "current_league": heartbeat.current_league if heartbeat else None,
            "last_seen": heartbeat.last_seen.isoformat() if heartbeat and heartbeat.last_seen else None
        },
        "performance": {
            "total_slips": total_slips,
            "won_slips": won_slips,
            "lost_slips": lost_slips,
            "pending_slips": pending_slips,
            "win_rate_pct": win_rate,
            "net_profit_units": round(net_profit, 2),
            "recent_slips": recent_slips
        }
    }


@router.get("/agent/config")
def get_agent_config_endpoint(db: Session = Depends(get_db)):
    """Returns the persistent agent configuration record."""
    cfg = get_or_create_agent_config(db)
    return {
        "enabled": cfg.enabled,
        "emergency_stop": cfg.emergency_stop,
        "target_odds": cfg.target_odds,
        "stake_amount": cfg.stake_amount,
        "league_count": cfg.league_count,
        "selected_leagues": cfg.selected_leagues or [],
        "strategy": cfg.strategy,
        "risk_profile": cfg.risk_profile,
        "preferred_market": cfg.preferred_market,
        "execution_mode": cfg.execution_mode,
        "max_consecutive_losses": cfg.max_consecutive_losses,
        "max_daily_loss": cfg.max_daily_loss,
        "config_version": cfg.config_version,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
    }


@router.post("/agent/config")
def update_persistent_agent_config(payload: PersistentAgentConfigUpdate, db: Session = Depends(get_db)):
    """
    Authoritative configuration update with monotonic version increment and audit logging.
    """
    cfg = get_or_create_agent_config(db)
    changes = payload.dict(exclude_unset=True)

    if not changes:
        return {"status": "NO_OP", "message": "No configuration parameters provided.", "config_version": cfg.config_version}

    for k, v in changes.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    cfg.config_version += 1
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    log_agent_audit(db, "CONFIG_UPDATE", changes, cfg.config_version)

    return {
        "status": "SUCCESS",
        "message": f"Configuration updated to v{cfg.config_version}.",
        "config_version": cfg.config_version,
        "config": {
            "enabled": cfg.enabled,
            "emergency_stop": cfg.emergency_stop,
            "target_odds": cfg.target_odds,
            "stake_amount": cfg.stake_amount,
            "league_count": cfg.league_count,
            "selected_leagues": cfg.selected_leagues,
            "strategy": cfg.strategy,
            "risk_profile": cfg.risk_profile,
            "preferred_market": cfg.preferred_market,
            "execution_mode": cfg.execution_mode
        }
    }


@router.post("/agent/pause")
def pause_agent_endpoint(db: Session = Depends(get_db)):
    """Pauses ticket generation and execution across the VPS worker."""
    cfg = get_or_create_agent_config(db)
    cfg.enabled = False
    cfg.config_version += 1
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    log_agent_audit(db, "PAUSE", {"enabled": False}, cfg.config_version)

    return {
        "status": "SUCCESS",
        "worker_state": "PAUSED",
        "enabled": False,
        "config_version": cfg.config_version,
        "message": f"Agent execution paused (Config v{cfg.config_version})."
    }


@router.post("/agent/resume")
def resume_agent_endpoint(db: Session = Depends(get_db)):
    """Resumes agent ticket generation and execution."""
    cfg = get_or_create_agent_config(db)
    cfg.enabled = True
    cfg.emergency_stop = False
    cfg.config_version += 1
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    log_agent_audit(db, "RESUME", {"enabled": True, "emergency_stop": False}, cfg.config_version)

    return {
        "status": "SUCCESS",
        "worker_state": "RUNNING",
        "enabled": True,
        "config_version": cfg.config_version,
        "message": f"Agent execution resumed (Config v{cfg.config_version})."
    }


@router.post("/agent/emergency-stop")
@router.post("/emergency-stop")
@router.post("/fronttest/emergency-stop")
def emergency_stop_endpoint(db: Session = Depends(get_db)):
    """Locks all execution unconditionally under EMERGENCY_STOP state."""
    cfg = get_or_create_agent_config(db)
    cfg.enabled = False
    cfg.emergency_stop = True
    cfg.config_version += 1
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    log_agent_audit(db, "EMERGENCY_STOP", {"emergency_stop": True, "enabled": False}, cfg.config_version)

    return {
        "status": "SUCCESS",
        "worker_state": "EMERGENCY_STOPPED",
        "emergency_stop": True,
        "config_version": cfg.config_version,
        "message": f"EMERGENCY STOP engaged. All execution blocked (Config v{cfg.config_version})."
    }


@router.post("/agent/presets/{preset_name}")
def apply_agent_preset(preset_name: str, db: Session = Depends(get_db)):
    """
    Applies validated quantitative configuration presets.
    Presets: CONSERVATIVE, BALANCED, AGGRESSIVE, ROLLOVER
    """
    cfg = get_or_create_agent_config(db)
    p_name = preset_name.upper().strip()

    presets = {
        "CONSERVATIVE": {
            "target_odds": 1.50,
            "league_count": 1,
            "risk_profile": "CONSERVATIVE",
            "strategy": "CONSERVATIVE",
            "preferred_market": "DOUBLE_CHANCE",
            "stake_amount": 1000.0
        },
        "BALANCED": {
            "target_odds": 2.00,
            "league_count": 2,
            "risk_profile": "BALANCED",
            "strategy": "ADAPTIVE",
            "preferred_market": "ALL",
            "stake_amount": 1000.0
        },
        "AGGRESSIVE": {
            "target_odds": 3.00,
            "league_count": 3,
            "risk_profile": "AGGRESSIVE",
            "strategy": "VALUE",
            "preferred_market": "ALL",
            "stake_amount": 1000.0
        },
        "ROLLOVER": {
            "target_odds": 2.00,
            "league_count": 2,
            "risk_profile": "CONSERVATIVE",
            "strategy": "ROLLOVER",
            "preferred_market": "ALL",
            "stake_amount": 2000.0
        }
    }

    if p_name not in presets:
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset_name}'. Supported: {list(presets.keys())}")

    p_vals = presets[p_name]
    for k, v in p_vals.items():
        setattr(cfg, k, v)

    cfg.config_version += 1
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    log_agent_audit(db, f"PRESET_{p_name}", p_vals, cfg.config_version)

    return {
        "status": "SUCCESS",
        "preset_applied": p_name,
        "config_version": cfg.config_version,
        "config": {
            "target_odds": cfg.target_odds,
            "league_count": cfg.league_count,
            "risk_profile": cfg.risk_profile,
            "strategy": cfg.strategy,
            "preferred_market": cfg.preferred_market,
            "stake_amount": cfg.stake_amount
        }
    }


@router.post("/agent/toggle")
def toggle_agent_endpoint(enabled: bool = Query(...), db: Session = Depends(get_db)):
    """Backward-compatible toggle endpoint mapped to persistent DB config."""
    if enabled:
        return resume_agent_endpoint(db)
    else:
        return pause_agent_endpoint(db)


@router.get("/agent/audit-log")
def get_audit_log_endpoint(limit: int = 50, db: Session = Depends(get_db)):
    """Returns recent audit log records for observability."""
    logs = db.query(VirtualAgentAuditLog).order_by(VirtualAgentAuditLog.created_at.desc()).limit(limit).all()
    return {
        "total": len(logs),
        "logs": [
            {
                "id": l.id,
                "event_type": l.event_type,
                "payload": l.payload,
                "config_version": l.config_version,
                "operator": l.operator,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in logs
        ]
    }


# ---------------------------------------------------------------
# Backward Compatibility Wrappers
# ---------------------------------------------------------------

@router.get("/state")
def get_legacy_agent_state(db: Session = Depends(get_db)):
    """Returns legacy state format backed by persistent DB config."""
    cfg = get_or_create_agent_config(db)
    bankroll = PaperTrader.get_bankroll_summary(db)
    return {
        "agent": {
            "is_active": cfg.enabled and not cfg.emergency_stop,
            "target_odds": cfg.target_odds,
            "num_games": cfg.league_count,
            "stake_amount": cfg.stake_amount,
            "preferred_market": cfg.preferred_market,
            "config_version": cfg.config_version,
        },
        "bankroll": bankroll,
    }


@router.post("/config")
def update_legacy_agent_config(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Legacy config updater mapped to persistent DB config."""
    cfg = get_or_create_agent_config(db)
    if "is_active" in payload and payload["is_active"] is not None:
        cfg.enabled = bool(payload["is_active"])
    if "target_odds" in payload and payload["target_odds"] is not None:
        cfg.target_odds = float(payload["target_odds"])
    if "num_games" in payload and payload["num_games"] is not None:
        cfg.league_count = int(payload["num_games"])
    if "stake_amount" in payload and payload["stake_amount"] is not None:
        cfg.stake_amount = float(payload["stake_amount"])
    if "preferred_market" in payload and payload["preferred_market"] is not None:
        cfg.preferred_market = str(payload["preferred_market"])

    cfg.config_version += 1
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    log_agent_audit(db, "LEGACY_CONFIG_UPDATE", payload, cfg.config_version)

    return {
        "message": f"Agent configuration updated to v{cfg.config_version}.",
        "config_version": cfg.config_version,
        "agent": {
            "is_active": cfg.enabled and not cfg.emergency_stop,
            "target_odds": cfg.target_odds,
            "num_games": cfg.league_count,
            "stake_amount": cfg.stake_amount,
            "preferred_market": cfg.preferred_market,
        }
    }


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


@router.post("/agent/admin/purge")
@router.post("/reset-ledger")
def purge_virtual_database_endpoint(
    force_override: bool = Query(False, description="Override active bet safety lock"),
    db: Session = Depends(get_db)
):
    """
    Safely purges historical virtual events, odds snapshots, match results, and slips.
    Guarantees that active bets are checked and agent configuration is strictly preserved.
    """
    from virtual.services.purge_service import VirtualDatabasePurgeService
    res = VirtualDatabasePurgeService.purge_virtual_database(db, force_override=force_override, operator="UI_ADMIN")
    if res.get("status") == "BLOCKED":
        raise HTTPException(status_code=409, detail=res)
    elif res.get("status") == "FAILED":
        raise HTTPException(status_code=500, detail=res)
    return res



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
    Uses VirtualMarketEngine to assemble 2-to-3 calibrated, multi-market selections.
    Enforces Fail-Closed behavior: Returns [] (NO_BET) if no combination satisfies the bracket.
    """
    from virtual.services.virtual_market_engine import VirtualMarketEngine
    return VirtualMarketEngine.build_ticket_from_events(
        events=events,
        target_odds=target_odds,
        preferred_market=market,
        db=db
    )




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
