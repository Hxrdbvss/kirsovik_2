"""Exercise the live UI and the model; keep a reproducible verification record."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent
student = 'ui_check_' + uuid.uuid4().hex[:10]
checks = []


def record(name, condition, details=None):
    checks.append({'name': name, 'passed': bool(condition), 'details': details})
    if not condition:
        raise AssertionError(name)


at = AppTest.from_file(str(ROOT / 'student_portal.py')).run(timeout=30)
at.text_input[0].set_value(student).run(timeout=30)
record('UI loads without exceptions', not at.exception)
record('Student identifier is saved in URL', at.query_params.get('student') == student)
record('Course map is present', any(tab.label == 'Карта курса' for tab in at.tabs))


def click(label):
    next(button for button in at.button if button.label == label).click().run(timeout=30)
    record(f'UI action: {label}', not at.exception)


click('Отметить материал изученным')
click('Проверить ответы')
record('Empty quiz is rejected in UI', any('пять вопросов' in item.value for item in at.warning))
questions = json.loads((ROOT / 'quizzes.json').read_text(encoding='utf-8'))['mat_01']['questions']
for correct, expected_action in [(0, 'repeat'), (3, 'practice'), (5, 'advance')]:
    for index, question in enumerate(questions):
        at.radio[index].set_value(question['correct'] if index < correct else (question['correct'] + 1) % len(question['options']))
    click('Проверить ответы')
    result = at.session_state['quiz_feedback']['result']
    record(f'UI adaptive branch: {expected_action}', result['action'] == expected_action, {'score': result['score']})
click('Проверить ответы')
progress = requests.get(f'http://127.0.0.1:8006/progress/{student}', timeout=10).json()
record('Live UI retake does not duplicate rewards', progress['total_points'] == 30, {'points': progress['total_points']})
record('All attempts persisted', len(progress['attempts']) == 4)
click('Перейти к следующей теме')
record('Next-topic button changes selected material', at.session_state['selected_material'] == 'mat_02')

click('Рассчитать оценку риска')
record('Risk result is retained in session state', at.session_state['risk_result']['student'] == student)
at.selectbox(key='selected_material').set_value('mat_01').run(timeout=30)
record('Changing lesson preserves the last risk result', at.session_state['risk_result']['student'] == student)

payload = {'student_id': student, 'code_module': 'AAA', 'date_registration': -30, 'num_of_prev_attempts': 0,
           'studied_credits': 60, 'vle_clicks': 0, 'vle_records': 0, 'submitted_count': 0, 'topic_query': 'Деревья решений'}
response = requests.post('http://127.0.0.1:8006/student-dashboard', json=payload, timeout=30)
record('Live OULAD inference through unified API', response.status_code == 200)
risk = response.json()['adaptive']['risk']
record('Risk score is in valid range', 0 <= risk['risk_score'] <= 1, risk)
payload['code_module'] = 'UNKNOWN'
response = requests.post('http://127.0.0.1:8007/predict-risk', json={key: value for key, value in payload.items() if key not in {'student_id', 'topic_query'}}, timeout=10)
record('Unknown OULAD module is rejected', response.status_code == 422)

report = {'verified_at': datetime.now(timezone.utc).isoformat(), 'student': student, 'checks': checks,
          'passed': sum(item['passed'] for item in checks), 'total': len(checks)}
(ROOT / 'project_results' / 'current_demo_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
