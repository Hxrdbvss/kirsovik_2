"""Check live academic screens without adding students to the working database."""
from datetime import datetime, timezone
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent
checks = []


def record(name, passed):
    checks.append({'name': name, 'passed': bool(passed)})
    if not passed:
        raise AssertionError(name)


def click(app, label):
    next(button for button in app.button if button.label == label).click().run(timeout=30)
    record(label, not app.exception)


learner = AppTest.from_file(str(ROOT/'student_portal.py'))
learner.query_params['student'] = 'demo_pi_21_002'
learner.run(timeout=30)
record('Registered synthetic profile loads', not learner.exception and learner.text_input(key='student_field').value == 'demo_pi_21_002')
record('Eight enrolled courses are offered', len(learner.selectbox(key='selected_discipline').options) == 8)
click(learner,'Учебный план')
record('Curriculum page is available', learner.query_params.get('section')=='plan')
click(learner,'Урок')
learner.selectbox(key='selected_discipline').set_value('python').run(timeout=30)
record('Course selection is reflected in URL', learner.query_params.get('discipline')=='python')
record('Python course has two topics and five questions', len(learner.selectbox(key='selected_material').options)==2 and len(learner.radio)==5)
learner.selectbox(key='demo_group_choice').set_value('ivt_21').run(timeout=30)
record('Group chooser contains fifteen students', len(learner.selectbox(key='demo_student_choice').options)==15)
learner.selectbox(key='demo_student_choice').set_value('demo_ivt_21_003').run(timeout=30)
click(learner,'Открыть профиль')
record('Demo profile button changes student identity',learner.text_input(key='student_field').value=='demo_ivt_21_003')
record('Group enrollment changes course options', any('Компьютерные сети' in option for option in learner.selectbox(key='selected_discipline').options))

admin = AppTest.from_file(str(ROOT/'student_portal.py'))
admin.query_params['view']='admin'
admin.run(timeout=30)
record('Administration initially shows login only',not admin.exception and len(admin.dataframe)==0 and any('Вход в администрирование'==heading.value for heading in admin.subheader))
admin.text_input(key='admin_password').set_value('invalid-demo-password')
click(admin,'Войти')
record('Incorrect credentials are rejected',any('Неверный логин' in error.value for error in admin.error))
access = (ROOT.parent/'.runtime/admin_access.txt').read_text(encoding='utf-8')
password = access.split('Пароль: ',1)[1].splitlines()[0]
admin.text_input(key='admin_password').set_value(password)
click(admin,'Войти')
record('Valid login exposes registered student list',not admin.exception and len(admin.dataframe[0].value)==30)
admin.selectbox(key='admin_group_filter').set_value('pi_21').run(timeout=30)
record('Group filter returns fifteen students',len(admin.dataframe[0].value)==15)
admin.text_input(key='admin_search').set_value('Белов').run(timeout=30)
record('Name search returns the requested student',len(admin.dataframe[0].value)==1 and 'Белов' in admin.dataframe[0].value.iloc[0]['Студент'])
record('Student card lists eight disciplines',len(admin.dataframe[1].value)==8)
admin.text_input(key='admin_search').set_value('несуществующий_профиль').run(timeout=30)
record('Empty search has a readable state',any('Нет студентов' in item.value for item in admin.info))
click(admin,'Выйти из админки')
record('Logout returns to protected login screen',len(admin.dataframe)==0 and 'admin_token' not in admin.session_state)

report = {'verified_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'passed':sum(item['passed'] for item in checks),'total':len(checks)}
(ROOT/'project_results/current_academy_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total']}))
