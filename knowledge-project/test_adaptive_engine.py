"""Behavioral checks for personalized routing; equal grades need not mean equal needs."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import learning_core as learning
from adaptive_engine import build_adaptive_state, policy_catalog, section_excerpt


class AdaptiveEngineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(learning,'PROGRESS_DB',Path(self.directory.name)/'test.db')
        self.db_patch.start()
        app = FastAPI()
        app.include_router(learning.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db_patch.stop()
        self.directory.cleanup()

    def submit(self, student, mid='mat_01', wrong=()):
        questions = learning.quizzes()[mid]['questions']
        answers = [(q['correct']+1)%len(q['options']) if index in wrong else q['correct'] for index,q in enumerate(questions)]
        response = self.client.post(f'/quiz/{mid}/submit',json={'student_id':student,'answers':answers})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def path(self, student, discipline='machine_learning'):
        response = self.client.get(f'/learning-path/{student}',params={'discipline_id':discipline})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_equal_scores_different_errors_produce_different_exercises(self):
        alice = self.submit('alice',wrong=(0,1))
        bob = self.submit('bob',wrong=(3,4))
        self.assertEqual((alice['score'],bob['score']),(60,60))
        a,b = alice['adaptive']['profiles']['mat_01'],bob['adaptive']['profiles']['mat_01']
        self.assertEqual({c['question_id'] for c in a['weak_concepts']},{'ml1','ml2'})
        self.assertEqual({c['question_id'] for c in b['weak_concepts']},{'ml4','ml5'})
        self.assertNotEqual(alice['adaptive']['recommendation']['steps'][1]['detail'],bob['adaptive']['recommendation']['steps'][1]['detail'])
        self.assertTrue(all(c['review_excerpt'].startswith('### ') for c in a['weak_concepts']))

    def test_same_latest_grade_different_histories_change_support_mode(self):
        self.submit('rising',wrong=(0,1,2,3))
        rising = self.submit('rising',wrong=(0,1))['adaptive']
        self.submit('falling')
        falling = self.submit('falling',wrong=(0,1))['adaptive']
        self.assertEqual(rising['profiles']['mat_01']['latest_score'],falling['profiles']['mat_01']['latest_score'])
        self.assertEqual(rising['profiles']['mat_01']['trend'],'growing')
        self.assertEqual(falling['profiles']['mat_01']['trend'],'declining')
        self.assertEqual(rising['recommendation']['kind'],'example')
        self.assertEqual(falling['recommendation']['kind'],'review')

    def test_recent_window_discards_old_errors_and_weights_recent_answers(self):
        self.submit('window',wrong=(0,1,2,3,4))
        for _ in range(3):
            self.submit('window')
        state = self.path('window')['adaptive']['profiles']['mat_01']
        self.assertEqual(state['recent_score'],100)
        self.assertTrue(all(c['observations']==3 and c['recent_accuracy']==100 for c in state['concepts']))
        self.submit('weighted')
        last = self.submit('weighted',wrong=(0,))['adaptive']['profiles']['mat_01']
        self.assertEqual(last['concepts'][0]['recent_accuracy'],33.3)
        self.assertFalse(last['concepts'][0]['last_correct'])

    def test_failure_in_a_later_branch_routes_to_its_actual_foundation(self):
        blocked = self.submit('branch',mid='mat_04',wrong=(0,1,2))['adaptive']['recommendation']
        self.assertEqual((blocked['material_id'],blocked['target_material_id'],blocked['kind']),('mat_01','mat_04','prerequisite'))
        self.submit('branch',mid='mat_01')
        # After repairing the foundation, resume the pending branch rather than catalog item 2.
        resumed = self.path('branch')['adaptive']['recommendation']
        self.assertEqual(resumed['material_id'],'mat_04')

    def test_transitive_prerequisite_chain_is_followed(self):
        recommendation = self.submit('chain',mid='mat_03',wrong=(0,1,2))['adaptive']['recommendation']
        self.assertEqual(recommendation['material_id'],'mat_01')
        self.submit('chain',mid='mat_01')
        self.assertEqual(self.path('chain')['recommended_material_id'],'mat_02')
        self.submit('chain',mid='mat_02')
        self.assertEqual(self.path('chain')['recommended_material_id'],'mat_03')

    def test_repeated_error_gets_priority_and_specific_excerpt(self):
        self.submit('repeat',wrong=(0,1))
        state = self.submit('repeat',wrong=(1,2))['adaptive']['profiles']['mat_01']
        self.assertEqual(state['weak_concepts'][0]['question_id'],'ml2')
        self.assertTrue(state['weak_concepts'][0]['repeated_error'])
        self.assertIn('Что значит',state['weak_concepts'][0]['review_section'])

    def test_a_failed_retake_requests_review_without_losing_rewards(self):
        self.submit('retake')
        result = self.submit('retake',wrong=(0,1,2,3,4))
        self.assertEqual(result['adaptive']['recommendation']['kind'],'review')
        self.assertTrue(result['adaptive']['profiles']['mat_01']['mastered'])
        self.assertEqual(result['progress']['total_points'],20)
        self.assertEqual(result['points_awarded'],0)
        self.assertEqual(self.submit('retake')['points_awarded'],0)

    def test_fresh_success_does_not_schedule_an_immediate_loop(self):
        for material in learning.materials():
            self.submit('finished',mid=material['id'])
        path = self.path('finished')
        self.assertIsNone(path['recommended_material_id'])
        self.assertFalse(path['adaptive']['due_reviews'])

    def test_review_intervals_and_due_dates_are_deterministic(self):
        now = datetime(2026,11,10,12,tzinfo=timezone.utc)
        material = learning.materials()[0]
        answers = [q['correct'] for q in learning.quizzes()['mat_01']['questions']]
        for count,interval in [(1,3),(2,7),(3,14),(4,14)]:
            history = [{'id':i,'material_id':'mat_01','answers':answers,'score':100,'created_at':'2026-11-01 12:00:00'} for i in range(count)]
            state = build_adaptive_state([material],learning.quizzes(),history,now)
            profile = state['profiles']['mat_01']
            self.assertEqual(profile['review_interval_days'],interval)
            self.assertEqual(profile['review_due'],interval<=9)
            self.assertEqual(bool(state['recommendation']),interval<=9)

    def test_scheduled_review_has_no_extra_reward(self):
        for material in learning.materials():
            self.submit('due',mid=material['id'])
        import academy_core
        with academy_core.connect() as db:
            db.execute("UPDATE quiz_attempts SET created_at='2020-01-01 00:00:00' WHERE student_id='due'")
        recommendation = self.path('due')['adaptive']['recommendation']
        self.assertEqual(recommendation['kind'],'scheduled_review')
        result = self.submit('due',mid=recommendation['material_id'])
        self.assertEqual(result['points_awarded'],0)
        self.assertEqual(result['progress']['total_points'],80)

    def test_diagnostics_are_isolated_by_student_and_discipline(self):
        self.submit('alice',wrong=(0,))
        self.submit('alice',mid='python_01',wrong=(2,))
        self.assertEqual(self.path('bob')['adaptive']['observed_concepts'],0)
        ml = self.path('alice')['adaptive']
        python = self.path('alice','python')['adaptive']
        self.assertEqual(set(ml['profiles']),{'mat_01','mat_02','mat_03','mat_04'})
        self.assertEqual(set(python['profiles']),{'python_01','python_02'})
        self.assertEqual(python['weak_concepts'],1)

    def test_invalid_answer_history_is_not_treated_as_evidence(self):
        material = learning.materials()[0]
        history = [{'id':1,'material_id':'mat_01','answers':'broken','score':100,'created_at':'2026-11-01 12:00:00'}]
        state = build_adaptive_state([material],learning.quizzes(),history)
        self.assertEqual(state['observed_concepts'],0)
        self.assertEqual(state['profiles']['mat_01']['trend'],'unknown')

    def test_policy_maps_every_question_and_graph_stays_within_disciplines(self):
        policy = policy_catalog()
        materials = {m['id']:m for m in learning.all_materials()}
        self.assertEqual(set(policy),set(materials))
        for mid,entry in policy.items():
            self.assertEqual({c['question_id'] for c in entry['concepts']},{q['id'] for q in learning.quizzes()[mid]['questions']})
            for concept in entry['concepts']:
                self.assertTrue(section_excerpt(materials[mid]['content'],concept['section']))
            def visit(node,parents):
                self.assertNotIn(node,parents)
                for prerequisite in policy[node]['prerequisites']:
                    self.assertEqual(materials[mid]['discipline_id'],materials[prerequisite]['discipline_id'])
                    visit(prerequisite,parents | {node})
            visit(mid,set())


if __name__=='__main__':
    unittest.main(verbosity=2)
