import json
import unittest

from tests import test_studio_api as _studio
from liveclips import store as store_module


class LearningApiTests(unittest.TestCase):
    # reaproveita só a preparação do teste da API do Estúdio, sem herdar os testes dele
    setUp = _studio.StudioApiTests.setUp
    close = _studio.StudioApiTests.close
    post = _studio.StudioApiTests.post

    def test_project_get_exposes_agent_context(self):
        code, got = self.post('/api/project/get', dict(id=self.item['id']))
        self.assertEqual(code, 200)
        for key in ('confidence', 'refinement', 'edges', 'refine', 'llm_titles', 'cut_warnings'):
            self.assertIn(key, got)
        self.assertEqual(got['cut_warnings'], [])
        self.assertEqual(got['profile']['second_pass'], 'small')   # 0.17: legenda precisa é o padrão

    def test_learning_details_shape_is_stable_when_there_is_no_data(self):
        code, got = self.post('/api/learning/details', dict(streamer=self.streamer))
        self.assertEqual(code, 200)
        self.assertIn('habits', got)
        self.assertIn('notes', got['habits'])
        self.assertFalse(got['styles']['enough'])
        self.assertIsInstance(got['calibration'], (list, dict))

    def test_accepting_a_term_does_not_trigger_reanalysis(self):
        before = store_module.analysis_key(self.app.store.streamer(self.streamer)['profile'])
        code, got = self.post('/api/learning/accept-term', dict(streamer=self.streamer, term='Coringa'))
        self.assertEqual(code, 200)
        self.assertIn('Coringa', got['learned_terms'])
        after = store_module.analysis_key(self.app.store.streamer(self.streamer)['profile'])
        self.assertEqual(before, after)
        self.post('/api/learning/accept-term', dict(streamer=self.streamer, term='coringa'))
        self.assertEqual(self.app.store.streamer(self.streamer)['profile']['learned_terms'].lower().count('coringa'), 1)
        code, _ = self.post('/api/learning/accept-term', dict(streamer=self.streamer, term='x'))
        self.assertEqual(code, 400)

    def test_refine_request_is_queued_and_visible(self):
        code, _ = self.post('/api/captions/refine', dict(id=self.item['id']))
        self.assertEqual(code, 200)
        self.assertEqual(self.app.engine.refine_queue, [(self.item['id'], 'small')])
        code, got = self.post('/api/project/get', dict(id=self.item['id']))
        self.assertEqual(got['refine']['status'], 'queued')
        code, _ = self.post('/api/captions/refine', dict(id='nao-existe'))
        self.assertEqual(code, 400)


if __name__ == '__main__':
    unittest.main()
