import json
import sys
import requests

url = 'http://127.0.0.1:8000/api/route-plans/'
payload = {"start_location": "New York, NY", "finish_location": "Boston, MA"}

try:
    r = requests.post(url, json=payload, timeout=30)
except Exception as e:
    print('ERROR:', e)
    sys.exit(2)

print('Status:', r.status_code)
try:
    print(json.dumps(r.json(), indent=2))
except Exception:
    print(r.text)
