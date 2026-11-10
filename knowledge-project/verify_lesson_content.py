"""Execute teaching examples in isolation and check compatibility with existing quizzes."""
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

import learning_core as core
from portal_ui import lesson_markdown

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {
    'mat_02':'повторить основы\nвыполнить практику\nперейти дальше\n',
    'mat_03':'А\n12.0\n',
    'mat_04':'[5, 7, 11]\n1.0\n',
    'python_01':'Анна 80.0\nпорог достигнут\n',
    'python_02':'73.33\nNone\n',
    'algorithms_01':'3\n-1\n',
    'algorithms_02':'изменить заголовок\nАнна\nВеб-технологии\n',
    'statistics_01':'6\n3\n[3]\n2.67\n',
    'statistics_02':'4\n0.25\n',
    'software_02':'',
    'os_02':'report.json\n80\n',
}
checks = []


def record(name, passed, details=None):
    checks.append({'name':name,'passed':bool(passed),'details':details})
    if not passed:
        raise AssertionError(name)


materials = core.all_materials()
record('All 22 lessons are available through the runtime catalog',len(materials)==22)
record('The library covers ten disciplines',len({item['discipline_id'] for item in materials})==10)
for material in materials:
    mid = material['id']
    original = (ROOT/'learning-content'/f'{mid}.md').read_text(encoding='utf-8').strip()
    record(f'{mid}: published text matches the editable original',material['content']==original)
    exported = lesson_markdown(material).decode('utf-8')
    record(f'{mid}: downloaded notes contain assignment, solution and links',all(value in exported for value in [material['assignment'],material['self_check'],material['sources'][0]['url']]))
    for code in re.findall(r'```python\n(.*?)```',original,re.S):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable,'-c',code],cwd=directory,env={**os.environ,'PYTHONIOENCODING':'utf-8'},capture_output=True,text=True,timeout=10)
        record(f'{mid}: executable Python example has the documented output',result.returncode==0 and result.stdout==EXPECTED[mid],{'returncode':result.returncode,'stdout':result.stdout})

sql01 = (ROOT/'learning-content/databases_01.md').read_text(encoding='utf-8')
with sqlite3.connect(':memory:') as db:
    db.executescript(re.search(r'```sql\n(.*?)```',sql01,re.S).group(1))
    record('SQL schema and selection example return the documented student',db.execute('SELECT full_name,group_id FROM students').fetchall()==[('Анна Белова',1)])
    try:
        db.execute("INSERT INTO students VALUES (102,'Тест',999)")
        rejected = False
    except sqlite3.IntegrityError:
        rejected = True
    record('SQL foreign key demonstration rejects an unknown group',rejected)
with sqlite3.connect(':memory:') as db:
    db.executescript("CREATE TABLE groups(id INTEGER PRIMARY KEY,name TEXT); CREATE TABLE students(id INTEGER PRIMARY KEY,full_name TEXT,group_id INTEGER); INSERT INTO groups VALUES(1,'ПИ-21'),(2,'ИВТ-21'),(3,'Пустая'); INSERT INTO students VALUES(1,'Анна',1),(2,'Борис',1),(3,'Вера',2);")
    queries = re.findall(r'```sql\n(.*?)```',(ROOT/'learning-content/databases_02.md').read_text(encoding='utf-8'),re.S)
    record('SQL grouping keeps a zero-student group',db.execute(queries[0]).fetchall()==[('ПИ-21',2),('ИВТ-21',1),('Пустая',0)])
    record('SQL filter returns the documented students',db.execute(queries[1]).fetchall()==[('Анна',),('Борис',)])

fingerprints = json.loads((ROOT/'learning-content/quiz_fingerprints.json').read_text(encoding='utf-8'))
for name,current in [('quizzes.json',ROOT/'knowledge-project/quizzes.json'),('additional_quizzes.json',ROOT/'datasets/academy_demo/additional_quizzes.json')]:
    after = json.loads(current.read_text(encoding='utf-8'))
    hashes = {mid:hashlib.sha256(json.dumps(item['questions'],ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest() for mid,item in after.items()}
    record(f'{name}: all question IDs, choices, keys and explanations match the baseline',hashes==fingerprints[name])

report = {'verified_at':datetime.now(timezone.utc).isoformat(),'lessons':len(materials),'body_words':sum(len(item['content'].split()) for item in materials),'checks':checks,'passed':sum(item['passed'] for item in checks),'total':len(checks)}
(ROOT/'knowledge-project/project_results/lesson_content_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ['lessons','body_words','passed','total']}))
