import asyncio
import json
import logging
import sys
import os

# Set up backend path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sportybet_ingestion import SportyBetIngestionService
from app.services.sportybet_reconciliation import SportyBetVerificationEngine
from app.services.pick_engine import MatchIQPickEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_live_tickets")

async def main():
    print("==================================================")
    print(" StatIQ Real-Time SportyBet Ticket & Code Generator")
    print("==================================================")

    # 1. Ingest upcoming top-flight fixtures
    print("\n[1/3] Fetching live upcoming fixtures from SportyBet API...")
    fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=100, force_refresh=True)
    print(f"-> Retrieved {len(fixtures)} live active fixtures across top tournaments.")

    if not fixtures:
        print("ERROR: No upcoming fixtures retrieved from SportyBet.")
        return

    pick_engine = MatchIQPickEngine(use_live_odds=True)
    recon_engine = SportyBetVerificationEngine()

    # 2. Build Ticket 1: 15-20 Odds Ticket A (Top Flight Multi)
    print("\n[2/3] Building Ticket 1 (~17x Odds)...")
    ticket1_data = pick_engine.build_ticket(
        fixture_pool=fixtures,
        target_total_odds=17.0,
        mode="ACCUMULATOR",
        target_mode="ODDS",
        risk_profile="BALANCED"
    )
    print(f"-> Ticket 1 Built: {len(ticket1_data.approved_legs)} legs | Odds: {ticket1_data.accumulated_odds:.2f}x")

    # Build Ticket 2: 15-20 Odds Ticket B (Alternative Multi)
    print("\nBuilding Ticket 2 (~18x Odds)...")
    ticket2_data = pick_engine.build_ticket(
        fixture_pool=fixtures,
        target_total_odds=18.0,
        mode="ACCUMULATOR",
        target_mode="ODDS",
        reshuffle_seed=42,
        risk_profile="BALANCED"
    )
    print(f"-> Ticket 2 Built: {len(ticket2_data.approved_legs)} legs | Odds: {ticket2_data.accumulated_odds:.2f}x")

    # Build Ticket 3: 20+ Games / High-Odds Long Ticket
    print("\nBuilding Ticket 3 (20 Games Long Ticket)...")
    ticket3_data = pick_engine.build_ticket(
        fixture_pool=fixtures,
        target_total_odds=35.0,
        mode="ACCUMULATOR",
        target_mode="GAMES",
        target_games=20,
        risk_profile="CONSERVATIVE"
    )
    print(f"-> Ticket 3 Built: {len(ticket3_data.approved_legs)} legs | Odds: {ticket3_data.accumulated_odds:.2f}x")

    # 3. Request Live Booking Codes from SportyBet
    async def book_ticket(ticket, label):
        selections = []
        for leg in ticket.approved_legs:
            ev_id = leg.get("fixture_id") or leg.get("eventId") or leg.get("external_fixture_id")
            m_id = leg.get("market_id") or leg.get("provider_market_id")
            o_id = leg.get("outcome_id") or leg.get("provider_outcome_id")
            spec = leg.get("specifier") or leg.get("provider_specifier")
            if ev_id and m_id and o_id and str(ev_id).startswith("sr:match:"):
                item = {
                    "eventId": str(ev_id),
                    "marketId": str(m_id),
                    "outcomeId": str(o_id),
                }
                if spec:
                    item["specifier"] = str(spec)
                selections.append(item)

        print(f"\nSubmitting {label} to SportyBet Booking API ({len(selections)} valid selections)...")
        if selections:
            res = await recon_engine.create_booking(selections=selections, region="ng")
            return res
        return {"status": "NO_VALID_SELECTIONS"}

    res1 = await book_ticket(ticket1_data, "Ticket 1 (17x Odds)")
    res2 = await book_ticket(ticket2_data, "Ticket 2 (18x Odds)")
    res3 = await book_ticket(ticket3_data, "Ticket 3 (20 Games)")

    print("\n" + "="*60)
    print("               FINAL SPORTYBET BOOKING CODES")
    print("="*60)

    for idx, (res, ticket, name) in enumerate([(res1, ticket1_data, "Ticket 1 (~17x Odds)"), (res2, ticket2_data, "Ticket 2 (~18x Odds)"), (res3, ticket3_data, "Ticket 3 (20 Games Long Ticket)")]):
        print(f"\n--- {name} ---")
        print(f"Total Legs: {len(ticket.approved_legs)} | Total Odds: {ticket.accumulated_odds:.2f}x")
        code = res.get("booking_code") or res.get("share_code")
        status = res.get("status")
        if code:
            print(f"BOOKING CODE: {code}")
            print(f"Direct Link: https://www.sportybet.com/ng/?shareCode={code}")
        else:
            print(f"Status: {status} | Message: {res.get('message')}")
        
        print("Picks Summary:")
        for l_idx, leg in enumerate(ticket.approved_legs, 1):
            h = leg.get('home_team')
            a = leg.get('away_team')
            sel = leg.get('selection_name') or leg.get('selection')
            odds = leg.get('estimated_odds') or leg.get('odds')
            print(f"  {l_idx}. {h} vs {a} -> {sel} @ {odds}")

if __name__ == "__main__":
    asyncio.run(main())
