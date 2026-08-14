import requests

r = requests.post('http://localhost:8000/api/api-login/', json={'mobile': 'SCH-3251', 'password': '123456'})
token = r.json()['access']

r2 = requests.post('http://localhost:8000/api/StaffView/', headers={'Authorization': 'Bearer ' + token}, json={'name': 'test', 'category': 1, 'email': 'test@test.com', 'mobile': '1234567890'})

print(r2.status_code)
with open('staff_err.html', 'w') as f:
    f.write(r2.text)
