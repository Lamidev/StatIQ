import logging
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.session import SessionLocal
from app.evaluation.backtester import WalkForwardBacktester

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("backtest_phase7")

def main():
    logger.info("Executing MatchIQ Phase 7 Feature Intelligence & Ensemble Walk-Forward Backtest...")
    with SessionLocal() as session:
        tester = WalkForwardBacktester(session)
        report = tester.run_backtest()
        
        # Save raw JSON report
        report_path = BASE_DIR.parent / "walk_forward_backtest_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Phase 7 Backtest JSON report saved to: {report_path}")
        print("\n" + "="*95)
        print("     MATCHIQ PHASE 7 FEATURE INTELLIGENCE & ENSEMBLE BACKTEST REPORT     ")
        print("="*95)
        
        print("\n--- 1. AUDIT TRAIL & ENSEMBLE FITTING ---")
        audit = report["audit"]
        print(f"Total Fixtures in DB          : {audit['total_fixtures_in_db']}")
        print(f"Evaluated Out-of-Sample Preds : {audit['evaluated_predictions']}")
        print(f"Excluded (Unplayed/Incomplete): {audit['excluded_unplayed_or_incomplete']}")
        print(f"Excluded (Warmup < 5 matches) : {audit['excluded_warmup_insufficient_matches']}")
        print(f"Fitted Temperature Scaling T  : {audit.get('fitted_temperature_T', 'N/A')}")
        print(f"Fitted Ensemble Weight w_DC   : {audit.get('fitted_ensemble_weight_dc', 'N/A')}")

        print("\n--- 2. 1X2 MODEL BENCHMARKING (STATISTICAL vs ML vs ENSEMBLE) ---")
        print(f"{'Model':<28} | {'Sample N':<9} | {'Accuracy %':<11} | {'Brier Score':<12} | {'Log Loss':<10} | {'ECE':<8}")
        print("-" * 92)
        for m_name, m_stats in report["models_1x2"].items():
            print(f"{m_name:<28} | {m_stats['sample_size']:<9} | {m_stats['ranking_accuracy_pct']:<10}% | {m_stats['brier_score']:<12} | {m_stats['log_loss']:<10} | {m_stats['ece']:<8}")

        print("\n--- 3. ROLLING 6-MONTH SEASONAL STABILITY DIAGNOSTICS ---")
        for m_name in ["Expanding_Prior_Baseline", "DixonColes_Calibrated", "XGBoost", "Weighted_Ensemble"]:
            print(f"\nModel: {m_name}")
            print(f"{'6-Month Window':<24} | {'Sample N':<9} | {'Accuracy %':<11} | {'Brier Score':<12} | {'Log Loss':<10}")
            print("-" * 75)
            for w in report["rolling_stability_6m"].get(m_name, []):
                win_str = f"{w['window_start']} to {w['window_end']}"
                print(f"{win_str:<24} | {w['sample_size']:<9} | {w['accuracy_pct']:<10}% | {w['brier_score']:<12} | {w['log_loss']:<10}")

        print("\n--- 4. SEASONAL PERFORMANCE BREAKDOWN ---")
        print(f"{'Season':<10} | {'Model':<26} | {'Sample N':<9} | {'Accuracy %':<11} | {'Brier Score':<12} | {'Log Loss':<10}")
        print("-" * 88)
        for s_year, s_models in report["seasons_breakdown"].items():
            for m_name in ["Expanding_Prior_Baseline", "DixonColes_Calibrated", "XGBoost", "Weighted_Ensemble"]:
                if m_name in s_models:
                    st = s_models[m_name]
                    print(f"{s_year:<10} | {m_name:<26} | {st['sample_size']:<9} | {st['accuracy_pct']:<10}% | {st['brier_score']:<12} | {st['log_loss']:<10}")

        print("\n" + "="*95)

if __name__ == "__main__":
    main()
