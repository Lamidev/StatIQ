"""
BacktestMetrics — Quantitative performance analytics for virtual trading strategies.

Calculates: ROI, Sharpe Ratio, Max Drawdown, Hit Rate, Profit Factor, Kelly Criterion,
and per-strategy breakdowns.
"""
import math
from typing import List, Dict, Any, Optional


class BacktestMetrics:
    """
    Computes all standard quantitative performance metrics from a list of settled
    backtested bets. All calculations are stateless and reproducible.
    """

    @classmethod
    def compute(cls, settled_bets: List[Dict[str, Any]], starting_bankroll: float = 1000.0) -> Dict[str, Any]:
        """
        Compute full performance metrics from a list of settled bet records.

        Each bet record is expected to have:
          - stake (float)
          - odds (float)
          - profit_loss (float): positive = win, negative = loss
          - signal (str): BET / WAIT / SKIP
          - strategy_code (str)
          - market_type (str)
          - settled_at (str ISO datetime)

        Returns a comprehensive metrics dict.
        """
        if not settled_bets:
            return cls._empty_metrics(starting_bankroll)

        # Filter to only BET signals that actually executed
        executed = [b for b in settled_bets if b.get("signal") == "BET"]

        if not executed:
            return cls._empty_metrics(starting_bankroll)

        total_bets = len(executed)
        wins = [b for b in executed if b.get("profit_loss", 0) > 0]
        losses = [b for b in executed if b.get("profit_loss", 0) <= 0]

        hit_rate = round(len(wins) / total_bets, 4) if total_bets > 0 else 0.0

        total_staked = sum(b.get("stake", 0) for b in executed)
        total_profit = sum(b.get("profit_loss", 0) for b in executed)
        gross_win = sum(b.get("profit_loss", 0) for b in wins)
        gross_loss = abs(sum(b.get("profit_loss", 0) for b in losses))

        roi = round(total_profit / total_staked, 4) if total_staked > 0 else 0.0
        profit_factor = round(gross_win / gross_loss, 3) if gross_loss > 0 else float("inf")
        average_odds = round(sum(b.get("odds", 1.0) for b in executed) / total_bets, 3)
        average_stake = round(total_staked / total_bets, 2)

        # Build equity curve for Sharpe and Drawdown
        equity_curve = cls._build_equity_curve(executed, starting_bankroll)
        max_drawdown_pct, max_drawdown_abs = cls._max_drawdown(equity_curve)
        sharpe = cls._sharpe_ratio(executed)
        kelly = cls._kelly_criterion(hit_rate, average_odds)

        # Expectancy (avg P&L per bet)
        expectancy = round(total_profit / total_bets, 4) if total_bets > 0 else 0.0

        # Longest winning/losing streaks
        win_streak, loss_streak = cls._streaks(executed)

        # Breakdown by strategy
        strategy_breakdown = cls._breakdown_by_key(executed, "strategy_code")
        market_breakdown = cls._breakdown_by_key(executed, "market_type")

        ending_bankroll = starting_bankroll + total_profit

        return {
            "summary": {
                "total_bets": total_bets,
                "wins": len(wins),
                "losses": len(losses),
                "hit_rate": hit_rate,
                "hit_rate_pct": round(hit_rate * 100, 2),
                "roi": roi,
                "roi_pct": round(roi * 100, 2),
                "profit_factor": profit_factor,
                "total_staked": round(total_staked, 2),
                "total_profit_loss": round(total_profit, 2),
                "gross_win": round(gross_win, 2),
                "gross_loss": round(gross_loss, 2),
                "expectancy_per_bet": expectancy,
                "average_odds": average_odds,
                "average_stake": average_stake,
                "starting_bankroll": starting_bankroll,
                "ending_bankroll": round(ending_bankroll, 2),
                "bankroll_growth_pct": round(((ending_bankroll - starting_bankroll) / starting_bankroll) * 100, 2),
            },
            "risk_metrics": {
                "sharpe_ratio": sharpe,
                "max_drawdown_pct": max_drawdown_pct,
                "max_drawdown_abs": max_drawdown_abs,
                "longest_win_streak": win_streak,
                "longest_loss_streak": loss_streak,
                "kelly_fraction": kelly,
                "kelly_pct": round(kelly * 100, 2),
            },
            "equity_curve": equity_curve,
            "strategy_breakdown": strategy_breakdown,
            "market_breakdown": market_breakdown,
        }

    @classmethod
    def _build_equity_curve(cls, executed: List[Dict[str, Any]], starting_bankroll: float) -> List[Dict[str, Any]]:
        """Builds chronological equity curve from settled bets."""
        curve = []
        running_balance = starting_bankroll
        for i, bet in enumerate(executed):
            pl = bet.get("profit_loss", 0)
            running_balance += pl
            curve.append({
                "bet_index": i + 1,
                "profit_loss": round(pl, 2),
                "cumulative_pl": round(running_balance - starting_bankroll, 2),
                "balance": round(running_balance, 2),
                "settled_at": bet.get("settled_at"),
            })
        return curve

    @classmethod
    def _max_drawdown(cls, equity_curve: List[Dict[str, Any]]) -> tuple:
        """Calculates max peak-to-trough drawdown from equity curve."""
        if not equity_curve:
            return 0.0, 0.0

        balances = [p["balance"] for p in equity_curve]
        peak = balances[0]
        max_dd_abs = 0.0
        max_dd_pct = 0.0

        for b in balances:
            if b > peak:
                peak = b
            dd_abs = peak - b
            dd_pct = dd_abs / peak if peak > 0 else 0.0
            if dd_abs > max_dd_abs:
                max_dd_abs = dd_abs
                max_dd_pct = dd_pct

        return round(max_dd_pct, 4), round(max_dd_abs, 2)

    @classmethod
    def _sharpe_ratio(cls, executed: List[Dict[str, Any]], risk_free_rate: float = 0.0) -> float:
        """Calculates simplified Sharpe Ratio using per-bet returns."""
        if len(executed) < 2:
            return 0.0

        returns = []
        for bet in executed:
            stake = bet.get("stake", 1.0)
            pl = bet.get("profit_loss", 0.0)
            if stake > 0:
                returns.append(pl / stake)

        if len(returns) < 2:
            return 0.0

        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0001

        sharpe = (mean_r - risk_free_rate) / std_dev
        return round(sharpe, 3)

    @classmethod
    def _kelly_criterion(cls, hit_rate: float, average_odds: float) -> float:
        """
        Calculates fractional Kelly stake size.
        Kelly = (b * p - q) / b  where b = decimal_odds - 1, p = win rate, q = loss rate
        """
        if average_odds <= 1.0 or hit_rate <= 0:
            return 0.0
        b = average_odds - 1.0
        p = hit_rate
        q = 1.0 - hit_rate
        kelly = (b * p - q) / b
        # Apply half-Kelly for safety
        half_kelly = max(0.0, kelly * 0.5)
        return round(half_kelly, 4)

    @classmethod
    def _streaks(cls, executed: List[Dict[str, Any]]) -> tuple:
        """Returns longest win streak and loss streak."""
        max_win_streak = 0
        max_loss_streak = 0
        cur_win = 0
        cur_loss = 0
        for bet in executed:
            if bet.get("profit_loss", 0) > 0:
                cur_win += 1
                cur_loss = 0
            else:
                cur_loss += 1
                cur_win = 0
            max_win_streak = max(max_win_streak, cur_win)
            max_loss_streak = max(max_loss_streak, cur_loss)
        return max_win_streak, max_loss_streak

    @classmethod
    def _breakdown_by_key(cls, executed: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        """Groups bets by a key (strategy_code or market_type) and computes per-group metrics."""
        groups: Dict[str, List] = {}
        for bet in executed:
            k = bet.get(key, "UNKNOWN")
            groups.setdefault(k, []).append(bet)

        result = []
        for group_key, bets in groups.items():
            wins = [b for b in bets if b.get("profit_loss", 0) > 0]
            total_pl = sum(b.get("profit_loss", 0) for b in bets)
            total_staked = sum(b.get("stake", 0) for b in bets)
            result.append({
                "label": group_key,
                "total_bets": len(bets),
                "wins": len(wins),
                "hit_rate_pct": round(len(wins) / len(bets) * 100, 1) if bets else 0.0,
                "total_profit_loss": round(total_pl, 2),
                "roi_pct": round(total_pl / total_staked * 100, 2) if total_staked > 0 else 0.0,
            })
        return sorted(result, key=lambda x: x["total_profit_loss"], reverse=True)

    @classmethod
    def _empty_metrics(cls, starting_bankroll: float) -> Dict[str, Any]:
        return {
            "summary": {
                "total_bets": 0,
                "wins": 0,
                "losses": 0,
                "hit_rate": 0.0,
                "hit_rate_pct": 0.0,
                "roi": 0.0,
                "roi_pct": 0.0,
                "profit_factor": 0.0,
                "total_staked": 0.0,
                "total_profit_loss": 0.0,
                "gross_win": 0.0,
                "gross_loss": 0.0,
                "expectancy_per_bet": 0.0,
                "average_odds": 0.0,
                "average_stake": 0.0,
                "starting_bankroll": starting_bankroll,
                "ending_bankroll": starting_bankroll,
                "bankroll_growth_pct": 0.0,
            },
            "risk_metrics": {
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "max_drawdown_abs": 0.0,
                "longest_win_streak": 0,
                "longest_loss_streak": 0,
                "kelly_fraction": 0.0,
                "kelly_pct": 0.0,
            },
            "equity_curve": [],
            "strategy_breakdown": [],
            "market_breakdown": [],
        }
