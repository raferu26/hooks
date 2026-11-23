import tempfile
import unittest
from unittest.mock import patch

from liveclips.engine import Engine
from liveclips.store import Store
from tests.helpers import setup_session


class Fairness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        setup_session(self.store)
        self.engine = Engine(self.store)

    def test_long_export_queue_does_not_starve_analysis(self):
        order = []
        with patch.object(self.engine, '_refine_step', return_value=False), \
             patch.object(self.engine, '_render_jobs', side_effect=lambda *a: order.append('render') or True), \
             patch.object(self.engine, '_session_step', side_effect=lambda *a: order.append('analise') or True), \
             patch.object(self.store, 'setting', return_value=False):
            for _ in range(9):
                self.engine.work_once()
        self.assertEqual(order[:4], ['render', 'render', 'render', 'analise'])
        self.assertGreaterEqual(order.count('analise'), 2)
        self.assertLessEqual(max(len(run) for run in ''.join('r' if x == 'render' else '|' for x in order).split('|')), 3)

    def test_paused_analysis_stays_paused_even_with_exports_waiting(self):
        order = []
        with patch.object(self.engine, '_refine_step', return_value=False), \
             patch.object(self.engine, '_render_jobs', side_effect=lambda *a: order.append('render') or True), \
             patch.object(self.engine, '_session_step', side_effect=lambda *a: order.append('analise') or True), \
             patch.object(self.store, 'setting', return_value=True):
            for _ in range(8):
                self.engine.work_once()
        self.assertNotIn('analise', order)


if __name__ == '__main__':
    unittest.main()
