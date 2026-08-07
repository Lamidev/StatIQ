import asyncio
import json
from app.adapters.bookmaker_adapter import SportyBetAdapter
from app.services.ticket_reeditor import re_edit_ticket

async def test_reedit():
    adapter = SportyBetAdapter(None)
    details = adapter.fetch_booking_code_details("LYTXQL")
    selections = details.get("selections", [])
    
    print(f"=== DECODED {len(selections)} SELECTIONS ===")
    
    print("\n--- TEST 1: REMOVE MODE (Target 20.0x) ---")
    res_remove = await re_edit_ticket(selections, target_odds=20.0, mode="REMOVE")
    print(f"Final Count: {res_remove['final_count']} | New Total Odds: {res_remove['new_total_odds']}x | Kept: {res_remove['kept']} | Removed: {res_remove['removed']}")
    
    print("\n--- TEST 2: SWAP MODE (Target 20.0x) ---")
    res_swap = await re_edit_ticket(selections, target_odds=20.0, mode="SWAP")
    print(f"Final Count: {res_swap['final_count']} | New Total Odds: {res_swap['new_total_odds']}x | Kept: {res_swap['kept']} | Swapped: {res_swap['swapped']}")

if __name__ == "__main__":
    asyncio.run(test_reedit())
