import json
import unittest

from liveclips import markers as M


class Parse(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(M.clock('1:02:03'), 3723)
        self.assertEqual(M.clock('01:23,5'), 83.5)
        self.assertEqual(M.clock(12), 12.0)
        for bad in ('-3', 'abc', '1:2:3:4', float('nan'), ''):
            with self.assertRaises(M.MarkerError):
                M.clock(bad)

    def test_json_csv_txt(self):
        j = json.dumps([{'t': '1:05', 'rotulo': 'clutch', 'antes': 5, 'depois': 7}, 30, {'segundos': 90}, {'x': 1}])
        out = M.parse(j, 'marcadores.json')
        self.assertEqual([m['time'] for m in out], [30.0, 65.0, 90.0])
        self.assertEqual(out[1]['label'], 'clutch')
        self.assertEqual((out[1]['pre'], out[1]['post']), (5.0, 7.0))
        csvt = 'tempo;rotulo;antes;depois\n0:45;ace;6;9\n;sem tempo\n2:00;fim\n'
        out = M.parse(csvt, 'marcadores.csv')
        self.assertEqual([(m['time'], m['label']) for m in out], [(45.0, 'ace'), (120.0, 'fim')])
        out = M.parse('# comentário\n0:10 primeira\n1:00:00 hora cheia\nlixo\n', 'marcadores.txt')
        self.assertEqual([m['time'] for m in out], [10.0, 3600.0])

    def test_rejects(self):
        with self.assertRaises(M.MarkerError):
            M.parse('{', 'a.json')
        with self.assertRaises(M.MarkerError):
            M.parse('1', 'a.xml')
        with self.assertRaises(M.MarkerError):
            M.parse(json.dumps([{'t': 5, 'antes': 999}]), 'a.json')


class Candidates(unittest.TestCase):
    def mk(self, *times, pre=8, post=12):
        return [dict(time=t, label=f'm{t}', pre=pre, post=post) for t in times]

    def test_close_markers_form_one_cut_without_duplicates(self):
        out = M.candidates_from_markers(self.mk(100, 110), 0, 600, 'g')
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual((c['start'], c['end']), (92.0, 122.0))
        self.assertEqual(len(c['markers']), 2)
        self.assertEqual(len(c['protected']), 2)

    def test_far_markers_make_separate_cuts_and_respect_edges(self):
        out = M.candidates_from_markers(self.mk(3, 300), 0, 320, 'g')
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]['start'], 0.0)            # não passa do começo da mídia
        self.assertLessEqual(out[1]['end'], 320)
        self.assertGreaterEqual(out[0]['end'] - out[0]['start'], 15.0)

    def test_many_markers_split_at_max_duration(self):
        out = M.candidates_from_markers(self.mk(*range(100, 400, 10)), 0, 1000, 'g')
        self.assertGreater(len(out), 1)
        for c in out:
            self.assertLessEqual(c['end'] - c['start'], 58.0 + .001)
        covered = sorted(m['time'] for c in out for m in c['markers'])
        self.assertEqual(covered, list(range(100, 400, 10)))      # nenhum marcador perdido nem repetido

    def test_origin_and_labels_come_from_the_file_only(self):
        c = M.candidates_from_markers([dict(time=50, label='clutch', pre=8, post=12)], 0, 100, 'g')[0]
        self.assertEqual(c['origin'], 'marcador')
        self.assertFalse(c['heuristic'])
        self.assertIn('clutch', c['reasons'][0])

    def test_signal_heuristic_is_flagged_and_has_rest_window(self):
        signals = dict(audio=[dict(time=50, strength=3), dict(time=60, strength=2.5), dict(time=200, strength=2)],
                       motion=[dict(time=51, strength=2)])
        out = M.candidates_from_signals(signals, 0, 400, 'g')
        self.assertEqual(len(out), 2)                              # 50 e 60 estão a menos de 25 s: só um deles
        for c in out:
            self.assertTrue(c['heuristic'] and c['exploratory'])
            self.assertLessEqual(c['score'], 4.5)
            self.assertIn('heurística', c['reasons'][0])
        self.assertEqual(out[0]['origin'], 'sinais')

    def test_heuristic_skips_what_a_marker_already_covers(self):
        marked = M.candidates_from_markers(self.mk(50), 0, 400, 'g')
        out = M.candidates_from_signals(dict(audio=[dict(time=52, strength=3)]), 0, 400, 'g', existing=marked)
        self.assertEqual(out, [])


class Epoch(unittest.TestCase):
    def test_maps_clock_time_to_session_time(self):
        rows = [dict(start=0.0, end=60.0, mtime=int(1000.0 * 1e9)), dict(start=60.0, end=120.0, mtime=int(1060.0 * 1e9))]
        self.assertEqual(M.epoch_to_session(rows, 970.0), 30.0)
        self.assertEqual(M.epoch_to_session(rows, 1030.0), 90.0)
        self.assertIsNone(M.epoch_to_session(rows, 5000.0))


if __name__ == '__main__':
    unittest.main()
