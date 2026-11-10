import csv
import io
import unittest

from portal_ui import progress_csv


class ProgressExportTests(unittest.TestCase):
    def test_csv_preserves_cyrillic_scores_and_all_attempts(self):
        progress = {'attempts': [
            {'material_id': 'mat_01', 'score': 0, 'correct_count': 0, 'question_count': 5, 'created_at': '2026-11-09 10:00:00'},
            {'material_id': 'mat_01', 'score': 100, 'correct_count': 5, 'question_count': 5, 'created_at': '2026-11-09 10:02:00'},
        ]}
        data = progress_csv(progress, {'mat_01': {'topic': 'Основы машинного обучения'}})
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0], 'Основы машинного обучения')
        self.assertEqual([rows[1][1], rows[2][1]], ['0', '100'])
        self.assertEqual(rows[2][4], '2026-11-09 10:02:00')

    def test_empty_history_still_has_valid_header(self):
        rows = list(csv.reader(io.StringIO(progress_csv({'attempts': []}, {}).decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 5)

    def test_history_survives_removed_catalog_entry(self):
        progress = {'attempts': [{'material_id': 'archived_topic', 'score': 80, 'correct_count': 4, 'question_count': 5, 'created_at': '2026-11-09 10:00:00'}]}
        self.assertIn('archived_topic', progress_csv(progress, {}).decode('utf-8-sig'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
