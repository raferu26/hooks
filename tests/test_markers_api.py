import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from liveclips.app import App
from tests.helpers import setup_session


class MarkersApi(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name, worker=False); self.addCleanup(self.app.close)
        self.streamer, self.sid, _ = setup_session(self.app.store)

    def call(self, path, **payload):
        return self.app.action(path, dict(payload, session=self.sid))

    def test_add_manual_marker_and_list(self):
        result = self.call('/api/session/marker', time='0:50', label='Pedido do chat')
        self.assertEqual(result['markers'][0]['time'], 50.0)
        self.assertFalse(result['approx'])

    def test_clock_marker_inside_recording_and_after_last_segment(self):
        last = self.app.store.segments(self.sid)[-1]
        end_epoch = float(last['mtime']) / 1e9
        inside = self.call('/api/session/marker', epoch=end_epoch - 5)
        self.assertFalse(inside['approx'])
        after = self.call('/api/session/marker', epoch=end_epoch + 30)
        self.assertTrue(after['approx'])
        with self.assertRaises(ValueError):
            self.call('/api/session/marker', epoch=end_epoch + 4000)   # longe demais do que foi gravado

    def test_import_markers_validates_and_rejects_bad_format(self):
        ok = self.call('/api/session/markers/import', name='m.txt', content='1:10 clutch\n2:00 risada')
        self.assertEqual(ok['imported'], 2)
        with self.assertRaises(ValueError):
            self.call('/api/session/markers/import', name='m.exe', content='x')
        with self.assertRaises(ValueError):
            self.call('/api/session/markers/import', name='m.json', content='[]')

    def test_import_and_clear_subtitles(self):
        srt = '1\n00:00:01,000 --> 00:00:03,000\nOlá\n'
        result = self.call('/api/session/subtitles/import', name='fala.srt', content=srt)
        self.assertEqual(result['subtitles']['count'], 1)
        cleared = self.call('/api/session/subtitles/clear')
        self.assertEqual(cleared['subtitles']['count'], 0)
        with self.assertRaises(ValueError):
            self.call('/api/session/subtitles/import', name='fala.doc', content=srt)

    def test_paste_text_builds_estimated_subtitles_and_warns(self):
        from liveclips import technical
        rng = np.random.default_rng(1); x = rng.standard_normal(technical.RATE * 12).astype(np.float32) * 1e-3
        for a, b in ((1, 4), (6, 10)):
            x[a * technical.RATE:b * technical.RATE] += rng.standard_normal((b - a) * technical.RATE).astype(np.float32) * .1
        db, step = technical.envelope_of(x)
        with mock.patch('liveclips.technical.envelope', return_value=(db, step)):
            r = self.call('/api/session/subtitles/paste', text='primeira frase colada\nsegunda frase colada', start=10, end=22)
        self.assertEqual(r['imported'], 2)
        self.assertEqual(r['timing'], 'estimado')
        self.assertEqual(r['subtitles']['count'], 2)
        self.assertGreaterEqual(r['subtitles']['first'], 10)                      # tempos de sessão, não do trecho
        with self.assertRaises(ValueError):
            self.call('/api/session/subtitles/paste', text='  ', start=10, end=22)
        with self.assertRaises(ValueError):
            self.call('/api/session/subtitles/paste', text='x', start=10, end=2000)

    def test_clear_markers(self):
        self.call('/api/session/marker', time=30)
        cleared = self.call('/api/session/markers/clear')
        self.assertEqual(cleared['markers'], [])


if __name__ == '__main__':
    unittest.main()
