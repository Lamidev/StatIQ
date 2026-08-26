"""
RiskEngine — Quantitative pre-bet risk gate and Kelly stake calculator.

Responsibilities:
  1. evaluate_bet_gate(): Run all pre-bet risk checks. Returns a RiskDecision
     with ALLOW / REDUCE / BLOCK and a full audit trail of every check.

  2. calculate_kelly_stake(): Compute the optimal fractional Kelly stake for a
     given edge, model probability, and odds against the current bankroll.

Risk Gates (evaluated in order, first failure blocks):
  ─────────────────────────────────────────────────────
  G1  Kill Switch         → Hard block if VIRTUAL_KILL_SWITCH=true
  G2  Agent Mode         → Block if not in PAPER or LIVE mode
  G3  Daily Loss Limit   → Block if today's loss >= MAX_DAILY_LOSS_PCT of bankroll
  G4  Drawdown Limit     → Block if peak-to-trough drawdown >= 20%
  G5  Consecutive Losses → Block if consecutive losses >= MAX_CONSECUTIVE_LOSSES
  G6  Open Exposure      → Block if current open exposure >= MAX_OPEN_EXPOSURE_PCT of balance
  G7  Min Edge           → Block if edge < MIN_EDGE_THRESHOLD
  G8  Min Odds           → Block if odds < 1.10
  G9  Bankroll Floor     → Block if available balance < £1.00
  ─────────────────────────────────────────────────────

Kelly Stake Formula:
  f = (b * p - q) / b
  where b = decimal_odds - 1, p = model_prob, q = 1 - model_prob
  Applied at ½ Kelly by default, capped at MAX_SINGLE_STAKE_PCT of available balance.
"""
import math
import datetime
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from virtual.core.config import virtual_config
from virtual.models.virtual_models import VirtualBankroll, VirtualPaperBet, VirtualPrediction

logger = logging.getLogger("statiq.virtual.risk_engine")


# ── Risk Decision Result ──────────────────────────────────────────────────────

class RiskDecision:
    def __init__(self, action: str, stake: float, reason: str, checks: List[Dict[str, Any]]):
        self.action = action          # "ALLOW" | "REDUCE" | "BLOCK"
        self.stake = stake            # Final computed stake (0.0 if BLOCK)
        self.reason = reason          # Human-readable primary reason
        self.checks = checks          # Full audit trail of all gate checks

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "stake": self.stake,
            "reason": self.reason,
            "checks": self.checks,
        }


# ── Risk Engine ───────────────────────────────────────────────────────────────

class RiskEngine:
    """
    Stateless quantitative risk gate for virtual paper trading.
    All methods take a DB session and return structured decisions.
    """

    HALF_KELLY_FRACTION: float = 0.5      # Apply half-Kelly conservatively
    MIN_STAKE: float = 0.50               # Absolute minimum stake (paper £)
    MAX_DRAWDOWN_BLOCK: float = 0.20      # Block at 20% peak-to-trough drawdown
    MIN_EDGE_ABSOLUTE: float = 0.01       # Hard floor edge gate

    @classmethod
    def evaluate_bet_gate(
        cls,
        db: Session,
        model_prob: float,
        market_prob: float,
        odds: float,
        strategy_code: str = "UNKNOWN",
    ) -> RiskDecision:
        """
        Runs all pre-bet risk gates for a candidate bet.
        Returns a RiskDecision with ALLOW, REDUCE, or BLOCK.
        """
        checks: List[Dict[str, Any]] = []
        bankroll = cls._get_bankroll(db)
        edge = model_prob - market_prob

        def gate(name: str, passed: bool, detail: str) -> bool:
            checks.append({"gate": name, "passed": passed, "detail": detail})
            return passed

        # G1 — Kill Switch
        if not gate("G1_KILL_SWITCH", not virtual_config.KILL_SWITCH_ACTIVE,
                    "Kill switch is ACTIVE — all bet firing suppressed." if virtual_config.KILL_SWITCH_ACTIVE
                    else "Kill switch is OFF."):
            return RiskDecision("BLOCK", 0.0, "Kill switch active.", checks)

        # G2 — Agent Mode
        allowed_modes = ("PAPER", "LIVE")
        mode_ok = virtual_config.AGENT_MODE.upper() in allowed_modes
        if not gate("G2_AGENT_MODE", mode_ok,
                    f"Agent mode is {virtual_config.AGENT_MODE} — must be PAPER or LIVE to fire bets."):
            return RiskDecision("BLOCK", 0.0, f"Agent mode is {virtual_config.AGENT_MODE}.", checks)

        # G3 — Daily Loss Limit
        today_pl = bankroll.daily_profit_loss if bankroll else 0.0
        starting = bankroll.starting_balance if bankroll else virtual_config.INITIAL_PAPER_BANKROLL
        daily_loss_pct = abs(min(0.0, today_pl)) / starting * 100 if starting > 0 else 0.0
        daily_ok = daily_loss_pct < virtual_config.MAX_DAILY_LOSS_PCT
        if not gate("G3_DAILY_LOSS_LIMIT", daily_ok,
                    f"Daily loss {daily_loss_pct:.2f}% vs limit {virtual_config.MAX_DAILY_LOSS_PCT}%."):
            return RiskDecision("BLOCK", 0.0,
                                f"Daily loss limit breached: {daily_loss_pct:.1f}% ≥ {virtual_config.MAX_DAILY_LOSS_PCT}%.", checks)

        # G4 — Drawdown Limit
        current_dd = (bankroll.max_drawdown_pct if bankroll else 0.0)
        dd_ok = current_dd < cls.MAX_DRAWDOWN_BLOCK
        if not gate("G4_DRAWDOWN_LIMIT", dd_ok,
                    f"Peak drawdown {current_dd*100:.1f}% vs limit {cls.MAX_DRAWDOWN_BLOCK*100:.0f}%."):
            return RiskDecision("BLOCK", 0.0,
                                f"Max drawdown breached: {current_dd*100:.1f}% ≥ {cls.MAX_DRAWDOWN_BLOCK*100:.0f}%.", checks)

        # G5 — Consecutive Losses
        consec = bankroll.consecutive_losses if bankroll else 0
        consec_ok = consec < virtual_config.MAX_CONSECUTIVE_LOSSES
        if not gate("G5_CONSECUTIVE_LOSSES", consec_ok,
                    f"{consec} consecutive losses vs limit {virtual_config.MAX_CONSECUTIVE_LOSSES}."):
            return RiskDecision("BLOCK", 0.0,
                                f"Consecutive loss streak: {consec} ≥ limit {virtual_config.MAX_CONSECUTIVE_LOSSES}.", checks)

        # G6 — Open Exposure
        avail = bankroll.available_balance if bankroll else 0.0
        current_balance = bankroll.current_balance if bankroll else avail
        exposure = bankroll.total_exposure if bankroll else 0.0
        exposure_pct = (exposure / current_balance * 100) if current_balance > 0 else 0.0
        exposure_ok = exposure_pct < virtual_config.MAX_OPEN_EXPOSURE_PCT
        if not gate("G6_OPEN_EXPOSURE", exposure_ok,
                    f"Open exposure {exposure_pct:.1f}% vs limit {virtual_config.MAX_OPEN_EXPOSURE_PCT}%."):
            return RiskDecision("BLOCK", 0.0,
                                f"Open exposure limit breached: {exposure_pct:.1f}% ≥ {virtual_config.MAX_OPEN_EXPOSURE_PCT}%.", checks)

        # G7 — Min Edge
        edge_ok = edge >= cls.MIN_EDGE_ABSOLUTE
        if not gate("G7_MIN_EDGE", edge_ok,
                    f"Edge {edge*100:.2f}% vs minimum {cls.MIN_EDGE_ABSOLUTE*100:.1f}%."):
            return RiskDecision("BLOCK", 0.0, f"Insufficient edge: {edge*100:.2f}%.", checks)

        # G8 — Min Odds
        odds_ok = odds >= 1.10
        if not gate("G8_MIN_ODDS", odds_ok,
                    f"Odds {odds} below minimum 1.10."):
            return RiskDecision("BLOCK", 0.0, f"Odds {odds} too low.", checks)

        # G9 — Bankroll Floor
        floor_ok = avail >= cls.MIN_STAKE
        if not gate("G9_BANKROLL_FLOOR", floor_ok,
                    f"Available balance ₦{avail:.2f} below minimum stake ₦{cls.MIN_STAKE}."):
            return RiskDecision("BLOCK", 0.0, f"Insufficient available balance: ₦{avail:.2f}.", checks)

        # ── All gates passed — compute Kelly stake ────────────────────────────
        kelly_stake, kelly_info = cls.calculate_kelly_stake(
            model_prob=model_prob,
            odds=odds,
            available_balance=avail,
        )

        checks.append({
            "gate": "KELLY_SIZING",
            "passed": True,
            "detail": kelly_info,
        })

        action = "ALLOW" if kelly_stake >= cls.MIN_STAKE else "REDUCE"
        final_stake = max(cls.MIN_STAKE, kelly_stake)

        # Final cap at MAX_SINGLE_STAKE_PCT
        max_stake = avail * (virtual_config.MAX_SINGLE_STAKE_PCT / 100.0)
        if final_stake > max_stake:
            final_stake = max_stake
            action = "REDUCE"
            checks.append({
                "gate": "MAX_STAKE_CAP",
                "passed": True,
                "detail": f"Stake capped at MAX_SINGLE_STAKE_PCT ({virtual_config.MAX_SINGLE_STAKE_PCT}%) = ₦{max_stake:.2f}",
            })

        final_stake = round(final_stake, 2)
        return RiskDecision(action, final_stake, f"All gates passed. Kelly stake: ₦{final_stake:.2f}.", checks)

    @classmethod
    def calculate_kelly_stake(
        cls,
        model_prob: float,
        odds: float,
        available_balance: float,
        kelly_fraction: float = HALF_KELLY_FRACTION,
    ) -> tuple:
        """
        Computes the Kelly-sized stake.
        Returns (stake_amount, info_string).
        """
        if odds <= 1.0 or model_prob <= 0:
            return cls.MIN_STAKE, f"Degenerate inputs (odds={odds}, p={model_prob}) — using minimum stake."

        b = odds - 1.0          # net odds (profit per ₦1 staked)
        p = model_prob
        q = 1.0 - p

        kelly_full = (b * p - q) / b
        kelly_applied = kelly_full * kelly_fraction

        if kelly_applied <= 0:
            return cls.MIN_STAKE, f"Kelly fraction negative ({kelly_full:.4f}) — edge insufficient for positive sizing."

        stake = available_balance * kelly_applied
        stake = max(cls.MIN_STAKE, round(stake, 2))

        info = (
            f"Kelly: f*={kelly_full:.4f} → ½-Kelly={kelly_applied:.4f} "
            f"× ₦{available_balance:.2f} available = ₦{stake:.2f} stake."
        )
        return stake, info

    @classmethod
    def get_current_risk_state(cls, db: Session) -> Dict[str, Any]:
        """
        Returns a comprehensive real-time risk state snapshot for the dashboard.
        """
        bankroll = cls._get_bankroll(db)
        if not bankroll:
            return cls._empty_risk_state()

        today_pl = bankroll.daily_profit_loss
        starting = bankroll.starting_balance
        current = bankroll.current_balance
        available = bankroll.available_balance
        exposure = bankroll.total_exposure

        daily_loss_pct = abs(min(0.0, today_pl)) / starting * 100 if starting > 0 else 0.0
        drawdown_pct = bankroll.max_drawdown_pct * 100
        exposure_pct = (exposure / current * 100) if current > 0 else 0.0
        consec_losses = bankroll.consecutive_losses

        # Risk level
        risk_level = cls._compute_risk_level(
            daily_loss_pct=daily_loss_pct,
            drawdown_pct=drawdown_pct,
            consec_losses=consec_losses,
            exposure_pct=exposure_pct,
        )

        # Is any gate tripped?
        kill_switch = virtual_config.KILL_SWITCH_ACTIVE
        is_halted = (
            kill_switch or
            daily_loss_pct >= virtual_config.MAX_DAILY_LOSS_PCT or
            drawdown_pct >= cls.MAX_DRAWDOWN_BLOCK * 100 or
            consec_losses >= virtual_config.MAX_CONSECUTIVE_LOSSES
        )

        return {
            "risk_level": risk_level,               # GREEN / AMBER / RED / HALTED
            "is_halted": is_halted,
            "kill_switch_active": kill_switch,
            "gates": {
                "G1_kill_switch": {"status": "FAIL" if kill_switch else "PASS", "value": kill_switch},
                "G3_daily_loss": {
                    "status": "FAIL" if daily_loss_pct >= virtual_config.MAX_DAILY_LOSS_PCT else "PASS",
                    "value_pct": round(daily_loss_pct, 2),
                    "limit_pct": virtual_config.MAX_DAILY_LOSS_PCT,
                },
                "G4_drawdown": {
                    "status": "FAIL" if drawdown_pct >= cls.MAX_DRAWDOWN_BLOCK * 100 else "PASS",
                    "value_pct": round(drawdown_pct, 2),
                    "limit_pct": cls.MAX_DRAWDOWN_BLOCK * 100,
                },
                "G5_consecutive_losses": {
                    "status": "FAIL" if consec_losses >= virtual_config.MAX_CONSECUTIVE_LOSSES else "PASS",
                    "value": consec_losses,
                    "limit": virtual_config.MAX_CONSECUTIVE_LOSSES,
                },
                "G6_open_exposure": {
                    "status": "FAIL" if exposure_pct >= virtual_config.MAX_OPEN_EXPOSURE_PCT else "PASS",
                    "value_pct": round(exposure_pct, 2),
                    "limit_pct": virtual_config.MAX_OPEN_EXPOSURE_PCT,
                },
            },
            "bankroll_snapshot": {
                "current_balance": round(current, 2),
                "available_balance": round(available, 2),
                "total_exposure": round(exposure, 2),
                "today_pl": round(today_pl, 2),
                "cumulative_roi_pct": round(bankroll.cumulative_roi * 100, 2),
                "consecutive_losses": consec_losses,
            },
            "kelly_example": cls._compute_kelly_example(available),
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @classmethod
    def _get_bankroll(cls, db: Session) -> Optional[VirtualBankroll]:
        return db.query(VirtualBankroll).filter(VirtualBankroll.mode == "PAPER").order_by(VirtualBankroll.id.desc()).first()

    @classmethod
    def _compute_risk_level(cls, daily_loss_pct, drawdown_pct, consec_losses, exposure_pct) -> str:
        if (daily_loss_pct >= virtual_config.MAX_DAILY_LOSS_PCT or
                drawdown_pct >= cls.MAX_DRAWDOWN_BLOCK * 100 or
                consec_losses >= virtual_config.MAX_CONSECUTIVE_LOSSES):
            return "HALTED"
        if (daily_loss_pct >= virtual_config.MAX_DAILY_LOSS_PCT * 0.6 or
                drawdown_pct >= cls.MAX_DRAWDOWN_BLOCK * 60 or
                consec_losses >= virtual_config.MAX_CONSECUTIVE_LOSSES * 0.6):
            return "RED"
        if (daily_loss_pct >= virtual_config.MAX_DAILY_LOSS_PCT * 0.35 or
                drawdown_pct >= cls.MAX_DRAWDOWN_BLOCK * 35 or
                consec_losses >= virtual_config.MAX_CONSECUTIVE_LOSSES * 0.4):
            return "AMBER"
        return "GREEN"

    @classmethod
    def _compute_kelly_example(cls, available: float) -> Dict[str, Any]:
        """Computes an illustrative Kelly stake for 65% prob at 1.85 odds."""
        stake, info = cls.calculate_kelly_stake(0.65, 1.85, available)
        return {
            "model_prob": 0.65,
            "odds": 1.85,
            "kelly_stake": stake,
            "description": info,
        }

    @classmethod
    def _empty_risk_state(cls) -> Dict[str, Any]:
        return {
            "risk_level": "UNKNOWN",
            "is_halted": False,
            "kill_switch_active": False,
            "gates": {},
            "bankroll_snapshot": {},
            "kelly_example": {},
        }
