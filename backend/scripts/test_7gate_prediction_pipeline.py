import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sportybet_ingestion import SportyBetIngestionService
from app.services.prediction_gate_service import PredictionGateService
from app.adapters.bookmaker_adapter import SportyBetAdapter

def test_7gate_pipeline():
    print("==================================================")
    print("     STATIQ V2.0 7-GATE PREDICTION PIPELINE       ")
    print("==================================================")

    # 1. Fetch live SportyBet fixtures
    print("\n[STEP 1] Ingesting Live SportyBet Fixtures...")
    fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=10, force_refresh=True)
    print(f"  • Ingested {len(fixtures)} live fixtures directly from SportyBet.")
    assert len(fixtures) > 0, "Must have active fixtures"

    # 2. Evaluate all fixtures through 7-Gate Engine
    print("\n[STEP 2] Running 7-Gate Mathematical Pipeline on Candidates...")
    approved_standard = []
    approved_rollover = []

    for f in fixtures:
        res_std = PredictionGateService.evaluate_fixture(f, min_quality=60, strategy="STANDARD")
        if res_std.approved:
            approved_standard.append((f, res_std))

        res_roll = PredictionGateService.evaluate_fixture(f, min_quality=75, strategy="ROLLOVER")
        if res_roll.approved:
            approved_rollover.append((f, res_roll))

    print(f"  • Total Approved Standard Picks: {len(approved_standard)}")
    print(f"  • Total Approved Rollover Banker Picks: {len(approved_rollover)}")

    assert len(approved_standard) > 0, "At least 1 standard pick must be approved"

    # Print first approved pick details
    f_sample, res_sample = approved_standard[0]
    pick = res_sample.primary_pick
    print(f"\n[SAMPLE APPROVED PICK]: {f_sample['home_team']} vs {f_sample['away_team']}")
    print(f"  • Data Quality Score: {res_sample.data_quality_score}/100")
    print(f"  • Selected Market:    {pick.market_name} -> {pick.selection_name} @ {pick.odds}")
    print(f"  • Model Probability:  {pick.model_probability * 100:.1f}%")
    print(f"  • Confidence Tier:    {pick.confidence_tier}")
    print(f"  • Locked IDs:         Event: {f_sample['event_id']} | Market: {pick.market_id} | Outcome: {pick.outcome_id}")
    print("  • 7-Gate Audit Log:")
    for log in res_sample.audit_log:
        print(f"      {log}")

    # 3. Test Booking Code Generation from 7-Gate Picks
    print("\n[STEP 3] Generating & Verifying SportyBet Booking Code from 7-Gate Picks...")
    adapter = SportyBetAdapter()
    selections = []
    
    for f_item, res_item in approved_standard[:3]:
        p = res_item.primary_pick
        selections.append({
            "provider_event_id": f_item["event_id"],
            "provider_market_id": p.market_id,
            "provider_outcome_id": p.outcome_id,
            "provider_specifier": p.specifier,
            "home_team": f_item["home_team"],
            "away_team": f_item["away_team"],
            "selection_name": p.selection_name,
            "odds": p.odds
        })

    booking_res = adapter.generate_code(selections=selections, country_code="ng")
    print(f"  • Booking Status: {booking_res.get('status')}")
    print(f"  • Booking Code:   {booking_res.get('booking_code')}")
    print(f"  • Verified:       {booking_res.get('verified')}")
    print(f"  • Share URL:      {booking_res.get('load_url')}")

    assert booking_res.get("status") == "SUCCESS", "Booking generation must succeed"
    assert booking_res.get("verified") is True, "Booking must pass 1-to-1 post-booking verification"

    print("\n>>> ALL 7-GATE PREDICTION PIPELINE TESTS PASSED 100%! <<<\n")

if __name__ == "__main__":
    test_7gate_pipeline()
