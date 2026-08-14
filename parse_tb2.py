import re
html = open('output3.html', encoding='utf-8').read()
m = re.search(r'Exception Value:.*?<pre>(.*?)</pre>', html, re.DOTALL)
if m:
    print('Exception:', m.group(1).strip())
# try to extract the traceback frames
frames = re.findall(r'<span class="file">(.*?)</span>.*?<span class="line">(.*?)</span>.*?<code>(.*?)</code>', html, re.DOTALL)
for f in frames:
    print(f[0].strip(), f[1].strip())
    print(f[2].strip().replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>'))
    print('---')
