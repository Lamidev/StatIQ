import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sportybet_ingestion import SportyBetIngestionService
from app.services.odds_engine import MarketProbabilityEngine
from app.adapters.bookmaker_adapter import SportyBetAdapter

def test_full_pipeline():
    print("==================================================")
    print("  STATIQ V2.0 SPORTYBET DETERMINISTIC PIPELINE    ")
    print("==================================================")

    # 1. Test Ingestion
    print("\n[TEST 1] Ingesting Live Upcoming SportyBet Fixtures...")
    fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=5, force_refresh=True)
    print(f"  • Ingested {len(fixtures)} live fixtures from SportyBet.")
    assert len(fixtures) > 0, "Must ingest at least 1 live upcoming event"

    ev = fixtures[0]
    print(f"  • Match: {ev['home_team']} vs {ev['away_team']}")
    print(f"  • Event ID: {ev['event_id']} | Game ID: {ev['game_id']}")
    print(f"  • 1X2 Odds: Home @ {ev['odds_home']} | Draw @ {ev['odds_draw']} | Away @ {ev['odds_away']}")
    assert ev['event_id'].startswith("sr:match:"), "Must have Sportradar match ID"

    # 2. Test Odds & Margin Analytics
    print("\n[TEST 2] Testing Market Probability & Favorite/Underdog Analytics...")
    analysis = MarketProbabilityEngine.analyze_fixture_odds(
        odds_home=ev['odds_home'],
        odds_draw=ev['odds_draw'],
        odds_away=ev['odds_away'],
        home_name=ev['home_team'],
        away_name=ev['away_team']
    )
    print(f"  • Bookmaker Margin: {analysis.margin * 100:.2f}%")
    print(f"  • Normalized Fair Probabilities: Home: {analysis.prob_home_true*100:.1f}%, Draw: {analysis.prob_draw_true*100:.1f}%, Away: {analysis.prob_away_true*100:.1f}%")
    print(f"  • Match Profile: {analysis.match_profile} (Favorite: {analysis.favorite_team})")
    print(f"  • Recommended Safe Option: {analysis.recommended_selection} (Market: {analysis.recommended_safe_market} @ {analysis.recommended_odds})")
    assert analysis.prob_home_true + analysis.prob_draw_true + analysis.prob_away_true > 0.99

    # 3. Test Deterministic Booking Code Generation with Post-Verification
    print("\n[TEST 3] Generating & Verifying SportyBet Booking Code...")
    adapter = SportyBetAdapter()
    
    # Build slip from the top 2 live fixtures
    selections = []
    for f in fixtures[:2]:
        mkt_dict = f.get("markets", {})
        m1 = mkt_dict.get("1X2") or next(iter(mkt_dict.values()), None)
        m_id = m1["market_id"] if m1 else "1"
        o_id = m1["outcomes"][0]["outcome_id"] if m1 and m1.get("outcomes") else "1"
        sel_name = m1["outcomes"][0]["selection_name"] if m1 and m1.get("outcomes") else "Home"

        selections.append({
            "provider_event_id": f["event_id"],
            "provider_market_id": m_id,
            "provider_outcome_id": o_id,
            "home_team": f["home_team"],
            "away_team": f["away_team"],
            "selection_name": sel_name,
            "odds": f["odds_home"]
        })

    booking_res = adapter.generate_code(selections=selections, country_code="ng")
    print(f"  • Booking API Status: {booking_res.get('status')}")
    print(f"  • Generated Code: {booking_res.get('booking_code')}")
    print(f"  • Verification Status: {booking_res.get('verification_status')}")
    print(f"  • Verified 1-to-1 Match: {booking_res.get('verified')}")
    print(f"  • Share URL: {booking_res.get('load_url')}")

    assert booking_res.get("status") == "SUCCESS", "Booking code generation must succeed"
    assert booking_res.get("booking_code") is not None, "Must return valid booking code"
    assert booking_res.get("verified") is True, "Booking code must be verified 1-to-1 against original selections"

    # 4. Test Strict Non-Substitution on Fake Match
    print("\n[TEST 4] Testing Strict Non-Substitution Rule (No Random Fallbacks)...")
    fake_selections = [{
        "provider_event_id": "sr:match:999999999999999",
        "home_team": "NonExistent FC",
        "away_team": "Fake United",
        "selection_name": "Home Win"
    }]
    fake_res = adapter.generate_code(selections=fake_selections, country_code="ng")
    print(f"  • Result for non-existent match: {fake_res.get('status')} ({fake_res.get('message')})")
    assert fake_res.get("status") in ("MATCH_NOT_FOUND", "CODE_GENERATION_FAILED"), "Must NEVER substitute an arbitrary random match"

    print("\n>>> ALL SPORTYBET DETERMINISTIC PIPELINE TESTS PASSED 100%! <<<\n")

if __name__ == "__main__":
    test_full_pipeline()
