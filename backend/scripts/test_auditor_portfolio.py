import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ticket_reeditor import re_edit_ticket
from app.adapters.bookmaker_adapter import SportyBetAdapter

async def test_auditor_portfolio():
    print("=" * 60)
    print(" Testing StatIQ Auditor Multi-Ticket Portfolio Generator ")
    print("=" * 60)

    # 1. Create a mock 35-game loaded slip from SportyBet
    sample_teams = [
        ("Arsenal", "Chelsea"), ("Liverpool", "Aston Villa"), ("Man City", "Wolves"),
        ("Real Madrid", "Sevilla"), ("Barcelona", "Valencia"), ("Atletico Madrid", "Getafe"),
        ("Inter Milan", "Roma"), ("Juventus", "Lazio"), ("Napoli", "Atalanta"),
        ("Bayern Munich", "Frankfurt"), ("Dortmund", "Stuttgart"), ("Leverkusen", "Mainz"),
        ("PSG", "Monaco"), ("Marseille", "Lille"), ("Lyon", "Nice"),
        ("Porto", "Braga"), ("Benfica", "Sporting CP"), ("Feyenoord", "Ajax"),
        ("Galatasaray", "Besiktas"), ("Fenerbahce", "Trabzonspor"), ("Celtic", "Hearts"),
        ("Salzburg", "Sturm Graz"), ("Young Boys", "Basel"), ("Club Brugge", "Genk"),
        ("Dinamo Zagreb", "Hajduk Split"), ("Olympiakos", "PAOK"), ("AEK Athens", "Panathinaikos"),
        ("Sparta Prague", "Slavia Prague"), ("Legia Warsaw", "Lech Poznan"), ("Malmo", "AIK"),
        ("Bodo Glimt", "Molde"), ("Copenhagen", "Midtjylland"), ("Steaua", "CFR Cluj"),
        ("Shakhtar", "Dynamo Kyiv"), ("Red Star", "Partizan")
    ]

    mock_selections = []
    for idx, (h, a) in enumerate(sample_teams):
        # Realistic ticket mix: 1X Double Chance, Over 1.5, and Straight Win
        if (idx % 3) == 0:
            m_name, s_name, odd, m_id, oc_id, spec = "Double Chance", f"{h} or Draw", 1.25, "10", "9", None
        elif (idx % 3) == 1:
            m_name, s_name, odd, m_id, oc_id, spec = "Over/Under", "Over 1.5", 1.22, "18", "12", "total=1.5"
        else:
            m_name, s_name, odd, m_id, oc_id, spec = "1X2", f"{h} to Win", 1.30, "1", "1", None

        mock_selections.append({
            "fixture_id": f"sr:match:{100000 + idx}",
            "external_fixture_id": f"sr:match:{100000 + idx}",
            "game_id": f"M{idx:03d}",
            "home_team": h,
            "away_team": a,
            "market_name": m_name,
            "selection_name": s_name,
            "odds": odd,
            "match_status": "UPCOMING",
            "provider_market_id": m_id,
            "provider_outcome_id": oc_id,
            "provider_specifier": spec,
        })

    print(f"\n[1/3] Created 35-Game Loaded SportyBet Ticket (35 selections).")

    # 2. Test REMOVE Mode with 3-Ticket Portfolio (10 games per ticket)
    print("\n[2/3] Running Re-Editor in REMOVE Mode (num_tickets=3, target_games=10)...")
    res_remove = await re_edit_ticket(
        selections=mock_selections,
        mode="REMOVE",
        target_mode="GAMES",
        target_games=10,
        num_tickets=3
    )

    port_remove = res_remove.get("portfolio_tickets", [])
    print(f"-> Generated {len(port_remove)} slips in REMOVE Portfolio!")
    assert len(port_remove) == 3, f"Expected 3 slips, got {len(port_remove)}"

    for s in port_remove:
        print(f"   • Slip #{s['ticket_index']}: {s['final_count']} Legs | Total Odds: ~{s['new_total_odds']}x | Avg Prob: {s['avg_win_prob']*100:.1f}%")
        assert s['final_count'] == 10, f"Expected 10 legs, got {s['final_count']}"

    # Overlap Audit in REMOVE mode
    matches_s1 = {f"{s['home_team']}_{s['away_team']}" for s in port_remove[0]["final_selections"]}
    matches_s2 = {f"{s['home_team']}_{s['away_team']}" for s in port_remove[1]["final_selections"]}
    matches_s3 = {f"{s['home_team']}_{s['away_team']}" for s in port_remove[2]["final_selections"]}

    overlap_1_2 = len(matches_s1.intersection(matches_s2))
    overlap_2_3 = len(matches_s2.intersection(matches_s3))
    overlap_1_3 = len(matches_s1.intersection(matches_s3))

    print(f"   [REMOVE Overlap Check] Slip 1&2: {overlap_1_2} overlap | Slip 2&3: {overlap_2_3} overlap | Slip 1&3: {overlap_1_3} overlap")
    assert overlap_1_2 == 0 and overlap_2_3 == 0 and overlap_1_3 == 0, "Expected zero overlap between slips!"

    # 3. Test AUDITOR Mode with 3-Ticket Portfolio (10 games per ticket)
    print("\n[3/3] Running Re-Editor in AUDITOR Mode (num_tickets=3, target_games=10)...")
    res_audit = await re_edit_ticket(
        selections=mock_selections,
        mode="AUDITOR",
        target_mode="GAMES",
        target_games=10,
        num_tickets=3
    )

    port_audit = res_audit.get("portfolio_tickets", [])
    print(f"-> Generated {len(port_audit)} slips in AUDITOR Portfolio!")
    assert len(port_audit) == 3, f"Expected 3 slips, got {len(port_audit)}"

    for s in port_audit:
        print(f"   • Slip #{s['ticket_index']}: {s['final_count']} Upgraded Legs | Total Odds: ~{s['new_total_odds']}x | Avg Prob: {s['avg_win_prob']*100:.1f}%")
        assert s['final_count'] == 10, f"Expected 10 legs, got {s['final_count']}"

    audit_s1 = {f"{s['home_team']}_{s['away_team']}" for s in port_audit[0]["final_selections"]}
    audit_s2 = {f"{s['home_team']}_{s['away_team']}" for s in port_audit[1]["final_selections"]}
    audit_s3 = {f"{s['home_team']}_{s['away_team']}" for s in port_audit[2]["final_selections"]}

    a_overlap_1_2 = len(audit_s1.intersection(audit_s2))
    a_overlap_2_3 = len(audit_s2.intersection(audit_s3))
    a_overlap_1_3 = len(audit_s1.intersection(audit_s3))

    print(f"   [AUDITOR Overlap Check] Slip 1&2: {a_overlap_1_2} overlap | Slip 2&3: {a_overlap_2_3} overlap | Slip 1&3: {a_overlap_1_3} overlap")
    assert a_overlap_1_2 == 0 and a_overlap_2_3 == 0 and a_overlap_1_3 == 0, "Expected zero overlap between auditor slips!"

    print("\n" + "=" * 60)
    print(" ALL AUDITOR PORTFOLIO TESTS PASSED CLEANLY! (100% SUCCESS) ")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_auditor_portfolio())
