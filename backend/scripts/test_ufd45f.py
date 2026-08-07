import httpx
import json

url = "https://www.sportybet.com/api/ng/orders/share/UFD45F"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sportybet.com/"
}

try:
    with httpx.Client(timeout=10.0, headers=headers) as client:
        resp = client.get(url)
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print(f"BizCode: {data.get('bizCode')}")
        print(f"Message: {data.get('message')}")
        order_data = data.get("data", {})
        outcomes = order_data.get("outcomes", [])
        print(f"Total Outcomes returned: {len(outcomes)}")
        if outcomes:
            print("First outcome keys:", list(outcomes[0].keys()))
            print("First outcome sample:", json.dumps(outcomes[0], indent=2))
        else:
            print("Full response data:", json.dumps(data, indent=2))
except Exception as e:
    print("Error:", e)
