"""
BacktestEngine — Historical simulation engine for virtual sports strategies.

CRITICAL NO-LEAKAGE RULE:
  The engine ONLY uses data that was OBSERVABLE at or before the event's
  scheduled_time. We simulate walking forward in time event-by-event,
  building frequency stats strictly from the past.

Architecture:
  1. Pull all SETTLED events in the requested date range from virtual.db.
  2. For each event (chronological order), rebuild the FrequencyAnalyzer
     context using ONLY prior events.
  3. Run the SignalGenerator logic against the event's locked-in odds.
  4. Simulate a flat-stake paper bet if signal == BET.
  5. Settle the bet immediately using the known VirtualResult.
  6. Accumulate performance metrics per strategy.
"""
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from virtual.models.virtual_models import VirtualEvent, VirtualOddsSnapshot, VirtualResult, VirtualLeague
from virtual.prediction.baseline_model import BaselineModel
from virtual.prediction.market_model import MarketModel
from virtual.prediction.statistical_model import StatisticalModel
from virtual.prediction.score_engine import PredictionScoreEngine
from virtual.backtesting.metrics import BacktestMetrics


class BacktestEngine:
    """
    Simulates historical strategy performance with strict temporal isolation.
    No future data is used in any calculation.
    """

    DEFAULT_STAKE = 10.0         # Default flat stake per bet (paper money)
    MIN_HISTORY_EVENTS = 30      # Minimum prior events needed before generating signals

    @classmethod
    def run(
        cls,
        db: Session,
        league_id: Optional[int] = None,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        stake_per_bet: float = DEFAULT_STAKE,
        starting_bankroll: float = 1000.0,
        min_edge: float = 0.035,
        min_model_prob: float = 0.65,
        min_odds: float = 1.25,
    ) -> Dict[str, Any]:
        """
        Runs the full backtest and returns complete metrics.

        Args:
            db: Active SQLAlchemy session.
            league_id: Restrict to a specific virtual league. None = all leagues.
            start_date: Inclusive start of the simulation window.
            end_date: Inclusive end of the simulation window.
            stake_per_bet: Flat stake to place on every BET signal.
            starting_bankroll: Starting capital for equity curve.
            min_edge: Minimum edge threshold to trigger a BET signal.
            min_model_prob: Minimum model probability threshold.
            min_odds: Minimum acceptable odds.

        Returns:
            dict with keys: config, settled_bets, metrics, events_processed, events_skipped
        """
        config = {
            "league_id": league_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "stake_per_bet": stake_per_bet,
            "starting_bankroll": starting_bankroll,
            "min_edge": min_edge,
            "min_model_prob": min_model_prob,
            "min_odds": min_odds,
        }

        # ── Step 1: Fetch all settled events in window (chronological) ──────────
        settled_events = cls._fetch_settled_events(db, league_id, start_date, end_date)
        total_events = len(settled_events)

        if total_events == 0:
            return {
                "config": config,
                "settled_bets": [],
                "metrics": BacktestMetrics.compute([], starting_bankroll),
                "events_processed": 0,
                "events_skipped": 0,
                "skip_reason": "No settled events found in the requested window.",
            }

        # ── Step 2: Walk forward through events with strict temporal gate ────────
        settled_bets: List[Dict[str, Any]] = []
        events_skipped = 0

        for i, event in enumerate(settled_events):
            # TEMPORAL GATE: only use events prior to this one for stat context
            prior_events = settled_events[:i]

            if len(prior_events) < cls.MIN_HISTORY_EVENTS:
                events_skipped += 1
                continue

            # Extract odds for this event (both 1X2 and Over/Under)
            h_odds, d_odds, a_odds, o_odds = cls._extract_event_odds(db, event.id)

            # Frequency stats from PRIOR events only (no-leakage enforcement)
            freq = cls._compute_prior_frequency(prior_events)

            # Statistical model
            stat_probs = StatisticalModel.calculate_match_probabilities(
                h_odds, a_odds,
                avg_league_goals=freq["avg_goals"]
            )

            # Evaluate the 3 candidates, same logic as SignalGenerator
            candidates = cls._evaluate_candidates(
                event=event,
                h_odds=h_odds,
                d_odds=d_odds,
                a_odds=a_odds,
                o_odds=o_odds,
                stat_probs=stat_probs,
                freq=freq,
                min_edge=min_edge,
                min_model_prob=min_model_prob,
                min_odds=min_odds,
            )

            # ── Step 3: Simulate bets & settle against real result ─────────────
            result: VirtualResult = event.result
            if not result:
                events_skipped += 1
                continue

            for candidate in candidates:
                if candidate["signal"] != "BET":
                    continue

                won = cls._evaluate_outcome(candidate["market_type"], candidate, result)
                pl = (stake_per_bet * candidate["odds"] - stake_per_bet) if won else -stake_per_bet

                settled_bets.append({
                    "event_id": event.id,
                    "provider_event_id": event.provider_event_id,
                    "home_team": event.home_team,
                    "away_team": event.away_team,
                    "scheduled_time": event.scheduled_time.isoformat(),
                    "settled_at": result.settled_at.isoformat() if result.settled_at else None,
                    "market_type": candidate["market_type"],
                    "selection": candidate["selection"],
                    "signal": "BET",
                    "odds": candidate["odds"],
                    "model_prob": candidate["model_prob"],
                    "edge": candidate["edge"],
                    "strategy_code": candidate["strategy_code"],
                    "stake": stake_per_bet,
                    "result_score": f"{result.home_score}-{result.away_score}",
                    "outcome": "WIN" if won else "LOSS",
                    "profit_loss": round(pl, 2),
                    "history_size": len(prior_events),
                })

        # ── Step 4: Compute aggregate metrics ───────────────────────────────────
        metrics = BacktestMetrics.compute(settled_bets, starting_bankroll)

        return {
            "config": config,
            "settled_bets": settled_bets,
            "metrics": metrics,
            "events_processed": total_events - events_skipped,
            "events_skipped": events_skipped,
        }

    # ────────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────────────────────────

    @classmethod
    def _fetch_settled_events(
        cls,
        db: Session,
        league_id: Optional[int],
        start_date: Optional[datetime.datetime],
        end_date: Optional[datetime.datetime],
    ) -> List[VirtualEvent]:
        """Fetches settled events with results, sorted chronologically."""
        q = (
            db.query(VirtualEvent)
            .join(VirtualResult, VirtualResult.event_id == VirtualEvent.id)
            .filter(VirtualEvent.status == "SETTLED")
        )
        if league_id:
            q = q.filter(VirtualEvent.league_id == league_id)
        if start_date:
            q = q.filter(VirtualEvent.scheduled_time >= start_date)
        if end_date:
            q = q.filter(VirtualEvent.scheduled_time <= end_date)

        return q.order_by(VirtualEvent.scheduled_time.asc()).all()

    @classmethod
    def _extract_event_odds(cls, db: Session, event_id: int) -> tuple:
        """Extracts home, draw, away, and over odds for an event safely."""
        snap_1x2 = (
            db.query(VirtualOddsSnapshot)
            .filter(VirtualOddsSnapshot.event_id == event_id, VirtualOddsSnapshot.market_type == "1X2")
            .order_by(VirtualOddsSnapshot.observed_at.asc())
            .first()
        )
        snap_ou = (
            db.query(VirtualOddsSnapshot)
            .filter(VirtualOddsSnapshot.event_id == event_id, VirtualOddsSnapshot.market_type == "OVER_UNDER")
            .order_by(VirtualOddsSnapshot.observed_at.asc())
            .first()
        )

        h_odds = snap_1x2.odds_home if (snap_1x2 and snap_1x2.odds_home) else 2.10
        d_odds = snap_1x2.odds_draw if (snap_1x2 and snap_1x2.odds_draw) else 3.40
        a_odds = snap_1x2.odds_away if (snap_1x2 and snap_1x2.odds_away) else 3.10
        o_odds = snap_ou.odds_over if (snap_ou and snap_ou.odds_over) else 1.82

        return float(h_odds), float(d_odds), float(a_odds), float(o_odds)

    @classmethod
    def _get_earliest_odds_snapshot(cls, db: Session, event_id: int) -> Optional[VirtualOddsSnapshot]:
        """Returns the FIRST odds snapshot for this event (closest to market open)."""
        return (
            db.query(VirtualOddsSnapshot)
            .filter(VirtualOddsSnapshot.event_id == event_id)
            .order_by(VirtualOddsSnapshot.observed_at.asc())
            .first()
        )

    @classmethod
    def _compute_prior_frequency(cls, prior_events: List[VirtualEvent]) -> Dict[str, Any]:
        """
        Computes rolling frequency stats from the prior events list without a DB session.
        This is a lightweight version of FrequencyAnalyzer using pre-fetched data.
        """
        if not prior_events:
            return {"avg_goals": 2.68, "home_win_rate": 0.45, "draw_rate": 0.28, "away_win_rate": 0.27, "sample_size": 0}

        total_goals = 0
        home_wins = 0
        draws = 0
        away_wins = 0
        count = 0

        for ev in prior_events:
            if ev.result:
                r = ev.result
                total_goals += r.total_goals
                if r.outcome_1x2 == "H":
                    home_wins += 1
                elif r.outcome_1x2 == "D":
                    draws += 1
                elif r.outcome_1x2 == "A":
                    away_wins += 1
                count += 1

        if count == 0:
            return {"avg_goals": 2.68, "home_win_rate": 0.45, "draw_rate": 0.28, "away_win_rate": 0.27, "sample_size": 0}

        return {
            "avg_goals": round(total_goals / count, 3),
            "home_win_rate": round(home_wins / count, 4),
            "draw_rate": round(draws / count, 4),
            "away_win_rate": round(away_wins / count, 4),
            "sample_size": count,
        }

    @classmethod
    def _evaluate_candidates(
        cls,
        event: VirtualEvent,
        h_odds: float, d_odds: float, a_odds: float, o_odds: float,
        stat_probs: Dict[str, Any],
        freq: Dict[str, Any],
        min_edge: float,
        min_model_prob: float,
        min_odds: float,
    ) -> List[Dict[str, Any]]:
        """Evaluates all candidate markets for a single event."""
        sample_size = freq.get("sample_size", 0)
        candidates = []

        # Candidate 1: Over 1.5 Goals
        over_15_odds = round(o_odds * 0.72, 2) if o_odds > 1.4 else 1.32
        over_15_model_prob = stat_probs.get("prob_over_1_5", 0.0)
        over_15_market_prob = MarketModel.get_selection_implied_probability("OVER", 1.32)
        score_1 = PredictionScoreEngine.score_candidate(over_15_model_prob, over_15_market_prob, sample_size, over_15_odds)
        candidates.append({
            "market_type": "OVER_UNDER_1.5",
            "selection": "Over 1.5 Goals",
            "odds": over_15_odds,
            "model_prob": over_15_model_prob,
            "market_prob": over_15_market_prob,
            "edge": score_1["edge"],
            "strategy_code": "VIRTUAL_OVER_15_STABLE",
            "signal": cls._decide_signal(score_1["edge"], over_15_model_prob, over_15_odds, min_edge, min_model_prob, min_odds),
        })

        # Candidate 2: 1X2 Home Win
        home_model_prob = stat_probs.get("prob_home", 0.0)
        home_market_prob = MarketModel.get_selection_implied_probability("1", h_odds, market_type="1X2", all_odds={"odds_home": h_odds, "odds_draw": d_odds, "odds_away": a_odds})
        score_2 = PredictionScoreEngine.score_candidate(home_model_prob, home_market_prob, sample_size, h_odds)
        candidates.append({
            "market_type": "1X2_HOME",
            "selection": f"{event.home_team} Win",
            "odds": h_odds,
            "model_prob": home_model_prob,
            "market_prob": home_market_prob,
            "edge": score_2["edge"],
            "strategy_code": "VIRTUAL_HOME_FAVORED_VALUE",
            "signal": cls._decide_signal(score_2["edge"], home_model_prob, h_odds, min_edge, min_model_prob, min_odds),
        })

        # Candidate 3: Double Chance 1X
        dc_prob = stat_probs.get("prob_double_chance_1x", 0.0)
        dc_odds = round(1.0 / (dc_prob * 1.08), 2) if dc_prob > 0 else 1.50
        dc_market_prob = round(dc_prob - 0.04, 4)
        score_3 = PredictionScoreEngine.score_candidate(dc_prob, dc_market_prob, sample_size, dc_odds)
        candidates.append({
            "market_type": "DOUBLE_CHANCE_1X",
            "selection": f"{event.home_team} or Draw (1X)",
            "odds": dc_odds,
            "model_prob": dc_prob,
            "market_prob": dc_market_prob,
            "edge": score_3["edge"],
            "strategy_code": "VIRTUAL_DOUBLE_CHANCE_1X",
            "signal": cls._decide_signal(score_3["edge"], dc_prob, dc_odds, min_edge, min_model_prob, min_odds),
        })

        return candidates

    @classmethod
    def _decide_signal(cls, edge: float, model_prob: float, odds: float, min_edge: float, min_model_prob: float, min_odds: float) -> str:
        """Mirrors the SignalGenerator decision logic exactly."""
        if edge >= min_edge and model_prob >= min_model_prob and odds >= min_odds:
            return "BET"
        elif edge >= 0.01 and model_prob >= 0.55:
            return "WAIT"
        return "SKIP"

    @classmethod
    def _evaluate_outcome(cls, market_type: str, candidate: Dict[str, Any], result: VirtualResult) -> bool:
        """
        Determines whether the candidate selection won given the actual result.
        Returns True if the bet won, False otherwise.
        """
        mt = market_type.upper()

        if mt == "OVER_UNDER_1.5":
            return result.is_over_1_5

        if mt == "OVER_UNDER_2.5":
            return result.is_over_2_5

        if mt == "OVER_UNDER_3.5":
            return result.is_over_3_5

        if mt == "1X2_HOME":
            return result.outcome_1x2 == "H"

        if mt == "1X2_AWAY":
            return result.outcome_1x2 == "A"

        if mt == "1X2_DRAW":
            return result.outcome_1x2 == "D"

        if mt == "DOUBLE_CHANCE_1X":
            return result.outcome_1x2 in ("H", "D")

        if mt == "DOUBLE_CHANCE_2X":
            return result.outcome_1x2 in ("A", "D")

        if mt == "DOUBLE_CHANCE_12":
            return result.outcome_1x2 in ("H", "A")

        if mt == "BTTS_YES":
            return result.is_btts

        if mt == "BTTS_NO":
            return not result.is_btts

        return False
