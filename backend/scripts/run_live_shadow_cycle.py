import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.session import SessionLocal, engine
from app.db.models import Base
from app.predictions.shadow_engine import LiveShadowEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("live_shadow_cycle")

def main():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    logger.info("Executing MatchIQ Phase 8 Daily Live Shadow Cycle...")
    with SessionLocal() as session:
        engine_svc = LiveShadowEngine(session)

        # 1. Ingest & predict upcoming fixtures prior to kickoff
        logger.info("1. Scanning and generating pre-kickoff predictions for upcoming 2026+ fixtures...")
        new_preds = engine_svc.predict_upcoming_fixtures()
        logger.info(f"-> Created {len(new_preds)} new live shadow prediction records.")

        # 2. Resolve completed fixtures
        logger.info("2. Checking status and resolving completed fixtures...")
        resolved = engine_svc.resolve_completed_fixtures()
        logger.info(f"-> Resolved {len(resolved)} completed live predictions.")

        # 3. Print live shadow stats
        stats = engine_svc.get_live_performance_stats(days=30)

        print("\n" + "="*85)
        print("          MATCHIQ PHASE 8 LIVE SHADOW LEDGER STATUS          ")
        print("="*85)
        print(f"Total Pending Upcoming Live Predictions : {len(new_preds)}")
        print(f"Total Completed Live Shadow Predictions : {stats.get('total_completed', 0)}")
        if stats.get("total_completed", 0) > 0:
            print(f"Live Shadow Accuracy (%)                : {stats.get('accuracy_pct')}%")
            print(f"Live Shadow Brier Score                 : {stats.get('brier_score')}")
            print(f"Live Shadow Log Loss                    : {stats.get('log_loss')}")
        else:
            print(f"Live Shadow Status                      : {stats.get('status')}")
        print("="*85 + "\n")

if __name__ == "__main__":
    main()
