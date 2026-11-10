"""Administration screens. Every data request is authenticated by the backend."""
import csv
from html import escape
import io

import streamlit as st

from portal_ui import html


def choose_profile():
    st.session_state['student_field'] = st.session_state['demo_student_choice']


def choose_course(course_id):
    st.session_state['selected_discipline'] = course_id
    st.session_state['selected_material'] = None


def curriculum(courses, selected):
    html('<div class="section-kicker">УЧЕБНЫЙ ПЛАН · СЕМЕСТР 3</div>')
    st.subheader('Все дисциплины вашей группы')
    st.caption('Выберите дисциплину, затем откройте вкладку «Обучение». Результаты тестов учитываются отдельно, баллы опыта суммируются.')
    for offset in range(0, len(courses), 2):
        columns = st.columns(2)
        for column, course in zip(columns, courses[offset:offset+2]):
            with column:
                html(f'<div class="discipline-card {"is-selected" if course["id"] == selected else ""}"><div class="eyebrow">{course["topic_count"]} ТЕМЫ · 5 ВОПРОСОВ В ТЕСТЕ</div><h3>{escape(course["name"])}</h3><p>{escape(course["description"])}</p><small>{escape(course["teacher"])}</small></div>')
                st.button('Открыть дисциплину', key=f'open_{course["id"]}', on_click=choose_course, args=(course['id'],), width='stretch', disabled=course['id']==selected)


def export_roster(students):
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Идентификатор','ФИО','Группа','Активен','Освоено тем','Всего тем','Прогресс, %','Баллы','Попытки','Статус'])
    for row in students:
        writer.writerow([row['id'],row['full_name'],row['group_name'],row['active'],row['mastered_topics'],row['total_topics'],row['completion_percent'],row['total_points'],row['attempts'],row['support']])
    return output.getvalue().encode('utf-8-sig')


def administration(api):
    if not st.session_state.get('admin_token'):
        html('<div class="admin-heading"><div class="eyebrow">ТРАЕКТОРИЯ · УПРАВЛЕНИЕ</div><h1>Кабинет администратора</h1><p>Группы, студенты и учебные результаты в одном месте.</p></div>')
        left, right = st.columns([1, 1])
        with left:
            with st.form('admin_login'):
                st.subheader('Вход в администрирование')
                username = st.text_input('Логин', value='admin', key='admin_username')
                password = st.text_input('Пароль', type='password', key='admin_password')
                submitted = st.form_submit_button('Войти', type='primary', width='stretch')
            if submitted:
                result = api('POST', '/admin/login', {'username': username, 'password': password})
                if result:
                    st.session_state['admin_token'] = result['token']
                    st.rerun()
        with right:
            html('<div class="lesson-card"><div class="eyebrow">ЛОКАЛЬНАЯ ДЕМОНСТРАЦИЯ</div><h3>Доступ владельца проекта</h3><p>Логин и автоматически созданный пароль находятся в файле <code>.runtime/admin_access.txt</code> внутри папки проекта.</p><p>В наборе данных — вымышленные студенты. Пароль не входит в архив программы.</p></div>')
        return
    data = api('GET', '/admin/overview', admin=True)
    if not data:
        return
    html('<div class="admin-heading"><div class="eyebrow">АКАДЕМИЧЕСКАЯ СРЕДА · СЕМЕСТР 3</div><h1>Студенты и группы</h1><p>Общая картина обучения и подробные результаты каждого студента.</p></div>')
    summary = data['summary']
    for column, label, value in zip(st.columns(4), ['Всего студентов','Учебные группы','Дисциплины','Нужна поддержка'], [summary['students'],summary['groups'],summary['disciplines'],summary['needs_support']]):
        column.metric(label,value)
    st.caption('Демонстрационная база синтетическая. «Нужна поддержка» означает, что по неосвоенной теме последний результат ниже 50 %. Это правило по тестам, не прогноз модели OULAD.')
    roster_tab, plans_tab, add_tab = st.tabs(['Все студенты', 'Группы и дисциплины', 'Добавить студента'])
    groups = {row['id']: row for row in data['groups']}
    with roster_tab:
        a,b,c = st.columns([2,1,1])
        search = a.text_input('Поиск по имени или идентификатору', placeholder='Начните вводить имя…', key='admin_search').strip().casefold()
        group_id = b.selectbox('Группа', ['all'] + list(groups), format_func=lambda key: 'Все группы' if key=='all' else groups[key]['name'], key='admin_group_filter')
        status = c.selectbox('Статус обучения', ['Все','Нужна поддержка','Нужна практика','Без затруднений','Нет попыток'], key='admin_support_filter')
        show_archived = st.checkbox('Показывать архивные профили', value=True, key='admin_archived')
        rows = [row for row in data['students'] if (not search or search in row['full_name'].casefold() or search in row['id'].casefold()) and (group_id=='all' or row['group_id']==group_id) and (status=='Все' or row['support']==status) and (show_archived or row['active'])]
        st.caption(f'Найдено: {len(rows)} из {len(data["students"])} · активных профилей: {summary["active"]}')
        if rows:
            st.dataframe([{'Студент':row['full_name'],'Группа':row['group_name'],'Прогресс, %':row['completion_percent'],'Освоено тем':f'{row["mastered_topics"]}/{row["total_topics"]}','Баллы':row['total_points'],'Попытки':row['attempts'],'Статус':row['support'],'Профиль':'Активен' if row['active'] else 'Архив','Идентификатор':row['id']} for row in rows], hide_index=True, width='stretch',
                column_config={'Прогресс, %':st.column_config.ProgressColumn(min_value=0,max_value=100,format='%d %%')})
            st.download_button('Скачать выбранный список CSV', export_roster(rows), 'students_filtered.csv', 'text/csv')
            student_id = st.selectbox('Карточка студента', [row['id'] for row in rows], format_func=lambda key: next(f'{row["full_name"]} · {row["group_name"]}' for row in rows if row['id']==key), key='admin_student_detail')
            detail = api('GET', f'/admin/students/{student_id}', admin=True)
            if detail:
                student = detail['student']
                with st.container(border=True):
                    st.subheader(student['full_name'])
                    st.caption(f'{student["id"]} · {student["group_name"]} · Последний тест: {student["last_activity"] or "ещё нет"} UTC')
                    st.dataframe([{'Дисциплина':course['name'],'Освоено тем':f'{course["progress"]["mastered_topics"]}/{course["progress"]["total_topics"]}','Баллы дисциплины':course['progress']['course_points'],'Попытки':len(course['progress']['attempts'])} for course in detail['courses']], hide_index=True, width='stretch')
                    with st.expander('История тестов'):
                        history = sorted([{'Дисциплина':course['name'],'Тема':attempt['material_id'],'Результат, %':attempt['score'],'Дата UTC':attempt['created_at']} for course in detail['courses'] for attempt in course['progress']['attempts']], key=lambda row: row['Дата UTC'],reverse=True)
                        if history:
                            st.dataframe(history, hide_index=True,width='stretch')
                        else:
                            st.info('Студент пока не проходил тесты.')
                    with st.expander('Изменить профиль'):
                        with st.form(f'edit_{student_id}'):
                            full_name = st.text_input('ФИО', value=student['full_name'], key=f'edit_name_{student_id}')
                            new_group = st.selectbox('Учебная группа', list(groups), index=list(groups).index(student['group_id']), format_func=lambda key:groups[key]['name'], key=f'edit_group_{student_id}')
                            active = st.checkbox('Профиль активен', value=bool(student['active']), key=f'edit_active_{student_id}')
                            st.caption('Архивация сохраняет историю. При переводе результаты по прежним дисциплинам остаются в базе; учебный план определяется новой группой.')
                            save = st.form_submit_button('Сохранить профиль')
                        if save:
                            result = api('PUT', f'/admin/students/{student_id}', {'id':student_id,'full_name':full_name,'group_id':new_group,'active':active}, admin=True)
                            if result:
                                st.session_state['admin_notice']='Профиль сохранён.'
                                st.rerun()
                    with st.expander('Пробелы и индивидуальные рекомендации'):
                        for course in detail['courses']:
                            adaptive = course['adaptive']
                            recommendation = adaptive['recommendation']
                            st.markdown(f'**{course["name"]}** · понятий для повторения: {adaptive["weak_concepts"]}')
                            st.write(recommendation['reason'] if recommendation else 'Все темы освоены; плановое повторение пока не требуется.')
                            weak = [concept['name'] for profile in adaptive['profiles'].values() for concept in profile['weak_concepts']]
                            if weak:
                                st.caption('Повторить: ' + '; '.join(weak))
        else:
            st.info('Нет студентов с выбранными условиями. Измените поиск или фильтры.')
    with plans_tab:
        for group in data['groups']:
            with st.container(border=True):
                st.subheader(group['name'])
                count = sum(row['group_id']==group['id'] for row in data['students'])
                st.caption(f'{group["program"]} · {count} студентов · {len(group["discipline_ids"])} дисциплин')
                st.dataframe([{'Дисциплина':course['name'],'Темы':course['topic_count'],'Преподаватель':course['teacher'],'Семестр':course['semester']} for course in data['disciplines'] if course['id'] in group['discipline_ids']],hide_index=True,width='stretch')
    with add_tab:
        st.subheader('Новый студент')
        st.caption('Добавленный профиль появится в общем списке. В учебном кабинете его можно открыть по идентификатору. Для демонстрации используйте вымышленные данные.')
        with st.form('add_student',clear_on_submit=True):
            new_id = st.text_input('Идентификатор нового студента',placeholder='student_031',max_chars=100)
            name = st.text_input('ФИО нового студента',max_chars=120)
            group = st.selectbox('Группа нового студента',list(groups),format_func=lambda key:groups[key]['name'])
            create = st.form_submit_button('Добавить студента',type='primary')
        if create:
            result = api('POST','/admin/students',{'id':new_id,'full_name':name,'group_id':group,'active':True},admin=True)
            if result:
                st.session_state['admin_notice']='Студент добавлен. Найдите его на вкладке «Все студенты».'
                st.rerun()
    if notice := st.session_state.pop('admin_notice',None):
        st.success(notice)
