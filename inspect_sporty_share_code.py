import httpx
import json

def test_share_code(code):
    regions = ["ng", "gh", "ke", "ug", "tz", "zm"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.sportybet.com"
    }

    print(f"=== TESTING SHARE CODE: {code} ===")
    for reg in regions:
        url = f"https://www.sportybet.com/api/{reg}/orders/share/{code}"
        try:
            r = httpx.get(url, headers=headers, timeout=5.0)
            data = r.json()
            biz = data.get("bizCode")
            print(f"Region '{reg}': status={r.status_code}, bizCode={biz}")
            if biz == 10000:
                print(f"  SUCCESS on region '{reg}'!")
                outcomes = data.get("data", {}).get("outcomes", [])
                for o in outcomes:
                    print(f"    - Match: {o.get('homeTeamName')} vs {o.get('awayTeamName')}")
        except Exception as e:
            print(f"  Error on region '{reg}': {e}")

if __name__ == "__main__":
    test_share_code("96D4B7")
    test_share_code("BB8Q14")
