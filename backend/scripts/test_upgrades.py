import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from app.services.pick_engine import MatchIQPickEngine
from app.services.sportybet_ingestion import SportyBetIngestionService
from app.api.endpoints.ticket_builder import BuildTicketRequest


print("=== 1. TESTING PICK ENGINE RISK PROFILE & MARKET FILTER ENFORCEMENT ===")

engine = MatchIQPickEngine(use_live_odds=True)
events = SportyBetIngestionService.fetch_upcoming_fixtures(limit=20)
print(f"Fetched {len(events)} fixtures from SportyBet.")

# Test 1: ULTRA_CONSERVATIVE mode
ticket_uc = engine.build_ticket(
    fixture_pool=events,
    target_total_odds=5.0,
    mode="ACCUMULATOR",
    target_mode="ODDS",
    risk_profile="ULTRA_CONSERVATIVE"
)

print(f"\n[Ultra-Conservative Test] Generated {len(ticket_uc.approved_legs)} legs @ {ticket_uc.accumulated_odds}x:")
has_straight_1x2 = False
for leg in ticket_uc.approved_legs:
    print(f"  - {leg['home_team']} vs {leg['away_team']} -> {leg['selection_name']} ({leg['market_name']}) @ {leg['odds']}")
    if leg['market_name'] == "Match Result":
        has_straight_1x2 = True

assert not has_straight_1x2, "FAILED: Ultra-Conservative ticket contained straight 1X2 market!"
print("PASSED: Ultra-Conservative strictly banned straight 1X2 wins.")

# Test 2: Custom Allowed Markets (Only DOUBLE_CHANCE and OVER_UNDER)
ticket_dc_only = engine.build_ticket(
    fixture_pool=events,
    target_total_odds=5.0,
    mode="ACCUMULATOR",
    target_mode="ODDS",
    allowed_markets=["DOUBLE_CHANCE", "OVER_UNDER"]
)

print(f"\n[Double Chance & Over/Under Only Test] Generated {len(ticket_dc_only.approved_legs)} legs:")
all_valid_categories = True
for leg in ticket_dc_only.approved_legs:
    m = leg['market_name']
    print(f"  - {leg['home_team']} vs {leg['away_team']} -> {leg['selection_name']} ({m}) @ {leg['odds']}")
    if m not in ("Double Chance", "Over/Under Goals"):
        all_valid_categories = False

assert all_valid_categories, "FAILED: Ticket contained markets outside allowed DOUBLE_CHANCE and OVER_UNDER!"
print("PASSED: Market filter strictly restricted selections to requested categories.")

print("\n=== 2. TESTING BUILD TICKET REQUEST MODEL ===")
req = BuildTicketRequest(
    target_odds=10.0,
    risk_profile="ULTRA_CONSERVATIVE",
    allowed_market_categories=["DOUBLE_CHANCE", "OVER_UNDER", "TEAM_GOALS"]
)
assert req.risk_profile == "ULTRA_CONSERVATIVE"
assert len(req.allowed_market_categories) == 3
print("PASSED: BuildTicketRequest schema verified.")

print("\n>>> ALL UPGRADE FUNCTIONALITIES VERIFIED SUCCESSFULLY! <<<")
