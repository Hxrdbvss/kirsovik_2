"""Isolated regression checks for enrollment, migration, seed data and admin access."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import academy_core as academy
import learning_core as learning


class AcademyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(learning, 'PROGRESS_DB', Path(self.directory.name)/'test.db')
        self.database_patch.start()
        self.password_patch = patch.dict(os.environ, {'LEARNING_ADMIN_PASSWORD':'test-password-only'})
        self.password_patch.start()
        academy._login_failures.clear()
        app = FastAPI()
        app.include_router(learning.router)
        app.include_router(academy.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.password_patch.stop()
        self.database_patch.stop()
        self.directory.cleanup()

    def auth(self):
        result = self.client.post('/admin/login',json={'username':'admin','password':'test-password-only'})
        self.assertEqual(result.status_code,200,result.text)
        return {'Authorization':'Bearer '+result.json()['token']}

    def test_seed_counts_and_plan_relationships(self):
        data = self.client.get('/academy/catalog').json()
        self.assertEqual(len(data['groups']),2)
        self.assertEqual(len(data['disciplines']),10)
        self.assertEqual(len(data['demo_students']),30)
        for group in data['groups']:
            self.assertEqual(len(group['discipline_ids']),8)
            self.assertEqual(sum(s['group_id']==group['id'] for s in data['demo_students']),15)
        self.assertEqual(len(learning.all_materials()),22)
        self.assertEqual(sum(len(q['questions']) for q in learning.quizzes().values()),110)

    def test_import_is_idempotent_and_preserves_existing_history(self):
        learning.init_progress_db()
        with academy.connect() as db:
            db.execute("INSERT INTO completions (student_id,item_type,item_id) VALUES ('existing','material','mat_01')")
        academy.ensure_academy()
        with academy.connect() as db:
            before = db.execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0]
            db.execute("UPDATE students SET full_name='Изменённое имя' WHERE id='demo_pi_21_001'")
        academy.ensure_academy()
        with academy.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0],before)
            self.assertEqual(db.execute("SELECT full_name FROM students WHERE id='demo_pi_21_001'").fetchone()[0],'Изменённое имя')
        self.assertEqual(learning.get_progress('existing')['total_points'],10)

    def test_all_seed_scores_are_reproducible_from_answers(self):
        academy.ensure_academy()
        quizzes = learning.quizzes()
        with academy.connect() as db:
            attempts = db.execute('SELECT * FROM quiz_attempts').fetchall()
        self.assertGreater(len(attempts),100)
        for attempt in attempts:
            questions = quizzes[attempt['material_id']]['questions']
            answers = json.loads(attempt['answers'])
            correct = sum(answer==q['correct'] for answer,q in zip(answers,questions))
            self.assertEqual(attempt['score'],round(correct/len(questions)*100))

    def test_enrollment_blocks_foreign_courses_and_accepts_assigned_ones(self):
        self.assertEqual(self.client.get('/learning-path/demo_pi_21_001?discipline_id=networks').status_code,403)
        self.assertEqual(self.client.get('/learning-path/demo_ivt_21_001?discipline_id=networks').status_code,200)
        self.assertEqual(self.client.post('/progress/complete',json={'student_id':'demo_pi_21_001','item_type':'material','item_id':'networks_01'}).status_code,403)
        answers = [q['correct'] for q in learning.quizzes()['networks_01']['questions']]
        self.assertEqual(self.client.post('/quiz/networks_01/submit',json={'student_id':'demo_pi_21_001','answers':answers}).status_code,403)
        self.assertEqual(self.client.get('/learning-path/free?discipline_id=missing').status_code,404)

    def test_course_progress_is_scoped_but_experience_is_global(self):
        for material in ['mat_01','python_01']:
            answers = [q['correct'] for q in learning.quizzes()[material]['questions']]
            self.assertEqual(self.client.post(f'/quiz/{material}/submit',json={'student_id':'scope','answers':answers}).status_code,200)
        ml = self.client.get('/progress/scope').json()
        python = self.client.get('/progress/scope?discipline_id=python').json()
        self.assertEqual((ml['mastered_topics'],python['mastered_topics']),(1,1))
        self.assertEqual((ml['total_topics'],python['total_topics']),(4,2))
        self.assertEqual((ml['course_points'],python['course_points']),(20,20))
        self.assertEqual((ml['total_points'],python['total_points']),(40,40))
        self.assertEqual([a['material_id'] for a in python['attempts']],['python_01'])

    def test_admin_routes_require_valid_session_and_logout_revokes_it(self):
        for method,path in [('get','/admin/overview'),('get','/admin/students/demo_pi_21_001'),('post','/admin/students'),('put','/admin/students/x')]:
            self.assertEqual(getattr(self.client,method)(path,**({'json':{'id':'x','full_name':'Тестовый Студент','group_id':'pi_21'}} if method!='get' else {})).status_code,401)
        self.assertEqual(self.client.post('/admin/login',json={'username':'admin','password':'wrong'}).status_code,401)
        headers = self.auth()
        self.assertEqual(self.client.get('/admin/overview',headers=headers).json()['summary']['students'],30)
        self.assertEqual(self.client.post('/admin/logout',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/admin/overview',headers=headers).status_code,401)

    def test_create_edit_archive_preserves_history_and_blocks_learning(self):
        headers = self.auth()
        payload = {'id':'added_student','full_name':'Тестовый Студент','group_id':'pi_21','active':True}
        self.assertEqual(self.client.post('/admin/students',json=payload,headers=headers).status_code,200)
        self.assertEqual(self.client.post('/admin/students',json=payload,headers=headers).status_code,409)
        self.client.post('/progress/complete',json={'student_id':payload['id'],'item_type':'material','item_id':'mat_01'})
        payload.update(full_name='Новое Имя Студента',group_id='ivt_21',active=False)
        self.assertEqual(self.client.put('/admin/students/added_student',json=payload,headers=headers).status_code,200)
        self.assertEqual(self.client.get('/academy/profile/added_student').status_code,403)
        self.assertEqual(self.client.get('/progress/added_student').status_code,403)
        self.assertEqual(self.client.get('/progress/added_student?_check_access=false').status_code,403)
        detail = self.client.get('/admin/students/added_student',headers=headers).json()
        self.assertEqual(detail['student']['full_name'],payload['full_name'])
        self.assertEqual(detail['student']['total_points'],10)
        self.assertEqual(len(detail['courses']),8)
        self.assertNotIn('added_student',[s['id'] for s in self.client.get('/academy/catalog').json()['demo_students']])


if __name__ == '__main__':
    unittest.main()
