import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import media, speaker

HAAR = Path('/tmp/haar.xml')  # só existe onde o detector foi baixado; sem ele o teste de vídeo é pulado


class Pure(unittest.TestCase):
    def test_seats_group_by_position_and_drop_rare_ones(self):
        frames = [[(.25, .4, .15, .25), (.75, .42, .15, .25)] for _ in range(20)] + [[(.5, .4, .1, .2)]]
        seats = speaker.seats_from(frames)
        self.assertEqual(len(seats), 2)
        self.assertLess(seats[0]['x'], .3)
        self.assertGreater(seats[1]['x'], .7)

    def test_choose_follows_clear_speaker_changes_and_ignores_noise(self):
        step = .25
        n = 80
        a = [3.0 if i < 32 else .2 for i in range(n)]
        b = [.2 if i < 32 else 3.0 for i in range(n)]
        for i in (10, 11):
            b[i] = 4.0  # ruído curto não pode causar troca
        turns = speaker.choose({0: a, 1: b}, step)
        self.assertEqual([t[2] for t in turns], [0, 1])
        self.assertAlmostEqual(turns[0][1], 8.0, delta=1.5)
        self.assertAlmostEqual(turns[-1][1], 20.0, delta=.01)

    def test_silence_keeps_the_current_speaker_and_min_turn_is_respected(self):
        step = .25
        quiet = {0: [.1] * 60, 1: [.1] * 60}
        self.assertEqual(len(speaker.choose(quiet, step)), 1)
        # trocas rápidas demais (cada 1 s) não geram turnos menores que MIN_TURN
        a = [3.0 if (i // 4) % 2 == 0 else .1 for i in range(80)]
        b = [.1 if (i // 4) % 2 == 0 else 3.0 for i in range(80)]
        turns = speaker.choose({0: a, 1: b}, step)
        for t in turns[:-1]:
            self.assertGreaterEqual(t[1] - t[0], speaker.MIN_TURN - .3)

    def test_plan_holds_then_slides(self):
        seats = {0: dict(x=.25), 1: dict(x=.75)}
        pts = speaker.plan_from_turns([(0, 6, 0), (6, 12, 1)], seats, 12)
        self.assertEqual([(p['x']) for p in pts], [.25, .25, .75])
        self.assertAlmostEqual(pts[1]['end'] - pts[1]['start'], speaker.TRANSITION, places=2)
        self.assertEqual(pts[-1]['end'], 12)
        self.assertTrue(all(p['face'] for p in pts))


@unittest.skipUnless(HAAR.is_file(), 'detector de rosto não baixado')
class RealVideo(unittest.TestCase):
    def make(self, folder):
        import cv2
        import numpy as np
        from skimage import data
        face = cv2.resize(data.astronaut()[20:220, 124:324, ::-1].copy(), (360, 360))
        out = Path(folder) / 'podcast.mp4'
        proc = subprocess.Popen([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '1280x720',
                                 '-r', '10', '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(out)],
                                stdin=subprocess.PIPE)
        for i in range(160):
            t = i / 10
            speaker_left = t < 6 or t >= 11
            frame = np.full((720, 1280, 3), 40, np.uint8)
            for left, x in ((True, 100), (False, 820)):
                img = face.copy()
                talking = (speaker_left == left)
                opening = 14 if talking and i % 2 == 0 else 0
                if talking:
                    cv2.ellipse(img, (180, 215), (45, 4 + opening), 0, 0, 360, (20, 20, 90), -1)
                frame[180:540, x:x + 360] = img
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        proc.wait()
        return out

    def test_follows_the_talking_face_in_a_two_person_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = self.make(tmp)
            info = media.probe(video)
            points = speaker.speaker_plan(video, 0, 16, info, cascade_path=str(HAAR))
            self.assertTrue(points, 'o plano veio vazio')
            def at(t):
                return next(p['x'] for p in points if p['start'] <= t < p['end'] + 1e-6)
            self.assertLess(at(3), .4)
            self.assertGreater(at(9), .6)
            self.assertLess(at(14), .4)
            # a troca acompanha a fala real (6 s e 11 s) com atraso pequeno
            switch1 = next(p['start'] for p in points if p['x'] > .6)
            self.assertLess(abs(switch1 - 6.0), 1.0, points)

    def test_single_person_scene_returns_no_plan(self):
        import cv2
        import numpy as np
        from skimage import data
        with tempfile.TemporaryDirectory() as tmp:
            face = cv2.resize(data.astronaut()[20:220, 124:324, ::-1].copy(), (360, 360))
            out = Path(tmp) / 'um.mp4'
            proc = subprocess.Popen([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '1280x720',
                                     '-r', '10', '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(out)], stdin=subprocess.PIPE)
            for i in range(100):
                frame = np.full((720, 1280, 3), 40, np.uint8)
                frame[180:540, 460:820] = face
                proc.stdin.write(frame.tobytes())
            proc.stdin.close()
            proc.wait()
            self.assertEqual(speaker.speaker_plan(out, 0, 10, media.probe(out), cascade_path=str(HAAR)), [])


if __name__ == '__main__':
    unittest.main()


class RenderWiring(unittest.TestCase):
    def test_render_uses_the_speaker_plan_and_produces_a_vertical_clip(self):
        from unittest.mock import patch
        from liveclips import editing
        from liveclips.store import DEFAULT_PROFILE
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'fonte.mp4'
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=15:duration=10',
                            '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000:duration=10', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
                            '-shortest', str(src)], check=True)
            base = dict(DEFAULT_PROFILE, min_free_gb=.1, threads=2, content_mode='video', reframe_mode='speaker')
            plan = editing.plan_edits({'start': 0, 'end': 10}, {}, profile=base)
            plan['decisions'] = []
            parts = [{'path': str(src), 'sha': media.sha_file(src), 'seq': 0, 'in': 0.0, 'out': 10.0, 'global_start': 0, 'global_end': 10, 'group_id': 'g'}]
            cand = {'id': 'spk', 'start': 0, 'end': 10, 'parts': parts, 'profile': base, 'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}}}
            points = [dict(start=0.0, end=4.65, face=True, x=.25, scene=False), dict(start=4.65, end=5.0, face=True, x=.25, scene=False),
                      dict(start=5.0, end=10.0, face=True, x=.75, scene=False)]
            with patch.object(speaker, 'speaker_plan', return_value=points) as spy:
                clip = media.render(cand, [], temp, False, pipeline='single', root=temp)
            self.assertTrue(spy.called)
            info = media.probe(clip)
            self.assertEqual((info['width'], info['height']), (1080, 1920))
            plan_file = next(Path(clip).parent.glob('plano_enquadramento.json'))
            self.assertIn('0.75', plan_file.read_text())
