import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.predictions.leg_odds_calculator import calculate_dynamic_leg_config
from app.services.pick_engine import MatchIQPickEngine, classify_league_tier, detect_match_archetype
from app.services.prediction_gate_service import PredictionGateService
from app.services.sportybet_ingestion import SportyBetIngestionService

def test_all():
    print("=== [TEST 1] Leg Odds Calculator Sweet Spots ===")
    cfg_15 = calculate_dynamic_leg_config(15.0)
    print(f"Target 15x -> Ideal legs: {cfg_15['ideal_legs']}, Leg target: {cfg_15['per_leg_target_odds']}, Min prob: {cfg_15['min_probability_threshold']}")
    assert 5 <= cfg_15['ideal_legs'] <= 7, "15x should be 5-7 legs"
    assert cfg_15['min_probability_threshold'] >= 0.75, "15x should have high probability threshold"

    cfg_20 = calculate_dynamic_leg_config(20.0)
    print(f"Target 20x -> Ideal legs: {cfg_20['ideal_legs']}, Leg target: {cfg_20['per_leg_target_odds']}, Min prob: {cfg_20['min_probability_threshold']}")
    assert 6 <= cfg_20['ideal_legs'] <= 8, "20x should be 6-8 legs"

    print("-> Test 1 PASSED!")

    print("\n=== [TEST 2] Dynamic Context Routing for '12' ===")
    engine = MatchIQPickEngine(use_live_odds=True)

    # Low-scoring defensive fixture (e.g. Saudi Div 1 / Under 2.5 <= 1.65)
    defensive_fix = {
        "fixture_id": "TEST_DEF_01",
        "home_team": "Al Bukiryah",
        "away_team": "AL Anwar",
        "competition": "Division 1",
        "country": "Saudi Arabia",
        "result_1x2": {"1": 2.60, "X": 2.80, "2": 2.70},
        "odds_home": 2.60, "odds_draw": 2.80, "odds_away": 2.70,
        "ou_lines": [{"line": 2.5, "over": 2.30, "under": 1.55}, {"line": 3.5, "over": 3.50, "under": 1.25}],
        "double_chance": {"1X": 1.35, "X2": 1.38, "12": 1.32}
    }
    cands_def = engine.evaluate_fixture_all_candidates(defensive_fix, per_leg_target_odds=1.30)
    selections_def = [c.selection_name for c in cands_def]
    print("Defensive fixture candidate picks:", selections_def)
    assert not any("12" in s for s in selections_def), "12 MUST be rejected on low-goal defensive fixture!"
    print("-> Test 2 (12 rejection on defensive trap) PASSED!")

    # High-scoring open fixture (e.g. Bundesliga / Rudes-Lokomotiva open match)
    open_fix = {
        "fixture_id": "TEST_OPEN_01",
        "home_team": "NK Rudes",
        "away_team": "NK Lokomotiva",
        "competition": "HNL",
        "country": "Croatia",
        "result_1x2": {"1": 3.40, "X": 3.80, "2": 1.90},
        "odds_home": 3.40, "odds_draw": 3.80, "odds_away": 1.90,
        "ou_lines": [{"line": 2.5, "over": 1.65, "under": 2.15}, {"line": 1.5, "over": 1.20, "under": 4.00}],
        "double_chance": {"1X": 1.75, "X2": 1.25, "12": 1.20}
    }
    cands_open = engine.evaluate_fixture_all_candidates(open_fix, per_leg_target_odds=1.25)
    selections_open = [c.selection_name for c in cands_open]
    print("Open fixture candidate picks:", selections_open)
    assert any("12" in s or "Over" in s or "X2" in s for s in selections_open), "Valid open picks should be present"
    print("-> Test 2 (Open fixture routing) PASSED!")

    print("\n=== [TEST 3] Away Powerhouse Protection (Hacken vs Sirius Rule) ===")
    away_power_fix = {
        "fixture_id": "TEST_AWAY_POWER_01",
        "home_team": "IK Sirius",
        "away_team": "BK Hacken",
        "competition": "Allsvenskan",
        "country": "Sweden",
        "result_1x2": {"1": 3.90, "X": 3.90, "2": 1.75},
        "odds_home": 3.90, "odds_draw": 3.90, "odds_away": 1.75,
        "ou_lines": [{"line": 2.5, "over": 1.50, "under": 2.40}],
        "double_chance": {"1X": 1.85, "X2": 1.22, "12": 1.20}
    }
    cands_away_power = engine.evaluate_fixture_all_candidates(away_power_fix, per_leg_target_odds=1.25)
    selections_away_power = [c.selection_name for c in cands_away_power]
    print("Away powerhouse candidate picks:", selections_away_power)
    assert not any("IK Sirius or Draw (1X)" in s for s in selections_away_power), "1X on underdog MUST be rejected vs away powerhouse!"
    print("-> Test 3 (Away powerhouse protection) PASSED!")

    print("\n=== [TEST 4] 20-Game Long Ticket & Ticket Builder Execution ===")
    sample_pool = [
        {
            "eventId": f"sr:match:1000{i}",
            "home_team": f"TeamA_{i}",
            "away_team": f"TeamB_{i}",
            "competition": f"League_{i % 5}",
            "country": "Europe",
            "result_1x2": {"1": 1.25, "X": 5.5, "2": 9.0},
            "odds_home": 1.25, "odds_draw": 5.5, "odds_away": 9.0,
            "ou_lines": [{"line": 1.5, "over": 1.18, "under": 4.5}],
            "double_chance": {"1X": 1.12, "X2": 3.5, "12": 1.15}
        }
        for i in range(25)
    ]
    ticket_20 = engine.build_ticket(sample_pool, target_total_odds=50.0, mode="ACCUMULATOR", target_mode="GAMES", target_games=20)
    print(f"20-Game Ticket Built: {len(ticket_20.approved_legs)} legs | Odds: {ticket_20.accumulated_odds:.2f}x")
    assert len(ticket_20.approved_legs) == 20, f"Expected 20 legs, got {len(ticket_20.approved_legs)}"
    print("-> Test 4 (20-Game Long Ticket) PASSED!")

    print("\n=======================================================")
    print(" ALL 4 QUANTITATIVE ENGINE INTEGRITY TESTS PASSED! 100% CLEAN")
    print("=======================================================")

if __name__ == "__main__":
    test_all()
