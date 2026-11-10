"""Explainable, rule-based routing from answer-level evidence and topic prerequisites.

Observed accuracy is not a probability of knowledge. Existing rewards and historical
mastery remain independent of the current recommendation and review schedule.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

CATALOG = Path(__file__).resolve().parent.parent/'learning-content/adaptive_catalog.json'


def policy_catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def section_excerpt(content, number):
    parts = re.split(r'(?=^### \d+\.)', content, flags=re.M)
    return next((part.strip() for part in parts if re.match(rf'^### {number}\.', part)), '')


def parse_time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def build_adaptive_state(materials, quizzes, history, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    policy = policy_catalog()
    catalog = {material['id']:material for material in materials}
    profiles = {}
    for mid, material in catalog.items():
        questions = quizzes[mid]['questions']
        mapping = {item['question_id']:item for item in policy[mid]['concepts']}
        observations = []
        for attempt in sorted((row for row in history if row['material_id']==mid), key=lambda row:row['id']):
            try:
                answers = json.loads(attempt['answers']) if isinstance(attempt['answers'],str) else attempt['answers']
                if len(answers)!=len(questions) or any(type(a) is not int or not 0 <= a < len(q['options']) for a,q in zip(answers,questions)):
                    continue
                observations.append({**attempt,'correct':[a==q['correct'] for a,q in zip(answers,questions)]})
            except (ValueError, TypeError, KeyError):
                continue
        recent = observations[-3:]
        weights = list(range(1,len(recent)+1))
        concepts = []
        for index, question in enumerate(questions):
            definition = mapping[question['id']]
            correctness = [row['correct'][index] for row in recent]
            accuracy = round(100*sum(weight*value for weight,value in zip(weights,correctness))/sum(weights),1) if weights else None
            fragment = section_excerpt(material['content'],definition['section'])
            concepts.append({**definition,'observations':len(recent),'recent_accuracy':accuracy,
                'last_correct':correctness[-1] if correctness else None,
                'repeated_error':len(correctness)>=2 and not any(correctness[-2:]),
                'needs_review':bool(correctness) and not correctness[-1],
                'review_section':fragment.splitlines()[0].removeprefix('### ') if fragment else f'Раздел {definition["section"]}',
                'review_excerpt':fragment})
        recent_score = round(sum(weight*row['score'] for weight,row in zip(weights,recent))/sum(weights),1) if recent else None
        change = recent[-1]['score']-recent[-2]['score'] if len(recent)>=2 else None
        trend = 'growing' if change is not None and change>=20 else 'declining' if change is not None and change<=-20 else 'stable' if change is not None else 'unknown'
        passed = any(row['score']>=80 for row in observations)
        consecutive_passes = 0
        for row in reversed(observations):
            if row['score']<80:
                break
            consecutive_passes += 1
        interval = [3,7,14][min(max(consecutive_passes,1),3)-1]
        latest_pass = next((row for row in reversed(observations) if row['score']>=80),None)
        last_success_time = parse_time(latest_pass['created_at']) if latest_pass else None
        review_at = last_success_time+timedelta(days=interval) if last_success_time else None
        weak = sorted((item for item in concepts if item['needs_review']), key=lambda item:(not item['repeated_error'],item['recent_accuracy'],item['question_id']))
        profiles[mid] = {'material_id':mid,'topic':material['topic'],'prerequisites':policy[mid]['prerequisites'],
            'concepts':concepts,'weak_concepts':weak,'recent_score':recent_score,'trend':trend,'score_change':change,
            'evidence_attempts':len(observations),'latest_score':observations[-1]['score'] if observations else None,
            'latest_attempt_id':observations[-1]['id'] if observations else -1,
            'mastered':bool(material.get('mastered',passed)),
            'repeated_difficulty':len(recent)>=2 and all(row['score']<80 for row in recent[-2:]),
            'next_review_at':review_at.strftime('%Y-%m-%d %H:%M:%S') if review_at else None,
            'review_interval_days':interval if review_at else None,
            'review_due':bool(review_at and review_at<=now)}

    def missing_foundations(mid, visiting=None):
        visiting = set(visiting or ())
        if mid in visiting:
            raise ValueError('Cycle in the topic prerequisite graph.')
        visiting.add(mid)
        for parent in profiles[mid]['prerequisites']:
            if parent not in profiles:
                raise ValueError('Prerequisite is outside the selected discipline.')
            ancestor = missing_foundations(parent, visiting)
            if ancestor:
                return ancestor
            base = profiles[parent]
            if not base['mastered'] or (base['latest_score'] is not None and base['latest_score']<80):
                return parent
        return None

    due = sorted([{'material_id':mid,'topic':item['topic'],'next_review_at':item['next_review_at']} for mid,item in profiles.items() if item['review_due']],key=lambda item:(item['next_review_at'],item['material_id']))
    recommendation = None
    failing = sorted((item for item in profiles.values() if item['latest_score'] is not None and item['latest_score']<80),key=lambda item:item['latest_attempt_id'],reverse=True)
    if failing:
        target = failing[0]
        foundation = missing_foundations(target['material_id'])
        if foundation:
            recommendation = {'material_id':foundation,'target_material_id':target['material_id'],'kind':'prerequisite',
                'reason':f'В теме «{target["topic"]}» последний результат {target["latest_score"]} %. Сначала закрепите связанную базовую тему «{profiles[foundation]["topic"]}»; затем вернитесь к затруднению.'}
        else:
            kind = 'review' if target['mastered'] else 'example' if target['repeated_difficulty'] else 'practice' if target['latest_score']>=50 else 'repair'
            reason = f'Последний результат по теме «{target["topic"]}» — {target["latest_score"]} %.'
            if target['repeated_difficulty']:
                reason += ' Две последние попытки ниже 80 %: сначала разберите пример и конкретные ошибки.'
            elif target['trend']=='growing':
                reason += ' Результат вырос: закрепите оставшиеся пробелы прицельной практикой.'
            elif target['trend']=='declining':
                reason += ' В последних попытках результат снизился: проверьте конкретные понятия.'
            else:
                reason += ' Следующий шаг выбран по ошибкам в отдельных понятиях.'
            if target['mastered']:
                reason += ' Прежнее освоение и награда сохраняются.'
            recommendation = {'material_id':target['material_id'],'target_material_id':target['material_id'],'kind':kind,'reason':reason}
    else:
        next_topic = next((item for item in profiles.values() if not item['mastered'] and not missing_foundations(item['material_id'])),None)
        if next_topic:
            recommendation = {'material_id':next_topic['material_id'],'target_material_id':next_topic['material_id'],'kind':'new',
                'reason':'Выбрана следующая неосвоенная тема с доступными предпосылками. Изучите объяснение, выполните задание и проверьте понимание.'}
        elif due:
            recommendation = {'material_id':due[0]['material_id'],'target_material_id':due[0]['material_id'],'kind':'scheduled_review',
                'reason':f'Все темы освоены. Для «{due[0]["topic"]}» наступил срок повторения: {due[0]["next_review_at"]} UTC. Подтвердите понимание без повторного начисления награды.'}
    if recommendation:
        selected = profiles[recommendation['material_id']]
        focus = selected['weak_concepts'][:3]
        recommendation['focus_concepts'] = [item['name'] for item in focus]
        recommendation['steps'] = [
            {'kind':'read','title':'Разобрать указанные разделы' if focus else 'Изучить объяснение и разобранный пример',
             'detail':'; '.join(dict.fromkeys(item['review_section'] for item in focus)) if focus else catalog[selected['material_id']]['summary']},
            {'kind':'practice','title':'Выполнить задания по пробелам' if focus else 'Выполнить самостоятельное задание',
             'detail':'\n'.join(item['exercise'] for item in focus) if focus else catalog[selected['material_id']]['assignment']},
            {'kind':'quiz','title':'Проверить понимание повторным тестом','detail':'Рекомендация обновится после отправки ответов. Награда за освоение выдаётся один раз.'}]
    return {'version':'rule-based-v2','evidence_window':3,'profiles':profiles,'recommendation':recommendation,'due_reviews':due,
        'observed_concepts':sum(concept['observations']>0 for item in profiles.values() for concept in item['concepts']),
        'weak_concepts':sum(concept['needs_review'] for item in profiles.values() for concept in item['concepts']),
        'method_note':'Диагностика по ответам и правилам, не вероятность знания. Используются до трёх последних попыток с весами 1…n; поздние ответы имеют больший вес. Интервалы повторения 3, 7 и 14 дней — проектные настройки.'}
