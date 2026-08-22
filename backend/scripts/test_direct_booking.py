import httpx
import json
import asyncio

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.sportybet.com",
    "Referer": "https://www.sportybet.com/ng/"
}

# 1. Fetch upcoming events with markets
url = "https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&pageSize=100"
with httpx.Client(timeout=10.0, headers=headers) as client:
    r = client.get(url)
    data = r.json().get("data", [])
    print(f"Fetched {len(data)} events")
    
    # Check first 3 events
    selections = []
    for ev in data[:10]:
        ev_id = ev.get("eventId")
        h = ev.get("homeTeamName")
        a = ev.get("awayTeamName")
        markets = ev.get("markets", [])
        m1 = next((m for m in markets if str(m.get("id")) in ["1", "10", "18"]), None)
        if m1:
            m_id = str(m1.get("id"))
            spec = m1.get("specifier")
            outcomes = m1.get("outcomes", [])
            if outcomes:
                oc = outcomes[0]
                oc_id = str(oc.get("id"))
                odds = float(oc.get("odds", 1.25))
                selections.append({
                    "eventId": ev_id,
                    "marketId": m_id,
                    "outcomeId": oc_id,
                    "specifier": spec
                })
                print(f"Added pick: {h} vs {a} | Market {m_id} Outcome {oc_id} @ {odds}")

    # Test booking creation on SportyBet
    if selections:
        book_url = "https://www.sportybet.com/api/ng/orders/share"
        payload = {"selections": selections[:5]}
        r_book = client.post(book_url, json=payload)
        print("Booking response status:", r_book.status_code)
        print("Booking response body:", r_book.text)
