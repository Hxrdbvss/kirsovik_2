"""Live UI checks for the observable adaptive cases; creates only isolated demo IDs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8006'
prefix = 'adaptive_ui_'+uuid.uuid4().hex[:8]
checks = []
quizzes = json.loads((ROOT/'quizzes.json').read_text(encoding='utf-8'))


def record(name, condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition:
        raise AssertionError(name)


def submit(student,mid,wrong):
    questions = quizzes[mid]['questions']
    answers = [(q['correct']+1)%len(q['options']) if index in wrong else q['correct'] for index,q in enumerate(questions)]
    response = requests.post(f'{BASE}/quiz/{mid}/submit',json={'student_id':student,'answers':answers},timeout=20)
    response.raise_for_status()
    return response.json()


def open_profile(student):
    app = AppTest.from_file(str(ROOT/'student_portal.py'))
    app.query_params['student']=student
    app.query_params['section']='lesson'
    app.run(timeout=40)
    record('Adaptive page loads without exceptions',not app.exception)
    return app


alice,bob = prefix+'_a',prefix+'_b'
a = submit(alice,'mat_01',{0,1})
b = submit(bob,'mat_01',{3,4})
record('Demonstration profiles have the same score',a['score']==b['score']==60)
app_a,app_b = open_profile(alice),open_profile(bob)
record('A shows the learner-specific concept',any('Обучение с учителем' in value.value and 'В фокусе:' in value.value for value in app_a.caption))
record('B shows different gaps at the same grade',any('Признаки объекта' in value.value and 'В фокусе:' in value.value for value in app_b.caption))
record('Reason and route are available',any(expander.label=='Почему выбран этот шаг и что делать' for expander in app_a.expander))
record('Targeted remediation is visible',any(heading.value=='Что стоит закрепить' for heading in app_a.subheader))
record('A links a concrete lesson fragment',any('Что значит' in expander.label for expander in app_a.expander))
app_a.button(key='nav_progress').click().run(timeout=40)
record('Knowledge profile contains all twenty course concepts',any('Понятие' in frame.value.columns and len(frame.value)==20 for frame in app_a.dataframe))
record('Practice does not grant a successful-test reward',a['points_awarded']==0 and a['progress']['total_points']==0)

student = prefix+'_dependency'
submit(student,'mat_03',{0,1,2})
dependency = open_profile(student)
record('An advanced-topic failure opens the foundation',dependency.session_state['selected_material']=='mat_01')
dependency.selectbox(key='selected_material').set_value('mat_03').run(timeout=40)
next(button for button in dependency.button if button.label=='Открыть рекомендованный шаг').click().run(timeout=40)
record('Recommended-step button returns to the prerequisite',not dependency.exception and dependency.session_state['selected_material']=='mat_01')

student = prefix+'_review'
submit(student,'mat_01',set())
submit(student,'mat_01',{0,1,2,3,4})
review = open_profile(student)
record('Failed retake keeps historical mastery and requests review',any('Восстановление понимания' in value.value for value in review.markdown))
review.button(key='nav_progress').click().run(timeout=40)
record('Successful history creates a review calendar',any('Интервал, дней' in frame.value.columns for frame in review.dataframe))
review.button(key='nav_rewards').click().run(timeout=40)
record('Review maintains the original reward',any('20 XP всего' in value.value for value in review.markdown))

report = {'verified_at':datetime.now(timezone.utc).isoformat(),'profiles':[alice,bob,prefix+'_dependency',student],'checks':checks,'passed':sum(item['passed'] for item in checks),'total':len(checks)}
(ROOT/'project_results/current_adaptive_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total']}))
