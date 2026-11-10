"""Explain adaptive choices with observable evidence, targeted exercises and review dates."""
from html import escape

import streamlit as st

from portal_ui import html

MODES = {'new':'Новая тема','repair':'Повторение понятий','practice':'Прицельная практика','example':'Разбор примера',
         'prerequisite':'Возврат к базовой теме','review':'Восстановление понимания','scheduled_review':'Плановое повторение'}
TRENDS = {'growing':'Растёт','declining':'Снижается','stable':'Без изменения','unknown':'Недостаточно попыток'}


def route_overview(adaptive, catalog, select_material):
    recommendation = adaptive.get('recommendation')
    if not recommendation:
        st.success('Все темы освоены. Срок планового повторения ещё не наступил.')
        return
    mid = recommendation['material_id']
    html(f'<div class="adaptive-route"><div class="eyebrow">ПЕРСОНАЛЬНЫЙ МАРШРУТ · {escape(MODES[recommendation["kind"]])}</div>'
         f'<h3>{escape(catalog[mid]["topic"])}</h3><p>{escape(recommendation["reason"])}</p></div>')
    if recommendation['focus_concepts']:
        st.caption('В фокусе: ' + ' · '.join(recommendation['focus_concepts']))
    if st.session_state.get('selected_material') != mid:
        st.button('Открыть рекомендованный шаг',key='open_adaptive_step',on_click=select_material,args=(mid,),type='primary')
    with st.expander('Почему выбран этот шаг и что делать'):
        for index, step in enumerate(recommendation['steps'],1):
            st.markdown(f'**{index}. {step["title"]}**')
            st.write(step['detail'])
        st.caption(adaptive['method_note'])
    if adaptive['due_reviews']:
        st.caption(f'Тем для планового повторения: {len(adaptive["due_reviews"])}. Даты доступны в разделе «Мой прогресс».')


def topic_diagnostics(material):
    profile = material.get('diagnostics')
    if not profile or not profile['evidence_attempts']:
        return
    with st.container(key='adaptive_diagnostics',border=True):
        st.subheader('Что стоит закрепить')
        score = profile['recent_score']
        st.caption(f'Взвешенный результат последних попыток: {score:g} % · Динамика: {TRENDS[profile["trend"]]} · Учтено попыток: {min(profile["evidence_attempts"],3)}')
        if not profile['weak_concepts']:
            st.success('В последней попытке нет ошибок по проверяемым понятиям.')
        else:
            for concept in profile['weak_concepts'][:3]:
                st.markdown(f'**{concept["name"]}**' + (' · повторная ошибка' if concept['repeated_error'] else ''))
                st.write(concept['exercise'])
                with st.expander(f'Повторить: {concept["review_section"]} · {concept["question_id"]}'):
                    st.markdown(concept['review_excerpt'])
            if len(profile['weak_concepts'])>3:
                st.caption('Показаны три приоритетных понятия. Полный список — в разделе «Мой прогресс».')
        st.caption('Диагностика основана на ответах к этим вопросам. Это ориентир для повторения; дополнительные задания проверяются самостоятельно.')


def knowledge_profile(adaptive):
    st.markdown('### Профиль знаний и повторение')
    st.caption('Для каждого понятия анализируются до трёх последних ответов. «Последний ответ верный» не означает доказанного знания всей темы.')
    rows = []
    for profile in adaptive['profiles'].values():
        for concept in profile['concepts']:
            rows.append({'Тема':profile['topic'],'Понятие':concept['name'],
                'Последний ответ':'Нет данных' if concept['last_correct'] is None else 'Повторить' if not concept['last_correct'] else 'Верный',
                'Взвешенная точность, %':concept['recent_accuracy'],'Ответов учтено':concept['observations'],
                'Повторная ошибка':'Да' if concept['repeated_error'] else 'Нет'})
    st.dataframe(rows,hide_index=True,width='stretch')
    calendar = [{'Тема':profile['topic'],'Повторить после, UTC':profile['next_review_at'],
                 'Интервал, дней':profile['review_interval_days'],'Состояние':'Пора повторить' if profile['review_due'] else 'Запланировано'}
                for profile in adaptive['profiles'].values() if profile['next_review_at']]
    if calendar:
        st.dataframe(calendar,hide_index=True,width='stretch')
    else:
        st.info('После первого успешного теста появится дата повторения.')
    st.caption(adaptive['method_note'])
