"""Cenas de reação (layout por intervalo): validação, mapa de tempo final (cortes, velocidade, replay, abertura), quadros reais."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import composition as C
from liveclips import editing, media, project

FPS = 30
REG = dict(webcam=dict(x=.70, y=.04, w=.28, h=.30), conteudo=dict(x=0, y=0, w=.6, h=1))


def comp(scenes=None, layout='cam_ampliada', **params):
    return C.clean(dict(layout=layout, regions=REG, params=params, scenes=scenes or []), 20)


class Validation(unittest.TestCase):
    def test_scene_rules(self):
        self.assertEqual(comp([]).get('scenes'), None)
        ok = comp([dict(id='a', start=2, end=5, layout='cinema', fade=.3), dict(id='b', start=5, end=8, layout='foco_reacao')])
        self.assertEqual([s['id'] for s in ok['scenes']], ['a', 'b'])
        self.assertEqual(ok['scenes'][1]['fade'], 0)
        for bad in ([dict(start=2, end=2.1, layout='cinema')], [dict(start=2, end=5, layout='x')],
                    [dict(start=2, end=6, layout='cinema'), dict(start=5, end=8, layout='cinema')], 'x',
                    [dict(start=i, end=i + .5, layout='cinema') for i in range(30)]):
            with self.assertRaises(ValueError, msg=str(bad)):
                comp(bad)

    def test_scene_is_clamped_to_clip_and_fade_limited(self):
        c = comp([dict(start=18, end=99, layout='cinema', fade=9)])
        self.assertEqual((c['scenes'][0]['end'], c['scenes'][0]['fade']), (20, 1))

    def test_scene_that_needs_an_unmarked_region_is_reported_not_rendered(self):
        c = comp([dict(id='d', start=1, end=3, layout='dueto')])
        self.assertEqual([(s['id'], m) for s, m in C.scene_problems(c)], [('d', ['webcam2'])])
        segs = C.segments(c, [(0, 5, 0, 5)], 5, FPS)
        self.assertEqual([s['variant'] for s in segs], ['base'])

    def test_project_rebase_moves_scenes_with_the_content(self):
        p = project.clean(dict(composition=dict(layout='cam_ampliada', regions=REG, scenes=[dict(id='a', start=5, end=9, layout='cinema')])), 20)
        moved = project.rebase(p, -3, 12)['composition']['scenes']
        self.assertEqual((moved[0]['start'], moved[0]['end']), (2, 6))
        dropped = project.rebase(p, -9, 12)['composition']['scenes']
        self.assertEqual(dropped, [])


class TimeMap(unittest.TestCase):
    def pieces(self, p, total=20):
        remap, teaser, lead = editing.remap_for(p, total, [])
        return media.composition_pieces(remap, teaser, lead), remap.length + lead

    def test_identity_timeline(self):
        c = comp([dict(id='a', start=4, end=8, layout='cinema')])
        pcs, dur = self.pieces(dict(speeds=[], freezes=[], replays=[], teaser=None))
        segs = C.segments(c, pcs, dur, FPS)
        self.assertEqual([(s['variant'], round(s['start'], 3), round(s['end'], 3)) for s in segs],
                         [('base', 0, 4), ('a', 4, 8), ('base', 8, 20)])

    def test_scene_follows_cuts(self):
        c = comp([dict(id='a', start=10, end=14, layout='cinema')])
        remap, teaser, lead = editing.remap_for({}, 20, [dict(start=2, end=6)])
        segs = C.segments(c, media.composition_pieces(remap, teaser, lead), remap.length + lead, FPS)
        scene = next(s for s in segs if s['variant'] == 'a')
        self.assertAlmostEqual(scene['start'], 6, places=2)        # 10 − 4 s cortados
        self.assertAlmostEqual(scene['end'], 10, places=2)
        self.assertAlmostEqual(segs[-1]['end'], 16, places=2)

    def test_scene_inside_a_cut_does_not_appear(self):
        c = comp([dict(id='a', start=3, end=5, layout='cinema')])
        remap, teaser, lead = editing.remap_for({}, 20, [dict(start=2, end=8)])
        segs = C.segments(c, media.composition_pieces(remap, teaser, lead), remap.length + lead, FPS)
        self.assertEqual({s['variant'] for s in segs}, {'base'})

    def test_scene_follows_speed_change(self):
        c = comp([dict(id='a', start=4, end=8, layout='cinema')])
        remap, teaser, lead = editing.remap_for(dict(speeds=[dict(start=4, end=8, rate=2)]), 20, [])
        segs = C.segments(c, media.composition_pieces(remap, teaser, lead), remap.length + lead, FPS)
        scene = next(s for s in segs if s['variant'] == 'a')
        self.assertAlmostEqual(scene['end'] - scene['start'], 2, places=2)   # 4 s a 2× ocupam 2 s

    def test_replay_shows_the_same_scene_again(self):
        c = comp([dict(id='a', start=4, end=8, layout='cinema')])
        remap, teaser, lead = editing.remap_for(dict(replays=[dict(id='r', start=5, end=7, rate=1, after=10, mute=True)]), 20, [])
        segs = C.segments(c, media.composition_pieces(remap, teaser, lead), remap.length + lead, FPS)
        self.assertEqual(sum(1 for s in segs if s['variant'] == 'a'), 2)

    def test_teaser_uses_the_scene_of_the_moment_it_shows(self):
        c = comp([dict(id='a', start=4, end=8, layout='cinema')])
        remap, teaser, lead = editing.remap_for(dict(teaser=dict(start=5, end=7)), 20, [])
        segs = C.segments(c, media.composition_pieces(remap, teaser, lead), remap.length + lead, FPS)
        self.assertEqual((segs[0]['variant'], round(segs[0]['end'], 2)), ('a', 2.0))   # a abertura (5–7 s) cai dentro da cena

    def test_segments_cover_everything_without_gaps_or_overlaps(self):
        c = comp([dict(id='a', start=3.1, end=6.37, layout='cinema', fade=.4), dict(id='b', start=9, end=12.2, layout='foco_reacao')])
        remap, teaser, lead = editing.remap_for(dict(speeds=[dict(start=2, end=5, rate=1.5)]), 20, [dict(start=14, end=15.3)])
        dur = remap.length + lead
        segs = C.segments(c, media.composition_pieces(remap, teaser, lead), dur, FPS)
        self.assertEqual(segs[0]['start'], 0)
        for before, after in zip(segs, segs[1:]):
            self.assertAlmostEqual(before['end'], after['start'], places=6)
        self.assertGreaterEqual(segs[-1]['end'] * FPS, round(dur * FPS))


def ffmpeg(*args):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', *args], check=True)


def solid_source(path, seconds=3):
    """Webcam vermelha, conteúdo azul, resto cinza; um contador de quadro no canto inferior direito (0–255 por quadro)."""
    ffmpeg('-f', 'lavfi', '-i', f'color=c=0x808080:s=1920x1080:r={FPS}:d={seconds}', '-vf',
           'drawbox=x=1344:y=43:w=538:h=324:color=0xFF0000:t=fill,drawbox=x=0:y=0:w=1152:h=1080:color=0x0000FF:t=fill',
           '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv444p', str(path))


def frames(source, graph, seconds=3):
    out = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-i', str(source), '-filter_complex',
                          graph + ';[base]scale=54:96:flags=area,format=rgb24[o]', '-map', '[o]', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, 96, 54, 3).astype(int)


class Pixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temp.name) / 's.mp4'
        solid_source(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def graph(self, scenes, **kw):
        c = comp(scenes, bg='black', **kw)
        segs = C.segments(c, [(0, 3, 0, 3)], 3, FPS)
        return C.video_graph(c, 1920, 1080, fps=FPS, segs=segs)

    def test_cut_switches_exactly_on_the_frame_without_dropping_or_duplicating(self):
        # base cam_ampliada: y=700 (linha 35 de 96) é webcam (vermelho); cinema com fundo preto: é barra (preto)
        out = frames(self.source, self.graph([dict(id='a', start=1.0, end=2.0, layout='cinema', content_fit='fit')]))
        self.assertEqual(len(out), 3 * FPS)
        red = out[:, 35, 27, 0] > 150
        self.assertTrue(red[:30].all() and not red[30:60].any() and red[60:].all(), red.astype(int).tolist())

    def test_fade_is_a_monotonic_ramp_over_the_requested_time(self):
        out = frames(self.source, self.graph([dict(id='a', start=1.0, end=2.0, layout='cinema', fade=.5)]))
        self.assertEqual(len(out), 3 * FPS)
        level = out[:, 35, 27, 0]
        ramp = level[30:46]                                    # 0,5 s = 15 quadros de mistura
        self.assertTrue((np.diff(ramp) <= 2).all(), ramp.tolist())   # vermelho → preto, sem voltar
        self.assertGreater(ramp[0], 200)
        self.assertLess(ramp[-1], 40)
        self.assertTrue(40 < ramp[7] < 215, ramp.tolist())       # meio da rampa: valor intermediário (não é corte)
        self.assertLess(level[50:58].max(), 30)                  # dentro da cena: estável
        self.assertGreater(level[75:].min(), 220)                # depois da cena e da volta suave: vermelho de novo

    def test_graph_decodes_the_source_once(self):
        g = self.graph([dict(id='a', start=1.0, end=2.0, layout='cinema')])
        self.assertEqual(g.count('[h]split='), 1)
        self.assertNotIn('movie=', g)
        self.assertNotIn('amovie=', g)

    def test_no_scene_is_identical_to_the_single_composition(self):
        c = comp([], bg='black')
        plain = C.video_graph(c, 1920, 1080, fps=FPS)
        scened = C.video_graph(c, 1920, 1080, fps=FPS, segs=C.segments(c, [(0, 3, 0, 3)], 3, FPS))
        self.assertEqual(plain, scened)


class RenderWithScenes(unittest.TestCase):
    def test_real_export_with_cut_and_scene_keeps_duration_and_one_audio(self):
        from tests.test_editor_pro import RealMediaTests
        helper = RealMediaTests('make_source')
        with tempfile.TemporaryDirectory() as temp:
            source = helper.make_source(temp, seconds=6, size='1280x720', preset='ultrafast')
            candidate = helper.candidate(source, seconds=6)
            candidate['profile']['content_mode'] = 'video'
            candidate['data']['project'] = project.clean(dict(
                cuts=[dict(start=1, end=2)],
                composition=dict(layout='cam_ampliada', regions=REG, scenes=[dict(id='a', start=3, end=5, layout='foco_reacao', fade=.3)])), 6)
            clip = media.render(candidate, [], temp, False, pipeline='single')
            info = media.probe(clip)
            self.assertEqual((info['width'], info['height']), (1080, 1920))
            self.assertAlmostEqual(info['duration'], 5, delta=.2)
            self.assertTrue(info['has_audio'])


if __name__ == '__main__':
    unittest.main()
