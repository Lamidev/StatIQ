import httpx
import json
import time

url = "https://www.sportybet.com/api/ng/orders/share/LYTXQL"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.sportybet.com/ng/',
    'Origin': 'https://www.sportybet.com'
}

with httpx.Client(timeout=8.0, headers=headers) as client:
    r = client.get(url)
    data = r.json().get("data", {})
    outcomes = data.get("outcomes", [])
    now_ms = time.time() * 1000

    print(f"Total Outcomes: {len(outcomes)}")
    total_odds = 1.0

    for i, out in enumerate(outcomes):
        home = out.get("homeTeamName", "Home")
        away = out.get("awayTeamName", "Away")
        
        # Extract market, selection, and odds from nested markets array
        markets = out.get("markets", [])
        mkt_name = "Match Result (1X2)"
        sel_name = "Home Win"
        odds_val = 1.80

        if markets and len(markets) > 0:
            mkt = markets[0]
            mkt_name = mkt.get("desc") or mkt.get("name") or mkt_name
            mkt_outcomes = mkt.get("outcomes", [])
            if mkt_outcomes and len(mkt_outcomes) > 0:
                sel_item = mkt_outcomes[0]
                sel_name = sel_item.get("desc") or sel_item.get("name") or sel_name
                try:
                    odds_val = float(sel_item.get("odds", 1.80))
                except (ValueError, TypeError):
                    odds_val = 1.80

        start_time = out.get("estimateStartTime") or 0
        match_status_code = out.get("matchStatus", "")
        mkt_status = markets[0].get("status") if markets else 1

        if match_status_code in ["H1", "H2", "HT"] or out.get("playedSeconds"):
            status_label = "In Progress / Live"
        elif match_status_code == "FT" or mkt_status == 3:
            status_label = "Settled / Concluded"
        elif start_time > 0 and start_time < now_ms:
            status_label = "In Progress / Live"
        else:
            status_label = "Upcoming / Bettable"

        total_odds *= odds_val
        print(f"[{i+1}] {home} vs {away} | Pick: {mkt_name} -> {sel_name} | Odds: {odds_val}x | Status: {status_label}")

    print(f"\nTotal Combined Odds Calculated: {round(total_odds, 2)}x")
