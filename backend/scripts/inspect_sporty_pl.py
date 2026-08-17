import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

r = httpx.get("https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&tournamentId=sr:tournament:17&pageSize=10", headers=headers).json()
events = r.get("data", [])
for ev in events[:5]:
    home = ev.get("homeTeamName")
    away = ev.get("awayTeamName")
    markets = ev.get("markets", {})
    if isinstance(markets, dict):
        markets = list(markets.values())
    print(f"\n==========================================")
    print(f"Match: {home} vs {away}")
    for m in markets:
        m_id = m.get("id")
        desc = m.get("desc") or m.get("name")
        spec = m.get("specifier")
        outcomes = [(o.get("id"), o.get("desc"), o.get("odds")) for o in (m.get("outcomes") or [])]
        if any(k in desc.lower() for k in ["handicap", "or over", "or under", "either", "chance", "or"]):
            print(f"  Mkt ID: {m_id:4} | Desc: {desc:35} | Spec: {str(spec):15} | Outcomes: {outcomes}")
