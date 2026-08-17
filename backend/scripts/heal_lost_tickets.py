"""
One-time database healing script for tickets wrongly marked as LOST.
Run this ONCE on the VPS: python scripts/heal_lost_tickets.py

Strategy:
- For each LOST ticket created TODAY, re-fetch the booking code from SportyBet
- Use SportyBet estimateStartTime as the authoritative kickoff time
- Any selection whose kickoff is in the future -> reset to UPCOMING / PENDING
- Recount losses; if loss_count is now 0, restore ticket to RUNNING
"""
import sys
import os
import sqlite3
import json
import time
import urllib.request
import ssl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "matchiq.db")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

now_ms = int(time.time() * 1000)
now_date_str = time.strftime("%Y-%m-%d")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*'
}

def fetch_sportybet_kickoffs(code: str) -> dict:
    """Fetch kickoff times from SportyBet for each selection in a booking code."""
    kickoffs = {}  # key: "home_vs_away", value: estimateStartTime in ms
    regions = ["ng", "gh", "ke", "ug"]
    for reg in regions:
        url = f"https://www.sportybet.com/api/{reg}/orders/share/{code.upper()}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("bizCode") == 10000:
                    for out in data.get("data", {}).get("outcomes", []):
                        h = out.get("homeTeamName") or out.get("homeTeam") or ""
                        a = out.get("awayTeamName") or out.get("awayTeam") or ""
                        est = out.get("estimateStartTime") or out.get("startTime") or 0
                        match_status = str(out.get("matchStatus") or "").strip().lower()
                        key = f"{h.lower().strip()}_{a.lower().strip()}"
                        kickoffs[key] = {"start_ms": est, "sb_status": match_status}
                    return kickoffs
        except Exception:
            pass
    return kickoffs


conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT id, code, created_at, status, locked_at_unix, selections FROM tracked_tickets ORDER BY locked_at_unix DESC")
rows = cursor.fetchall()

print(f"[Healer] Total tickets in database: {len(rows)}")
print(f"[Healer] Current time: {now_date_str} | now_ms={now_ms}")

healed = 0
for r in rows:
    tid, code, created_at, status, locked_at_unix, selections_json = r
    if not selections_json:
        continue

    # Only target today's tickets that are marked LOST
    if status != "LOST":
        continue
    if not created_at or now_date_str not in str(created_at):
        continue

    selections = json.loads(selections_json)
    print(f"\n[Healer] Checking ticket {tid} | Code: {code} | Created: {created_at}")

    # Fetch authoritative kickoff times from SportyBet
    sb_kickoffs = {}
    if code and code not in ("CUSTOM", "AI-BUILDER-INTERNAL", "ROLLOVER-INTERNAL", ""):
        try:
            sb_kickoffs = fetch_sportybet_kickoffs(code)
            print(f"  SportyBet returned {len(sb_kickoffs)} kickoff entries")
        except Exception as e:
            print(f"  Could not fetch SportyBet data for {code}: {e}")

    changed = False
    for s in selections:
        h = str(s.get("home_team") or "").lower().strip()
        a = str(s.get("away_team") or "").lower().strip()
        key = f"{h}_{a}"

        # 1. Try to get authoritative kickoff from SportyBet response
        sb_info = sb_kickoffs.get(key)
        sb_start_ms = sb_info.get("start_ms", 0) if sb_info else 0
        sb_status = sb_info.get("sb_status", "") if sb_info else ""

        # 2. Fall back to stored kickoff time
        stored_start_ms = s.get("start_time_ms") or 0
        kickoff_ms = sb_start_ms if sb_start_ms > 0 else stored_start_ms

        # 3. Determine if match is genuinely in the future
        is_not_started = (
            kickoff_ms > now_ms  # kickoff is in the future
            or sb_status in ("not start", "notstart", "0", "pre", "upcoming", "")
        )

        # 4. If SportyBet says "Not start" or kickoff is in future, reset the leg
        if is_not_started:
            old_leg = s.get("leg_status")
            s["match_status"] = "UPCOMING"
            s["is_live"] = False
            s["leg_status"] = "PENDING"
            s["result"] = "--"
            s["score"] = "--"
            s["home_score"] = None
            s["away_score"] = None
            if kickoff_ms > 0:
                s["start_time_ms"] = kickoff_ms
            print(f"  HEALED: {s.get('home_team')} vs {s.get('away_team')} | {old_leg} -> PENDING (kickoff in {(kickoff_ms - now_ms)/3600000:.1f}h)")
            changed = True
        else:
            print(f"  SKIP: {s.get('home_team')} vs {s.get('away_team')} | status={sb_status} | leg={s.get('leg_status')}")

    if changed:
        # Recount losses after healing
        loss_count = sum(1 for s in selections if s.get("leg_status") == "LOST")
        new_status = "LOST" if loss_count > 0 else "RUNNING"
        cursor.execute(
            "UPDATE tracked_tickets SET status = ?, loss_count = ?, selections = ?, flex_status_text = ? WHERE id = ?",
            (new_status, loss_count, json.dumps(selections), None if new_status == "RUNNING" else "Ticket Lost", tid)
        )
        print(f"  => Ticket {tid} updated: {status} -> {new_status} | losses remaining: {loss_count}")
        healed += 1

conn.commit()
conn.close()
print(f"\n[Healer] Done. Healed {healed} tickets. Run 'git pull' then restart the server if not already done.")
