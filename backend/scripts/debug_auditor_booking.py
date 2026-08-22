import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ticket_reeditor import re_edit_ticket
from app.adapters.bookmaker_adapter import SportyBetAdapter
from app.services.sportybet_ingestion import SportyBetIngestionService

async def main():
    adapter = SportyBetAdapter()
    
    # Test decoding code QUJ692
    print("--- 1. Testing decode of code QUJ692 ---")
    decoded = adapter.fetch_booking_code_details("QUJ692")
    print(f"Decoded status: {decoded.get('status')}, Selections: {len(decoded.get('selections', []))}")
    if decoded.get("selections"):
        print(f"Sample decoded sel: {decoded['selections'][0]}")

    sels = decoded.get("selections", [])
    if not sels:
        print("Could not decode QUJ692, creating synthetic...")
        return

    print("\n--- 2. Auditing decoded ticket (2 Tickets, 4 Games each) in AUDITOR mode ---")
    res_aud = await re_edit_ticket(
        selections=sels,
        mode="AUDITOR",
        target_mode="GAMES",
        target_games=4,
        num_tickets=2
    )

    for s in res_aud.get("portfolio_tickets", []):
        t_idx = s['ticket_index']
        print(f"\nAuditor Slip #{t_idx} ({len(s['final_selections'])} legs):")
        for x in s['final_selections']:
            print(f"  - {x.get('home_team')} vs {x.get('away_team')} | EventID: {x.get('event_id')} | Mkt: {x.get('provider_market_id')} | Out: {x.get('provider_outcome_id')} | Spec: {x.get('provider_specifier')} | Sel: {x.get('selection_name')}")
        b = adapter.generate_booking_code(s["final_selections"])
        print(f"Booking result Slip #{t_idx}: Status={b.get('status')}, Code={b.get('booking_code')}, Msg={b.get('message')}")

if __name__ == "__main__":
    asyncio.run(main())
