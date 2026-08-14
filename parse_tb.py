import re
html = open('output3.html', encoding='utf-8').read()
m = re.search(r'(?<=<textarea id="traceback_area" cols="140" rows="25">)(.*?)(?=</textarea>)', html, re.DOTALL)
if m:
    print(m.group(1).strip())
else:
    print("No textarea found")
