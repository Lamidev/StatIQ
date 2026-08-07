import urllib.request
import json
import ssl

def fetch_sportybet_code(code, country="ng"):
    url = f"https://www.sportybet.com/api/{country}/orders/share/{code}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.sportybet.com/",
            "Origin": "https://www.sportybet.com"
        }
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("Testing LYTXQL...")
    res = fetch_sportybet_code("LYTXQL")
    print(json.dumps(res, indent=2)[:3000])
