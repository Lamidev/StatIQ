import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.sportybet.com",
    "Referer": "https://www.sportybet.com/ng/"
}

with httpx.Client(timeout=8.0, headers=headers) as client:
    # Test 1: factsCenter/wapUpcomingEvents
    url1 = "https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&pageSize=30"
    r1 = client.get(url1)
    print(f"URL 1 Status: {r1.status_code}")
    if r1.status_code == 200:
        j1 = r1.json()
        print(f"BizCode: {j1.get('bizCode')}, message: {j1.get('message')}")
        data = j1.get("data", [])
        if isinstance(data, dict):
            events = data.get("events", [])
            print(f"Found {len(events)} events in dict")
            if events:
                print("First event:", events[0].get("eventId"), events[0].get("homeTeamName"), "vs", events[0].get("awayTeamName"))
        elif isinstance(data, list):
            print(f"Found {len(data)} events in list")
            if data:
                print("First event:", data[0].get("eventId"), data[0].get("homeTeamName"), "vs", data[0].get("awayTeamName"))
        else:
            print("Unknown data type:", type(data))
    else:
        print("Response text:", r1.text[:200])

    # Test 2: SportyBet popular events / basic schedule
    url2 = "https://www.sportybet.com/api/ng/factsCenter/popularEvents?sportId=sr:sport:1"
    r2 = client.get(url2)
    print(f"\nURL 2 Status: {r2.status_code}")
    if r2.status_code == 200:
        j2 = r2.json()
        print(f"BizCode: {j2.get('bizCode')}, data len: {len(j2.get('data', [])) if isinstance(j2.get('data'), list) else 'dict'}")
