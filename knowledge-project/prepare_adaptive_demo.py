"""Create three explicit synthetic demonstration profiles once; never reset history."""
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8006'


def prepare():
    quizzes = json.loads((ROOT/'quizzes.json').read_text(encoding='utf-8'))
    cases = [('adaptive_demo_a','mat_01',{0,1}),('adaptive_demo_b','mat_01',{3,4}),('adaptive_demo_prerequisite','mat_03',{0,1,2})]
    results = []
    for student,mid,wrong in cases:
        progress = requests.get(f'{BASE}/progress/{student}',timeout=20)
        progress.raise_for_status()
        created = not progress.json()['attempts']
        if created:
            questions = quizzes[mid]['questions']
            answers = [(q['correct']+1)%len(q['options']) if index in wrong else q['correct'] for index,q in enumerate(questions)]
            response = requests.post(f'{BASE}/quiz/{mid}/submit',json={'student_id':student,'answers':answers},timeout=20)
            response.raise_for_status()
        path = requests.get(f'{BASE}/learning-path/{student}',timeout=20)
        path.raise_for_status()
        adaptive = path.json()['adaptive']
        results.append({'student':student,'created':created,'url':f'http://localhost:8501/?student={student}&discipline=machine_learning',
            'mode':adaptive['recommendation']['kind'] if adaptive['recommendation'] else None,
            'focus':adaptive['recommendation']['focus_concepts'] if adaptive['recommendation'] else [],
            'reason':adaptive['recommendation']['reason'] if adaptive['recommendation'] else None})
    (ROOT/'project_results/adaptive_demo_profiles.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'student':item['student'],'created':item['created'],'mode':item['mode']} for item in results]))
    return results


if __name__=='__main__':
    prepare()
