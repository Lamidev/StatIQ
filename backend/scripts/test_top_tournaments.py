import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.sportybet.com",
    "Referer": "https://www.sportybet.com/ng/"
}

with httpx.Client(timeout=10.0, headers=headers) as client:
    # 1. Test queryEventsBySportTree
    url = "https://www.sportybet.com/api/ng/factsCenter/queryEventsBySportTree?sportId=sr:sport:1&pageSize=100"
    r = client.get(url)
    print(f"queryEventsBySportTree status: {r.status_code}")
    if r.status_code == 200:
        data = r.json().get("data", {})
        print("Data keys:", list(data.keys()) if isinstance(data, dict) else len(data))

    # 2. Test tournament endpoints for EPL (sr:tournament:17), LaLiga (sr:tournament:8), Bundesliga (sr:tournament:35), Serie A (sr:tournament:23), Ligue 1 (sr:tournament:34)
    tournaments = [
        ("Premier League", "sr:tournament:17"),
        ("La Liga", "sr:tournament:8"),
        ("Bundesliga", "sr:tournament:35"),
        ("Serie A", "sr:tournament:23"),
        ("Ligue 1", "sr:tournament:34"),
        ("Championship", "sr:tournament:18"),
        ("Eredivisie", "sr:tournament:37"),
        ("Liga Portugal", "sr:tournament:238"),
        ("Super Lig", "sr:tournament:52")
    ]

    for name, t_id in tournaments:
        u = f"https://www.sportybet.com/api/ng/factsCenter/tournamentEvents?tournamentId={t_id}&pageSize=50"
        res = client.get(u)
        if res.status_code == 200:
            events = res.json().get("data", [])
            print(f"[{name}] {t_id} -> {len(events)} events found")
            for ev in events[:2]:
                print(f"   -> {ev.get('homeTeamName')} vs {ev.get('awayTeamName')} (ID: {ev.get('eventId')})")
        else:
            print(f"[{name}] {t_id} failed: {res.status_code}")
