import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ticket_tracker import evaluate_pick, _parse_full_and_ht_scores, evaluate_pick_status
from app.api.endpoints.notifications import sync_historical_win_notifications

def test_evaluations():
    print("--- Testing 1st Half Goal Market Evaluations ---")

    # Case 1: FT is 1-0, but 1st half was 0-0 -> 1st Half Over 0.5 MUST BE LOST
    res1 = evaluate_pick("1st Half Over 0.5 Goals", home_score=1, away_score=0, ht_home_score=0, ht_away_score=0)
    print(f"Test 1 (FT 1-0, HT 0-0 -> 1st Half Over 0.5): {res1} (Expected: LOST)")
    assert res1 == "LOST", f"Expected LOST but got {res1}"

    # Case 2: FT is 1-0, 1st half was 1-0 -> 1st Half Over 0.5 MUST BE WON
    res2 = evaluate_pick("1st Half Over 0.5 Goals", home_score=1, away_score=0, ht_home_score=1, ht_away_score=0)
    print(f"Test 2 (FT 1-0, HT 1-0 -> 1st Half Over 0.5): {res2} (Expected: WON)")
    assert res2 == "WON", f"Expected WON but got {res2}"

    # Case 3: FT is 0-0 -> 1st Half Over 0.5 MUST BE LOST even if HT score isn't explicitly passed
    res3 = evaluate_pick("1st Half Over 0.5 Goals", home_score=0, away_score=0)
    print(f"Test 3 (FT 0-0 -> 1st Half Over 0.5): {res3} (Expected: LOST)")
    assert res3 == "LOST", f"Expected LOST but got {res3}"

    # Case 4: Parse parenthetical scores "1-0 (0-0)"
    h, a, ht_h, ht_a = _parse_full_and_ht_scores("1-0 (0-0)")
    print(f"Test 4 (Parse '1-0 (0-0)'): FT={h}-{a}, HT={ht_h}-{ht_a} (Expected: FT=1-0, HT=0-0)")
    assert (h, a, ht_h, ht_a) == (1, 0, 0, 0), f"Expected (1,0,0,0) got {(h,a,ht_h,ht_a)}"

    # Case 5: Parse parenthetical scores "2:1 (1:0)"
    h, a, ht_h, ht_a = _parse_full_and_ht_scores("2:1 (1:0)")
    print(f"Test 5 (Parse '2:1 (1:0)'): FT={h}-{a}, HT={ht_h}-{ht_a} (Expected: FT=2-1, HT=1-0)")
    assert (h, a, ht_h, ht_a) == (2, 1, 1, 0), f"Expected (2,1,1,0) got {(h,a,ht_h,ht_a)}"

    # Case 6: Sync notifications test
    notifs = sync_historical_win_notifications()
    print(f"Test 6 (Notification Sync): Synced {len(notifs)} win notifications cleanly.")

    print("\n✅ ALL UNIT VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_evaluations()
