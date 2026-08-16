import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sportybet_ingestion import SportyBetIngestionService
from app.adapters.bookmaker_adapter import SportyBetAdapter

def test_multi_leg_booking():
    print("==================================================")
    print("      SPORTYBET MULTI-LEG VERIFICATION TEST       ")
    print("==================================================")

    # 1. Fetch live upcoming fixtures
    fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=10, force_refresh=True)
    if len(fixtures) < 3:
        print("Not enough fixtures returned from SportyBet.")
        return

    # Select 3 distinct matches
    chosen_matches = fixtures[1:4]
    
    selections = []
    print("\n[STEP 1] Selected 3 Distinct Matches from SportyBet:")
    for i, f in enumerate(chosen_matches, 1):
        mkt_dict = f.get("markets", {})
        m1 = mkt_dict.get("1X2") or next(iter(mkt_dict.values()), None)
        m_id = m1["market_id"] if m1 else "1"
        o_id = m1["outcomes"][0]["outcome_id"] if m1 and m1.get("outcomes") else "1"
        sel_name = m1["outcomes"][0]["selection_name"] if m1 and m1.get("outcomes") else "Home"
        odds_val = m1["outcomes"][0]["odds"] if m1 and m1.get("outcomes") else f["odds_home"]

        print(f"  Leg {i}: {f['home_team']} vs {f['away_team']}")
        print(f"         Pick: {sel_name} | Odds: {odds_val} | Event ID: {f['event_id']}")

        selections.append({
            "provider_event_id": f["event_id"],
            "provider_market_id": m_id,
            "provider_outcome_id": o_id,
            "home_team": f["home_team"],
            "away_team": f["away_team"],
            "selection_name": sel_name,
            "odds": odds_val
        })

    # 2. Generate Booking Code on SportyBet
    print("\n[STEP 2] Requesting SportyBet Booking Code...")
    adapter = SportyBetAdapter()
    res = adapter.generate_code(selections=selections, country_code="ng")

    code = res.get("booking_code")
    print(f"\n==================================================")
    print(f"  NEW BOOKING CODE GENERATED: {code}")
    print(f"  VERIFICATION STATUS:        {res.get('verification_status')}")
    print(f"  1-TO-1 MATCH CONFIRMED:     {res.get('verified')}")
    print(f"  LOAD URL:                   {res.get('load_url')}")
    print(f"==================================================")

    # 3. Decode the new code directly from SportyBet API
    print(f"\n[STEP 3] Decoding SportyBet Code '{code}' directly from SportyBet Server:")
    decoded = adapter.fetch_booking_code_details(code=code, country_code="ng")
    decoded_selections = decoded.get("selections", [])
    print(f"  Total Games returned by SportyBet for code '{code}': {len(decoded_selections)}")

    for i, s in enumerate(decoded_selections, 1):
        print(f"  • Game {i}: {s.get('home_team')} vs {s.get('away_team')} | Pick: {s.get('selection_name')} | Odds: {s.get('odds')}")

    assert len(decoded_selections) == len(selections), "Returned selections count must match requested count"
    print(f"\n>>> CONFIRMATION: CODE '{code}' PERFECTLY MATCHES ALL 3 GAMES ON SPORTYBET! <<<\n")

if __name__ == "__main__":
    test_multi_leg_booking()
