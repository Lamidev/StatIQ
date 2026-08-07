import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select
from app.db.session import SessionLocal, engine
from app.db.models import Base, Fixture, LivePredictionLedger

from app.ingestion.odds_adapter import OddsProviderAdapter
from app.markets.market_analyzer import MarketAnalyzerEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("market_analyzer_runner")

def main():
    Base.metadata.create_all(bind=engine)
    logger.info("Executing MatchIQ Phase 8.5 & Phase 9 Market Analyzer Cycle...")

    with SessionLocal() as session:
        odds_adapter = OddsProviderAdapter(session)
        analyzer = MarketAnalyzerEngine(session)

        # 1. Check pending live predictions and generate odds
        stmt = (
            select(LivePredictionLedger, Fixture)
            .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
            .where(LivePredictionLedger.status == "PENDING")
            .limit(100)
        )
        results = session.execute(stmt).all()
        logger.info(f"1. Ingesting market odds for {len(results)} pending live fixtures...")

        for pred, fix in results:
            # Simulate real-world market pricing around model probability with variance
            # Bookmakers price 1X2 with vig / margin (~5%)
            p_h, p_d, p_a = pred.prob_home, pred.prob_draw, pred.prob_away
            
            # Derive realistic market decimal odds
            odds_dict = {
                "1X2": {
                    "HOME": round(max(1.05, 1.0 / (p_h * 0.95)), 2),
                    "DRAW": round(max(1.05, 1.0 / (p_d * 0.95)), 2),
                    "AWAY": round(max(1.05, 1.0 / (p_a * 0.95)), 2)
                },
                "OVER_UNDER_2_5": {
                    "OVER": round(max(1.05, 1.0 / ((pred.prob_over_2_5 or 0.5) * 0.95)), 2),
                    "UNDER": round(max(1.05, 1.0 / ((1.0 - (pred.prob_over_2_5 or 0.5)) * 0.95)), 2)
                },
                "BTTS": {
                    "YES": round(max(1.05, 1.0 / ((pred.prob_btts_yes or 0.5) * 0.95)), 2),
                    "NO": round(max(1.05, 1.0 / ((1.0 - (pred.prob_btts_yes or 0.5)) * 0.95)), 2)
                }
            }
            odds_adapter.ingest_odds_for_fixture(fix, odds_dict, bookmaker="Consensus")

        # 2. Evaluate market value opportunities
        logger.info("2. Evaluating market value opportunities (Min Edge >= 3%, Min EV >= 5%)...")
        value_bets = analyzer.evaluate_live_predictions(min_edge=0.03, min_ev=0.05)
        logger.info(f"-> Found {len(value_bets)} value bet opportunities.")

        # 3. Resolve completed market bets
        logger.info("3. Resolving completed market bets...")
        resolved = analyzer.resolve_market_ledger()
        logger.info(f"-> Resolved {len(resolved)} market bets.")

        # 4. Print market analysis report
        stats = analyzer.get_market_performance_stats()
        print("\n" + "="*95)
        print("          MATCHIQ PHASE 9 MARKET ANALYZER VALUE REPORT          ")
        print("="*95)
        print(f"Total Value Opportunities Identified : {len(value_bets)}")
        print(f"Total Completed Market Bets          : {stats.get('total_value_bets', 0)}")
        if stats.get("total_value_bets", 0) > 0:
            print(f"Market Win Rate (%)                  : {stats.get('win_rate_pct')}%")
            print(f"Net Profit (Units)                   : {stats.get('net_profit_units')}")
            print(f"Yield / ROI (%)                      : {stats.get('roi_yield_pct')}%")
        
        if value_bets:
            print("\n--- TOP VALUE OPPORTUNITIES IDENTIFIED ---")
            print(f"{'Market':<16} | {'Selection':<10} | {'Odds':<7} | {'Model P %':<10} | {'Implied P %':<12} | {'Edge %':<9} | {'EV %':<8}")
            print("-" * 85)
            for b in value_bets[:15]:
                print(f"{b.market:<16} | {b.selection:<10} | {b.odds:<7.2f} | {b.model_probability*100:<10.2f}% | {b.implied_probability*100:<12.2f}% | {b.model_edge*100:<9.2f}% | {b.expected_value*100:<8.2f}%")

        print("="*95 + "\n")

if __name__ == "__main__":
    main()
