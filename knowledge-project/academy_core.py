"""Synthetic academic roster, enrollment, protected administration and seed import."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

import learning_core as learning

DATA = Path(__file__).resolve().parent.parent / 'datasets' / 'academy_demo'
ACCESS_FILE = Path(__file__).resolve().parent.parent / '.runtime' / 'admin_access.txt'
router = APIRouter()
_lock = threading.RLock()
_login_failures = []


def dataset():
    return json.loads((DATA / 'academy.json').read_text(encoding='utf-8'))


def connect():
    connection = sqlite3.connect(learning.PROGRESS_DB, timeout=20)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_academy():
    """Import once, atomically; an existing student's history is never reset."""
    with _lock:
        learning.init_progress_db()
        with connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS academy_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS academic_groups (id TEXT PRIMARY KEY, name TEXT NOT NULL, program TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS disciplines (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, teacher TEXT NOT NULL, semester INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS group_disciplines (group_id TEXT NOT NULL, discipline_id TEXT NOT NULL, PRIMARY KEY(group_id, discipline_id));
                CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, full_name TEXT NOT NULL, group_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS admin_sessions (token_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL);
            ''')
            seed = dataset()
            if db.execute('SELECT 1 FROM academy_meta WHERE key=?', (seed['version'],)).fetchone():
                return
            # Serialize seed checks across API processes as well as threads.
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM academy_meta WHERE key=?', (seed['version'],)).fetchone():
                return
            for group in seed['groups']:
                db.execute('INSERT OR IGNORE INTO academic_groups VALUES (?,?,?)', (group['id'], group['name'], group['program']))
                db.executemany('INSERT OR IGNORE INTO group_disciplines VALUES (?,?)', [(group['id'], course) for course in group['discipline_ids']])
            for course in seed['disciplines']:
                db.execute('INSERT OR IGNORE INTO disciplines VALUES (?,?,?,?,?)', tuple(course[key] for key in ['id', 'name', 'description', 'teacher', 'semester']))
            imported = set()
            for student in seed['students']:
                created = db.execute('INSERT OR IGNORE INTO students (id,full_name,group_id,active,source) VALUES (?,?,?,?,?)',
                    (student['id'], student['full_name'], student['group_id'], int(student['active']), 'synthetic')).rowcount
                if created:
                    imported.add(student['id'])
            quiz_data = learning.quizzes()
            for activity in seed['activities']:
                if activity['student_id'] not in imported:
                    continue
                sid, mid, stamp = activity['student_id'], activity['material_id'], activity['created_at']
                db.execute('INSERT OR IGNORE INTO completions (student_id,item_type,item_id,completed_at) VALUES (?,?,?,?)', (sid, 'material', mid, stamp))
                answers = activity['answers']
                questions = quiz_data[mid]['questions']
                correct = sum(answer == question['correct'] for answer, question in zip(answers, questions))
                score = round(correct / len(questions) * 100)
                db.execute('INSERT INTO quiz_attempts (student_id,material_id,answers,correct_count,question_count,score,created_at) VALUES (?,?,?,?,?,?,?)',
                    (sid, mid, json.dumps(answers), correct, len(questions), score, stamp))
                if score >= 80:
                    db.execute('INSERT OR IGNORE INTO completions (student_id,item_type,item_id,completed_at) VALUES (?,?,?,?)', (sid, 'task', f'quiz_{mid}', stamp))
            db.execute('INSERT INTO academy_meta VALUES (?,?)', (seed['version'], 'imported'))


def check_access(student_id, discipline_id):
    ensure_academy()
    with connect() as db:
        if not db.execute('SELECT 1 FROM disciplines WHERE id=?', (discipline_id,)).fetchone():
            raise HTTPException(404, 'Дисциплина не найдена.')
        student = db.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
        if student:
            if not student['active']:
                raise HTTPException(403, 'Профиль архивирован. Обратитесь к администратору.')
            if not db.execute('SELECT 1 FROM group_disciplines WHERE group_id=? AND discipline_id=?', (student['group_id'], discipline_id)).fetchone():
                raise HTTPException(403, 'Дисциплина не входит в учебный план группы.')


@router.get('/academy/catalog')
def catalog():
    ensure_academy()
    with connect() as db:
        groups = [dict(row) for row in db.execute('SELECT * FROM academic_groups ORDER BY name')]
        for group in groups:
            group['discipline_ids'] = [row[0] for row in db.execute('SELECT discipline_id FROM group_disciplines WHERE group_id=? ORDER BY discipline_id', (group['id'],))]
        courses = [dict(row) for row in db.execute('SELECT * FROM disciplines ORDER BY name')]
        # Only fictional dataset identities are available in the public demo chooser.
        students = [dict(row) for row in db.execute("SELECT id,full_name,group_id FROM students WHERE active=1 AND source='synthetic' ORDER BY full_name")]
    counts = {}
    for material in learning.all_materials():
        key = material['discipline_id']
        counts[key] = counts.get(key, 0) + 1
    for course in courses:
        course['topic_count'] = counts.get(course['id'], 0)
    return {'groups': groups, 'disciplines': courses, 'demo_students': students, 'synthetic': True, 'dataset_version': dataset()['version']}


@router.get('/academy/profile/{student_id}')
def profile(student_id: str):
    student_id = learning.valid_student(student_id)
    ensure_academy()
    with connect() as db:
        row = db.execute('SELECT * FROM students WHERE id=?', (student_id,)).fetchone()
    data = catalog()
    if not row:
        return {'id': student_id, 'full_name': student_id, 'group_name': 'Свободный демопрофиль', 'source': 'anonymous', 'disciplines': data['disciplines']}
    student = dict(row)
    if not student['active']:
        raise HTTPException(403, 'Профиль архивирован. Обратитесь к администратору.')
    group = next(group for group in data['groups'] if group['id'] == student['group_id'])
    return {**student, 'group_name': group['name'], 'disciplines': [course for course in data['disciplines'] if course['id'] in group['discipline_ids']]}


def admin_password():
    configured = os.environ.get('LEARNING_ADMIN_PASSWORD')
    if configured:
        return configured
    with _lock:
        ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not ACCESS_FILE.exists():
            password = secrets.token_urlsafe(18)
            ACCESS_FILE.write_text('Локальная учебная демонстрация\nАдрес: http://localhost:8501/?view=admin\nЛогин: admin\nПароль: ' + password + '\nНе включайте этот файл в архив проекта.\n', encoding='utf-8')
            try:
                ACCESS_FILE.chmod(0o600)
            except OSError:
                pass
        return ACCESS_FILE.read_text(encoding='utf-8').split('Пароль: ', 1)[1].splitlines()[0]


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@router.post('/admin/login')
def login(request: Login):
    ensure_academy()
    with _lock:
        now = time.time()
        _login_failures[:] = [stamp for stamp in _login_failures if now - stamp < 60]
        if len(_login_failures) >= 10:
            raise HTTPException(429, 'Слишком много попыток. Повторите вход через минуту.')
        if not (hmac.compare_digest(request.username.encode(), b'admin') and hmac.compare_digest(request.password.encode(), admin_password().encode())):
            _login_failures.append(now)
            raise HTTPException(401, 'Неверный логин или пароль.')
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('DELETE FROM admin_sessions WHERE expires_at < ?', (now,))
        db.execute('INSERT INTO admin_sessions VALUES (?,?)', (hashlib.sha256(token.encode()).hexdigest(), now + 8 * 3600))
    return {'token': token, 'expires_in': 8 * 3600}


def authorized(authorization: str | None = Header(default=None)):
    ensure_academy()
    token = authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connect() as db:
        row = db.execute('SELECT expires_at FROM admin_sessions WHERE token_hash=?', (digest,)).fetchone()
    if not token or not row or row['expires_at'] <= time.time():
        raise HTTPException(401, 'Для доступа к администрированию выполните вход.')
    return digest


@router.post('/admin/logout')
def logout(digest=Depends(authorized)):
    with connect() as db:
        db.execute('DELETE FROM admin_sessions WHERE token_hash=?', (digest,))
    return {'ok': True}


def roster():
    """Batch-read all student activity; include archived and manually created profiles."""
    with connect() as db:
        students = [dict(row) for row in db.execute('SELECT s.*,g.name AS group_name FROM students s JOIN academic_groups g ON s.group_id=g.id ORDER BY g.name,s.full_name')]
        attempts = [dict(row) for row in db.execute('SELECT id,student_id,material_id,score,created_at FROM quiz_attempts ORDER BY id')]
        completions = [dict(row) for row in db.execute('SELECT student_id,item_type,item_id FROM completions')]
        plans = {}
        for row in db.execute('SELECT * FROM group_disciplines'):
            plans.setdefault(row['group_id'], set()).add(row['discipline_id'])
    all_materials = learning.all_materials()
    for student in students:
        ids = {material['id'] for material in all_materials if material['discipline_id'] in plans[student['group_id']]}
        history = [attempt for attempt in attempts if attempt['student_id'] == student['id'] and attempt['material_id'] in ids]
        latest = {attempt['material_id']: attempt for attempt in history}
        mastered = {attempt['material_id'] for attempt in history if attempt['score'] >= 80}
        done = [item for item in completions if item['student_id'] == student['id']]
        student.update(total_topics=len(ids), mastered_topics=len(mastered), completion_percent=round(len(mastered) / max(len(ids), 1) * 100),
            attempts=len(history), total_points=sum(10 if item['item_type'] == 'material' else 20 for item in done),
            average_score=round(sum(item['score'] for item in latest.values()) / len(latest), 1) if latest else None,
            last_activity=max((attempt['created_at'] for attempt in history), default=None),
            support='Нужна поддержка' if any(item['score'] < 50 and key not in mastered for key,item in latest.items()) else 'Нужна практика' if any(item['score'] < 80 and key not in mastered for key,item in latest.items()) else 'Без затруднений' if history else 'Нет попыток')
    return students


@router.get('/admin/overview', dependencies=[Depends(authorized)])
def overview():
    data = catalog()
    students = roster()
    return {'students': students, 'groups': data['groups'], 'disciplines': data['disciplines'],
        'summary': {'students': len(students), 'active': sum(s['active'] for s in students), 'groups': len(data['groups']), 'disciplines': len(data['disciplines']), 'needs_support': sum(s['support']=='Нужна поддержка' and s['active'] for s in students)},
        'synthetic': True}


@router.get('/admin/students/{student_id}', dependencies=[Depends(authorized)])
def student_detail(student_id: str):
    student = next((item for item in roster() if item['id'] == student_id), None)
    if not student:
        raise HTTPException(404, 'Студент не найден.')
    data = catalog()
    group = next(item for item in data['groups'] if item['id'] == student['group_id'])
    # Read-only admin inspection is allowed for archived accounts too.
    courses = []
    for course in data['disciplines']:
        if course['id'] in group['discipline_ids']:
            progress = learning.progress_for(student_id, course['id'])
            path = learning.assemble_path(student_id, course['id'], progress)
            courses.append({**course, 'progress': progress, 'adaptive': path['adaptive']})
    return {'student': student, 'courses': courses}


class StudentWrite(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=3, max_length=120)
    group_id: str = Field(min_length=1, max_length=80)
    active: bool = True

    @field_validator('id', 'full_name', 'group_id')
    @classmethod
    def strip_text(cls, value):
        if not value.strip():
            raise ValueError('Заполните поле.')
        return value.strip()


def save_student(request, creating):
    learning.valid_student(request.id)
    if len(request.full_name) < 3:
        raise HTTPException(422, 'Укажите имя не короче трёх символов.')
    with connect() as db:
        if not db.execute('SELECT 1 FROM academic_groups WHERE id=?', (request.group_id,)).fetchone():
            raise HTTPException(422, 'Выберите существующую группу.')
        exists = db.execute('SELECT 1 FROM students WHERE id=?', (request.id,)).fetchone()
        if creating and exists:
            raise HTTPException(409, 'Такой идентификатор уже занят.')
        if not creating and not exists:
            raise HTTPException(404, 'Студент не найден.')
        if creating:
            db.execute('INSERT INTO students (id,full_name,group_id,active,source) VALUES (?,?,?,?,?)', (request.id,request.full_name,request.group_id,int(request.active),'manual'))
        else:
            db.execute('UPDATE students SET full_name=?,group_id=?,active=? WHERE id=?', (request.full_name,request.group_id,int(request.active),request.id))
    return {'ok': True, 'student_id': request.id}


@router.post('/admin/students', dependencies=[Depends(authorized)])
def create_student(request: StudentWrite):
    return save_student(request, True)


@router.put('/admin/students/{student_id}', dependencies=[Depends(authorized)])
def edit_student(student_id: str, request: StudentWrite):
    if student_id != request.id:
        raise HTTPException(422, 'Идентификатор существующего студента менять нельзя.')
    return save_student(request, False)
