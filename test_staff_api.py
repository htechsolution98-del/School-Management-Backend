import requests
import json
import re

r = requests.post('http://localhost:8000/api/api-login/', json={'mobile': 'SCH-3251', 'password': '123456'})
print(f"Login status: {r.status_code}")

cookies = r.cookies
headers = {'X-CSRFToken': cookies.get('csrftoken', '')}
if 'access_token' in cookies:
    headers['Authorization'] = 'Bearer ' + cookies['access_token']

r2 = requests.post('http://localhost:8000/api/StaffView/', cookies=cookies, headers=headers, json={
    'name': 'test',
    'category': 1,
    'email': 'test@test.com',
    'mobile': '1234567890'
})

print(f"Staff status: {r2.status_code}")
if r2.status_code == 500:
    title = re.search(r'<title>(.*?)</title>', r2.text, re.DOTALL)
    if title:
        print("Error Title:", title.group(1).strip())
    exc = re.search(r'<table class="meta">.*?<th>Exception Value:</th>\s*<td><pre>(.*?)</pre></td>', r2.text, re.DOTALL)
    if exc:
        print("Exception Value:", exc.group(1).strip())
    else:
        print("Exception value not found, writing to staff_err.html")
        with open('staff_err.html', 'w') as f:
            f.write(r2.text)
