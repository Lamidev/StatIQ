"""
WalkForwardEvaluator — Walk-Forward Optimization & Out-of-Sample Testing.

Divides the historical timeline into train/test windows and evaluates strategy
performance on each out-of-sample segment independently.

This prevents overfitting that would occur if we tuned parameters on the full
historical dataset before backtesting.

Method:
  1. Divide total settled events into N equal time-based windows.
  2. For each window W[i]:
     a. TRAIN: All events in W[0..i-1] (in-sample).
     b. TEST:  Events in W[i] (out-of-sample, unseen).
  3. Run BacktestEngine on the TEST window using TRAIN data as context.
  4. Collect OOS (Out-Of-Sample) metrics per window.
  5. Aggregate results across all windows.
"""
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from virtual.backtesting.engine import BacktestEngine
from virtual.backtesting.metrics import BacktestMetrics
from virtual.models.virtual_models import VirtualEvent, VirtualResult


class WalkForwardEvaluator:
    """
    Performs walk-forward analysis to assess strategy robustness.
    """

    @classmethod
    def run(
        cls,
        db: Session,
        league_id: Optional[int] = None,
        n_windows: int = 5,
        stake_per_bet: float = 10.0,
        starting_bankroll: float = 1000.0,
        min_edge: float = 0.035,
        min_model_prob: float = 0.65,
        min_odds: float = 1.25,
    ) -> Dict[str, Any]:
        """
        Runs walk-forward evaluation across N equal time windows.

        Returns:
            dict with keys: windows, aggregate_metrics, config
        """
        config = {
            "n_windows": n_windows,
            "league_id": league_id,
            "stake_per_bet": stake_per_bet,
            "starting_bankroll": starting_bankroll,
            "min_edge": min_edge,
            "min_model_prob": min_model_prob,
            "min_odds": min_odds,
        }

        # Fetch all settled events sorted chronologically
        all_events = cls._fetch_all_settled(db, league_id)

        if len(all_events) < BacktestEngine.MIN_HISTORY_EVENTS * 2:
            return {
                "config": config,
                "windows": [],
                "aggregate_metrics": BacktestMetrics.compute([], starting_bankroll),
                "total_events": len(all_events),
                "error": f"Insufficient data: need at least {BacktestEngine.MIN_HISTORY_EVENTS * 2} settled events for walk-forward analysis.",
            }

        # Divide events into N windows
        window_size = len(all_events) // n_windows
        windows_result = []
        all_settled_bets: List[Dict[str, Any]] = []

        for w in range(n_windows):
            test_start_idx = w * window_size
            test_end_idx = (w + 1) * window_size if w < n_windows - 1 else len(all_events)

            test_events = all_events[test_start_idx:test_end_idx]
            train_events = all_events[:test_start_idx]

            if not test_events:
                continue

            window_start = test_events[0].scheduled_time
            window_end = test_events[-1].scheduled_time
            train_size = len(train_events)

            # Run backtest on test window with train history pre-seeded
            window_result = cls._run_window(
                db=db,
                train_events=train_events,
                test_events=test_events,
                stake_per_bet=stake_per_bet,
                starting_bankroll=starting_bankroll,
                min_edge=min_edge,
                min_model_prob=min_model_prob,
                min_odds=min_odds,
                window_num=w + 1,
                window_start=window_start,
                window_end=window_end,
                train_size=train_size,
            )

            windows_result.append(window_result)
            all_settled_bets.extend(window_result.get("settled_bets", []))

        # Aggregate across all OOS windows
        aggregate_metrics = BacktestMetrics.compute(all_settled_bets, starting_bankroll)

        return {
            "config": config,
            "windows": windows_result,
            "aggregate_metrics": aggregate_metrics,
            "total_events": len(all_events),
            "total_oos_bets": len([b for b in all_settled_bets if b.get("signal") == "BET"]),
        }

    @classmethod
    def _run_window(
        cls,
        db: Session,
        train_events: List[VirtualEvent],
        test_events: List[VirtualEvent],
        stake_per_bet: float,
        starting_bankroll: float,
        min_edge: float,
        min_model_prob: float,
        min_odds: float,
        window_num: int,
        window_start: datetime.datetime,
        window_end: datetime.datetime,
        train_size: int,
    ) -> Dict[str, Any]:
        """Runs a single walk-forward window with the given train/test split."""
        settled_bets: List[Dict[str, Any]] = []
        events_skipped = 0

        for i, event in enumerate(test_events):
            # Combine train history + prior test events as context
            prior_context = train_events + test_events[:i]

            if len(prior_context) < BacktestEngine.MIN_HISTORY_EVENTS:
                events_skipped += 1
                continue

            h_odds, d_odds, a_odds, o_odds = BacktestEngine._extract_event_odds(db, event.id)

            freq = BacktestEngine._compute_prior_frequency(prior_context)
            stat_probs = __import__(
                "virtual.prediction.statistical_model",
                fromlist=["StatisticalModel"]
            ).StatisticalModel.calculate_match_probabilities(
                h_odds, a_odds,
                avg_league_goals=freq["avg_goals"]
            )

            candidates = BacktestEngine._evaluate_candidates(
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

            result = event.result
            if not result:
                events_skipped += 1
                continue

            for candidate in candidates:
                if candidate["signal"] != "BET":
                    continue

                won = BacktestEngine._evaluate_outcome(candidate["market_type"], candidate, result)
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
                    "window": window_num,
                })

        window_metrics = BacktestMetrics.compute(settled_bets, starting_bankroll)

        return {
            "window": window_num,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "train_size": train_size,
            "test_size": len(test_events),
            "events_skipped": events_skipped,
            "settled_bets": settled_bets,
            "metrics": window_metrics,
        }

    @classmethod
    def _fetch_all_settled(cls, db: Session, league_id: Optional[int]) -> List[VirtualEvent]:
        """Fetches all settled events with results in chronological order."""
        q = (
            db.query(VirtualEvent)
            .join(VirtualResult, VirtualResult.event_id == VirtualEvent.id)
            .filter(VirtualEvent.status == "SETTLED")
        )
        if league_id:
            q = q.filter(VirtualEvent.league_id == league_id)
        return q.order_by(VirtualEvent.scheduled_time.asc()).all()
