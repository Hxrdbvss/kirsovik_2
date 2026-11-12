"""Presentation components and progress exports for the learning portal."""
import csv
from html import escape
import io
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
LESSON_INFO = {
    'mat_01': {'summary': 'Разберитесь, как модель учится на примерах и зачем проверять её на новых данных.', 'outcomes': ['Признаки и ответы', 'Классификация', 'Проверка качества']},
    'mat_02': {'summary': 'Проследите путь от условия в узле до предсказания и узнайте, что ограничивает сложность дерева.', 'outcomes': ['Узлы и листья', 'Правила решения', 'Переобучение']},
    'mat_03': {'summary': 'Узнайте, как несколько деревьев объединяют ответы голосованием и усреднением.', 'outcomes': ['Ансамбль', 'Голосование', 'Усреднение']},
    'mat_04': {'summary': 'Постройте простой числовой прогноз и научитесь отличать зависимость от причинной связи.', 'outcomes': ['Линейная модель', 'Коэффициенты', 'Числовой прогноз']},
}


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def apply_style():
    html('<style>' + (ROOT / 'assets/portal.css').read_text(encoding='utf-8') + '</style>')


def hero(student_id, mastered, total, discipline_name='Машинное обучение'):
    percent = round(mastered / max(total, 1) * 100)
    circle = 2 * 3.14159265 * 59
    html(f'''<div class="hero"><div><div class="eyebrow">ВАШ ПЕРСОНАЛЬНЫЙ КУРС</div>
        <h1>{escape(discipline_name)}.<br>Шаг за шагом.</h1>
        <p>Изучайте понятия, проверяйте понимание и двигайтесь дальше с рекомендацией по вашему результату.</p>
        <span class="hero-user">Профиль · {escape(student_id)}</span></div>
        <div class="hero-orbit"><svg viewBox="0 0 145 145" aria-hidden="true">
        <circle cx="72.5" cy="72.5" r="59" fill="none" stroke="#416052" stroke-width="6"/>
        <circle cx="72.5" cy="72.5" r="59" fill="none" stroke="#b8ecc9" stroke-width="6" stroke-linecap="round"
        stroke-dasharray="{circle:.2f}" stroke-dashoffset="{circle * (1 - percent / 100):.2f}"/></svg>
        <div class="orbit-label"><strong>{percent}%</strong><small>курса освоено</small></div></div></div>''')


def lesson_meta(material, number, question_count=5):
    status = 'Тема освоена' if material['mastered'] else 'Нужно закрепить' if material['latest_score'] is not None else 'Материал прочитан' if material['read'] else 'Новая тема'
    html(f'<div class="lesson-meta"><span class="chip">ТЕМА {number:02d}</span>'
         f'<span class="chip">{escape(material["level"])}</span><span class="chip">{question_count} вопросов</span>'
         f'<span class="chip {"done" if material["mastered"] else ""}">{status}</span></div>')


def score_panel(result):
    titles = {'repeat': 'Вернёмся к основам', 'practice': 'Закрепим на практике', 'advance': 'Тема освоена'}
    reward = f'+{result["points_awarded"]} баллов за первое успешное прохождение' if result['points_awarded'] else 'Попытка сохранена в вашей истории'
    html(f'<div class="score-panel {result["action"]}"><div class="score-number">{result["score"]}%</div><div>'
         f'<div class="score-title">{titles[result["action"]]}</div>'
         f'<div class="score-copy">Верно {result["correct_count"]} из {result["question_count"]}. {escape(result["message"])}</div>'
         f'<div class="score-reward">{reward}</div></div></div>')


def course_card(material, number, recommended):
    status = 'Повторение сейчас' if material['mastered'] and recommended else 'Освоена' if material['mastered'] else 'Рекомендуется сейчас' if recommended else 'Впереди'
    best = f'Лучший результат: {material["best_score"]}%' if material['best_score'] is not None else 'Тест ещё не пройден'
    info = {'summary': material.get('summary', LESSON_INFO.get(material['id'], {}).get('summary', material['topic']))}
    html(f'<div class="lesson-card {"is-current" if recommended else ""}"><div class="lesson-number">{number:02d}</div>'
         f'<div class="lesson-meta"><span class="chip {"done" if material["mastered"] else ""}">{status}</span></div>'
         f'<h3>{escape(material["topic"])}</h3><p>{escape(info["summary"])}</p>'
         f'<div class="lesson-card-footer"><span>{best}</span><span>Попыток: {material["attempt_count"]}</span></div></div>')


def achievement_card(title, description, unlocked):
    html(f'<div class="achievement {"" if unlocked else "locked"}"><div class="achievement-symbol">{"✓" if unlocked else "○"}</div>'
         f'<strong>{escape(title)}</strong><small>{escape(description)}</small></div>')


def progress_csv(progress, catalog):
    """Return an Excel-friendly UTF-8 CSV with one row per quiz attempt."""
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Тема', 'Результат, %', 'Верных ответов', 'Всего вопросов', 'Дата и время UTC'])
    for attempt in progress['attempts']:
        title = catalog.get(attempt['material_id'], {}).get('topic', attempt['material_id'])
        writer.writerow([title, attempt['score'], attempt['correct_count'], attempt['question_count'], attempt['created_at']])
    return output.getvalue().encode('utf-8-sig')


def lesson_markdown(material):
    """Download the current lesson with its assignment, solution guide and references."""
    parts = [f'# {material["title"]}', '', material['content']]
    if material.get('assignment'):
        parts += ['', '## Самостоятельная работа', '', material['assignment']]
    if material.get('self_check'):
        parts += ['', '## Ориентир для самопроверки', '', material['self_check']]
    if material.get('sources'):
        parts += ['', '## Источники и дополнительное чтение', '']
        parts.extend(f'- [{source["title"]}]({source["url"]})' for source in material['sources'])
    return ('\n'.join(parts)+'\n').encode('utf-8')
