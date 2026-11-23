import tempfile
import unittest

from liveclips import telemetry as tel


class ModeTests(unittest.TestCase):
    def test_default_matches_previous_encode(self):
        self.assertEqual(('medium', '18'), tel.encode_args({}))
        self.assertEqual(('medium', '18'), tel.encode_args({'quality_mode': 'nao_existe'}))

    def test_modes_ordered_by_effort(self):
        self.assertEqual(('veryfast', '21'), tel.encode_args({'quality_mode': 'rapido'}))
        self.assertLessEqual(tel.MODES['entrega']['crf'], tel.MODES['qualidade']['crf'])
        for mode in tel.MODES.values():
            self.assertLessEqual(mode['revisoes'], 2)


class StatsTests(unittest.TestCase):
    def test_percentile(self):
        self.assertIsNone(tel.percentile([], .5))
        self.assertEqual(5, tel.percentile([5], .95))
        self.assertAlmostEqual(2.5, tel.percentile([1, 2, 3, 4], .5))
        self.assertAlmostEqual(3.85, tel.percentile([1, 2, 3, 4], .95))

    def test_recorder_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = tel.Telemetry(tmp)
            for s in (1, 2, 3, 10):
                t.record('render', s)
            t.record('qc', .5)
            with self.assertRaises(ValueError):
                with t.stage('analise'):
                    raise ValueError('x')
            report = t.report()
            self.assertEqual('render', report['gargalo'])
            self.assertEqual(4, report['etapas']['render']['n'])
            self.assertEqual(1, report['etapas']['analise']['erros'])
            self.assertIsNotNone(report['aviso'])               # menos de 20 amostras

    def test_corrupt_line_ignored_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = tel.Telemetry(tmp)
            self.assertEqual([], t.rows())
            t.path.write_text('{ruim\n{"stage":"a","seconds":1}\n', encoding='utf-8')
            self.assertEqual(1, len(t.rows()))


if __name__ == '__main__':
    unittest.main()
