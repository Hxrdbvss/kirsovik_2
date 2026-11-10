import requests
import streamlit as st

API = "http://127.0.0.1:8006"

st.set_page_config(
    page_title="Адаптивное обучение",
    page_icon="📚",
    layout="centered",
)

st.title("Адаптивное обучение")
st.caption(
    "Учебный прототип: прогноз использует модель, обученную на OULAD. "
    "Результат не является оценкой способностей студента."
)


def post_api(endpoint, payload):
    try:
        response = requests.post(
            f"{API}{endpoint}",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Не удалось обратиться к API: {error}")
        return None


def get_api(endpoint):
    try:
        response = requests.get(f"{API}{endpoint}", timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Не удалось получить прогресс: {error}")
        return None


student_id = st.text_input(
    "Идентификатор студента",
    value="demo_interface",
    max_chars=100,
).strip()

st.subheader("Данные за первые 30 дней")

with st.form("student_data"):
    module = st.selectbox(
        "Модуль OULAD",
        ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"],
    )

    registration = st.number_input(
        "День регистрации относительно начала курса",
        max_value=30,
        value=-30,
        step=1,
    )

    previous_attempts = st.number_input(
        "Предыдущие попытки",
        min_value=0,
        value=0,
        step=1,
    )

    credits = st.number_input(
        "Учебные кредиты",
        min_value=0,
        value=60,
        step=1,
    )

    clicks = st.number_input(
        "Действия в учебной среде",
        min_value=0,
        value=0,
        step=1,
    )

    records = st.number_input(
        "Записи активности",
        min_value=0,
        value=0,
        step=1,
    )

    submitted = st.number_input(
        "Отправленные задания",
        min_value=0,
        value=0,
        step=1,
    )

    topic = st.selectbox(
        "Тема материала",
        [
            "Основы машинного обучения",
            "Деревья решений",
            "Случайный лес",
            "Линейная регрессия",
        ],
    )

    submitted_form = st.form_submit_button("Получить результат")


if submitted_form:
    if not student_id:
        st.warning("Введи идентификатор студента.")
    else:
        payload = {
            "student_id": student_id,
            "code_module": module,
            "date_registration": registration,
            "num_of_prev_attempts": previous_attempts,
            "studied_credits": credits,
            "vle_clicks": clicks,
            "vle_records": records,
            "submitted_count": submitted,
            "topic_query": topic,
        }

        result = post_api("/student-dashboard", payload)

        if result is not None:
            st.session_state["dashboard"] = result
            st.session_state["dashboard_student"] = student_id


dashboard = st.session_state.get("dashboard")

if dashboard and st.session_state.get("dashboard_student") == student_id:
    adaptive = dashboard["adaptive"]
    risk = adaptive["risk"]

    st.subheader("Результат")
    st.write(f"Оценка модели: **{risk['risk_score']:.4f}**")
    st.write(f"Порог: **{risk['threshold']:.2f}**")

    if risk["risk_flag"]:
        st.info(
            "Модель отметила возможный риск. "
            "Можно предложить дополнительные материалы."
        )
    else:
        st.success(
            "Оценка модели ниже выбранного порога. "
            "Можно продолжить обучение по текущему плану."
        )

    st.subheader("Материалы")
    st.write(adaptive["message"])

    for material in adaptive["materials"]:
        st.markdown(f"**{material['title']}**")
        st.write(
            f"Тема: {material['topic']} · "
            f"Уровень: {material['level']}"
        )

        with st.expander("Открыть материал"):
            content = get_api(
                f"/material-content/{requests.utils.quote(material['id'], safe='')}"
            )
            if content is not None:
                st.write(content["content"])

        if st.button(
            "Отметить изученным",
            key=f"complete_{material['id']}",
        ):
            saved = post_api(
                "/progress/complete",
                {
                    "student_id": student_id,
                    "item_type": "material",
                    "item_id": material["id"],
                },
            )

            if saved is not None:
                st.success(saved["message"])
                st.info(
                    "Нажми «Получить результат» ещё раз, "
                    "чтобы обновить список материалов."
                )


st.subheader("Прогресс")

if st.button("Показать прогресс"):
    if not student_id:
        st.warning("Введи идентификатор студента.")
    else:
        progress = get_api(f"/progress/{requests.utils.quote(student_id, safe='')}")

        if progress is not None:
            st.write(f"Баллы: **{progress['total_points']}**")
            st.write(
                f"Изучено материалов: {progress['completed_materials']}; "
                f"выполнено заданий: {progress['completed_tasks']}."
            )

            if progress["achievements"]:
                st.write("Достижения:")
                for achievement in progress["achievements"]:
                    st.write(f"🏅 {achievement}")
            else:
                st.write("Достижений пока нет.")


st.caption(
    "Тема выбирается пользователем. Соответствие между курсами OULAD "
    "и материалами каталога не проверялось. "
    "Действия сохраняются локально без проверки их фактического выполнения."
)
