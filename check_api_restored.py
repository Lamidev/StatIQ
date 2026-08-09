import httpx

def check_api():
    r = httpx.get("http://127.0.0.1:8000/api/v1/ticket-tracker/list")
    print(f"Status: {r.status_code}")
    data = r.json()
    tickets = data.get("tickets", [])
    print(f"Total Tracked Tickets in API: {len(tickets)}")
    for t in tickets:
        print(f"  - [{t.get('status'):7s}] ID: {t.get('id')} | Mode: {t.get('mode')} | Code: {t.get('code')} | Odds: {t.get('total_odds')}x")

if __name__ == "__main__":
    check_api()
