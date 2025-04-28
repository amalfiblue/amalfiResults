import requests
import json

try:
    print('Testing /candidates endpoint:')
    response = requests.get('http://localhost:8000/candidates')
    candidates = response.json()['candidates']
    print(f"Number of candidates returned: {len(candidates)}")
    print(f"First few candidates: {json.dumps(candidates[:2], indent=2)}")
    
    all_warringah = all(c['electorate'] == 'WARRINGAH' for c in candidates)
    print(f"All candidates are for Warringah: {all_warringah}")
except Exception as e:
    print(f"Error: {e}")
