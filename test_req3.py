import urllib.request
import json
req = urllib.request.Request(
    'http://localhost:8000/api/SchoolView/',
    data=json.dumps({'name': 'Test School', 'email': 'test@example.com', 'phone': '1234567890', 'login_id': 1, 'feature_ids': [1]}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
try:
    urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    with open('output3.html', 'w', encoding='utf-8') as f:
        f.write(e.read().decode('utf-8'))
