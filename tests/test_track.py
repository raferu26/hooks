import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import media, track
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store, profile_checked
from liveclips.timeline import build_timeline, plan

W, H, FPS, SECONDS, SIDE = 960, 540, 10, 12, 120


def make_video(path, cut_at=None):
    """Quadrado texturizado que anda da esquerda para a direita sobre fundo estático com ruído.
    `cut_at`: a partir desse instante o quadro vira outra cena (corte de cena)."""
    rng = np.random.default_rng(7)
    background = (rng.integers(60, 120, (H, W, 3))).astype(np.uint8)
    patch = rng.integers(0, 255, (SIDE, SIDE, 3)).astype(np.uint8)
    other = np.full((H, W, 3), 235, np.uint8)
    other[:, ::40] = 20
    proc = subprocess.Popen([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS),
                             '-i', '-', '-f', 'lavfi', '-i', f'sine=frequency=330:duration={SECONDS}:sample_rate=48000',
                             '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '10', '-crf', '12', '-c:a', 'aac',
                             '-shortest', '-f', 'mpegts', str(path)], stdin=subprocess.PIPE)
    for i in range(FPS * SECONDS):
        t = i / FPS
        if cut_at is not None and t >= cut_at:
            frame = other
        else:
            frame = background.copy()
            x = int(100 + 600 * t / SECONDS)
            frame[200:200 + SIDE, x:x + SIDE] = patch
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError('ffmpeg falhou')


ROI = [100 / W, 200 / H, SIDE / W, SIDE / H]


class Tracking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.moving = Path(cls.temp.name) / 'move.ts'
        cls.cut = Path(cls.temp.name) / 'corte.ts'
        make_video(cls.moving)
        make_video(cls.cut, cut_at=6)
        cls.info = media.probe(cls.moving)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_follows_moving_region(self):
        points = track.track_plan(self.moving, 0, 12, self.info, ROI)
        self.assertTrue(points)
        self.assertTrue(all(p['face'] for p in points), [p for p in points if not p['face']])
        xs = [p['x'] for p in points]
        self.assertAlmostEqual(xs[0], (100 + SIDE / 2) / W, delta=.03)
        self.assertGreater(xs[-1], .6)                      # terminou à direita
        self.assertTrue(all(b >= a - .02 for a, b in zip(xs, xs[1:])), xs)   # sem retrocessos
        # posição esperada (centro do quadrado) em ~6 s
        mid = next(p for p in points if p['start'] >= 6)
        expect = (100 + 600 * mid['start'] / SECONDS + SIDE / 2) / W
        self.assertAlmostEqual(mid['x'], expect, delta=.05)

    def test_same_format_as_dynamic_plan(self):
        for p in track.track_plan(self.moving, 0, 12, self.info, ROI):
            self.assertTrue({'start', 'end', 'face', 'x'} <= set(p))
            self.assertLess(p['start'], p['end'])

    def test_offset_is_respected(self):
        # a partir de 4 s o quadrado já está mais à direita; a ROI foi marcada no começo do trecho analisado
        moved = [(100 + 600 * 4 / SECONDS) / W, 200 / H, SIDE / W, SIDE / H]
        points = track.track_plan(self.moving, 4, 6, self.info, moved)
        self.assertTrue(points)
        self.assertAlmostEqual(points[0]['x'], (100 + 600 * 4 / SECONDS + SIDE / 2) / W, delta=.03)

    def test_flat_region_is_refused(self):
        flat = Path(self.temp.name) / 'plano.ts'
        media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=gray:s={W}x{H}:r=10:d=4',
                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-f', 'mpegts', str(flat)], timeout=60)
        self.assertEqual(track.track_plan(flat, 0, 4, media.probe(flat), [.4, .4, .2, .2]), [])

    def test_scene_cut_drops_confidence(self):
        points = track.track_plan(self.cut, 0, 12, self.info, ROI)
        self.assertTrue(points)
        before = [p for p in points if p['end'] <= 5.9]
        after = [p for p in points if p['start'] >= 6.5]
        self.assertTrue(all(p['face'] for p in before))
        self.assertTrue(after and not any(p['face'] for p in after))   # perdeu → quadro volta ao padrão, sem pular para outro lugar

    def test_no_region_no_plan_and_vertical_source_untouched(self):
        self.assertEqual(track.track_plan(self.moving, 0, 12, self.info, None), [])
        self.assertEqual(track.track_plan(self.moving, 0, 12, dict(width=720, height=1280), ROI), [])

    def test_roi_validation(self):
        self.assertIsNone(track.valid_roi(None))
        for bad in ([0, 0, 1], [0, 0, .01, .5], [.9, .9, .3, .3], [-.1, 0, .2, .2], [float('nan'), 0, .2, .2]):
            with self.assertRaises(ValueError):
                track.valid_roi(bad)
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, reframe_mode='rastreio', track_roi=ROI))['reframe_mode'], 'rastreio')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, track_roi=[.9, .9, .3, .3]))

    def test_reframe_points_routes_to_tracker_without_ai(self):
        import sys
        profile = dict(DEFAULT_PROFILE, ai_mode='sem_ia', reframe_mode='rastreio', track_roi=ROI)
        before = set(sys.modules)
        points = media.reframe_points(profile, self.moving, 0, 12, self.info)
        self.assertTrue(any(p['face'] for p in points))
        new = {m.split('.')[0] for m in set(sys.modules) - before}
        self.assertFalse(new & {'faster_whisper', 'mediapipe', 'torch', 'onnxruntime'}, new)
        # sem região marcada, o rastreio recusa e o quadro fica no padrão
        self.assertEqual(media.reframe_points(dict(profile, track_roi=None), self.moving, 0, 12, self.info), [])

    def test_filter_uses_tracked_points(self):
        points = track.track_plan(self.moving, 0, 12, self.info, ROI)
        graph = media.video_filters(30, self.info, points)
        self.assertIn('crop=1080:1920', graph)
        self.assertIn('enable=', graph)


class RealRender(unittest.TestCase):
    """Exportação real no modo sem IA, com vídeo importado e enquadramento por rastreio."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(cls.temp.name)
        cls.streamer = cls.store.create_streamer('Rastreio')
        cls.profile = dict(DEFAULT_PROFILE, ai_mode='sem_ia', min_free_gb=.5, second_pass='off', reframe_mode='rastreio', track_roi=ROI)
        cls.store.save_profile(cls.streamer, cls.profile)
        cls.sid = cls.store.new_session(cls.streamer, 'video')
        session = cls.store.session(cls.sid)
        (Path(session['path']) / 'fonte.json').write_text(json.dumps(dict(mode='video', reframe_mode='rastreio', url='', title='t')), encoding='utf-8')
        file = Path(session['source']) / 'segmento_00000.ts'
        make_video(file)
        info = media.probe(file)
        stat = file.stat()
        with cls.store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (cls.sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns,
                       'done', json.dumps({'segments': [], 'signals': {'audio': [], 'motion': [], 'warnings': []}})))
        rows = build_timeline(cls.store.segments(cls.sid))
        group = rows[0]['group_id']
        data = dict(start=0.0, end=11.0, group_id=group, score=5.0, reasons=['teste'], transcript='fala', content_mode='video',
                    reframe_mode='rastreio', transcript_segments=[dict(start=1, end=3, text='uma fala curta', words=[])])
        profile = dict(cls.store.streamer(cls.streamer)['profile'], content_mode='video', reframe_mode='rastreio')
        cls.store.propose(cls.sid, data, plan(rows, 0.0, 11.0, group), profile)
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

    def test_render_done_with_tracked_plan(self):
        self.assertEqual(self.done['status'], 'done', self.done.get('error'))
        plan_file = self.folder() / 'plano_enquadramento.json'
        self.assertTrue(plan_file.is_file())
        points = json.loads(plan_file.read_text(encoding='utf-8'))
        self.assertTrue(any(p['face'] for p in points))
        self.assertGreater(points[-1]['x'], points[0]['x'] + .2)     # o enquadramento acompanhou o quadrado
        info = media.probe(self.folder() / 'clipe.mp4')
        self.assertEqual((info['width'], info['height']), (1080, 1920))

    def test_no_retreat(self):
        manifest = json.loads((self.folder() / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertNotIn('recuo', manifest)


if __name__ == '__main__':
    unittest.main()
