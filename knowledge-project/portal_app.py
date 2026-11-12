"""Streamlit page composition and API interaction for the learning portal."""
from html import escape
import json
import os
from urllib.parse import quote

import requests
import streamlit as st

from portal_ui import LESSON_INFO, achievement_card, apply_style, course_card, hero, html, lesson_meta, progress_csv, score_panel, lesson_markdown
from academy_portal import administration, choose_profile, curriculum
from adaptive_ui import route_overview, topic_diagnostics, knowledge_profile

API = os.environ.get('LEARNING_API_URL', 'http://127.0.0.1:8006')


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


def sidebar(academy, admin_view=False):
    with st.sidebar:
        html('<div class="brand"><span class="brand-mark">т</span>Траектория</div><div class="eyebrow">УЧЕБНЫЙ КАБИНЕТ</div>')
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
        st.caption('Материал → тест → рекомендация')
        st.markdown('**Ваши награды**')
        st.caption('10 баллов за прочитанный материал\n\n20 баллов за первый успешный тест\n\nНовый уровень каждые 100 баллов')
        st.divider()
        st.caption('Демонстрационный учебный кабинет без пароля студента. Админка защищена отдельным входом.')
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
        html('<div class="section-kicker">ШАГ 02 · САМОПРОВЕРКА</div>')
        st.subheader('Проверьте понимание')
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
    html('<div class="section-kicker">ПРОГРАММА ОБУЧЕНИЯ</div>')
    st.subheader(f'{len(path["materials"])} темы. Одна траектория.')
    st.write('Освоение определяется лучшим результатом теста. Текущий персональный шаг также учитывает ошибки, динамику, зависимости тем и срок повторения; выбирать материалы самостоятельно по-прежнему можно.')
    for start in range(0, len(path['materials']), 2):
        columns = st.columns(2)
        for index, material in enumerate(path['materials'][start:start + 2]):
            with columns[index]:
                course_card(material, start + index + 1, material['id'] == path['recommended_material_id'])
    st.caption('Откройте нужную тему через список «Выберите тему» во вкладке «Обучение».')


def progress_view(progress, catalog, student_id):
    html('<div class="section-kicker">ОТ ДЕЙСТВИЙ К РЕЗУЛЬТАТУ</div>')
    st.subheader('Ваши результаты')
    st.write(f'Изучено материалов: **{progress["completed_materials"]}**. Успешно пройдено тестов: **{progress["completed_tasks"]}**.')
    st.caption(f'В выбранной дисциплине: {progress.get("course_points", progress["total_points"])} баллов. Общий опыт по всем дисциплинам: {progress["total_points"]}. Достижения ниже относятся к выбранной дисциплине.')
    st.progress(progress['points_in_level'] / 100, text=f'До уровня {progress["level"] + 1}: {progress["points_to_next_level"]} баллов')
    st.markdown('### Достижения')
    achievements = [('Первый изученный материал', 'Отметьте первый материал прочитанным.'),
                    ('Первый пройденный тест', 'Наберите не менее 80 % в одном тесте.'),
                    ('Без ошибок', 'Ответьте верно на все пять вопросов.'),
                    ('Все темы освоены', 'Успешно пройдите тест по каждой теме.')]
    for start in range(0, len(achievements), 2):
        columns = st.columns(2)
        for index, (title, description) in enumerate(achievements[start:start + 2]):
            with columns[index]:
                achievement_card(title, description, title in progress['achievements'])
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
    student_id = sidebar(academy, admin_view)
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
    html(f'<div class="profile-strip"><span><strong>{escape(profile["full_name"])}</strong> · {escape(profile["group_name"])}</span><span class="chip">{len(courses)} ДИСЦИПЛИН</span></div>')
    left,right = st.columns([3,1])
    discipline = left.selectbox('Дисциплина',list(courses),format_func=lambda key:courses[key]['name'],key='selected_discipline')
    right.caption('Учебный план · семестр 3\n\nДемонстрационные данные')
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
    hero(student_id, progress['mastered_topics'], progress['total_topics'], courses[discipline]['name'])
    columns = st.columns(4)
    for column, label, value in zip(columns, ['Освоено тем', 'Баллы опыта', 'Уровень', 'Попытки тестов'],
        [f'{progress["mastered_topics"]} / {progress["total_topics"]}', progress['total_points'], progress['level'], len(progress['attempts'])]):
        column.metric(label, value)
    st.caption('Освоение и попытки — в выбранной дисциплине. Опыт и уровень — общие по всем дисциплинам.')
    study_tab, course_tab, progress_tab, plan_tab, analytics_tab = st.tabs(['Обучение', 'Карта курса', 'Мой прогресс', 'Учебный план', 'Аналитика OULAD'])
    with study_tab:
        study_view(path, student_id, catalog)
    with course_tab:
        course_view(path)
    with progress_tab:
        progress_view(progress, catalog, student_id)
        knowledge_profile(path['adaptive'])
    with plan_tab:
        curriculum(list(courses.values()),discipline)
    with analytics_tab:
        analytics_view(student_id, catalog)
    html('<div class="footnote">Траектория · Учебная среда<br>Материал прочитан — это первый шаг. Тема освоена, когда лучший результат теста не ниже 80 %.</div>')
