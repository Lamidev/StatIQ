"""
Risk Engine API Routes — Real-time risk dashboard, gate audits, and config.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from virtual.core.db import get_db
from virtual.core.config import virtual_config
from virtual.risk.risk_engine import RiskEngine

router = APIRouter()


@router.get("/state")
def get_risk_state(db: Session = Depends(get_db)):
    """
    Returns the complete real-time risk state:
    risk level, gate statuses, bankroll snapshot, and Kelly example.
    """
    return RiskEngine.get_current_risk_state(db)


@router.get("/config")
def get_risk_config():
    """Returns the current risk configuration limits."""
    return {
        "agent_mode": virtual_config.AGENT_MODE,
        "kill_switch_active": virtual_config.KILL_SWITCH_ACTIVE,
        "limits": {
            "max_daily_loss_pct": virtual_config.MAX_DAILY_LOSS_PCT,
            "max_single_stake_pct": virtual_config.MAX_SINGLE_STAKE_PCT,
            "max_consecutive_losses": virtual_config.MAX_CONSECUTIVE_LOSSES,
            "max_open_exposure_pct": virtual_config.MAX_OPEN_EXPOSURE_PCT,
            "min_edge_threshold": virtual_config.MIN_EDGE_THRESHOLD,
        },
        "kelly": {
            "half_kelly_fraction": RiskEngine.HALF_KELLY_FRACTION,
            "min_stake": RiskEngine.MIN_STAKE,
            "max_drawdown_block_pct": RiskEngine.MAX_DRAWDOWN_BLOCK * 100,
        },
    }


@router.post("/audit-gate")
def audit_gate(
    model_prob: float = 0.65,
    market_prob: float = 0.55,
    odds: float = 1.85,
    strategy_code: str = "AUDIT",
    db: Session = Depends(get_db),
):
    """
    Runs a simulated bet through all risk gates and returns the full
    audit trail. Useful for testing parameter sets without firing a real bet.
    """
    decision = RiskEngine.evaluate_bet_gate(
        db=db,
        model_prob=model_prob,
        market_prob=market_prob,
        odds=odds,
        strategy_code=strategy_code,
    )
    return decision.to_dict()


@router.post("/calculate-kelly")
def calculate_kelly(
    model_prob: float = 0.65,
    odds: float = 1.85,
    db: Session = Depends(get_db),
):
    """
    Calculates the Kelly-optimal stake for a given model probability and odds
    against the current available bankroll.
    """
    from virtual.models.virtual_models import VirtualBankroll
    bankroll = db.query(VirtualBankroll).filter(VirtualBankroll.mode == "PAPER").order_by(VirtualBankroll.id.desc()).first()
    available = bankroll.available_balance if bankroll else virtual_config.INITIAL_PAPER_BANKROLL

    stake, info = RiskEngine.calculate_kelly_stake(
        model_prob=model_prob,
        odds=odds,
        available_balance=available,
    )
    return {
        "model_prob": model_prob,
        "odds": odds,
        "available_balance": available,
        "kelly_stake": stake,
        "description": info,
    }
