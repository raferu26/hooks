"""Checagem antes de gravar e registro do último pedaço curto."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

from liveclips import preflight
from liveclips.engine import Engine
from liveclips.store import Store
from tests.helpers import setup_session


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        d=patch('liveclips.media.free_bytes',return_value=100*1024**3);d.start();self.addCleanup(d.stop)
        t=patch('liveclips.media.tool_status',return_value=dict(ffmpeg='x',ffprobe='x',streamlink='x'));t.start();self.addCleanup(t.stop)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.capture=MagicMock();self.capture.state.return_value=[];self.capture.limit.return_value=5
        self.streamer=self.store.create_streamer('DAVA')

    def run_pre(self,devices=0):
        return preflight.run(self.store,self.engine,self.capture,self.streamer,devices=devices)

    def check(self,result,id):return next(c for c in result['checks'] if c['id']==id)

    def test_missing_webcam_is_a_warning_that_says_where_to_fix(self):
        result=self.run_pre();item=self.check(result,'webcam')
        self.assertEqual(item['level'],'aviso');self.assertEqual(item['action'],'settings:cam');self.assertIn('Webcam e quadro',item['detail'])
        self.assertIn(result['level'],('aviso','erro'))

    def test_marked_webcam_is_ok(self):
        setup_session(self.store,'DAVA','L')
        self.assertEqual(self.check(self.run_pre(),'webcam')['level'],'ok')

    def test_cpu_transcription_mentions_measured_speed_and_lives(self):
        self.engine.rtf.extend([0.3,0.3]);item=self.check(self.run_pre(0),'transcricao')
        self.assertIn('18 s de transcrição por minuto',item['detail'])

    def test_gpu_is_reported_as_ok(self):
        self.assertEqual(self.check(self.run_pre(1),'transcricao')['level'],'ok')

    def test_broken_cuda_falls_back_to_cpu_in_the_report(self):
        self.engine.cuda_broken=True
        self.assertIn('processador',self.check(self.run_pre(1),'transcricao')['title'])

    def test_missing_streamlink_is_an_error(self):
        with patch('liveclips.media.tool_status',return_value=dict(ffmpeg='x',ffprobe='x',streamlink=None)):
            result=self.run_pre()
        self.assertEqual(self.check(result,'ferramentas')['level'],'erro');self.assertEqual(result['level'],'erro')

    def test_slot_limit_reached_is_an_error(self):
        self.capture.state.return_value=[1,2,3,4,5]
        self.assertEqual(self.check(self.run_pre(),'limite')['level'],'erro')

    def test_low_disk_is_an_error(self):
        with patch('liveclips.media.free_bytes',return_value=3*1024**3):
            self.assertEqual(self.check(self.run_pre(),'disco')['level'],'erro')


class ShortLastSegmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.streamer,self.sid,_=setup_session(self.store,'X','S',durations=(60,))
        self.session=self.store.session(self.sid)
        tiny=Path(self.session['source'])/'segmento_00001.ts';tiny.write_bytes(b'\x01'*50000)
        old=time.time()-100;os.utime(tiny,(old,old))
        # a 1ª do helper (130 KB) já está registrada; a curta é a 2ª e última

    def scan(self,closed,duration):
        with self.store.connect(True) as c:c.execute('UPDATE sessions SET closed=? WHERE id=?',(1 if closed else 0,self.sid))
        with patch('liveclips.engine.media.probe',return_value=dict(duration=duration,signature='same-format')):
            return self.engine.scan_one(self.store.session(self.sid))

    def test_open_session_ignores_a_small_file(self):
        self.assertFalse(self.scan(False,30));self.assertEqual(len(self.store.segments(self.sid)),1)

    def test_closed_session_registers_short_last_piece_when_readable(self):
        self.assertTrue(self.scan(True,12.5));self.assertEqual(len(self.store.segments(self.sid)),2)

    def test_closed_session_skips_unreadable_or_tiny_piece(self):
        self.assertFalse(self.scan(True,1.0));self.assertEqual(len(self.store.segments(self.sid)),1)


if __name__=='__main__':
    unittest.main()


class StreamlinkFailureTests(unittest.TestCase):
    def test_json_error_on_stdout_is_explained_in_portuguese(self):
        from liveclips.capture import explain_failure
        text=explain_failure(b'{"error": "No playable streams found on this URL: https://x"}',b'')
        self.assertIn('Não há transmissão no ar',text);self.assertIn('No playable streams',text)

    def test_empty_output_says_it_does_not_know_why(self):
        from liveclips.capture import explain_failure
        self.assertIn('não informou o motivo',explain_failure(b'',b''))

    def test_unknown_error_is_passed_through(self):
        from liveclips.capture import explain_failure
        self.assertEqual(explain_failure(b'',b'algo estranho'),'algo estranho')

    def test_inspect_url_raises_the_real_reason(self):
        from liveclips import capture
        cp=MagicMock();cp.returncode=1;cp.stdout=b'{"error": "No playable streams found on this URL"}';cp.stderr=b''
        with patch('liveclips.capture.subprocess.run',return_value=cp),patch('liveclips.capture.media.tool',side_effect=lambda n:n):
            with self.assertRaisesRegex(RuntimeError,'Não há transmissão no ar'):capture.inspect_url('https://www.youtube.com/live/abc')
