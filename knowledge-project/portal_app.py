"""Streamlit page composition and API interaction for the learning portal."""
from html import escape
import json
import os
from urllib.parse import quote

import requests
import streamlit as st

from portal_ui import ACHIEVEMENTS, LESSON_INFO, achievement_card, apply_style, course_timeline, progress_ledger, html, lesson_meta, progress_csv, reward_note, score_panel, lesson_markdown
from academy_portal import administration, choose_profile, curriculum
from adaptive_ui import route_overview, topic_diagnostics, knowledge_profile

API = os.environ.get('LEARNING_API_URL', 'http://127.0.0.1:8006')


SECTIONS = {
    'today': 'Сегодня',
    'lesson': 'Урок',
    'route': 'Маршрут',
    'rewards': 'Награды',
    'progress': 'Мой прогресс',
    'plan': 'Учебный план',
    'analytics': 'Аналитика OULAD',
}


def navigate(section, material_id=None):
    st.query_params['section'] = section
    if material_id is not None:
        select_material(material_id)


def api(method, endpoint, payload=None, admin=False):
    """Call the learning API and show a readable message on connection or input errors."""
    try:
        headers = {'Authorization': f'Bearer {st.session_state.get("admin_token", "")}'} if admin else {}
        response = requests.request(method, f'{API}{endpoint}', json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        if admin and getattr(error, 'response', None) is not None and error.response.status_code == 401:
            st.session_state.pop('admin_token', None)
            st.rerun()
        detail = 'Проверьте, что сервис запущен, и повторите запрос.'
        if getattr(error, 'response', None) is not None:
            try:
                server_detail = error.response.json().get('detail')
                detail = server_detail if isinstance(server_detail, str) else 'Проверьте заполнение полей и повторите запрос.'
            except ValueError:
                pass
        st.error(f'Не удалось выполнить запрос. {detail}')
        return None


def select_material(material_id):
    st.session_state['selected_material'] = material_id


def sidebar(academy, admin_view, section):
    with st.sidebar:
        html('<div class="brand"><span class="brand-mark">т</span>Траектория</div>')
        if not admin_view:
            with st.container(key='workspace_menu'):
                for key, label in SECTIONS.items():
                    st.button(label, key=f'nav_{key}', on_click=navigate, args=(key,),
                              type='primary' if key == section else 'secondary', width='stretch')
            st.divider()
        if st.button('Учебный кабинет' if admin_view else 'Администрирование', width='stretch'):
            st.query_params['view'] = 'learn' if admin_view else 'admin'
            st.rerun()
        if admin_view:
            st.caption('Администрирование доступно после входа. Данные проверяются сервером.')
            if st.session_state.get('admin_token') and st.button('Выйти из админки', width='stretch'):
                api('POST', '/admin/logout', admin=True)
                st.session_state.pop('admin_token',None)
                st.rerun()
            return None
        if 'student_field' not in st.session_state:
            st.session_state['student_field'] = st.query_params.get('student', 'course_demo')
        student_id = st.text_input('Идентификатор студента', key='student_field', max_chars=100).strip()
        with st.expander('Выбрать демостудента'):
            groups = {group['id']:group for group in academy['groups']}
            group_id = st.selectbox('Группа демостудента', list(groups), format_func=lambda key:groups[key]['name'], key='demo_group_choice')
            students = {student['id']:student for student in academy['demo_students'] if student['group_id']==group_id}
            if students:
                st.selectbox('Демостудент', list(students),format_func=lambda key:students[key]['full_name'],key='demo_student_choice')
                st.button('Открыть профиль',on_click=choose_profile,width='stretch')
            st.caption('Все имена и результаты в наборе вымышлены.')
        html('<div class="sidebar-note">Один идентификатор — одна история обучения. Выберите демостудента или создайте свободный профиль.</div>')
    return student_id


def study_view(path, student_id, catalog):
    recommended = path['recommended_material_id']
    if st.session_state.get('selected_material') not in catalog:
        st.session_state['selected_material'] = recommended or next(iter(catalog))
    route_overview(path['adaptive'],catalog,select_material)
    labels = {key: f'{"✓" if value["mastered"] else "○"}  {value["topic"]}' for key, value in catalog.items()}
    selected = st.selectbox('Выберите тему', list(catalog), format_func=lambda key: labels[key], key='selected_material')
    material = catalog[selected]
    quiz = api('GET', f'/quiz/{selected}')
    number = list(catalog).index(selected) + 1
    with st.container(key='lesson_reading'):
        lesson_meta(material, number, len(quiz['questions']) if quiz else 5)
        st.subheader(material['title'])
        info = material if material.get('outcomes') else LESSON_INFO.get(selected, {})
        html('<div class="outcomes">' + ''.join(f'<span>{escape(text)}</span>' for text in info.get('outcomes', [])) + '</div>')
        if material.get('reading_minutes'):
            st.caption(f'Чтение около {material["reading_minutes"]} мин · Самостоятельная работа около {material["practice_minutes"]} мин')
        st.markdown(material['content'])
        if material.get('assignment'):
            with st.expander('Самостоятельная работа'):
                st.markdown(material['assignment'])
                st.caption('Выполните задание самостоятельно. Автоматическая проверка этой работы не проводится; освоение подтверждается тестом ниже.')
            with st.expander('Ориентир для самопроверки'):
                st.markdown(material['self_check'])
            with st.expander('Источники и дополнительное чтение'):
                for source in material['sources']:
                    st.markdown(f'- [{source["title"]}]({source["url"]})')
            st.download_button('Скачать конспект .md', data=lesson_markdown(material), file_name=f'lesson_{selected}.md', mime='text/markdown',key=f'lesson_download_{selected}')
        reward_note(10, material['read'], 'За первую отметку о чтении этой темы')
        if material['read']:
            st.caption('✓ Материал отмечен изученным · 10 баллов уже учтены')
        elif st.button('Отметить материал изученным', key=f'read_{student_id}_{selected}'):
            saved = api('POST', '/progress/complete', {'student_id': student_id, 'item_type': 'material', 'item_id': selected})
            if saved:
                st.rerun()
        if material['mastered'] and recommended and recommended != selected:
            st.button('Перейти к следующей теме', on_click=select_material, args=(recommended,), type='primary')
    feedback = st.session_state.get('quiz_feedback')
    current_feedback = feedback and feedback['student'] == student_id and feedback['material'] == selected
    if current_feedback:
        score_panel(feedback['result'])
    elif material['latest_score'] is not None:
        st.info(f'Последний результат: {material["latest_score"]} %. Лучший: {material["best_score"]} %. {material["message"]}')
    topic_diagnostics(material)
    if material['action'] == 'practice':
        with st.container(border=True):
            st.markdown('**Дополнительное задание**')
            st.write(material['practice'])
            st.caption('Для самостоятельной работы. Проверьте понимание повторным тестом — он подтвердит освоение темы.')
    with st.container(key='quiz_panel'):
        st.subheader('Проверьте понимание')
        reward_note(20, material['mastered'], 'За первый результат от 80 % по этой теме')
        html('<p class="section-description">От 80 % — освоение темы. Персональный шаг учитывает ошибки, динамику попыток, базовые темы и срок повторения.</p>')
        if quiz:
            with st.form(f'quiz_{student_id}_{selected}', clear_on_submit=False):
                answers = []
                for number, question in enumerate(quiz['questions'], 1):
                    answers.append(st.radio(f'{number}. {question["text"]}', range(len(question['options'])),
                        format_func=lambda index, options=question['options']: options[index], index=None,
                        key=f'answer_{student_id}_{selected}_{question["id"]}'))
                submitted = st.form_submit_button('Проверить ответы', type='primary')
            if submitted:
                if any(answer is None for answer in answers):
                    st.warning('Ответьте на все пять вопросов, затем отправьте тест.')
                else:
                    result = api('POST', f'/quiz/{selected}/submit', {'student_id': student_id, 'answers': answers})
                    if result:
                        st.session_state['quiz_feedback'] = {'student': student_id, 'material': selected, 'result': result}
                        st.rerun()
        if current_feedback:
            result = feedback['result']
            notify = st.success if result['passed'] else st.info
            notify(f'Результат: {result["score"]} % · Верно: {result["correct_count"]} из {result["question_count"]}. {result["message"]}')
            with st.expander('Разбор ответов'):
                for item in feedback['result']['feedback']:
                    st.markdown(f'{"✓" if item["correct"] else "✗"} **{item["question"]}**')
                    st.write(f'Верный ответ: {item["correct_answer"]}. {item["explanation"]}')


def course_view(path):
    st.subheader('Этапы курса')
    course_timeline(path['materials'], path['recommended_material_id'])
    st.button('Перейти к уроку', on_click=navigate, args=('lesson',))


def today_view(path, catalog):
    recommendation = path['adaptive'].get('recommendation')
    main_column, ledger = st.columns([7, 4], gap='large')
    with main_column:
        with st.container(key='today_focus'):
            if recommendation:
                material_id = recommendation['material_id']
                material = catalog[material_id]
                html(f'<div class="today-feature"><span>Рекомендация на сегодня</span>'
                     f'<h2>{escape(material["topic"])}</h2>'
                     f'<p>{escape(recommendation["reason"])}</p></div>')
                st.button('Открыть урок', key='today_open_lesson', type='primary',
                          on_click=navigate, args=('lesson', material_id), width='stretch')
                reward_note(10, material['read'], 'За первую отметку о чтении')
                reward_note(20, material['mastered'], 'За первый результат от 80 %')
            else:
                st.success('Все темы освоены. Срок планового повторения ещё не наступил.')
                st.button('Посмотреть маршрут', on_click=navigate, args=('route',))
    with ledger:
        progress_ledger(path['progress'])
        st.button('Посмотреть награды', on_click=navigate, args=('rewards',), width='stretch')


def rewards_view(progress):
    unlocked = set(progress['achievements'])
    st.subheader(f'Достижения · {len(unlocked)} из {len(ACHIEVEMENTS)}')
    st.caption('Достижения открываются отдельно в каждой дисциплине. Опыт и уровни общие для всех дисциплин.')
    for start in range(0, len(ACHIEVEMENTS), 2):
        columns = st.columns(2)
        for column, (title, description, number) in zip(columns, ACHIEVEMENTS[start:start + 2]):
            with column:
                achievement_card(title, description, title in unlocked, number)
    st.markdown('### Как начисляется опыт')
    st.write('За первую отметку о чтении темы начисляется **10 XP**, за первый успешный тест по ней — **20 XP**. Каждые **100 XP** повышают уровень. Повторные тесты сохраняются в истории и уточняют рекомендации.')
    st.caption(f'Опыт в этой дисциплине: {progress.get("course_points", progress["total_points"])} XP.')


def progress_view(progress, catalog, student_id):
    html('<div class="section-kicker">ОТ ДЕЙСТВИЙ К РЕЗУЛЬТАТУ</div>')
    st.subheader('Ваши результаты')
    st.write(f'Изучено материалов: **{progress["completed_materials"]}**. Успешно пройдено тестов: **{progress["completed_tasks"]}**.')
    st.caption(f'В выбранной дисциплине: {progress.get("course_points", progress["total_points"])} баллов. Общий опыт по всем дисциплинам: {progress["total_points"]}. Достижения ниже относятся к выбранной дисциплине.')
    st.progress(progress['points_in_level'] / 100, text=f'До уровня {progress["level"] + 1}: {progress["points_to_next_level"]} баллов')
    with st.container(key='progress_history'):
        st.markdown('### История тестирования')
        if progress['attempts']:
            rows = [{'Тема': catalog.get(item['material_id'], {}).get('topic', item['material_id']), 'Результат, %': item['score'],
                     'Верных ответов': item['correct_count'], 'Дата и время UTC': item['created_at']} for item in reversed(progress['attempts'])]
            st.dataframe(rows, hide_index=True, width='stretch')
            if len(rows) > 1:
                with st.expander('Как менялись результаты'):
                    st.line_chart({'Попытка': list(range(1, len(progress['attempts']) + 1)),
                                   'Результат, %': [attempt['score'] for attempt in progress['attempts']]},
                                  x='Попытка', y='Результат, %', y_label='Процент верных ответов', x_label='Попытка')
        else:
            html('<div class="empty-state"><strong>Всё начинается с первой попытки</strong>Пройдите тест — здесь появятся результаты и история вашего продвижения.</div>')
        st.caption('Выгрузка содержит данные текущего профиля. Время попыток указано в UTC.')
        left, right = st.columns(2)
        left.download_button('Скачать историю CSV', data=progress_csv(progress, catalog), file_name=f'progress_{student_id}.csv', mime='text/csv')
        right.download_button('Скачать прогресс JSON', data=json.dumps(progress, ensure_ascii=False, indent=2), file_name=f'progress_{student_id}.json', mime='application/json')


def analytics_view(student_id, catalog):
    html('<div class="section-kicker">ДОПОЛНИТЕЛЬНАЯ АНАЛИТИКА</div>')
    st.subheader('Экспериментальная оценка учебного риска')
    st.write('Модель анализирует показатели активности за первые 30 дней курса OULAD. Этот прогноз показан отдельно от вашей учебной траектории и результатов тестов.')
    with st.container(key='risk_panel'):
        with st.form('risk_form'):
            left, right = st.columns(2)
            module = left.selectbox('Модуль OULAD', ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'GGG'])
            registration = right.number_input('День регистрации относительно начала курса', max_value=30, value=-30, step=1)
            previous = left.number_input('Предыдущие попытки', min_value=0, value=0, step=1)
            credits = right.number_input('Учебные кредиты', min_value=0, value=60, step=1)
            clicks = left.number_input('Действия в учебной среде', min_value=0, value=0, step=1)
            records = right.number_input('Записи активности', min_value=0, value=0, step=1)
            submitted_count = left.number_input('Отправленные задания', min_value=0, value=0, step=1)
            predict = st.form_submit_button('Рассчитать оценку риска')
        if predict:
            material = catalog.get(st.session_state.get('selected_material'), next(iter(catalog.values())))
            payload = {'student_id': student_id, 'code_module': module, 'date_registration': registration,
                       'num_of_prev_attempts': previous, 'studied_credits': credits, 'vle_clicks': clicks,
                       'vle_records': records, 'submitted_count': submitted_count, 'topic_query': material['topic']}
            with st.spinner('Рассчитываем прогноз по данным формы…'):
                result = api('POST', '/student-dashboard', payload)
            if result:
                st.session_state['risk_result'] = {'student': student_id, 'risk': result['adaptive']['risk'], 'inputs': payload}
        result = st.session_state.get('risk_result')
        if result and result['student'] == student_id:
            risk = result['risk']
            st.metric('Оценка модели', f'{risk["risk_score"]:.4f}')
            st.write(f'Порог: {risk["threshold"]:.2f}. {risk["recommendation"]}')
            st.caption('Результат относится к последней отправленной форме. После изменения значений выполните расчёт повторно.')
    st.caption('Прогноз не является оценкой способностей студента. Перенос модели OULAD на этот учебный курс не проверялся. Он не влияет на освоение тем и баллы.')


def main():
    st.set_page_config(page_title='Траектория — учиться шаг за шагом', page_icon='🌿', layout='wide')
    apply_style()
    academy = api('GET','/academy/catalog')
    if not academy:
        return
    admin_view = st.query_params.get('view') == 'admin'
    section = st.query_params.get('section', 'today')
    if section not in SECTIONS:
        section = 'today'
    student_id = sidebar(academy, admin_view, section)
    if admin_view:
        administration(api)
        return
    if not student_id:
        st.info('Укажите идентификатор студента в боковой панели.')
        return
    if not all(char.isalnum() or char in '._-' for char in student_id):
        st.warning('В идентификаторе используйте буквы, цифры, точки, дефисы или подчёркивания.')
        return
    if st.query_params.get('student') != student_id:
        st.query_params['student'] = student_id
    if st.session_state.get('profile_owner') != student_id:
        st.session_state['profile_owner'] = student_id
        st.session_state['selected_material'] = None
        st.session_state.pop('quiz_feedback', None)
        st.session_state.pop('risk_result', None)
    profile = api('GET', f'/academy/profile/{quote(student_id,safe="")}')
    if not profile:
        return
    courses = {course['id']:course for course in profile['disciplines']}
    if st.session_state.get('selected_discipline') not in courses:
        requested = st.query_params.get('discipline','machine_learning')
        st.session_state['selected_discipline'] = requested if requested in courses else next(iter(courses))
    with st.sidebar:
        discipline = st.selectbox('Дисциплина', list(courses), format_func=lambda key:courses[key]['name'],
                                  key='selected_discipline')
    st.query_params['discipline'] = discipline
    if st.session_state.get('course_owner') != discipline:
        st.session_state['course_owner'] = discipline
        st.session_state['selected_material'] = None
        st.session_state.pop('quiz_feedback',None)
    path = api('GET', f'/learning-path/{quote(student_id, safe="")}?discipline_id={discipline}')
    if path is None:
        return
    progress = path['progress']
    catalog = {material['id']: material for material in path['materials']}
    # Keep the lesson selection when its widget is hidden on another screen.
    if 'selected_material' in st.session_state:
        st.session_state['selected_material'] = st.session_state['selected_material']
    html(f'<header class="workspace-heading"><p>{escape(courses[discipline]["name"])}</p>'
         f'<h1>{escape(SECTIONS[section])}</h1>'
         f'<span>{escape(profile["full_name"])} · {escape(profile["group_name"])}</span></header>')
    if section == 'today':
        today_view(path, catalog)
    elif section == 'lesson':
        study_view(path, student_id, catalog)
    elif section == 'route':
        course_view(path)
    elif section == 'rewards':
        progress_ledger(progress)
        rewards_view(progress)
    elif section == 'progress':
        progress_view(progress, catalog, student_id)
        knowledge_profile(path['adaptive'])
    elif section == 'plan':
        curriculum(list(courses.values()), discipline)
    elif section == 'analytics':
        analytics_view(student_id, catalog)
