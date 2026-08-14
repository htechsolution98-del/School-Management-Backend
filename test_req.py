import requests
import re
resp = requests.post("http://localhost:8000/api/api-login/", json={"mobile": "SCH-3251", "password": "123456"})
html = resp.text
text = re.sub(r'<[^>]+>', '', html)
with open('traceback.txt', 'w', encoding='utf-8') as f:
    f.write(text)
