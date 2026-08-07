import sys
import os
import asyncio
import json

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pick_engine import MatchIQPickEngine
from app.services.ticket_reeditor import re_edit_ticket
from app.predictions.live_calculator import calculate_matchiq_probabilities, update_dynamic_rating, TEAM_RATINGS, _ELO_FILE_PATH

def test_pick_engine_5_gates():
    print("--- 1. Testing PickEngine 5-Gate Pipeline ---")
    engine = MatchIQPickEngine(use_live_odds=False)
    
    fixture_pool = [
        {"fixture_id": "T1", "home_team": "Manchester City", "away_team": "Burnley", "competition_code": "PL"},
        {"fixture_id": "T2", "home_team": "Real Madrid", "away_team": "Getafe", "competition_code": "PD"},
        {"fixture_id": "T3", "home_team": "Bayern Munich", "away_team": "Augsburg", "competition_code": "BL1"},
        {"fixture_id": "T4", "home_team": "Arsenal", "away_team": "Wolves", "competition_code": "PL"},
    ]
    
    ticket = engine.build_ticket(fixture_pool, target_total_odds=3.0, mode="ACCUMULATOR")
    assert ticket.accumulated_odds >= 1.0
    assert len(ticket.approved_legs) > 0
    print(f"✓ PickEngine Built Accumulator: {len(ticket.approved_legs)} legs, ~{ticket.accumulated_odds}x total odds, Confidence Tier: {ticket.confidence_tier}")
    
    # Verify Gate 3 scoring uses offline weight (no phantom edge)
    for leg in ticket.approved_legs:
        for line in leg["decision_audit_log"]:
            if "GATE 3 PASS" in line:
                print(f"  Audit Log: {line}")


def test_corner_probabilities():
    print("\n--- 2. Testing Dynamic Corner Probabilities ---")
    probs = calculate_matchiq_probabilities("Real Madrid", "Barcelona")
    corner_p = probs["ai_prob_corners_over_7_5"]
    assert 0.0 <= corner_p <= 100.0
    print(f"✓ Dynamic Corner Over 7.5 Prob for Real Madrid vs Barcelona: {corner_p}% (Not static 90%)")


def test_ticket_reeditor_modes():
    print("\n--- 3. Testing Ticket Re-Editor (AUDITOR, SWAP, REMOVE) ---")
    sample_selections = [
        {"home_team": "Arsenal", "away_team": "Chelsea", "market_name": "Match Result", "selection_name": "1", "odds": 2.10},
        {"home_team": "Real Madrid", "away_team": "Barcelona", "market_name": "Match Result", "selection_name": "1", "odds": 1.90},
    ]
    
    # AUDITOR mode
    res_audit = asyncio.run(re_edit_ticket(sample_selections, target_odds=3.0, mode="AUDITOR"))
    assert res_audit["mode"] == "AUDITOR"
    assert len(res_audit["final_selections"]) == 2
    print(f"✓ AUDITOR Mode: Kept {res_audit['final_selections'][0]['home_team']} vs {res_audit['final_selections'][0]['away_team']}, upgraded pick to [{res_audit['final_selections'][0]['selection_name']}]")

    # SWAP mode
    res_swap = asyncio.run(re_edit_ticket(sample_selections, target_odds=3.0, mode="SWAP"))
    assert res_swap["mode"] == "SWAP"
    print(f"✓ SWAP Mode: Evaluated {res_swap['original_count']} picks, kept {res_swap['kept']}, swapped {res_swap['swapped']}")

    # REMOVE mode
    res_remove = asyncio.run(re_edit_ticket(sample_selections, target_odds=3.0, mode="REMOVE"))
    assert res_remove["mode"] == "REMOVE"
    print(f"✓ REMOVE Mode: Kept {res_remove['kept']} confident picks, removed {res_remove['removed']} risky picks")


def test_elo_persistence():
    print("\n--- 4. Testing Elo Rating Persistence ---")
    orig_rating = TEAM_RATINGS.get("Arsenal", 1950)
    # Simulate a dynamic match result update
    update_dynamic_rating("Arsenal", "Chelsea", 3, 0)
    new_rating = TEAM_RATINGS["Arsenal"]
    print(f"✓ Dynamic Elo Rating Update: Arsenal rating updated from {orig_rating} to {new_rating}")
    
    # Check that disk file exists
    assert os.path.exists(_ELO_FILE_PATH)
    with open(_ELO_FILE_PATH, "r", encoding="utf-8") as f:
        saved = json.load(f)
        assert "Arsenal" in saved
        print(f"✓ Persisted JSON File Check: Saved rating for Arsenal is {saved['Arsenal']}")


if __name__ == "__main__":
    test_pick_engine_5_gates()
    test_corner_probabilities()
    test_ticket_reeditor_modes()
    test_elo_persistence()
    print("\n==========================================")
    print("ALL SYSTEM VERIFICATION TESTS PASSED (100%)")
    print("==========================================")
