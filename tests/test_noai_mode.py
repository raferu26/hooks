import json
import sys
import tempfile
import unittest
from pathlib import Path

from liveclips import media
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store

FORBIDDEN = ('faster_whisper', 'mediapipe', 'torch', 'onnxruntime', 'tensorflow')


class Blocker:
    """Registra qualquer tentativa de importar um componente de IA e a recusa."""
    def __init__(self):
        self.attempts = []

    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in FORBIDDEN:
            self.attempts.append(name)
            raise ImportError('bloqueado no teste: ' + name)
        return None


def make_source(target, seconds=100):
    # áudio com um trecho alto (a partir de 40 s) e vídeo com movimento; sem fala.
    audio = f"sine=frequency=300:duration={seconds}:sample_rate=48000,volume='if(gt(t,40),if(lt(t,48),1.0,0.15),0.15)':eval=frame"
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}',
               '-f', 'lavfi', '-i', audio, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30',
               '-c:a', 'aac', '-b:a', '96k', '-f', 'mpegts', str(target)], timeout=240)


class NoAiMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(cls.temp.name)
        cls.streamer = cls.store.create_streamer('SemIA')
        cls.profile = dict(DEFAULT_PROFILE, ai_mode='sem_ia', camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off', voice_preset='natural', title_template='{rotulo}')
        cls.store.save_profile(cls.streamer, cls.profile)
        sid = cls.sid = cls.store.new_session(cls.streamer, 'sessão sem IA')
        session = cls.store.session(sid)
        file = Path(session['source']) / 'segmento_00000.ts'
        make_source(file)
        info = media.probe(file)
        stat = file.stat()
        with cls.store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size,
                       stat.st_mtime_ns, 'new', '{}'))
        Path(session['path'], 'marcadores.json').write_text(json.dumps(
            [dict(time=50, label='Pedido do chat', pre=8, post=10)]), encoding='utf-8')
        Path(session['path'], 'legendas').mkdir(exist_ok=True)
        Path(session['path'], 'legendas', 'fala.srt').write_text(
            '1\n00:00:46,000 --> 00:00:50,000\nIsto veio de um arquivo de legenda\n\n2\n00:00:51,000 --> 00:00:54,000\nSegunda fala importada\n', encoding='utf-8')
        cls.blocker = Blocker()
        sys.meta_path.insert(0, cls.blocker)
        cls.engine = Engine(cls.store)
        profile = cls.store.streamer(cls.streamer)['profile']
        session = cls.store.session(sid)
        cls.analyzed = cls.engine.analyze_one(session, profile)
        session = cls.store.session(sid)
        cls.engine.suggest_one(session, profile)
        cls.clips = cls.store.rows('SELECT id,version,start,end,parts,status FROM candidates WHERE streamer=?', (cls.streamer,))

    @classmethod
    def tearDownClass(cls):
        sys.meta_path.remove(cls.blocker)
        cls.temp.cleanup()

    def test_analysis_is_free_of_models(self):
        self.assertTrue(self.analyzed)
        segment = self.store.segments(self.sid)[0]
        self.assertEqual(segment['status'], 'done')
        self.assertEqual(self.blocker.attempts, [])

    def test_marker_creates_candidate_with_origin_and_without_invented_meaning(self):
        self.assertTrue(self.clips)
        full = [self.store.candidate(c['id']) for c in self.clips]
        marked = [c for c in full if c['data'].get('origin') == 'marcador']
        self.assertTrue(marked, [c['data'].get('origin') for c in full])
        top = marked[0]
        self.assertLessEqual(top['start'], 50 - 3)
        self.assertGreaterEqual(top['end'], 50 + 3)
        self.assertEqual(top['data'].get('ai_mode'), 'sem_ia')
        self.assertIn('Pedido do chat', ' '.join(top['data'].get('reasons', [])))

    def test_imported_subtitles_only_feed_caption_text(self):
        full = [self.store.candidate(c['id']) for c in self.clips]
        marked = [c for c in full if c['data'].get('origin') == 'marcador'][0]
        self.assertIn('arquivo de legenda', marked['data'].get('transcript', ''))
        self.assertEqual(marked['data'].get('transcript_segments_origin'), 'importada')

    def test_heuristic_candidates_are_flagged(self):
        full = [self.store.candidate(c['id']) for c in self.clips]
        for c in full:
            if c['data'].get('origin') != 'marcador':
                self.assertTrue(c['data'].get('heuristic'))

    def test_render_and_qc_run_without_ai(self):
        item = self.clips[0]
        self.store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve', editorial_confirmed=True)
        self.engine.do_render(item['id'], False)
        done = self.store.candidate(item['id'])
        self.assertEqual(done['status'], 'done', done.get('error'))
        report = done['data'].get('qc')
        self.assertTrue(report, 'QC não rodou')
        self.assertNotIn('rosto', ' '.join(i['id'] for i in report['items']))
        self.assertEqual(self.blocker.attempts, [])

    def test_camera_detection_blocked_in_profile(self):
        from liveclips.engine import ai_free
        self.assertTrue(ai_free(self.store.streamer(self.streamer)['profile']))


if __name__ == '__main__':
    unittest.main()
