import json
import tempfile
import unittest
from pathlib import Path

from liveclips import media
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store
from liveclips.timeline import build_timeline, plan


def real_source(path, seconds=40):
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}',
               '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}:sample_rate=48000', '-c:v', 'libx264', '-preset', 'veryfast',
               '-pix_fmt', 'yuv420p', '-g', '30', '-c:a', 'aac', '-b:a', '96k', '-f', 'mpegts', str(path)], timeout=240)


class Combined(unittest.TestCase):
    """Vários módulos opcionais ligados ao mesmo tempo no caminho real de exportação."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(cls.temp.name)
        cls.streamer = cls.store.create_streamer('Combo')
        cls.profile = dict(DEFAULT_PROFILE, camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off', voice_preset='natural',
                           auto_color='histograma', cut_fade='suave', slow_interp='mistura', stabilize='leve', cover=True)
        cls.store.save_profile(cls.streamer, cls.profile)
        cls.sid = cls.store.new_session(cls.streamer, 'combinado')
        session = cls.store.session(cls.sid)
        file = Path(session['source']) / 'segmento_00000.ts'
        real_source(file)
        info = media.probe(file); stat = file.stat()
        with cls.store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (cls.sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns,
                       'done', json.dumps({'segments': [], 'signals': {'audio': [], 'motion': [], 'warnings': []}})))
        rows = build_timeline(cls.store.segments(cls.sid))
        group = next(r['group_id'] for r in rows if r['start'] <= 5 < r['end'])
        data = dict(start=5.0, end=30.0, group_id=group, score=9.0, reasons=['teste'], transcript='fala de teste',
                    transcript_segments=[dict(start=6, end=9, text='uma fala curta', words=[])])
        key, _ = cls.store.propose(cls.sid, data, plan(rows, 5.0, 30.0, group), cls.store.streamer(cls.streamer)['profile'])
        cls.key = key
        item = cls.store.rows('SELECT id,version,start,end,parts FROM candidates WHERE streamer=?', (cls.streamer,))[0]
        cls.store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve', editorial_confirmed=True)
        Engine(cls.store).do_render(item['id'], False)
        cls.done = cls.store.candidate(item['id'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def folder(self):
        path = Path(self.done['export_path'])
        return path if path.is_dir() else path.parent

    def test_render_done_and_no_retreat(self):
        self.assertEqual(self.done['status'], 'done', self.done.get('error'))
        manifest = json.loads((self.folder() / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertNotIn('recuo', manifest, manifest.get('recuo'))
        self.assertTrue(manifest.get('color_report'))
        self.assertEqual(manifest['profile']['voice_preset'], 'natural')

    def test_output_is_vertical_with_audio_and_cover(self):
        info = media.probe(self.folder() / 'clipe.mp4')
        self.assertEqual((info['width'], info['height']), (1080, 1920))
        self.assertTrue(info['has_audio'])
        self.assertTrue((self.folder() / 'capa_9x16.jpg').is_file())

    def test_qc_ran_and_has_no_error(self):
        report = self.done['data']['qc']
        self.assertNotEqual(report['level'], 'erro', report['summary'])


if __name__ == '__main__':
    unittest.main()
