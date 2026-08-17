import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from app.adapters.bookmaker_adapter import SportyBetAdapter
from app.services.sportybet_reconciliation import SportyBetVerificationEngine

from app.services.ticket_reeditor import re_edit_ticket
from app.services.ticket_tracker import evaluate_pick_status
from app.services.sportybet_ingestion import SportyBetIngestionService

adapter = SportyBetAdapter()
print("=== 1. TESTING SUB-MARKET RESOLUTION IN BOOKMAKER ADAPTER ===")

test_submarkets = [
    ("2nd Half - Double Chance", "Home or Away", "Narpes Kraft", "SJK Akatemia/2", "60", "10"),
    ("2nd Half - Double Chance", "Home or Draw", "Narpes Kraft", "SJK Akatemia/2", "60", "9"),
    ("2nd Half - Double Chance", "Away or Draw", "Narpes Kraft", "SJK Akatemia/2", "60", "11"),
    ("1st Half - Double Chance", "Home or Away", "Liverpool", "Como 1907", "41", "10"),
    ("Salzburg Over/Under", "Over 1.5", "WSG Tirol", "Salzburg", "21", "12"),
    ("Home Team to Win Either Half", "Yes", "SK Brann", "HamKam", "73", "75"),
    ("Away Team to Win Either Half", "Yes", "RC Lens", "PSG", "74", "75"),
    ("Double Chance", "Home or Away", "FC Cajamarca", "Universitario", "10", "10"),
    ("Over/Under", "Over 1.5", "Harju JK Laagri", "FCI Levadia", "18", "12"),
    ("GG/NG", "Yes", "FC Supra", "Atletico Ottawa", "29", "24"),
    ("Asian Handicap (+1.5)", "Erzurumspor FK (+1.5)", "Amed Sportif", "Erzurumspor FK", "16", "3"),
    ("1X2", "Home", "HB Torshavn", "Tofta B68", "1", "1"),
]

passed_submarkets = 0
for mkt, sel, h, a, exp_m, exp_o in test_submarkets:
    m_id, o_id, spec = adapter._resolve_market_payload([], mkt, sel, h, a)
    status = "PASS" if (m_id == exp_m and o_id == exp_o) else f"FAIL (Got m_id={m_id}, o_id={o_id}, expected m_id={exp_m}, o_id={exp_o})"
    print(f"[{status}] Market: \"{mkt}\" | Pick: \"{sel}\" -> Market ID: {m_id}, Outcome ID: {o_id}, Specifier: {spec}")
    if m_id == exp_m and o_id == exp_o:
        passed_submarkets += 1

print(f"\nSubmarket Resolution: {passed_submarkets}/{len(test_submarkets)} Passed")

print("\n=== 2. TESTING SPORTYBET LIVE FIXTURES INGESTION ===")
events = SportyBetIngestionService.fetch_upcoming_fixtures(limit=10)
print(f"Fetched {len(events)} live upcoming SportyBet fixtures successfully.")
if events:
    e0 = events[0]
    print(f"Sample event: {e0.get('home_team')} vs {e0.get('away_team')} | EventID: {e0.get('event_id')}")

print("\n=== 3. TESTING EVALUATOR STATUS ENGINE (ALL MARKETS) ===")
eval_tests = [
    ("Colo-Colo 2-2 Draw (Pick: 1X2 Home)", evaluate_pick_status("1X2 — Home", 2, 2, "Colo-Colo", "CD O'Higgins", True), "LOST"),
    ("FC Supra 1-2 (Pick: GG/NG Yes)", evaluate_pick_status("GG/NG — Yes", 1, 2, "FC Supra", "Ottawa", True), "WON"),
    ("Narpes Kraft 2-2 FT, 2-1 2H (Pick: 2nd Half DC 12)", evaluate_pick_status("2nd Half - Double Chance — Home or Away", 2, 2, "Narpes", "SJK", True, ht_home_score=0, ht_away_score=1), "WON"),
    ("Nasaf 1-2 (Pick: Goal Bounds Away 1-3+)", evaluate_pick_status("Goal Bounds - Away — 1-3+", 1, 2, "Nasaf", "Pakhtakor", True), "WON"),
    ("Cincinnati 2-3 FT, 2-1 HT (Pick: Both Halves Under 1.5 - No)", evaluate_pick_status("Both Halves Under 1.5 — No", 2, 3, "Cincinnati", "CT United", True, ht_home_score=2, ht_away_score=1), "WON"),
    ("Frosinone 6 Corners (Pick: Corners Over 7.5)", evaluate_pick_status("Corners - Over/Under — Over 7.5", 4, 1, "Frosinone", "Juve Stabia", True, total_corners=6), "LOST"),
    ("Sarpsborg 10 Corners (Pick: Corners Over 8.5)", evaluate_pick_status("Corners - Over/Under — Over 8.5", 1, 2, "Sarpsborg", "Sandefjord", True, total_corners=10), "WON"),
]

passed_evals = 0
for name, res, exp in eval_tests:
    status = "PASS" if res == exp else f"FAIL (Got {res}, expected {exp})"
    print(f"[{status}] {name} -> Result: {res}")
    if res == exp:
        passed_evals += 1

print(f"\nEvaluators Status: {passed_evals}/{len(eval_tests)} Passed")

print("\n=== 4. TESTING RE-EDITOR / AUDITOR PIPELINE ===")
async def test_reeditor():
    dummy_selections = [
        {
            "home_team": "Manchester City",
            "away_team": "Everton",
            "market_name": "Match Result",
            "selection_name": "1",
            "odds": 1.25,
            "match_status": "UPCOMING"
        },
        {
            "home_team": "Real Madrid",
            "away_team": "Osasuna",
            "market_name": "Match Result",
            "selection_name": "1",
            "odds": 1.30,
            "match_status": "UPCOMING"
        }
    ]
    res = await re_edit_ticket(
        selections=dummy_selections,
        target_odds=2.0,
        mode="AUDITOR",
        target_mode="ODDS"
    )
    print(f"Re-Editor Mode: {res.get('mode')} | Final Selections: {len(res.get('final_selections', []))}")
    print(f"New Total Odds: {res.get('new_total_odds')}")
    print("Re-Editor Execution SUCCESS!")

asyncio.run(test_reeditor())
print("\n>>> ALL SYSTEM FUNCTIONALITY VERIFICATION COMPLETE! <<<")
