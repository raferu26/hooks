"""Sugestões determinísticas: conteúdo parado + webcam em movimento (sem IA). Vídeo sintético com intervalo parado conhecido."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import media, reaction_signals as S
from liveclips import composition as C

REG = dict(webcam=dict(x=.70, y=.04, w=.28, h=.30), conteudo=dict(x=0, y=0, w=.6, h=1))


def make(path, seconds=12, still=(4, 8)):
    """Conteúdo (esquerda) em movimento, parado entre `still`; webcam (canto) sempre se mexendo."""
    first, frozen, last = still[0], still[1] - still[0], seconds - still[1]
    graph = (f"testsrc2=s=1152x1080:r=10:d={first}[c1];testsrc2=s=1152x1080:r=10:d=0.2,loop=loop={int(frozen * 10) - 1}:size=1,setpts=N/(10*TB)[c2];"
             f"testsrc2=s=1152x1080:r=10:d={last}[c3];[c1][c2][c3]concat=n=3:v=1:a=0[c];"
             f"testsrc2=s=538x324:r=10:d={seconds},hue=h=t*90[w];color=c=0x303030:s=1920x1080:r=10:d={seconds}[bg];[bg][c]overlay=0:0[x];[x][w]overlay=1344:43")
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-filter_complex', graph, '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-qp', '18', '-pix_fmt', 'yuv420p', str(path)], check=True)


class Options(unittest.TestCase):
    def test_defaults_and_clamps(self):
        self.assertEqual(S.clean_options(None), dict(S.DEFAULTS, limit=8))
        o = S.clean_options(dict(min_seconds=99, still_below=0, limit=500))
        self.assertEqual((o['min_seconds'], o['still_below'], o['limit']), (30, .05, 20))
        with self.assertRaises(ValueError):
            S.clean_options(dict(still_below='x'))
        with self.assertRaises(ValueError):
            S.clean_options(dict(move_above=float('nan')))


class Rules(unittest.TestCase):
    O = S.clean_options({})

    def test_requires_still_content_and_moving_webcam_for_long_enough(self):
        content = np.array([5] * 10 + [.2] * 20 + [5] * 10, float)
        webcam = np.array([6] * 40, float)
        runs = S.find_runs(content, webcam, self.O)
        self.assertEqual(len(runs), 1)
        self.assertAlmostEqual(runs[0]['start'], 2.0)
        self.assertAlmostEqual(runs[0]['end'], 6.0)
        self.assertEqual(S.find_runs(content, np.zeros(40), self.O), [])           # webcam parada: não sugere
        self.assertEqual(S.find_runs(np.array([.2] * 5, float), webcam, self.O), [])  # parado por 1 s só: curto demais

    def test_short_motion_blips_are_merged_and_close_suggestions_dropped(self):
        content = np.array([.2] * 15 + [4] * 2 + [.2] * 15, float)                  # 0,4 s de movimento no meio
        runs = S.find_runs(content, np.full(32, 6.0), self.O)
        self.assertEqual(len(runs), 1)
        near = [dict(start=0, end=3, content_motion=.2, webcam_motion=6), dict(start=4, end=7, content_motion=.2, webcam_motion=5)]
        self.assertEqual(len(S.rank(near, self.O)), 1)                              # coladas (<3 s): fica a melhor

    def test_every_suggestion_explains_the_rule(self):
        r = S.rank([dict(start=1, end=4, content_motion=.2, webcam_motion=6)], self.O)[0]
        self.assertIn('quase não mudou', r['reason'])
        self.assertIn('Heurística de pixels', S.rule_text(self.O))


class Real(unittest.TestCase):
    def test_finds_the_frozen_stretch_in_a_real_video(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / 'v.mp4'
            make(video)
            info = media.probe(video)
            motion = S.region_motion(media.tool('ffmpeg'), video, 0, 12, REG, (info['display_width'], info['display_height']), info['sar'])
            runs = S.rank(S.find_runs(motion['conteudo'], motion['webcam'], S.clean_options({})), S.clean_options({}))
            self.assertEqual(len(runs), 1, runs)
            self.assertAlmostEqual(runs[0]['start'], 4, delta=.5)
            self.assertAlmostEqual(runs[0]['end'], 8, delta=.5)

    def test_api_endpoint_requires_regions_and_returns_disclaimer(self):
        from tests.test_composicao_presets import ApplyToCuts
        case = ApplyToCuts('test_resolve_endpoint_returns_the_render_plan')
        case.setUp()
        try:
            with self.assertRaises(ValueError):
                case.app.action('/api/composition/suggest', dict(id=case.ids[0], composition=dict(layout='cam_ampliada', regions=dict(webcam=REG['webcam']))))
            r = case.app.action('/api/composition/suggest', dict(id=case.ids[0], composition=dict(layout='cam_ampliada', regions=REG)))
            self.assertIn('disclaimer', r)
            self.assertIsInstance(r['suggestions'], list)
        finally:
            case.doCleanups()


if __name__ == '__main__':
    unittest.main()
