import json
from app.services.ticket_tracker import get_tracked_tickets, save_tracked_tickets, evaluate_pick

tickets = get_tracked_tickets()
total_legs = 0
won_legs = 0
lost_legs = 0

for t in tickets:
    all_won = True
    any_lost = False
    all_concluded = True

    for sel in t.get("selections", []):
        total_legs += 1
        score_str = sel.get("score")
        if score_str and ("-" in str(score_str) or ":" in str(score_str)):
            sep = "-" if "-" in str(score_str) else ":"
            parts = str(score_str).split(sep)
            try:
                h = int(parts[0].strip())
                a = int(parts[1].strip())
                mkt = sel.get("market_name") or ""
                pick = sel.get("selection_name") or sel.get("selection") or ""
                full_pick = f"{mkt} — {pick}".strip(" —") if mkt else pick

                w = evaluate_pick(full_pick, h, a, sel.get("home_team", ""), sel.get("away_team", ""))
                sel["leg_status"] = "WON" if w else "LOST"
                if w:
                    won_legs += 1
                else:
                    lost_legs += 1
                    any_lost = True
                    all_won = False
            except Exception as e:
                print(f"Error parsing score for {sel}: {e}")
        else:
            all_concluded = False

    if any_lost:
        t["status"] = "LOST"
    elif all_concluded and len(t.get("selections", [])) > 0:
        t["status"] = "WON"

save_tracked_tickets(tickets)
print(f"DONE: Re-graded {total_legs} total legs across {len(tickets)} tickets: {won_legs} WON, {lost_legs} LOST.")
