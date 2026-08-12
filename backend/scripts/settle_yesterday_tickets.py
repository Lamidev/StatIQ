import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ticket_tracker import (
    get_tracked_tickets,
    save_tracked_tickets,
    evaluate_tracked_tickets,
    sync_tracked_tickets_with_live_apis
)
from app.api.endpoints.notifications import sync_historical_win_notifications

def settle_tickets():
    print("--- Settle Tracked Tickets (Live Sync & Regrade) ---")
    
    # 1. Fetch live API updates & re-evaluate all running tickets
    tickets = sync_tracked_tickets_with_live_apis()
    print(f"Loaded and synced {len(tickets)} tracked tickets.")

    now_ms = time.time() * 1000
    updated_count = 0

    for t in tickets:
        status = t.get("status", "RUNNING")
        selections = t.get("selections", [])
        
        # Check if ticket was staked yesterday or earlier, or if all legs kickoff ms > 2 hours ago
        all_finished = True
        for sel in selections:
            kickoff_ms = sel.get("start_time_ms") or 0
            match_st = str(sel.get("match_status") or "").upper()
            
            # If match started > 2 hours ago or has a score, treat as finished
            if kickoff_ms > 0 and (now_ms - kickoff_ms) > (2.5 * 3600 * 1000):
                sel["match_status"] = "CONCLUDED"
            elif match_st not in ("CONCLUDED", "FINISHED", "FT", "ENDED", "COMPLETED"):
                all_finished = False

        # Force re-evaluation of tickets
        evaluate_tracked_tickets()

    # Re-evaluate all tickets
    settled_tickets = evaluate_tracked_tickets()
    
    won_cnt = sum(1 for t in settled_tickets if t.get("status") == "WON")
    lost_cnt = sum(1 for t in settled_tickets if t.get("status") == "LOST")
    running_cnt = sum(1 for t in settled_tickets if t.get("status") == "RUNNING")

    print(f"Settlement Complete: {won_cnt} WON, {lost_cnt} LOST, {running_cnt} RUNNING out of {len(settled_tickets)} tickets.")

    # Sync notifications
    sync_historical_win_notifications()
    print("Cleaned up and synced win notifications.")

if __name__ == "__main__":
    settle_tickets()
