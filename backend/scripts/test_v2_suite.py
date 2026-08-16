import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.evaluators.base import MatchStateContext
from app.evaluators.router import SettlementRouter
from app.evaluators.combo import evaluate_combo
from app.evaluators.win_either_half import evaluate_win_either_half
from app.evaluators.total_goals import evaluate_total_goals
from app.evaluators.double_chance import evaluate_double_chance
from app.evaluators.match_result import evaluate_match_result
from app.evaluators.btts import evaluate_btts
from app.evaluators.handicap import evaluate_handicap
from app.evaluators.corners import evaluate_corners
from app.providers.resolver import FixtureIdentityResolver
from app.services.live_scheduler import LiveTrackingScheduler

def run_tests():
    print("==================================================")
    print("       STATIQ V2.0 AUTOMATED SUITE VERIFICATION   ")
    print("==================================================")

    # 1. Test COMBO OR Evaluator
    print("\n[TEST 1] COMBO_OR Evaluator:")
    ctx_won_goals = MatchStateContext(home_score=1, away_score=2, is_concluded=True)
    res1 = evaluate_combo({"combo_type": "OR", "target_team": "HOME", "over_line": 2.5}, ctx_won_goals)
    print(f"  • Home Win or Over 2.5 on (1 - 2): {res1.status} (Expected: WON)")
    assert res1.status == "WON"

    ctx_won_team = MatchStateContext(home_score=2, away_score=0, is_concluded=True)
    res2 = evaluate_combo({"combo_type": "OR", "target_team": "HOME", "over_line": 2.5}, ctx_won_team)
    print(f"  • Home Win or Over 2.5 on (2 - 0): {res2.status} (Expected: WON)")
    assert res2.status == "WON"

    # 2. Test Win Either Half
    print("\n[TEST 2] WIN_EITHER_HALF Evaluator:")
    ctx_weh_h1 = MatchStateContext(home_score=1, away_score=3, half_time_home_score=1, half_time_away_score=0, is_concluded=True)
    res3 = evaluate_win_either_half({"target_team": "HOME"}, ctx_weh_h1)
    print(f"  • Home WEH on FT 1-3 with HT 1-0: {res3.status} (Expected: WON)")
    assert res3.status == "WON"

    ctx_weh_draw = MatchStateContext(home_score=3, away_score=3, is_concluded=True)
    res4 = evaluate_win_either_half({"target_team": "AWAY"}, ctx_weh_draw)
    print(f"  • Away WEH on 3-3 comeback draw: {res4.status} (Expected: WON)")
    assert res4.status == "WON"

    # 3. Test Total Goals Early Win & Full-Time
    print("\n[TEST 3] TOTAL_GOALS Evaluator:")
    ctx_live_over = MatchStateContext(home_score=2, away_score=1, is_concluded=False, is_live=True)
    res5 = evaluate_total_goals({"direction": "OVER", "line": 2.5}, ctx_live_over)
    print(f"  • In-Play Over 2.5 at (2 - 1): {res5.status} | Early Settled: {res5.is_early_settled} (Expected: WON)")
    assert res5.status == "WON" and res5.is_early_settled

    # 4. Test SettlementRouter inference
    print("\n[TEST 4] SettlementRouter Inference:")
    router_res = SettlementRouter.evaluate(
        market_type="",
        market_def={"selection_name": "Udinese Win or Over 2.5 Goals", "market_name": "Combo Safety"},
        ctx=MatchStateContext(home_score=2, away_score=1, is_concluded=True, home_team="Udinese", away_team="Calcio Padova")
    )
    print(f"  • Udinese Win or Over 2.5 Goals via Router: {router_res.status} (Expected: WON)")
    assert router_res.status == "WON"

    # 5. Test FixtureIdentityResolver
    print("\n[TEST 5] FixtureIdentityResolver:")
    db = SessionLocal()
    fix = FixtureIdentityResolver.resolve_and_persist(
        db=db,
        home_team="Udinese Calcio",
        away_team="Calcio Padova 1910",
        competition="Coppa Italia",
        sportybet_game_id="37522",
        sportradar_event_id="sr:match:68852186"
    )
    print(f"  • Canonical ID generated & mapped: {fix.id} (Home: {fix.home_team}, Away: {fix.away_team})")
    assert fix.id.startswith("fx_")

    # 6. Test LiveTrackingScheduler Tick
    print("\n[TEST 6] LiveTrackingScheduler Tick:")
    scheduler = LiveTrackingScheduler()
    sleep_sec = scheduler.sync_and_settle_all(db=db)
    print(f"  • Dynamic sync cycle completed. Next suggested sleep: {sleep_sec}s")
    db.close()

    print("\n>>> ALL V2.0 AUTOMATED TESTS PASSED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    run_tests()
