import sys
import os
import asyncio

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.pick_engine import MatchIQPickEngine
from app.services.sportybet_ingestion import SportyBetIngestionService
from app.adapters.bookmaker_adapter import SportyBetAdapter

async def test_portfolio_builder():
    print("==================================================")
    print(" Testing StatIQ Multi-Ticket Portfolio Generator ")
    print("==================================================")

    # 1. Ingest live fixtures from SportyBet API
    print("\n[1/3] Fetching live fixture pool from SportyBet...")
    fixtures = SportyBetIngestionService.fetch_upcoming_fixtures(limit=120)
    print(f"-> Fetched {len(fixtures)} live fixtures from SportyBet.")

    # 2. Build 3-Ticket Portfolio with 15 Games each
    engine = MatchIQPickEngine(use_live_odds=True)
    print("\n[2/3] Generating 3-Ticket Portfolio (15 Games per Ticket, Zero Overlap)...")
    portfolio = engine.build_portfolio(
        fixture_pool=fixtures,
        num_tickets=3,
        target_total_odds=20.0,
        mode="ACCUMULATOR",
        target_mode="GAMES",
        target_games=15,
        risk_profile="BALANCED",
        overlap_mode="ZERO_OVERLAP"
    )

    print(f"-> Generated {len(portfolio)} tickets in Portfolio!")

    adapter = SportyBetAdapter()
    ticket_fixtures_sets = []

    for idx, t in enumerate(portfolio, 1):
        print(f"\n--- Portfolio Slip #{idx} ---")
        print(f"Total Legs: {len(t.approved_legs)} | Total Odds: {t.accumulated_odds:.2f}x | Confidence Tier: {t.confidence_tier}")
        
        f_ids = [leg.get("fixture_id") or leg.get("event_id") for leg in t.approved_legs]
        ticket_fixtures_sets.append(set(f_ids))

        # Generate SportyBet code
        code_res = adapter.generate_booking_code(t.approved_legs, country_code="ng")
        booking_code = code_res.get("booking_code")
        print(f"SPORTYBET BOOKING CODE: {booking_code}")
        print(f"Share URL: {code_res.get('load_url')}")

        print("Picks:")
        for l_idx, leg in enumerate(t.approved_legs[:5], 1):
            print(f"  {l_idx}. {leg.get('home_team')} vs {leg.get('away_team')} -> {leg.get('selection_name')} @ {leg.get('estimated_odds')}")
        if len(t.approved_legs) > 5:
            print(f"  ... and {len(t.approved_legs) - 5} more legs")

    # 3. Check Overlap
    print("\n[3/3] Auditing Portfolio Independence & Overlap...")
    overlap_1_2 = ticket_fixtures_sets[0].intersection(ticket_fixtures_sets[1])
    overlap_2_3 = ticket_fixtures_sets[1].intersection(ticket_fixtures_sets[2])
    overlap_1_3 = ticket_fixtures_sets[0].intersection(ticket_fixtures_sets[2])

    print(f"Overlap Slip 1 & 2: {len(overlap_1_2)} matches ({overlap_1_2})")
    print(f"Overlap Slip 2 & 3: {len(overlap_2_3)} matches ({overlap_2_3})")
    print(f"Overlap Slip 1 & 3: {len(overlap_1_3)} matches ({overlap_1_3})")

    assert len(overlap_1_2) == 0, "Slip 1 and Slip 2 MUST have 0 overlapping matches!"
    assert len(overlap_2_3) == 0, "Slip 2 and Slip 3 MUST have 0 overlapping matches!"
    assert len(overlap_1_3) == 0, "Slip 1 and Slip 3 MUST have 0 overlapping matches!"

    print("\n=======================================================")
    print(" ALL PORTFOLIO TESTS PASSED! 100% UNCORRELATED RISK ")
    print("=======================================================")

if __name__ == "__main__":
    asyncio.run(test_portfolio_builder())
