import json
import os
from datetime import datetime

file_path = os.path.abspath(os.path.join("backend", "data", "tracked_tickets.json"))

with open(file_path, "r", encoding="utf-8") as f:
    tickets = json.load(f)

yesterday = "2026-08-08"

tickets_played = 0
tickets_won_flex = 0
tickets_won_no_flex = 0
tickets_lost = 0
tickets_voided = 0
tickets_running = 0

total_legs = 0
legs_won = 0
legs_lost = 0
legs_void = 0

for t in tickets:
    if t.get("created_at", "").startswith(yesterday):
        tickets_played += 1
        status = t.get("status", "").upper()
        flex = str(t.get("flex_cut", "OFF")).upper()
        
        if status == "WON":
            if flex == "OFF":
                tickets_won_no_flex += 1
            else:
                tickets_won_flex += 1
        elif status == "LOST":
            tickets_lost += 1
        elif status == "VOID":
            tickets_voided += 1
        elif status == "RUNNING":
            tickets_running += 1
            
        # Count legs
        for leg in t.get("selections", []):
            total_legs += 1
            l_stat = leg.get("status", "").upper()
            if l_stat == "WON":
                legs_won += 1
            elif l_stat == "LOST":
                legs_lost += 1
            elif l_stat == "VOID":
                legs_void += 1

print(f"--- YESTERDAY ({yesterday}) STATS ---")
print(f"Total Tickets Played: {tickets_played}")
print(f"Tickets WON (No Flex): {tickets_won_no_flex}")
print(f"Tickets WON (With Flex): {tickets_won_flex}")
print(f"Tickets LOST: {tickets_lost}")
print(f"Tickets VOIDED: {tickets_voided}")
print(f"Tickets RUNNING: {tickets_running}")
print("\n--- INDIVIDUAL LEGS ---")
print(f"Total Legs: {total_legs}")
print(f"Legs WON: {legs_won} ({legs_won/total_legs*100:.1f}%)" if total_legs else "Legs WON: 0")
print(f"Legs LOST: {legs_lost} ({legs_lost/total_legs*100:.1f}%)" if total_legs else "Legs LOST: 0")
print(f"Legs VOID: {legs_void}")
