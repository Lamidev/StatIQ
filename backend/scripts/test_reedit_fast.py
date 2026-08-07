import asyncio
import json
from app.services.ticket_reeditor import re_edit_ticket

async def test():
    selections = [
        {'home_team': 'Arsenal', 'away_team': 'Chelsea', 'market_name': 'Match Result', 'selection_name': 'Home Win', 'odds': 1.25, 'match_status': 'UPCOMING'},
        {'home_team': 'Real Madrid', 'away_team': 'Getafe', 'market_name': 'Match Result', 'selection_name': 'Home Win', 'odds': 2.10, 'match_status': 'UPCOMING'}
    ]
    res_remove = await re_edit_ticket(selections, 5.0, 'REMOVE')
    print("=== REMOVE MODE ===")
    print(json.dumps(res_remove, indent=2))
    
    res_swap = await re_edit_ticket(selections, 5.0, 'SWAP')
    print("\n=== SWAP MODE ===")
    print(json.dumps(res_swap, indent=2))

if __name__ == "__main__":
    asyncio.run(test())
