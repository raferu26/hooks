import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from liveclips import media, ranking, visual


class Pure(unittest.TestCase):
    def test_flash_burst_and_cut_are_told_apart(self):
        n = 40
        motion = [.01] * n
        luma = [.3] * n
        luma[10] = .6
        motion[10] = .05                       # clarão
        for i in (20, 21, 22):
            motion[i] = .14                    # rajada de movimento
        motion[30] = .6                        # corte de cena (tela de carregamento, menu...)
        for i in range(30, n):
            luma[i] = .9                       # a mudança permanece: é corte, não clarão
        kinds = {(e['kind']): e for e in visual.events_from(motion, luma)}
        self.assertIn('flash', kinds)
        self.assertIn('rajada', kinds)
        self.assertIn('corte', kinds)
        self.assertEqual(kinds['flash']['time'], 5.0)
        flashes = [e for e in visual.events_from(motion, luma) if e['kind'] == 'flash']
        self.assertEqual(len(flashes), 1)  # o salto de brilho do corte não vira clarão

    def test_quiet_footage_has_no_events(self):
        self.assertEqual(visual.events_from([.005] * 60, [.4] * 60), [])


class Real(unittest.TestCase):
    def test_real_video_with_flash_and_webcam_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'jogo.mp4'
            # fundo calmo; clarão em t=5 s; a "webcam" (canto sup. esquerdo) tem movimento constante que NÃO pode contar
            flash = "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=fill:enable='between(t,5,5.4)'"
            cam = "drawbox=x=0:y=0:w=iw*0.25:h=ih*0.3:color=red:t=fill:enable='lt(mod(t,0.5),0.25)'"
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                            f'color=c=0x303a45:s=640x360:r=10:d=12,{cam},{flash}', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-pix_fmt', 'yuv420p', str(out)], check=True)
            with_mask = visual.analyze(out, 12, camera_rect=[0, 0, .25, .3])
            self.assertTrue(with_mask['ok'])
            kinds = [e['kind'] for e in with_mask['events']]
            self.assertIn('flash', kinds)
            near = [e for e in with_mask['events'] if abs(e['time'] - 5.0) <= 1.0]
            self.assertTrue(near)
            self.assertFalse([e for e in with_mask['events'] if e['kind'] == 'rajada'], with_mask['events'])
            without = visual.analyze(out, 12, camera_rect=None)
            self.assertGreaterEqual(len(without['events']), len(with_mask['events']))

    def test_unreadable_video_returns_a_warning_not_an_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'x.mp4'
            bad.write_bytes(b'nada')
            r = visual.analyze(bad, 10)
            self.assertFalse(r['ok'])
            self.assertTrue(r['warnings'])


if __name__ == '__main__':
    unittest.main()
