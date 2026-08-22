import httpx
import json
import time

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.sportybet.com",
    "Referer": "https://www.sportybet.com/ng/"
}

# Category IDs on SportyBet:
# 1 = England, 8 = Spain, 30 = Germany, 31 = Italy, 7 = France, 35 = Netherlands, 44 = Portugal, 46 = Turkey, 24 = Scotland, 23 = Belgium
categories = [1, 8, 30, 31, 7, 35, 44, 46, 24, 23, 34, 291, 155, 384]

all_events = []
with httpx.Client(timeout=10.0, headers=headers) as client:
    for cat_id in categories:
        url = f"https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&categoryId=sr:category:{cat_id}&pageSize=50"
        try:
            r = client.get(url)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if isinstance(data, list):
                    all_events.extend(data)
                elif isinstance(data, dict) and "events" in data:
                    all_events.extend(data["events"])
        except Exception as e:
            pass

    # Also fetch general upcoming
    for p in range(1, 6):
        url = f"https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&pageSize=100"
        try:
            r = client.get(url)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if isinstance(data, list): all_events.extend(data)
                elif isinstance(data, dict) and "events" in data: all_events.extend(data["events"])
        except: pass

print(f"Total events fetched across categories: {len(all_events)}")

# Deduplicate
unique_events = {}
for ev in all_events:
    ev_id = ev.get("eventId")
    if ev_id and ev_id not in unique_events:
        unique_events[ev_id] = ev

print(f"Unique events: {len(unique_events)}")

now_ms = time.time() * 1000.0
parsed_fixtures = []

for ev_id, ev in unique_events.items():
    start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
    if start_ms > 0 and start_ms <= (now_ms + 180000):
        continue
    
    status = str(ev.get("status") or ev.get("match_status") or "").upper()
    if status in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "ENDED", "CANCELLED", "POSTPONED"]:
        continue
    
    home = ev.get("homeTeamName") or "Home"
    away = ev.get("awayTeamName") or "Away"
    sport = ev.get("sport", {})
    cat = sport.get("category", {}) if isinstance(sport, dict) else {}
    tourn = cat.get("tournament", {}) if isinstance(cat, dict) else {}
    comp = tourn.get("name") if isinstance(tourn, dict) else (ev.get("tournamentName") or "")
    country = cat.get("name") if isinstance(cat, dict) else ""

    markets = ev.get("markets", [])
    if not markets:
        continue

    m1 = next((m for m in markets if str(m.get("id")) == "1"), None)
    m10 = next((m for m in markets if str(m.get("id")) == "10"), None)
    m18 = [m for m in markets if str(m.get("id")) == "18"]

    odds_h, odds_d, odds_a = None, None, None
    if m1:
        for out in m1.get("outcomes", []):
            desc = (out.get("desc") or "").upper()
            try:
                ov = float(out.get("odds", 0))
                if desc in ["HOME", "1"]: odds_h = ov
                elif desc in ["DRAW", "X"]: odds_d = ov
                elif desc in ["AWAY", "2"]: odds_a = ov
            except: pass

    parsed_fixtures.append({
        "eventId": ev_id,
        "gameId": ev.get("gameId"),
        "home": home,
        "away": away,
        "comp": comp,
        "country": country,
        "start_ms": start_ms,
        "odds_h": odds_h,
        "odds_d": odds_d,
        "odds_a": odds_a,
        "m1": m1,
        "m10": m10,
        "m18": m18
    })

print(f"Parsed active fixtures: {len(parsed_fixtures)}")

# Classify candidate picks
candidates = []
for f in parsed_fixtures:
    h, a = f["home"], f["away"]
    oh, od, oa = f["odds_h"], f["odds_d"], f["odds_a"]
    if not oh or not oa:
        continue

    # Double Chance
    m10 = f["m10"]
    if m10:
        for out in m10.get("outcomes", []):
            desc = (out.get("desc") or "").upper()
            oc_id = str(out.get("id"))
            try: ov = float(out.get("odds", 0))
            except: ov = 0.0
            
            # 1X on solid home favorite
            if ("1X" in desc or desc == "HOME/DRAW") and 1.10 <= ov <= 1.35 and oh <= 2.10:
                candidates.append({
                    "fixture": f"{h} vs {a}",
                    "comp": f["comp"],
                    "country": f["country"],
                    "market_name": "Double Chance",
                    "selection_name": f"{h} or Draw (1X)",
                    "odds": ov,
                    "eventId": f["eventId"],
                    "marketId": "10",
                    "outcomeId": oc_id,
                    "specifier": m10.get("specifier"),
                    "safety": "ELITE" if oh <= 1.50 else "HIGH"
                })
            # X2 on solid away favorite
            elif ("X2" in desc or desc == "DRAW/AWAY") and 1.10 <= ov <= 1.35 and oa <= 2.10:
                candidates.append({
                    "fixture": f"{h} vs {a}",
                    "comp": f["comp"],
                    "country": f["country"],
                    "market_name": "Double Chance",
                    "selection_name": f"Draw or {a} (X2)",
                    "odds": ov,
                    "eventId": f["eventId"],
                    "marketId": "10",
                    "outcomeId": oc_id,
                    "specifier": m10.get("specifier"),
                    "safety": "ELITE" if oa <= 1.50 else "HIGH"
                })

    # Over 1.5 Goals
    for m in f["m18"]:
        spec = str(m.get("specifier") or "")
        if "1.5" in spec:
            for out in m.get("outcomes", []):
                desc = (out.get("desc") or "").upper()
                oc_id = str(out.get("id"))
                try: ov = float(out.get("odds", 0))
                except: ov = 0.0
                if "OVER" in desc and 1.14 <= ov <= 1.35:
                    candidates.append({
                        "fixture": f"{h} vs {a}",
                        "comp": f["comp"],
                        "country": f["country"],
                        "market_name": "Over/Under",
                        "selection_name": "Over 1.5 Goals",
                        "odds": ov,
                        "eventId": f["eventId"],
                        "marketId": str(m.get("id")),
                        "outcomeId": oc_id,
                        "specifier": spec,
                        "safety": "HIGH"
                    })

    # Straight Win on Heavy Favorites (odds <= 1.35)
    m1 = f["m1"]
    if m1:
        for out in m1.get("outcomes", []):
            desc = (out.get("desc") or "").upper()
            oc_id = str(out.get("id"))
            try: ov = float(out.get("odds", 0))
            except: ov = 0.0
            if desc in ["HOME", "1"] and 1.12 <= ov <= 1.35 and oh <= 1.35:
                candidates.append({
                    "fixture": f"{h} vs {a}",
                    "comp": f["comp"],
                    "country": f["country"],
                    "market_name": "1X2",
                    "selection_name": f"{h} Win",
                    "odds": ov,
                    "eventId": f["eventId"],
                    "marketId": "1",
                    "outcomeId": oc_id,
                    "specifier": None,
                    "safety": "ELITE"
                })
            elif desc in ["AWAY", "2"] and 1.12 <= ov <= 1.35 and oa <= 1.35:
                candidates.append({
                    "fixture": f"{h} vs {a}",
                    "comp": f["comp"],
                    "country": f["country"],
                    "market_name": "1X2",
                    "selection_name": f"{a} Win",
                    "odds": ov,
                    "eventId": f["eventId"],
                    "marketId": "1",
                    "outcomeId": oc_id,
                    "specifier": None,
                    "safety": "ELITE"
                })

print(f"Total qualified cushioned candidates: {len(candidates)}")

def book_ticket_on_sportybet(picks, name):
    selections = []
    tot_odds = 1.0
    for p in picks:
        tot_odds *= p["odds"]
        item = {
            "eventId": p["eventId"],
            "marketId": p["marketId"],
            "outcomeId": p["outcomeId"],
        }
        if p.get("specifier"):
            item["specifier"] = p["specifier"]
        selections.append(item)
    
    url = "https://www.sportybet.com/api/ng/orders/share"
    with httpx.Client(timeout=10.0, headers=headers) as client:
        r = client.post(url, json={"selections": selections})
        if r.status_code == 200:
            data = r.json()
            if data.get("bizCode") == 10000:
                share_code = data.get("data", {}).get("shareCode")
                return {
                    "name": name,
                    "code": share_code,
                    "odds": round(tot_odds, 2),
                    "legs": len(picks),
                    "picks": picks,
                    "status": "SUCCESS"
                }
            else:
                return {"name": name, "status": "FAILED", "msg": data.get("message"), "picks": picks, "odds": round(tot_odds, 2)}
        return {"name": name, "status": "HTTP_ERROR", "picks": picks, "odds": round(tot_odds, 2)}

# Build Ticket 1 (~16.5x Odds)
t1_picks = []
tot1 = 1.0
used_events1 = set()
for c in candidates:
    if c["eventId"] not in used_events1:
        t1_picks.append(c)
        used_events1.add(c["eventId"])
        tot1 *= c["odds"]
        if tot1 >= 16.0 and len(t1_picks) >= 8:
            break

res1 = book_ticket_on_sportybet(t1_picks, "Ticket 1 (15 - 20 Odds Acca A)")

# Build Ticket 2 (~17.5x Odds)
t2_picks = []
tot2 = 1.0
used_events2 = set()
for c in reversed(candidates):
    if c["eventId"] not in used_events2:
        t2_picks.append(c)
        used_events2.add(c["eventId"])
        tot2 *= c["odds"]
        if tot2 >= 16.5 and len(t2_picks) >= 8:
            break

res2 = book_ticket_on_sportybet(t2_picks, "Ticket 2 (15 - 20 Odds Acca B)")

# Build Ticket 3 (20+ Games / 20+ Odds)
t3_picks = []
tot3 = 1.0
used_events3 = set()
for c in candidates:
    if c["eventId"] not in used_events3:
        t3_picks.append(c)
        used_events3.add(c["eventId"])
        tot3 *= c["odds"]
        if len(t3_picks) >= 20:
            break

res3 = book_ticket_on_sportybet(t3_picks, "Ticket 3 (20 Games Long Ticket - 20+ Odds)")

print("\n" + "="*60)
print("             SPORTYBET LIVE BOOKING CODES")
print("="*60)
for res in [res1, res2, res3]:
    print(f"\n>>> {res['name']} <<<")
    print(f"Status: {res['status']}")
    print(f"BOOKING CODE: {res.get('code')}")
    print(f"Total Odds: {res.get('odds')}x | Legs: {len(res.get('picks', []))}")
    print(f"Direct Link: https://www.sportybet.com/ng/?shareCode={res.get('code')}")
    print("Selections:")
    for idx, p in enumerate(res.get("picks", []), 1):
        print(f"  {idx}. {p['fixture']} ({p['comp']}) -> {p['selection_name']} @ {p['odds']}")
