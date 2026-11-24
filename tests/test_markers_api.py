import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from liveclips.app import App
from tests.helpers import candidate, setup_session


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

    def _speech_env(self):
        from liveclips import technical
        rng = np.random.default_rng(2); x = rng.standard_normal(technical.RATE * 20).astype(np.float32) * 1e-3
        for a, b in ((1, 6), (8, 14), (15, 19)):
            x[a * technical.RATE:b * technical.RATE] += rng.standard_normal((b - a) * technical.RATE).astype(np.float32) * .1
        return technical.envelope_of(x)

    def test_captions_from_text_returns_studio_lines_without_writing_anything(self):
        item, _ = candidate(self.app.store, self.sid, 10, 30)
        with mock.patch('liveclips.technical.envelope', return_value=self._speech_env()):
            r = self.app.action('/api/captions/from-text', dict(id=item['id'], text='primeira frase colada\nsegunda frase colada\nterceira frase colada'))
        self.assertEqual(r['timing'], 'estimado')
        self.assertEqual(len(r['lines']), 3)
        self.assertTrue(all(0 <= l['start'] < l['end'] <= r['duration'] + .5 for l in r['lines']))       # tempos relativos ao corte
        self.assertTrue(all(l['words'] for l in r['lines']))
        self.assertEqual(self.app.store.candidate(item['id'])['version'], item['version'])               # nada foi gravado
        with self.assertRaises(ValueError):
            self.app.action('/api/captions/from-text', dict(id=item['id'], text='   '))

    def test_captions_from_file_windows_the_recording_or_uses_clip_relative_times(self):
        item, _ = candidate(self.app.store, self.sid, 10, 30)
        srt = '1\n00:00:12,000 --> 00:00:15,000\nDentro do corte\n\n2\n00:01:00,000 --> 00:01:02,000\nFora do corte\n'
        r = self.app.action('/api/captions/from-file', dict(id=item['id'], name='a.srt', content=srt))
        self.assertEqual([l['text'] for l in r['lines']], ['Dentro do corte'])
        self.assertEqual((r['lines'][0]['start'], r['lines'][0]['end']), (2.0, 5.0))              # relativo ao início do corte
        self.assertEqual(r['timing'], 'arquivo')
        rel = self.app.action('/api/captions/from-file', dict(id=item['id'], name='a.srt', content='1\n00:00:01,000 --> 00:00:03,000\nJá relativo\n', relative=True))
        self.assertEqual((rel['lines'][0]['start'], rel['lines'][0]['end']), (1.0, 3.0))
        with self.assertRaises(ValueError):
            self.app.action('/api/captions/from-file', dict(id=item['id'], name='a.srt', content='1\n00:05:00,000 --> 00:05:02,000\nLonge\n'))
        with self.assertRaises(ValueError):
            self.app.action('/api/captions/from-file', dict(id=item['id'], name='a.exe', content=srt))

    def test_captions_from_text_with_taps_uses_them(self):
        item, _ = candidate(self.app.store, self.sid, 10, 30)
        with mock.patch('liveclips.technical.envelope', return_value=self._speech_env()):
            r = self.app.action('/api/captions/from-text', dict(id=item['id'], text='um dois três\nquatro cinco seis', taps=[2.0, 9.0]))
        self.assertEqual(r['timing'], 'toques')
        self.assertEqual([round(l['start'], 1) for l in r['lines']], [2.0, 9.0])

    def test_clear_markers(self):
        self.call('/api/session/marker', time=30)
        cleared = self.call('/api/session/markers/clear')
        self.assertEqual(cleared['markers'], [])


if __name__ == '__main__':
    unittest.main()
