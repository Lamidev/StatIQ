"""
Paper Trading API Routes — Live ledger, bankroll, bet history, and manual controls.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from virtual.core.db import get_db
from virtual.paper.paper_trader import PaperTrader
from virtual.workers.paper_worker import PaperTradingWorker

router = APIRouter()


@router.get("/bankroll")
def get_bankroll(db: Session = Depends(get_db)):
    """Returns the current paper bankroll state."""
    return PaperTrader.get_bankroll_summary(db)


@router.get("/open-bets")
def get_open_bets(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """Returns all currently open (unsettled) paper bets."""
    bets = PaperTrader.get_open_bets(db, limit=limit)
    return {"count": len(bets), "bets": bets}


@router.get("/history")
def get_bet_history(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    """Returns settled paper bet history."""
    bets = PaperTrader.get_settled_bets(db, limit=limit)
    wins = sum(1 for b in bets if b.get("outcome") == "WIN")
    losses = sum(1 for b in bets if b.get("outcome") == "LOSS")
    total_pl = sum(b.get("profit_loss") or 0 for b in bets)
    return {
        "count": len(bets),
        "wins": wins,
        "losses": losses,
        "total_profit_loss": round(total_pl, 2),
        "bets": bets,
    }


@router.get("/session-stats")
def get_session_stats(db: Session = Depends(get_db)):
    """Returns today's live session stats — win rate, P&L, streak."""
    return PaperTrader.get_session_stats(db)


@router.get("/worker-status")
def get_worker_status():
    """Returns the status of the background paper trading worker."""
    return PaperTradingWorker.get_status()


@router.post("/manual/fire-bets")
def manual_fire_bets(db: Session = Depends(get_db)):
    """
    Manually triggers a bet-firing cycle.
    Useful for testing or forcing a scan without waiting for the background worker.
    """
    result = PaperTrader.fire_bets_for_upcoming_events(db)
    return {"message": "Bet firing cycle completed.", "result": result}


@router.post("/manual/settle")
def manual_settle(db: Session = Depends(get_db)):
    """
    Manually triggers a settlement scan.
    Settles any open bets whose events now have results.
    """
    result = PaperTrader.settle_open_bets(db)
    return {"message": "Settlement scan completed.", "result": result}


@router.post("/bankroll/reset")
def reset_bankroll(db: Session = Depends(get_db)):
    """
    Resets the paper bankroll to the configured starting balance.
    This closes all open bets and clears the ledger.
    WARNING: This is destructive — used for testing or starting a fresh session.
    """
    from virtual.models.virtual_models import VirtualPaperBet, VirtualBankroll
    from virtual.core.config import virtual_config

    # Void all open bets (return stake to bankroll first)
    open_bets = db.query(VirtualPaperBet).filter(VirtualPaperBet.status == "OPEN").all()
    for bet in open_bets:
        bet.status = "VOIDED"
        bet.profit_loss = 0.0
        bet.settled_at = None

    # Delete all bankroll records and reseed
    db.query(VirtualBankroll).delete()
    db.commit()

    bankroll = PaperTrader.ensure_bankroll(db)
    return {
        "message": f"Bankroll reset to ₦{virtual_config.INITIAL_PAPER_BANKROLL:,.2f}. {len(open_bets)} open bets voided.",
        "bankroll": PaperTrader.get_bankroll_summary(db),
    }
