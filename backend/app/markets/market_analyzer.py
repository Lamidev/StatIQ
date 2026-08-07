import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_

from app.db.models import Fixture, LivePredictionLedger, MarketOdds, MarketShadowLedger

class MarketAnalyzerEngine:
    """
    Phase 9 Market Analyzer & Value Selection Engine.
    Compares MatchIQ Model Probabilities against Bookmaker Odds to identify value bets:
        Implied Probability = 1 / Decimal Odds
        Model Edge = P_Model - P_Implied
        Expected Value (EV) = (P_Model * Decimal Odds) - 1
    Strictly isolated from prediction engine mathematics.
    """
    def __init__(self, session):
        self.session = session

    def evaluate_live_predictions(self, min_edge: float = 0.03, min_ev: float = 0.05) -> List[MarketShadowLedger]:
        """
        Scans pending live predictions and evaluates available bookmaker odds.
        Persists positive EV value opportunities into MarketShadowLedger.
        """
        stmt = (
            select(LivePredictionLedger, Fixture)
            .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
            .where(LivePredictionLedger.status == "PENDING")
        )
        results = self.session.execute(stmt).all()

        new_value_bets = []

        for pred, fix in results:
            # Fetch latest odds for fixture
            odds_stmt = select(MarketOdds).where(MarketOdds.fixture_id == fix.id).order_by(MarketOdds.timestamp.desc())
            odds_list = list(self.session.execute(odds_stmt).scalars().all())

            # Map predictions to markets
            mkt_probs = {
                ("1X2", "HOME"): pred.prob_home,
                ("1X2", "DRAW"): pred.prob_draw,
                ("1X2", "AWAY"): pred.prob_away,
                ("OVER_UNDER_2_5", "OVER"): pred.prob_over_2_5,
                ("OVER_UNDER_2_5", "UNDER"): (1.0 - (pred.prob_over_2_5 or 0.5)),
                ("BTTS", "YES"): pred.prob_btts_yes,
                ("BTTS", "NO"): (1.0 - (pred.prob_btts_yes or 0.5))
            }

            for odd_item in odds_list:
                key = (odd_item.market, odd_item.selection)
                if key not in mkt_probs or mkt_probs[key] is None:
                    continue

                p_model = mkt_probs[key]
                p_implied = 1.0 / odd_item.odds
                edge = p_model - p_implied
                ev = (p_model * odd_item.odds) - 1.0

                # Check if already recorded in ledger
                check_stmt = select(MarketShadowLedger).where(
                    and_(
                        MarketShadowLedger.fixture_id == fix.id,
                        MarketShadowLedger.market == odd_item.market,
                        MarketShadowLedger.selection == odd_item.selection,
                        MarketShadowLedger.bookmaker == odd_item.bookmaker
                    )
                )
                existing = self.session.execute(check_stmt).scalar_one_or_none()
                if existing is not None:
                    continue

                # Filter value opportunity criteria
                if edge >= min_edge and ev >= min_ev:
                    ledger_entry = MarketShadowLedger(
                        fixture_id=fix.id,
                        live_prediction_id=pred.id,
                        market=odd_item.market,
                        selection=odd_item.selection,
                        bookmaker=odd_item.bookmaker,
                        odds=odd_item.odds,
                        model_probability=p_model,
                        implied_probability=p_implied,
                        model_edge=edge,
                        expected_value=ev,
                        status="PENDING",
                        created_at=datetime.datetime.now(datetime.timezone.utc)
                    )
                    self.session.add(ledger_entry)
                    new_value_bets.append(ledger_entry)

        self.session.commit()
        return new_value_bets

    def resolve_market_ledger(self) -> List[MarketShadowLedger]:
        """
        Resolves pending MarketShadowLedger value bets once fixtures finish.
        Calculates profit/loss (Win: +odds-1, Loss: -1.0).
        """
        stmt = (
            select(MarketShadowLedger, Fixture)
            .join(Fixture, MarketShadowLedger.fixture_id == Fixture.id)
            .where(
                and_(
                    MarketShadowLedger.status == "PENDING",
                    Fixture.status == "FINISHED",
                    Fixture.home_score.isnot(None)
                )
            )
        )
        results = self.session.execute(stmt).all()
        resolved = []

        for bet, fix in results:
            h_s, a_s = fix.home_score, fix.away_score
            tot_goals = h_s + a_s
            actual_1x2 = "HOME" if h_s > a_s else ("AWAY" if a_s > h_s else "DRAW")
            btts_actual = (h_s > 0 and a_s > 0)

            won = False
            if bet.market == "1X2" and bet.selection == actual_1x2:
                won = True
            elif bet.market == "OVER_UNDER_2_5":
                if bet.selection == "OVER" and tot_goals > 2.5: won = True
                elif bet.selection == "UNDER" and tot_goals <= 2.5: won = True
            elif bet.market == "BTTS":
                if bet.selection == "YES" and btts_actual: won = True
                elif bet.selection == "NO" and not btts_actual: won = True

            bet.status = "WIN" if won else "LOSS"
            bet.profit_loss = round((bet.odds - 1.0), 4) if won else -1.0
            bet.resolved_at = datetime.datetime.now(datetime.timezone.utc)
            resolved.append(bet)

        self.session.commit()
        return resolved

    def get_market_performance_stats(self) -> Dict[str, Any]:
        """
        Returns betting performance summary: Total Value Bets, Win Rate (%), Total Stake, Net Profit, ROI (Yield %).
        """
        stmt = select(MarketShadowLedger).where(MarketShadowLedger.status.in_(["WIN", "LOSS"]))
        completed = list(self.session.execute(stmt).scalars().all())

        total = len(completed)
        if total == 0:
            return {
                "total_value_bets": 0,
                "win_rate_pct": 0.0,
                "net_profit_units": 0.0,
                "roi_pct": 0.0,
                "status": "No completed market bets yet"
            }

        wins = sum(1 for b in completed if b.status == "WIN")
        net_profit = sum(b.profit_loss for b in completed if b.profit_loss is not None)
        roi = (net_profit / total) * 100.0

        return {
            "total_value_bets": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate_pct": round((wins / total) * 100.0, 2),
            "net_profit_units": round(net_profit, 4),
            "roi_yield_pct": round(roi, 2)
        }
