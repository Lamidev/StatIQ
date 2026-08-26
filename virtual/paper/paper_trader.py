"""
PaperTrader — Simulated bet execution and settlement engine.

Responsibilities:
  1. fire_bets_for_upcoming_events(): Evaluates upcoming events via SignalGenerator,
     creates VirtualPrediction + VirtualPaperBet rows for every BET signal,
     and debits the VirtualBankroll.

  2. settle_open_bets(): Scans all OPEN paper bets whose event now has a
     VirtualResult, settles WIN/LOSS, credits/debits bankroll, updates stats.

  3. ensure_bankroll(): Guarantees a bankroll record exists, creates one at the
     configured starting balance if not.

SAFETY RULES:
  - Never double-fire a bet for the same (event_id, market_type) pair.
  - Never settle a bet twice.
  - All DB writes are within atomic transactions.
"""
import uuid
import datetime
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from virtual.core.config import virtual_config
from virtual.core.db import SessionLocal
from virtual.models.virtual_models import (
    VirtualEvent,
    VirtualOddsSnapshot,
    VirtualResult,
    VirtualStrategy,
    VirtualPrediction,
    VirtualPaperBet,
    VirtualBankroll,
    VirtualAgentLog,
)
from virtual.strategy.signal_generator import SignalGenerator
from virtual.strategy.strategy_registry import StrategyRegistry
from virtual.risk.risk_engine import RiskEngine

logger = logging.getLogger("statiq.virtual.paper_trader")


class PaperTrader:
    """
    Autonomous paper trading execution layer.
    """

    FLAT_STAKE_PCT: float = 0.005  # 0.5% of available bankroll per bet (conservative)

    # ── Bankroll Management ──────────────────────────────────────────────────

    @classmethod
    def ensure_bankroll(cls, db: Session) -> VirtualBankroll:
        """Returns existing bankroll or seeds a new one at the configured starting balance."""
        bankroll = db.query(VirtualBankroll).filter(VirtualBankroll.mode == "PAPER").order_by(VirtualBankroll.id.desc()).first()
        if not bankroll:
            bankroll = VirtualBankroll(
                mode="PAPER",
                starting_balance=virtual_config.INITIAL_PAPER_BANKROLL,
                current_balance=virtual_config.INITIAL_PAPER_BANKROLL,
                available_balance=virtual_config.INITIAL_PAPER_BANKROLL,
                total_exposure=0.0,
                total_bets=0,
                won_bets=0,
                lost_bets=0,
                daily_profit_loss=0.0,
                cumulative_roi=0.0,
                max_drawdown_pct=0.0,
                consecutive_losses=0,
            )
            db.add(bankroll)
            db.commit()
            db.refresh(bankroll)
            logger.info(f"[PaperTrader] Bankroll seeded at ₦{virtual_config.INITIAL_PAPER_BANKROLL:,.2f}")
        return bankroll

    @classmethod
    def get_bankroll_summary(cls, db: Session) -> Dict[str, Any]:
        """Returns a serialisable bankroll summary dict."""
        br = cls.ensure_bankroll(db)
        win_rate = (br.won_bets / br.total_bets * 100.0) if br.total_bets > 0 else 0.0
        total_pl = br.current_balance - br.starting_balance
        roi_pct = (total_pl / br.starting_balance * 100.0) if br.starting_balance > 0 else 0.0
        return {
            "mode": br.mode,
            "starting_balance": br.starting_balance,
            "current_balance": br.current_balance,
            "available_balance": br.available_balance,
            "total_exposure": br.total_exposure,
            "total_bets": br.total_bets,
            "won_bets": br.won_bets,
            "lost_bets": br.lost_bets,
            "win_rate_pct": round(win_rate, 2),
            "daily_profit_loss": br.daily_profit_loss,
            "total_profit_loss": round(total_pl, 2),
            "cumulative_roi_pct": round(roi_pct, 2),
            "max_drawdown_pct": round(br.max_drawdown_pct * 100, 2),
            "consecutive_losses": br.consecutive_losses,
            "updated_at": br.updated_at.isoformat() if br.updated_at else None,
        }

    # ── Bet Firing ───────────────────────────────────────────────────────────

    @classmethod
    def fire_bets_for_upcoming_events(cls, db: Session) -> Dict[str, Any]:
        """
        Runs SignalGenerator against upcoming events and places paper bets
        for all BET signals that don't already have an open bet.
        Returns a summary of what was placed.
        """
        if virtual_config.KILL_SWITCH_ACTIVE:
            logger.warning("[PaperTrader] Kill switch active — bet firing suppressed.")
            return {"placed": 0, "skipped": 0, "kill_switch": True}

        StrategyRegistry.ensure_strategies_in_db(db)
        bankroll = cls.ensure_bankroll(db)

        signals = SignalGenerator.generate_signals_for_upcoming_events(db, limit=50)
        placed = 0
        skipped = 0

        for sig in signals:
            if sig["signal"] != "BET":
                skipped += 1
                continue

            event_id = sig["event_id"]
            market_type = sig["market_type"]

            # De-duplicate: skip if we already have an open/settled prediction for this (event, market)
            existing = (
                db.query(VirtualPrediction)
                .filter(
                    VirtualPrediction.event_id == event_id,
                    VirtualPrediction.market_type == market_type,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

            # ── Risk Engine Gate (replaces flat stake) ──────────────────────
            risk_decision = RiskEngine.evaluate_bet_gate(
                db=db,
                model_prob=sig["model_probability"],
                market_prob=sig["market_probability"],
                odds=sig["odds"],
                strategy_code=sig["strategy_code"],
            )

            if risk_decision.action == "BLOCK":
                cls._log(db, "RiskEngine", "WARNING",
                         f"BET BLOCKED [{sig['home_team']} v {sig['away_team']} | {sig['selection']}]: {risk_decision.reason}",
                         event_id=sig["provider_event_id"])
                skipped += 1
                continue

            stake = risk_decision.stake

            if stake > bankroll.available_balance:
                logger.warning("[PaperTrader] Insufficient available balance — skipping bet.")
                skipped += 1
                continue

            # Resolve strategy DB row
            strategy_row = db.query(VirtualStrategy).filter(VirtualStrategy.code == sig["strategy_code"]).first()

            # Create prediction audit record
            pred = VirtualPrediction(
                prediction_uuid=str(uuid.uuid4()),
                event_id=event_id,
                strategy_id=strategy_row.id if strategy_row else None,
                strategy_version=strategy_row.current_version if strategy_row else "v1.0.0",
                market_type=market_type,
                selection=sig["selection"],
                odds_at_prediction=sig["odds"],
                model_probability=sig["model_probability"],
                market_probability=sig["market_probability"],
                edge=sig["edge"],
                confidence=sig["confidence"],
                sample_size_at_prediction=0,
                signal="BET",
                status="ACTIVE",
            )
            db.add(pred)
            db.flush()  # get pred.id

            # Create paper bet
            potential_return = round(stake * sig["odds"], 2)
            bet = VirtualPaperBet(
                prediction_id=pred.id,
                stake=stake,
                odds=sig["odds"],
                potential_return=potential_return,
                status="OPEN",
                profit_loss=None,
                placed_at=datetime.datetime.utcnow(),
            )
            db.add(bet)

            # Debit bankroll
            bankroll.available_balance = round(bankroll.available_balance - stake, 2)
            bankroll.total_exposure = round(bankroll.total_exposure + stake, 2)
            bankroll.total_bets += 1
            bankroll.updated_at = datetime.datetime.utcnow()

            cls._log(db, "PaperTrader", "INFO",
                     f"BET PLACED: {sig['home_team']} v {sig['away_team']} | {sig['selection']} @ {sig['odds']} | Stake: ₦{stake:.2f} | Edge: +{sig['edge_pct']}%",
                     event_id=sig["provider_event_id"])
            placed += 1

        db.commit()
        return {"placed": placed, "skipped": skipped, "kill_switch": False}

    # ── Settlement ───────────────────────────────────────────────────────────

    @classmethod
    def settle_open_bets(cls, db: Session) -> Dict[str, Any]:
        """
        Looks up all OPEN paper bets and settles them if the event has a result.
        Returns settlement summary.
        """
        bankroll = cls.ensure_bankroll(db)

        # Load all OPEN bets with their predictions and events
        open_bets: List[VirtualPaperBet] = (
            db.query(VirtualPaperBet)
            .join(VirtualPrediction, VirtualPrediction.id == VirtualPaperBet.prediction_id)
            .filter(VirtualPaperBet.status == "OPEN")
            .all()
        )

        won = 0
        lost = 0
        unsettled = 0

        for bet in open_bets:
            pred = bet.prediction
            if not pred:
                continue

            event = db.query(VirtualEvent).filter(VirtualEvent.id == pred.event_id).first()
            if not event:
                continue

            result: Optional[VirtualResult] = event.result
            if not result:
                unsettled += 1
                continue

            # Determine outcome
            is_win = cls._resolve_outcome(pred.market_type, result)
            pl = round((bet.stake * bet.odds - bet.stake), 2) if is_win else round(-bet.stake, 2)

            # Update bet
            bet.status = "SETTLED"
            bet.profit_loss = pl
            bet.settled_at = datetime.datetime.utcnow()

            # Update prediction
            pred.status = "SETTLED"

            # Update bankroll
            bankroll.available_balance = round(bankroll.available_balance + bet.stake + pl, 2)
            bankroll.current_balance = round(bankroll.current_balance + pl, 2)
            bankroll.total_exposure = round(max(0.0, bankroll.total_exposure - bet.stake), 2)
            bankroll.daily_profit_loss = round(bankroll.daily_profit_loss + pl, 2)

            if is_win:
                bankroll.won_bets += 1
                bankroll.consecutive_losses = 0
                won += 1
            else:
                bankroll.lost_bets += 1
                bankroll.consecutive_losses += 1
                lost += 1

            # Recalculate ROI
            total_pl = bankroll.current_balance - bankroll.starting_balance
            bankroll.cumulative_roi = round(total_pl / bankroll.starting_balance, 4) if bankroll.starting_balance > 0 else 0.0

            # Drawdown tracking (peak-to-trough)
            if bankroll.current_balance < bankroll.starting_balance:
                dd_pct = (bankroll.starting_balance - bankroll.current_balance) / bankroll.starting_balance
                bankroll.max_drawdown_pct = max(bankroll.max_drawdown_pct, dd_pct)

            bankroll.updated_at = datetime.datetime.utcnow()

            outcome_str = "WIN" if is_win else "LOSS"
            cls._log(db, "PaperTrader", "INFO",
                     f"BET SETTLED [{outcome_str}]: {event.home_team} v {event.away_team} | {pred.selection} | "
                     f"Score: {result.home_score}-{result.away_score} | P&L: ₦{pl:+.2f}",
                     event_id=event.provider_event_id)

        db.commit()
        return {"won": won, "lost": lost, "unsettled": unsettled}

    # ── Ledger Queries ───────────────────────────────────────────────────────

    @classmethod
    def get_open_bets(cls, db: Session, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns all open (unsettled) paper bets."""
        bets = (
            db.query(VirtualPaperBet)
            .join(VirtualPrediction, VirtualPrediction.id == VirtualPaperBet.prediction_id)
            .filter(VirtualPaperBet.status == "OPEN")
            .order_by(VirtualPaperBet.placed_at.desc())
            .limit(limit)
            .all()
        )
        return [cls._serialise_bet(b) for b in bets]

    @classmethod
    def get_settled_bets(cls, db: Session, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns recently settled paper bets."""
        bets = (
            db.query(VirtualPaperBet)
            .join(VirtualPrediction, VirtualPrediction.id == VirtualPaperBet.prediction_id)
            .filter(VirtualPaperBet.status == "SETTLED")
            .order_by(VirtualPaperBet.settled_at.desc())
            .limit(limit)
            .all()
        )
        return [cls._serialise_bet(b) for b in bets]

    @classmethod
    def get_session_stats(cls, db: Session) -> Dict[str, Any]:
        """Computes live session stats from the current day's settled bets."""
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        today_bets = (
            db.query(VirtualPaperBet)
            .join(VirtualPrediction, VirtualPrediction.id == VirtualPaperBet.prediction_id)
            .filter(
                VirtualPaperBet.status == "SETTLED",
                VirtualPaperBet.settled_at >= today_start,
            )
            .all()
        )

        wins = [b for b in today_bets if (b.profit_loss or 0) > 0]
        losses = [b for b in today_bets if (b.profit_loss or 0) <= 0]
        total_pl = sum(b.profit_loss or 0 for b in today_bets)
        total_staked = sum(b.stake for b in today_bets)

        # Streak tracking
        all_settled = (
            db.query(VirtualPaperBet)
            .filter(VirtualPaperBet.status == "SETTLED")
            .order_by(VirtualPaperBet.settled_at.desc())
            .limit(20)
            .all()
        )
        streak = cls._compute_current_streak(all_settled)

        open_bets = db.query(VirtualPaperBet).filter(VirtualPaperBet.status == "OPEN").count()

        return {
            "today_bets": len(today_bets),
            "today_wins": len(wins),
            "today_losses": len(losses),
            "today_hit_rate_pct": round(len(wins) / len(today_bets) * 100, 1) if today_bets else 0.0,
            "today_profit_loss": round(total_pl, 2),
            "today_roi_pct": round(total_pl / total_staked * 100, 2) if total_staked > 0 else 0.0,
            "open_bets": open_bets,
            "current_streak": streak,
        }

    # ── Internal Helpers ─────────────────────────────────────────────────────

    @classmethod
    def _resolve_outcome(cls, market_type: str, result: VirtualResult) -> bool:
        """Returns True if the market selection won."""
        mt = market_type.upper()
        if mt == "OVER_UNDER_1.5": return result.is_over_1_5
        if mt == "OVER_UNDER_2.5": return result.is_over_2_5
        if mt == "OVER_UNDER_3.5": return result.is_over_3_5
        if mt == "1X2_HOME": return result.outcome_1x2 == "H"
        if mt == "1X2_AWAY": return result.outcome_1x2 == "A"
        if mt == "1X2_DRAW": return result.outcome_1x2 == "D"
        if mt == "DOUBLE_CHANCE_1X": return result.outcome_1x2 in ("H", "D")
        if mt == "DOUBLE_CHANCE_2X": return result.outcome_1x2 in ("A", "D")
        if mt == "DOUBLE_CHANCE_12": return result.outcome_1x2 in ("H", "A")
        if mt == "BTTS_YES": return result.is_btts
        if mt == "BTTS_NO": return not result.is_btts
        return False

    @classmethod
    def _serialise_bet(cls, bet: VirtualPaperBet) -> Dict[str, Any]:
        """Serialises a VirtualPaperBet + related prediction/event into a response dict."""
        pred = bet.prediction
        event = pred.event if pred else None
        return {
            "bet_id": bet.id,
            "prediction_uuid": pred.prediction_uuid if pred else None,
            "status": bet.status,
            "home_team": event.home_team if event else None,
            "away_team": event.away_team if event else None,
            "league_name": event.league.name if (event and event.league) else "Virtual Football",
            "scheduled_time": event.scheduled_time.isoformat() if (event and event.scheduled_time) else None,
            "market_type": pred.market_type if pred else None,
            "selection": pred.selection if pred else None,
            "odds": bet.odds,
            "stake": bet.stake,
            "potential_return": bet.potential_return,
            "model_probability": pred.model_probability if pred else None,
            "edge": pred.edge if pred else None,
            "signal": pred.signal if pred else "BET",
            "confidence": pred.confidence if pred else None,
            "strategy_code": pred.strategy.code if (pred and pred.strategy) else None,
            "profit_loss": bet.profit_loss,
            "outcome": "WIN" if (bet.profit_loss and bet.profit_loss > 0) else ("LOSS" if (bet.profit_loss is not None and bet.profit_loss <= 0) else None),
            "placed_at": bet.placed_at.isoformat() if bet.placed_at else None,
            "settled_at": bet.settled_at.isoformat() if bet.settled_at else None,
        }

    @classmethod
    def _compute_current_streak(cls, recent_bets: List[VirtualPaperBet]) -> Dict[str, Any]:
        """Computes the current active win/loss streak from most recent bets."""
        if not recent_bets:
            return {"type": "none", "count": 0}
        streak_type = "win" if (recent_bets[0].profit_loss or 0) > 0 else "loss"
        count = 0
        for b in recent_bets:
            is_win = (b.profit_loss or 0) > 0
            if (streak_type == "win" and is_win) or (streak_type == "loss" and not is_win):
                count += 1
            else:
                break
        return {"type": streak_type, "count": count}

    @classmethod
    def _log(cls, db: Session, worker: str, level: str, message: str, event_id: str = None):
        log = VirtualAgentLog(
            worker_name=worker,
            level=level,
            event_id=event_id,
            message=message,
        )
        db.add(log)
