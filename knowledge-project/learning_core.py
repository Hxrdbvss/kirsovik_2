"""Local learning flow: content, assessment, recommendations and progress."""
import csv
import json
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictInt, field_validator

ROOT = Path(__file__).resolve().parent
PROGRESS_DB = Path(os.environ.get('LEARNING_PROGRESS_DB', ROOT / 'learning_progress.db'))
router = APIRouter()


def materials(discipline_id='machine_learning'):
    content = json.loads((ROOT / 'material_content.json').read_text(encoding='utf-8'))
    with (ROOT.parent / 'graph-db-lab' / 'learning_materials.csv').open(encoding='utf-8-sig', newline='') as stream:
        catalog = list(csv.DictReader(stream))
    original = [{**content[row['id']], **row, 'discipline_id': 'machine_learning'} for row in catalog]
    extra = json.loads((ROOT.parent / 'datasets/academy_demo/additional_materials.json').read_text(encoding='utf-8'))
    return [item for item in original + extra if item['discipline_id'] == discipline_id]


def all_materials():
    extra = json.loads((ROOT.parent / 'datasets/academy_demo/additional_materials.json').read_text(encoding='utf-8'))
    return materials() + extra


def quizzes():
    return {**json.loads((ROOT / 'quizzes.json').read_text(encoding='utf-8')),
            **json.loads((ROOT.parent / 'datasets/academy_demo/additional_quizzes.json').read_text(encoding='utf-8'))}


def find_material(material_id):
    for material in all_materials():
        if material['id'] == material_id:
            return material
    raise HTTPException(status_code=404, detail='Учебный материал не найден.')


def init_progress_db():
    with sqlite3.connect(PROGRESS_DB, timeout=10) as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                item_type TEXT NOT NULL CHECK (item_type IN ('material', 'task')),
                item_id TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (student_id, item_type, item_id)
            );
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                material_id TEXT NOT NULL,
                answers TEXT NOT NULL,
                correct_count INTEGER NOT NULL,
                question_count INTEGER NOT NULL,
                score INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS quiz_student ON quiz_attempts(student_id, material_id);
        ''')


def valid_student(value):
    value = value.strip()
    if not value or len(value) > 100 or not all(char.isalnum() or char in '._-' for char in value):
        raise HTTPException(status_code=422, detail='Используйте от 1 до 100 букв, цифр, точек, дефисов или подчёркиваний в идентификаторе.')
    return value


class CompleteRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    item_type: str
    item_id: str = Field(min_length=1, max_length=100)

    @field_validator('student_id', 'item_id')
    @classmethod
    def strip_text(cls, value):
        if not value.strip():
            raise ValueError('Поле не должно быть пустым.')
        return value.strip()


@router.post('/progress/complete')
def complete_item(request: CompleteRequest):
    request.student_id = valid_student(request.student_id)
    if request.item_type != 'material':
        raise HTTPException(status_code=422, detail='Задание засчитывается только после прохождения теста.')
    material = find_material(request.item_id)
    from academy_core import check_access
    check_access(request.student_id, material['discipline_id'])
    init_progress_db()
    with sqlite3.connect(PROGRESS_DB, timeout=10) as connection:
        cursor = connection.execute(
            'INSERT INTO completions (student_id, item_type, item_id) VALUES (?, ?, ?) ON CONFLICT DO NOTHING',
            (request.student_id, 'material', request.item_id),
        )
        created = cursor.rowcount == 1
    return {'created': created, 'message': 'Материал отмечен изученным. +10 баллов.' if created else 'Материал уже отмечен. Повторные баллы не начисляются.'}


def attempt_rows(student_id, include_answers=False):
    init_progress_db()
    with sqlite3.connect(PROGRESS_DB, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        columns = 'id, material_id, correct_count, question_count, score, created_at' + (', answers' if include_answers else '')
        rows = connection.execute(
            f'SELECT {columns} FROM quiz_attempts WHERE student_id = ? ORDER BY id',
            (student_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get('/progress/{student_id}')
def get_progress(student_id: str, discipline_id: str = 'machine_learning'):
    from academy_core import check_access
    check_access(student_id, discipline_id)
    return progress_for(student_id, discipline_id)


def progress_for(student_id, discipline_id='machine_learning'):
    student_id = valid_student(student_id)
    init_progress_db()
    with sqlite3.connect(PROGRESS_DB, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute('SELECT item_type, item_id, completed_at FROM completions WHERE student_id = ? ORDER BY id', (student_id,)).fetchall()
    all_actions = [dict(row) for row in rows]
    ids = {material['id'] for material in materials(discipline_id)}
    actions = [action for action in all_actions if action['item_id'] in ids or (action['item_type'] == 'task' and action['item_id'].removeprefix('quiz_') in ids)]
    read_count = sum(action['item_type'] == 'material' for action in actions)
    task_count = sum(action['item_type'] == 'task' for action in actions)
    points = sum(10 if action['item_type'] == 'material' else 20 for action in all_actions)
    attempts = [attempt for attempt in attempt_rows(student_id) if attempt['material_id'] in ids]
    mastered_ids = {attempt['material_id'] for attempt in attempts if attempt['score'] >= 80}
    achievements = []
    if read_count:
        achievements.append('Первый изученный материал')
    if mastered_ids:
        achievements.append('Первый пройденный тест')
    if any(attempt['score'] == 100 for attempt in attempts):
        achievements.append('Без ошибок')
    if ids and mastered_ids.issuperset(ids):
        achievements.append('Все темы освоены')
    return {
        'student_id': student_id, 'completed_materials': read_count, 'completed_tasks': task_count,
        'discipline_id': discipline_id, 'course_points': read_count * 10 + task_count * 20,
        'mastered_topics': len(mastered_ids), 'total_topics': len(ids), 'total_points': points,
        'level': points // 100 + 1, 'points_in_level': points % 100, 'points_to_next_level': 100 - points % 100,
        'achievements': achievements, 'actions': actions, 'attempts': attempts,
    }


def adaptation(score):
    if score < 50:
        return 'repeat', 'Повторите материал и разберите ошибки, затем пройдите тест ещё раз.'
    if score < 80:
        return 'practice', 'Выполните дополнительное задание и повторите тест. Для перехода нужно не менее 80 %.'
    return 'advance', 'Тема освоена. Можно перейти к следующему материалу.'


@router.get('/learning-path/{student_id}')
def learning_path(student_id: str, discipline_id: str = 'machine_learning'):
    student_id = valid_student(student_id)
    progress = get_progress(student_id, discipline_id)
    return assemble_path(student_id, discipline_id, progress)


def assemble_path(student_id, discipline_id, progress):
    read_ids = {action['item_id'] for action in progress['actions'] if action['item_type'] == 'material'}
    result = []
    recommended = None
    quiz_data = quizzes()
    for material in materials(discipline_id):
        scores = [a['score'] for a in progress['attempts'] if a['material_id'] == material['id']]
        best = max(scores) if scores else None
        latest = scores[-1] if scores else None
        mastered = best is not None and best >= 80
        if not mastered and recommended is None:
            recommended = material['id']
        action, message = adaptation(latest) if latest is not None else ('study', 'Изучите материал и пройдите тест из пяти вопросов.')
        if mastered:
            action, message = 'advance', 'Тема освоена. Материал и тест доступны для повторения.'
        result.append({**material, 'read': material['id'] in read_ids, 'mastered': mastered,
                       'best_score': best, 'latest_score': latest, 'attempt_count': len(scores),
                       'action': action, 'message': message, 'practice': quiz_data[material['id']]['practice']})
    from adaptive_engine import build_adaptive_state
    adaptive = build_adaptive_state(result, quiz_data, attempt_rows(student_id, include_answers=True))
    if adaptive['recommendation']:
        recommended = adaptive['recommendation']['material_id']
    for material in result:
        material['diagnostics'] = adaptive['profiles'][material['id']]
    return {'student_id': student_id, 'materials': result, 'recommended_material_id': recommended, 'progress': progress, 'adaptive': adaptive}


@router.get('/quiz/{material_id}')
def get_quiz(material_id: str):
    find_material(material_id)
    quiz = quizzes()[material_id]
    return {'material_id': material_id, 'questions': [{'id': q['id'], 'text': q['text'], 'options': q['options']} for q in quiz['questions']]}


class QuizSubmission(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    answers: list[StrictInt] = Field(min_length=1, max_length=20)

    @field_validator('student_id')
    @classmethod
    def student(cls, value):
        if not value.strip():
            raise ValueError('Идентификатор не должен быть пустым.')
        return value.strip()


@router.post('/quiz/{material_id}/submit')
def submit_quiz(material_id: str, request: QuizSubmission):
    request.student_id = valid_student(request.student_id)
    material = find_material(material_id)
    from academy_core import check_access
    check_access(request.student_id, material['discipline_id'])
    quiz = quizzes()[material_id]
    questions = quiz['questions']
    if len(request.answers) != len(questions) or any(not 0 <= answer < len(question['options']) for answer, question in zip(request.answers, questions)):
        raise HTTPException(status_code=422, detail='Ответьте на каждый вопрос допустимым вариантом.')
    correct_count = sum(answer == question['correct'] for answer, question in zip(request.answers, questions))
    score = round(correct_count / len(questions) * 100)
    init_progress_db()
    with sqlite3.connect(PROGRESS_DB, timeout=10) as connection:
        cursor = connection.execute(
            'INSERT INTO quiz_attempts (student_id, material_id, answers, correct_count, question_count, score) VALUES (?, ?, ?, ?, ?, ?)',
            (request.student_id, material_id, json.dumps(request.answers), correct_count, len(questions), score),
        )
        attempt_id = cursor.lastrowid
        awarded = False
        if score >= 80:
            cursor = connection.execute('INSERT INTO completions (student_id, item_type, item_id) VALUES (?, ?, ?) ON CONFLICT DO NOTHING', (request.student_id, 'task', f'quiz_{material_id}'))
            awarded = cursor.rowcount == 1
    action, message = adaptation(score)
    path = learning_path(request.student_id, material['discipline_id'])
    return {'attempt_id': attempt_id, 'material_id': material_id, 'score': score, 'correct_count': correct_count,
            'question_count': len(questions), 'passed': score >= 80, 'action': action, 'message': message,
            'points_awarded': 20 if awarded else 0, 'practice': quiz['practice'] if action == 'practice' else None,
            'feedback': [{'question': q['text'], 'correct': answer == q['correct'], 'correct_answer': q['options'][q['correct']], 'explanation': q['explanation']} for answer, q in zip(request.answers, questions)],
            'progress': path['progress'], 'adaptive': path['adaptive']}
