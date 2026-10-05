import os, sys, re, inspect, importlib
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms.settings')

import django
django.setup()

from django.apps import apps
from rest_framework import serializers

created_models = set(
    m.__name__ for m in apps.get_models()
    if m._meta.app_label == 'sms_app' and any(f.name == 'created_at' for f in m._meta.fields)
)

files_to_process = [
    'sms_app.academic_serializers',
    'sms_app.staff_serializers',
    'sms_app.finance_serializers',
    'sms_app.inventory_serializers',
    'sms_app.school_serializers',
    'sms_app.student_serializers',
    'sms_app.serializer',
    'sms_app.harsh_serializer',
    'sms_app.auth_serializers',
]

for fname in files_to_process:
    try:
        mod = importlib.import_module(fname)
    except Exception as e:
        print('ERR', fname, e)
        continue
    # get file path
    modfile = mod.__file__
    with open(modfile, 'r', encoding='utf-8') as f:
        content = f.read()

    changed = False
    # find all ModelSerializer classes in this module
    # pattern: class ClassName(serializers.ModelSerializer):
    # we need to handle class definitions - simple approach: for each class that has Meta with model in created_models and != CustomUser
    # iterate classes
    for name in dir(mod):
        obj = getattr(mod, name)
        if inspect.isclass(obj) and issubclass(obj, serializers.ModelSerializer) and obj != serializers.ModelSerializer:
            try:
                meta = obj.Meta
                m = meta.model
            except Exception:
                continue
            mname = m.__name__
            if mname not in created_models or mname == 'CustomUser':
                continue
            # find the class definition in content
            # look for 'class ' + name + '(serializers.ModelSerializer)'
            pattern = r'class\s+' + re.escape(name) + r'\s*\(.*?ModelSerializer.*?\):'
            # find all matches? maybe same name not possible; find the class block
            # easier: search for pattern followed by Meta
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                continue
            start = m.start()
            # find the end of this class (next class at same indent level or end of file)
            # rough: look for next ^class at col 0
            rest = content[start+1:]
            # find next top-level class
            end_match = re.search(r'^\n?class\s+\w+', rest, re.M)
            if end_match:
                class_end = start + 1 + end_match.start()
            else:
                class_end = len(content)
            class_block = content[start:class_end]
            # now look inside class_block for Meta
            meta_match = re.search(r'class\s+Meta\s*:', class_block)
            if not meta_match:
                continue
            # find meta block end - next class or next top-level def/class inside? or just next non-indented def/class? simpler: look for next line that starts at same indent as Meta? or just find next 'class ' or 'def ' at column 0 in the rest of class_block after meta
            meta_start = meta_match.start()
            meta_rest = class_block[meta_start:]
            # find end of meta - typically next top-level thing in class? or next unindented class/def after meta? better look for next line that is not indented (starts at col 0) and is class/def - but inside class, methods are indented; Meta is inside class
            # easier: in class_block, find end of Meta by looking for next line that starts at col 0 after meta_start? no, everything inside class is indented. Better to look for next '    def ' or '    class ' (4 spaces) at same level as methods, or just take until end of class_block
            # or look for pattern of next method def at same indentation level as typical methods? or just modify within class_block
            # find fields/exclude in meta
            # check if has __all__
            if re.search(r'fields\s*=\s*"__all__"', class_block, re.M):
                # no change
                continue
            # check exclude
            excl_m = re.search(r'exclude\s*=\s*\[([^\]]+)\]', class_block, re.M)
            if excl_m:
                excl_content = excl_m.group(1)
                # if created_at not in exclude, no change
                if 'created_at' not in excl_content:
                    continue
                # if it is excluded, remove it
                # reconstruct exclude list
                items = [x.strip().strip("'\"") for x in excl_content.split(',')]
                items = [x for x in items if x and x != 'created_at']
                new_excl = '[' + ', '.join(repr(i) for i in items) + ']'
                new_block = class_block.replace(excl_m.group(0), 'exclude = ' + new_excl)
                content = content[:start] + new_block + content[class_end:]
                changed = True
                continue
            # has explicit fields list
            fields_m = re.search(r'fields\s*=\s*\[([^\]]+)\]', class_block, re.M)
            if fields_m:
                fields_content = fields_m.group(1)
                # check if created_at already there
                # simple check
                if "'created_at'" in fields_content or '"created_at"' in fields_content:
                    continue
                # add created_at first
                new_fields = 'fields = ["created_at", ' + fields_content.lstrip() + ']'
                new_block = class_block.replace(fields_m.group(0), new_fields)
                content = content[:start] + new_block + content[class_end:]
                changed = True
                continue
            # also tuple form? fields = ("id", ...)
            fields_m2 = re.search(r'fields\s*=\s*\(([^\)]+)\)', class_block, re.M)
            if fields_m2:
                fields_content = fields_m2.group(1)
                if "'created_at'" in fields_content or '"created_at"' in fields_content:
                    continue
                # add to tuple - put first
                new_fields = 'fields = ("created_at", ' + fields_content.lstrip() + ')'
                new_block = class_block.replace(fields_m2.group(0), new_fields)
                content = content[:start] + new_block + content[class_end:]
                changed = True
                continue
            # maybe just add if it's missing and we have fields as list/tuple not caught? try broader
    if changed:
        with open(modfile, 'w', encoding='utf-8') as f:
            f.write(content)
        print('MODIFIED', fname)

print('done')
