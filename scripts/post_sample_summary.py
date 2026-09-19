import requests

url = 'http://127.0.0.1:8000/api/route-plans/'
payload = {"start_location": "New York, NY", "finish_location": "Boston, MA"}

try:
    r = requests.post(url, json=payload, timeout=30)
except Exception as e:
    print('ERROR:', e)
    raise SystemExit(2)

print('Status:', r.status_code)
try:
    j = r.json()
    print('Top-level keys:', list(j.keys()))
    if 'id' in j:
        print('id:', j['id'])
    if 'map_url' in j:
        print('map_url:', j['map_url'])
except Exception:
    print('Response text:', r.text)
