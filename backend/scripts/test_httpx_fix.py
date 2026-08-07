import httpx
import urllib.request
import json
import ssl
import time

url = "https://www.sportybet.com/api/ng/orders/share/LYTXQL"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.sportybet.com/ng/',
    'Origin': 'https://www.sportybet.com'
}

print("--- Method 1: httpx with follow_redirects ---")
t0 = time.time()
try:
    with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True, verify=False) as client:
        r = client.get(url)
        print(f"Status: {r.status_code}, Time: {round(time.time()-t0, 2)}s")
        print(f"Outcomes: {len(r.json().get('data', {}).get('outcomes', []))}")
except Exception as e:
        print(f"HTTPX Error: {e}")

print("\n--- Method 2: urllib.request ---")
t0 = time.time()
try:
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=8.0) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"Status: {resp.status}, Time: {round(time.time()-t0, 2)}s")
        print(f"Outcomes: {len(data.get('data', {}).get('outcomes', []))}")
except Exception as e:
    print(f"Urllib Error: {e}")
