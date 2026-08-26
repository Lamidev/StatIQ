import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pick_engine import MatchIQPickEngine
from app.services.ticket_reeditor import score_selection, re_edit_ticket
import asyncio

async def main():
    engine = MatchIQPickEngine(use_live_odds=True)

    print("--- TEST 1: TACTICAL ARCHETYPE ASSIGNMENT ---")
    # Equal Strength match (Swansea vs Sheffield United)
    fix_swansea = {
        'home_team': 'Swansea City',
        'away_team': 'Sheffield United',
        'odds_home': 2.60,
        'odds_draw': 3.20,
        'odds_away': 2.70,
        'ou_lines': [{'line': '1.5', 'over': 1.35, 'under': 3.0}],
        'double_chance': {'1X': 1.38, 'X2': 1.40, '12': 1.33}
    }
    dec1 = engine.evaluate_fixture_markets(fix_swansea)
    print(f"Swansea vs Sheff Utd -> [{dec1.market_name}] {dec1.selection_name} @ {dec1.estimated_odds}x (Prob: {dec1.model_probability*100:.1f}%)")

    # Heavy Favorite (Real Madrid vs Espanyol)
    fix_madrid = {
        'home_team': 'Real Madrid',
        'away_team': 'Espanyol',
        'odds_home': 1.22,
        'odds_draw': 6.00,
        'odds_away': 12.0,
        'ou_lines': [{'line': '1.5', 'over': 1.15, 'under': 4.5}],
        'double_chance': {'1X': 1.04, 'X2': 4.20, '12': 1.12}
    }
    dec2 = engine.evaluate_fixture_markets(fix_madrid)
    print(f"Real Madrid vs Espanyol -> [{dec2.market_name}] {dec2.selection_name} @ {dec2.estimated_odds}x (Prob: {dec2.model_probability*100:.1f}%)")

    # Tight low-scoring match (Valencia vs Celta)
    fix_valencia = {
        'home_team': 'Valencia',
        'away_team': 'Celta',
        'odds_home': 2.30,
        'odds_draw': 3.10,
        'odds_away': 3.10,
        'ou_lines': [{'line': '1.5', 'over': 1.42, 'under': 2.65}, {'line': '3.5', 'over': 4.0, 'under': 1.22}],
        'double_chance': {'1X': 1.33, 'X2': 1.55, '12': 1.33}
    }
    dec3 = engine.evaluate_fixture_markets(fix_valencia)
    print(f"Valencia vs Celta -> [{dec3.market_name}] {dec3.selection_name} @ {dec3.estimated_odds}x (Prob: {dec3.model_probability*100:.1f}%)")

    print("\n--- TEST 2: MULTI-TICKET STRICT ZERO OVERLAP ---")
    pool = []
    teams = [
        ('Arsenal', 'Chelsea', 'PL'), ('Liverpool', 'Everton', 'PL'), ('Man City', 'Spurs', 'PL'),
        ('Barcelona', 'Getafe', 'PD'), ('Real Madrid', 'Betis', 'PD'), ('Atletico', 'Sevilla', 'PD'),
        ('Inter', 'Monza', 'SA'), ('Milan', 'Torino', 'SA'), ('Juventus', 'Roma', 'SA'), ('Napoli', 'Lazio', 'SA'),
        ('Bayern', 'Augsburg', 'BL1'), ('Dortmund', 'Bochum', 'BL1'), ('Leverkusen', 'Mainz', 'BL1'),
        ('PSG', 'Rennes', 'FL1'), ('Monaco', 'Lille', 'FL1'), ('Marseille', 'Lyon', 'FL1'),
        ('Ajax', 'Utrecht', 'DED'), ('PSV', 'Feyenoord', 'DED'), ('Benfica', 'Porto', 'PPL'), ('Sporting', 'Braga', 'PPL')
    ]
    for idx, (h, a, comp) in enumerate(teams):
        pool.append({
            'fixture_id': f'fx_{idx+1}',
            'event_id': f'sr:match:{10000+idx+1}',
            'home_team': h,
            'away_team': a,
            'competition_code': comp,
            'competition': comp,
            'odds_home': 1.35 if idx % 2 == 0 else 2.40,
            'odds_draw': 4.50 if idx % 2 == 0 else 3.20,
            'odds_away': 8.00 if idx % 2 == 0 else 2.80,
            'double_chance': {'1X': 1.10 if idx % 2 == 0 else 1.35, 'X2': 2.80 if idx % 2 == 0 else 1.45, '12': 1.18},
            'ou_lines': [{'line': '1.5', 'over': 1.18, 'under': 4.20}, {'line': '3.5', 'over': 3.50, 'under': 1.25}]
        })

    res = engine.build_portfolio(
        fixture_pool=pool,
        num_tickets=3,
        target_total_odds=5.0,
        target_mode='GAMES',
        target_games=5,
        overlap_mode='ZERO_OVERLAP'
    )

    print(f"Total Portfolio Tickets Built: {len(res)}")
    used_fixtures_per_ticket = []
    for i, t in enumerate(res):
        f_list = [f"{leg['home_team']} vs {leg['away_team']}" for leg in t.approved_legs]
        used_fixtures_per_ticket.append(set(f_list))
        print(f"Ticket #{i+1} ({len(t.approved_legs)} legs, Odds: {t.accumulated_odds:.2f}x): {f_list}")

    overlap_1_2 = used_fixtures_per_ticket[0].intersection(used_fixtures_per_ticket[1])
    overlap_1_3 = used_fixtures_per_ticket[0].intersection(used_fixtures_per_ticket[2])
    overlap_2_3 = used_fixtures_per_ticket[1].intersection(used_fixtures_per_ticket[2])

    print(f"Overlap (T1 vs T2): {len(overlap_1_2)} | Overlap (T1 vs T3): {len(overlap_1_3)} | Overlap (T2 vs T3): {len(overlap_2_3)}")
    assert len(overlap_1_2) == 0 and len(overlap_1_3) == 0 and len(overlap_2_3) == 0, "FAIL: Found overlapping fixtures across slips!"
    print("SUCCESS: 100% Strict Zero Overlap Confirmed Across All Portfolio Slips!")

    print("\n--- TEST 3: RE-EDITOR (REMOVE & AUDITOR MODES) ---")
    sample_slip = [
        {'home_team': 'Swansea City', 'away_team': 'Sheffield United', 'market_name': 'Double Chance', 'selection_name': 'Swansea or Sheffield (12)', 'odds': 1.33},
        {'home_team': 'Valencia', 'away_team': 'Celta', 'market_name': 'Over/Under', 'selection_name': 'Over 1.5', 'odds': 1.42},
        {'home_team': 'Nottingham Forest', 'away_team': 'Leeds United', 'market_name': 'Over/Under', 'selection_name': 'Over 1.5', 'odds': 1.34},
        {'home_team': 'Real Madrid', 'away_team': 'Espanyol', 'market_name': 'Match Result', 'selection_name': '1', 'odds': 1.22},
        {'home_team': 'Inter', 'away_team': 'Monza', 'market_name': 'Match Result', 'selection_name': '1', 'odds': 1.20},
        {'home_team': 'Sporting', 'away_team': 'Alverca', 'market_name': 'Match Result', 'selection_name': '1', 'odds': 1.23},
    ]

    # Test REMOVE mode (Risk Purge)
    res_remove = await re_edit_ticket(selections=sample_slip, mode='REMOVE', target_mode='GAMES', target_games=10)
    print(f"REMOVE Mode Result -> Kept: {res_remove['kept']} legs, Purged: {res_remove['removed']} risky legs.")
    for rem in res_remove['removed_selections']:
        print(f"  [PURGED] {rem['home_team']} vs {rem['away_team']} ({rem['selection_name']}): {rem['reason']}")

    # Test AUDITOR mode (Tactical Upgrades)
    res_audit = await re_edit_ticket(selections=sample_slip, mode='AUDITOR', target_mode='GAMES', target_games=10)
    print(f"AUDITOR Mode Result -> {len(res_audit['final_selections'])} selections upgraded:")
    for aud in res_audit['final_selections']:
        print(f"  [UPGRADED] {aud['home_team']} vs {aud['away_team']}: '{aud['selection_name']}' @ {aud['odds']}x | {aud['reason']}")

if __name__ == '__main__':
    asyncio.run(main())
