import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sqlite3
import json
from app.db.session import SessionLocal
from app.services.ticket_tracker import evaluate_tracked_tickets, save_tracked_tickets

def reconcile_all():
    db = SessionLocal()
    print("[Reconcile] Running complete evaluation sweep over all tracked tickets...")
    evaluated_tickets = evaluate_tracked_tickets(db=db)
    
    changed_count = 0
    won_count = 0
    lost_count = 0
    running_count = 0

    print(f"\n--- AUDIT RESULTS FOR ALL {len(evaluated_tickets)} TICKETS ---")
    for t in evaluated_tickets:
        tid = t.get("id")
        status = t.get("status")
        code = t.get("code")
        created = t.get("created_at")
        pot_win = t.get("potential_win")
        legs = t.get("selections", [])
        
        if status == "WON":
            won_count += 1
        elif status == "LOST":
            lost_count += 1
        else:
            running_count += 1

        leg_details = []
        for s in legs:
            h = s.get("home_team")
            a = s.get("away_team")
            sc = s.get("score")
            pick = s.get("selection_name") or s.get("selection")
            lst = s.get("leg_status")
            leg_details.append(f"{h} vs {a} ({sc}) -> Pick: {pick} [{lst}]")

        print(f"\nTicket: {tid} | Code: {code} | Status: {status} | Pot Win: N{pot_win:,.2f} | Created: {created}")
        for ld in leg_details:
            print(f"  • {ld}")

    save_tracked_tickets(evaluated_tickets, db=db)
    print(f"\n[Summary] Won: {won_count} | Lost: {lost_count} | Running: {running_count}")
    db.close()

if __name__ == "__main__":
    reconcile_all()
