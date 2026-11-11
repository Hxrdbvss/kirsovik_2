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


ACHIEVEMENTS = (
    ('Первый изученный материал', 'Отметьте первый материал изученным.', '01'),
    ('Первый пройденный тест', 'Наберите не менее 80 % в одном тесте.', '02'),
    ('Без ошибок', 'Получите 100 % в любом тесте дисциплины.', '03'),
    ('Все темы освоены', 'Наберите от 80 % по каждой теме дисциплины.', '04'),
)


def progress_ledger(progress):
    level = int(progress['level'])
    points = int(progress['points_in_level'])
    html(f'''<div class="course-masthead"><div class="course-title">
        <div class="eyebrow">Прогресс в дисциплине</div>
        <p>Освоено тем: <strong>{progress["mastered_topics"]} из {progress["total_topics"]}</strong></p>
        </div><section class="xp-panel" aria-label="Игровой прогресс">
        <div class="xp-top"><strong><small>Уровень</small> {level:02d}</strong><span>{progress["total_points"]} XP всего</span></div>
        <progress value="{points}" max="100" aria-label="Опыт на текущем уровне"></progress>
        <div class="xp-meta"><span>{points} / 100 XP</span><span>До уровня {level + 1}: {progress["points_to_next_level"]} XP</span></div>
        </section></div>''')


def reward_note(reward, completed, instruction):
    state = 'Получено' if completed else 'Доступно'
    html(f'<div class="reward-line {"earned" if completed else ""}">'
         f'<strong>+{reward} XP</strong><span>{escape(instruction)}</span><small>{state}</small></div>')


def course_timeline(materials, recommended):
    rows = []
    for index, material in enumerate(materials, 1):
        current = material['id'] == recommended
        mastered = material['mastered']
        status = 'Освоено' if mastered else 'Конспект изучен' if material['read'] else 'Впереди'
        if current:
            status = 'Рекомендовано повторить' if mastered else 'Следующий шаг'
        score = material['best_score']
        score_text = 'Тест не пройден' if score is None else f'Лучший результат: {score} %'
        rows.append(
            f'<li class="{"current" if current else ""} {"mastered" if mastered else ""}">'
            f'<span class="stage-number">{index:02d}</span><div class="stage-topic">'
            f'<strong>{escape(material["topic"])}</strong><small>{score_text}</small></div>'
            f'<span class="stage-state">{status}</span></li>'
        )
    html('<ol class="course-timeline" aria-label="Этапы курса">' + ''.join(rows) + '</ol>')


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


def achievement_card(title, description, unlocked, number):
    state = 'Открыто' if unlocked else 'Закрыто'
    html(f'<div class="achievement {"" if unlocked else "locked"}">'
         f'<div class="achievement-top"><span class="achievement-symbol">{"✓" if unlocked else number}</span>'
         f'<span>{state}</span></div><strong>{escape(title)}</strong><small>{escape(description)}</small></div>')


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
