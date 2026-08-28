import requests
import sys

query = '[out:json];area[name="Nairobi"]->.a;node(area.a)[amenity=restaurant];out body 3;'
url = 'https://overpass-api.de/api/interpreter'

print(f"Testing Overpass API at {url}")
print(f"Query: {query}")

try:
    r = requests.post(url, data={'data': query}, timeout=60)
    print(f"Status: {r.status_code}")
    print(f"Headers: {dict(r.headers)}")
    print(f"Response length: {len(r.text)}")
    if r.status_code == 200:
        data = r.json()
        print(f"Elements: {len(data.get('elements', []))}")
        for e in data.get('elements', [])[:3]:
            tags = e.get('tags', {})
            print(f"  - {tags.get('name', '?')}")
    else:
        print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

# Also try simple GET
print("\n--- Trying GET ---")
try:
    r = requests.get(url, params={'data': '[out:json];node(1);out;'}, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")