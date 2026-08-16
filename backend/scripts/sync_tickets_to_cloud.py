import os
import sys
import json
import sqlite3
import httpx

def sync_to_cloud():
    print("==================================================")
    print("   STATIQ CLOUD SEEDER & TICKET SYNC SCRIPT       ")
    print("==================================================")

    sqlite_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "matchiq.db"))
    print(f"\n[Step 1] Reading local SQLite database ({sqlite_path})...")
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    
    cur.execute("SELECT id, code, mode, target_odds, total_odds, stake, flex_cut, potential_win, status, created_at, locked_at_unix, selections, settled_at, flex_status_text, allowed_losses, loss_count, is_live, stale, stale_reason FROM tracked_tickets")
    rows = cur.fetchall()
    print(f"  -> Found {len(rows)} local tickets.")

    tickets_payload = []
    for r in rows:
        selections_data = json.loads(r[11]) if isinstance(r[11], str) else (r[11] or [])
        tickets_payload.append({
            "id": r[0],
            "code": r[1] or "CUSTOM",
            "mode": r[2] or "SWAP",
            "target_odds": float(r[3] or 1.5),
            "total_odds": float(r[4] or 1.5),
            "stake": float(r[5] or 100.0),
            "flex_cut": r[6],
            "potential_win": float(r[7] or 150.0),
            "status": r[8] or "RUNNING",
            "created_at": r[9] or "",
            "locked_at_unix": int(r[10] or 0),
            "selections": selections_data,
            "settled_at": r[12],
            "flex_status_text": r[13],
            "allowed_losses": r[14],
            "loss_count": r[15],
            "is_live": bool(r[16]),
            "stale": bool(r[17]),
            "stale_reason": r[18]
        })
    conn.close()

    cloud_url = "https://statiq-backend.onrender.com/api/v1/ticket-tracker/import-tickets"
    print(f"\n[Step 2] Sending {len(tickets_payload)} tickets to Cloud Backend ({cloud_url})...")
    
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(cloud_url, json={"tickets": tickets_payload})
            print("HTTP Status:", resp.status_code)
            if resp.status_code == 200:
                data = resp.json()
                print("Cloud Response:", json.dumps(data, indent=2))
                print("\n>>> ALL LOCAL TICKETS SUCCESSFULLY SEEDED INTO PRODUCTION CLOUD! <<<")
            else:
                print("Error Response:", resp.text)
    except Exception as e:
        print("Upload failed:", e)

if __name__ == "__main__":
    sync_to_cloud()
