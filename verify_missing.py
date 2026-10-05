import sys, os, inspect, importlib, re
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms.settings')
import django
django.setup()
from rest_framework import serializers
from django.apps import apps

created_models = set(m.__name__ for m in apps.get_models() if m._meta.app_label=='sms_app' and any(f.name=='created_at' for f in m._meta.fields))
files = ['sms_app.academic_serializers','sms_app.staff_serializers','sms_app.finance_serializers','sms_app.inventory_serializers','sms_app.school_serializers','sms_app.student_serializers','sms_app.serializer','sms_app.harsh_serializer','sms_app.auth_serializers']
missing = []
for fname in files:
    try:
        mod = importlib.import_module(fname)
    except Exception:
        continue
    modfile = mod.__file__
    with open(modfile, 'r', encoding='utf-8') as f:
        content = f.read()
    for name in dir(mod):
        obj = getattr(mod, name)
        if inspect.isclass(obj) and issubclass(obj, serializers.ModelSerializer) and obj != serializers.ModelSerializer:
            try:
                mname = obj.Meta.model.__name__
            except Exception:
                continue
            if mname not in created_models or mname == 'CustomUser':
                continue
            pattern = r'class\s+' + re.escape(name) + r'\s*\(.*?ModelSerializer.*?\):'
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                continue
            start = m.start()
            rest = content[start+1:]
            endm = re.search(r'^\n?class\s+\w+', rest, re.M)
            if endm:
                class_end = start+1+endm.start()
            else:
                class_end = len(content)
            class_block = content[start:class_end]
            has_created = False
            if re.search(r'fields\s*=\s*"__all__"', class_block, re.M):
                has_created = True
            else:
                excl_m = re.search(r'exclude\s*=\s*\[([^\]]+)\]', class_block, re.M)
                if excl_m:
                    excl_content = excl_m.group(1)
                    items = [x.strip().strip("'\"") for x in re.split(r',', excl_content)]
                    if 'created_at' not in items:
                        has_created = True
                    else:
                        has_created = False
                else:
                    if re.search(r'fields\s*=\s*\[([^\]]*)["\']created_at["\']', class_block, re.M) or re.search(r'fields\s*=\s*\(([^\)]*)["\']created_at["\']', class_block, re.M):
                        has_created = True
            if not has_created:
                missing.append((fname, name, mname))
if missing:
    for x in missing[:30]:
        print(x[0] + ':' + x[1] + ':' + x[2])
    print('TOTAL', len(missing))
else:
    print('ALL_OK')
