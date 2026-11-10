"""Regression checks for assessment, rewards and persistent learning state."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
import learning_core as core


class LearningFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.old_database = core.PROGRESS_DB
        core.PROGRESS_DB = Path(self.directory.name) / 'test.db'
        app = FastAPI()
        app.include_router(core.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        core.PROGRESS_DB = self.old_database
        self.directory.cleanup()

    def submit(self, correct, student='test', material='mat_01'):
        questions = core.quizzes()[material]['questions']
        answers = [q['correct'] if i < correct else (q['correct'] + 1) % len(q['options']) for i, q in enumerate(questions)]
        response = self.client.post(f'/quiz/{material}/submit', json={'student_id': student, 'answers': answers})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_three_adaptive_branches_and_next_topic(self):
        for correct, score, action in [(0, 0, 'repeat'), (2, 40, 'repeat'), (3, 60, 'practice'), (4, 80, 'advance')]:
            result = self.submit(correct)
            self.assertEqual((result['score'], result['action']), (score, action))
            self.assertEqual(result['points_awarded'], 20 if action == 'advance' else 0)
        path = self.client.get('/learning-path/test').json()
        self.assertEqual(path['recommended_material_id'], 'mat_02')
        self.assertTrue(next(m for m in path['materials'] if m['id'] == 'mat_01')['mastered'])

    def test_repeated_success_cannot_farm_points(self):
        self.assertEqual(self.submit(5)['points_awarded'], 20)
        self.assertEqual(self.submit(5)['points_awarded'], 0)
        self.assertEqual(self.client.get('/progress/test').json()['total_points'], 20)

    def test_failed_retake_preserves_previously_mastered_topic(self):
        self.submit(5)
        self.submit(0)
        path = self.client.get('/learning-path/test').json()
        material = next(m for m in path['materials'] if m['id'] == 'mat_01')
        self.assertEqual((material['latest_score'], material['best_score']), (0, 100))
        self.assertTrue(material['mastered'])

    def test_reading_does_not_replace_assessment(self):
        for _ in range(2):
            response = self.client.post('/progress/complete', json={'student_id': 'test', 'item_type': 'material', 'item_id': 'mat_01'})
            self.assertEqual(response.status_code, 200)
        progress = self.client.get('/progress/test').json()
        self.assertEqual((progress['total_points'], progress['completed_materials'], progress['mastered_topics']), (10, 1, 0))

    def test_no_unknown_materials_or_unverified_tasks(self):
        for item_type, item_id, status in [('material', 'fake', 404), ('task', 'quiz_mat_01', 422)]:
            response = self.client.post('/progress/complete', json={'student_id': 'test', 'item_type': item_type, 'item_id': item_id})
            self.assertEqual(response.status_code, status)
        self.assertEqual(self.client.get('/progress/test').json()['total_points'], 0)

    def test_invalid_answers_leave_no_attempts(self):
        for answers in [[0], [9] * 5, [-1] * 5, [True] * 5, ['0'] * 5]:
            response = self.client.post('/quiz/mat_01/submit', json={'student_id': 'test', 'answers': answers})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get('/progress/test').json()['attempts'], [])
        response = self.client.post('/quiz/mat_01/submit', json={'student_id': 'bad/id', 'answers': [0] * 5})
        self.assertEqual(response.status_code, 422)

    def test_quiz_get_does_not_expose_answer_key(self):
        data = self.client.get('/quiz/mat_01').json()
        self.assertEqual(len(data['questions']), 5)
        self.assertTrue(all('correct' not in question for question in data['questions']))

    def test_students_have_separate_persistent_history(self):
        self.submit(5, student='alice')
        self.assertEqual(self.client.get('/progress/bob').json()['total_points'], 0)
        app = FastAPI()
        app.include_router(core.router)
        with TestClient(app) as second_client:
            self.assertEqual(second_client.get('/progress/alice').json()['completed_tasks'], 1)

    def test_concurrent_success_awards_points_once(self):
        core.init_progress_db()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.submit(5), range(4)))
        self.assertEqual(sum(item['points_awarded'] for item in results), 20)
        self.assertEqual(len(self.client.get('/progress/test').json()['attempts']), 4)

    def test_complete_course_reaches_level_two(self):
        for material in core.materials():
            self.client.post('/progress/complete', json={'student_id': 'test', 'item_type': 'material', 'item_id': material['id']})
            self.submit(5, material=material['id'])
        path = self.client.get('/learning-path/test').json()
        self.assertIsNone(path['recommended_material_id'])
        self.assertEqual((path['progress']['total_points'], path['progress']['level']), (120, 2))
        self.assertIn('Все темы освоены', path['progress']['achievements'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
