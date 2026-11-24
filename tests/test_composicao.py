"""Composição de reação (sem IA): validação, geometria e PIXELS do FFmpeg contra o plano de `composition.resolve()`."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import composition as C
from liveclips import media, project

SW, SH = 1920, 1080
BLOCK = 120
WEBCAM = dict(x=.70, y=.04, w=.28, h=.30)        # webcam do streamer, canto superior direito
CONTENT = dict(x=0.0, y=0.0, w=.68, h=1.0)        # conteúdo reagido, lado esquerdo
CAM2 = dict(x=.36, y=.04, w=.28, h=.30)


def pattern():
    """Quadro 1920x1080 de blocos 120x120 com cores determinísticas bem distintas (identifica qualquer pixel da fonte)."""
    rng = np.random.RandomState(7)
    cells = rng.randint(0, 6, size=(SH // BLOCK, SW // BLOCK, 3)) * 48 + 15
    return np.kron(cells, np.ones((BLOCK, BLOCK, 1))).astype(np.uint8)


def source_color(frame, x, y):
    """Cor da fonte em (x,y) se a vizinhança de ±5 px for uniforme; senão None (borda de bloco: ponto descartado)."""
    x, y = int(round(x)), int(round(y))
    patch = frame[max(0, y - 5):y + 6, max(0, x - 5):x + 6].reshape(-1, 3)
    if not (patch == patch[0]).all():
        return None
    return patch[0].astype(int)


def encode_source(path, frame):
    raw = Path(str(path) + '.rgb')
    raw.write_bytes(frame.tobytes() * 12)
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{SW}x{SH}',
                    '-r', '10', '-i', str(raw), '-t', '1', '-vf', 'format=yuv444p', '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv444p',
                    str(path)], check=True)
    raw.unlink()


def render_frame(source, graph, at=.3, size=(1080, 1920)):
    out = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-ss', str(at), '-i', str(source), '-filter_complex', graph + ';[base]format=rgb24[rgb]',
                          '-map', '[rgb]', '-frames:v', '1', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(size[1], size[0], 3).astype(int)


def regions_for(layout):
    reg = dict(webcam=WEBCAM, conteudo=CONTENT)
    if layout == 'dueto':
        reg = dict(webcam=dict(x=.70, y=.02, w=.28, h=.5), webcam2=dict(x=.36, y=.02, w=.28, h=.5))
    if layout == 'duas_cams':
        reg['webcam2'] = CAM2
    return reg


class Validation(unittest.TestCase):
    def test_none_and_empty_mean_no_composition(self):
        self.assertIsNone(C.clean(None))
        self.assertIsNone(C.clean({}))

    def test_unknown_layout_is_an_error(self):
        with self.assertRaises(ValueError):
            C.clean(dict(layout='inexistente'))

    def test_invalid_regions_are_errors(self):
        for bad in (dict(x=.1, y=.1, w=.3), dict(x='a', y=0, w=.3, h=.3), dict(x=float('nan'), y=0, w=.3, h=.3),
                    dict(x=.1, y=.1, w=.005, h=.3), dict(x=1.4, y=.1, w=.2, h=.3), dict(x=.2, y=-.9, w=.2, h=.3), 'x'):
            with self.assertRaises(ValueError, msg=str(bad)):
                C.clean(dict(layout='cam_ampliada', regions=dict(webcam=bad)))

    def test_region_partly_outside_is_clipped_to_the_frame(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.8, y=-.1, w=.4, h=.4))))
        r = comp['regions']['webcam']
        self.assertAlmostEqual(r['x'] + r['w'], 1.0, places=4)
        self.assertEqual(r['y'], 0)

    def test_negative_size_rectangles_are_normalized(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.5, y=.5, w=-.2, h=-.2))))
        self.assertEqual(comp['regions']['webcam'], dict(x=.3, y=.3, w=.2, h=.2))

    def test_params_are_clamped_and_enums_checked(self):
        comp = C.clean(dict(layout='cam_ampliada', params=dict(split=5, gap=999, content_zoom=-3)))
        self.assertEqual(comp['params']['split'], .85)
        self.assertEqual(comp['params']['gap'], 40)
        self.assertEqual(comp['params']['content_zoom'], 1)
        for bad in (dict(content_fit='x'), dict(bg='x'), dict(pip='x')):
            with self.assertRaises(ValueError):
                C.clean(dict(layout='cam_ampliada', params=bad))

    def test_unsafe_text_never_reaches_the_graph(self):
        comp = C.clean(dict(layout='cam_flutuante', regions=regions_for('cam_flutuante'),
                            params=dict(bg='color', bg_color="#12345;drop", pip_border=4, pip_border_color="'; rm -rf")))
        self.assertEqual(comp['params']['bg_color'], '#101010')
        graph = C.video_graph(comp, SW, SH)
        self.assertNotIn('rm -rf', graph)
        self.assertNotIn('drop', graph)

    def test_incomplete_composition_is_saved_but_not_ready(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=dict(webcam=WEBCAM)))
        self.assertFalse(C.is_ready(comp))
        self.assertEqual(C.missing_roles(comp), ['conteudo'])
        with self.assertRaises(ValueError):
            C.video_graph(comp, SW, SH)

    def test_project_clean_roundtrip_and_old_projects(self):
        old = project.clean({}, 30)
        self.assertIsNone(old['composition'])        # projeto antigo (sem o campo) abre sem composição
        raw = dict(composition=dict(layout='cam_ampliada', regions=regions_for('cam_ampliada')))
        a = project.clean(raw, 30)
        self.assertEqual(project.clean(a, 30)['composition'], a['composition'])   # idempotente

    def test_catalog_lists_the_eight_layouts_and_three_main_ones_first(self):
        cat = C.catalog()
        self.assertEqual(len(cat['layouts']), 8)
        self.assertEqual([l['id'] for l in cat['layouts'] if l['group'] == 'main'], ['cam_compacta', 'cam_ampliada', 'cam_flutuante'])


class Geometry(unittest.TestCase):
    def test_every_layout_stays_inside_the_canvas_even_and_undistorted(self):
        for layout in C.LAYOUTS:
            for fit in C.FITS:
                for gap in (0, 12):
                    comp = C.clean(dict(layout=layout, regions=regions_for(layout),
                                        params=dict(content_fit=fit, cam_fit=fit, cam2_fit=fit, content_zoom=1.7, gap=gap, content_fx=.2)))
                    plan = C.resolve(comp, SW, SH)
                    self.assertTrue(plan['ready'])
                    for layer in plan['layers']:
                        x, y = layer['pos']
                        w, h = layer['size']
                        cx, cy, cw, ch = layer['crop']
                        msg = f'{layout}/{fit}/{layer["role"]}'
                        self.assertTrue(0 <= x and x + w <= 1080 and 0 <= y and y + h <= 1920, msg)
                        self.assertTrue(all(v % 2 == 0 for v in (x, y, w, h, cx, cy, cw, ch)), msg)
                        self.assertTrue(0 <= cx and cx + cw <= SW and 0 <= cy and cy + ch <= SH, msg)
                        self.assertLess(layer['aspect_error'], .012, msg)

    def test_fit_shows_the_whole_region_fill_crops(self):
        reg = dict(webcam=WEBCAM, conteudo=CONTENT)
        fit = C.resolve(C.clean(dict(layout='cinema', regions=reg)), SW, SH)
        content = next(l for l in fit['layers'] if l['role'] == 'conteudo')
        self.assertEqual(content['hidden'], 0)
        fill = C.resolve(C.clean(dict(layout='cam_ampliada', regions=reg)), SW, SH)
        content = next(l for l in fill['layers'] if l['role'] == 'conteudo')
        self.assertGreater(content['hidden'], .1)
        self.assertTrue(any('fora do quadro' in w for w in fill['warnings']))

    def test_small_webcam_warns_about_upscale(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.8, y=.05, w=.1, h=.1), conteudo=CONTENT)))
        self.assertTrue(any('ampliada' in w for w in C.resolve(comp, SW, SH)['warnings']))

    def test_floating_window_keeps_the_webcam_aspect_and_respects_the_corner(self):
        for corner in ('tl', 'tr', 'bl', 'br'):
            comp = C.clean(dict(layout='cam_flutuante', regions=regions_for('cam_flutuante'), params=dict(pip=corner)))
            cam = next(l for l in C.resolve(comp, SW, SH)['layers'] if l['role'] == 'webcam')
            self.assertAlmostEqual(cam['size'][0] / cam['size'][1], (WEBCAM['w'] * SW) / (WEBCAM['h'] * SH), delta=.02)
            self.assertEqual(cam['pos'][0] < 540, corner[1] == 'l')
            self.assertEqual(cam['pos'][1] < 960, corner[0] == 't')

    def test_foco_reacao_can_hide_the_content_window(self):
        comp = C.clean(dict(layout='foco_reacao', regions=regions_for('foco_reacao'), params=dict(hide_content=True)))
        self.assertEqual([l['role'] for l in C.resolve(comp, SW, SH)['layers']], ['webcam'])

    def test_resolution_independence(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada')))
        a, b = C.resolve(comp, 1920, 1080), C.resolve(comp, 3840, 2160)
        for la, lb in zip(a['layers'], b['layers']):
            self.assertEqual((la['size'], la['pos']), (lb['size'], lb['pos']))
            for u, v in zip(la['crop'], lb['crop']):
                self.assertAlmostEqual(u * 2, v, delta=4)


class Pixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.frame = pattern()
        cls.source = Path(cls.temp.name) / 'fonte.mp4'
        encode_source(cls.source, cls.frame)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_layers(self, comp, tolerance=14):
        graph = C.video_graph(comp, SW, SH)
        out = render_frame(self.source, graph)
        plan = C.resolve(comp, SW, SH)
        checked = 0
        for layer in plan['layers']:
            x, y = layer['pos']
            w, h = layer['size']
            cx, cy, cw, ch = layer['crop']
            for u in (.15, .4, .62, .85):
                for v in (.15, .4, .62, .85):
                    expected = source_color(self.frame, cx + u * cw, cy + v * ch)
                    if expected is None:
                        continue
                    got = out[int(y + v * h), int(x + u * w)]
                    # a camada de cima prevalece: ignora pontos cobertos por outra camada de z maior
                    covered = any(o['z'] > layer['z'] and o['pos'][0] <= x + u * w < o['pos'][0] + o['size'][0]
                                  and o['pos'][1] <= y + v * h < o['pos'][1] + o['size'][1] for o in plan['layers'])
                    if covered:
                        continue
                    self.assertLessEqual(int(np.abs(got - expected).max()), tolerance,
                                         f'{comp["layout"]}/{layer["role"]} em ({u},{v}): {got} != {expected}')
                    checked += 1
        self.assertGreaterEqual(checked, 4, comp['layout'])
        return out, plan

    def test_all_eight_layouts_match_the_plan_pixel_by_pixel(self):
        for layout in C.LAYOUTS:
            for fit in ('fill', 'fit'):
                with self.subTest(layout=layout, fit=fit):
                    comp = C.clean(dict(layout=layout, regions=regions_for(layout), params=dict(content_fit=fit, cam_fit=fit, cam2_fit=fit)))
                    self.check_layers(comp)

    def test_custom_zoom_and_focus_match_the_plan(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada'),
                            params=dict(content_fit='custom', content_zoom=1.6, content_fx=.9, content_fy=.2, cam_fit='custom', cam_zoom=1.3)))
        self.check_layers(comp)

    def test_gap_and_solid_background_show_the_chosen_color(self):
        comp = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada'), params=dict(gap=20, bg='color', bg_color='#FF00AA')))
        out, plan = self.check_layers(comp)
        top = C._even(1920 * comp['params']['split'])
        strip = out[top + 8:top + 12, 100:980]
        self.assertTrue((np.abs(strip - np.array([255, 0, 170])).max(axis=2) <= 16).all())

    def test_cinema_fit_leaves_background_bars_not_stretched_content(self):
        comp = C.clean(dict(layout='cinema', regions=regions_for('cinema'), params=dict(bg='black', content_fit='fit')))
        out, plan = self.check_layers(comp)
        content = next(l for l in plan['layers'] if l['role'] == 'conteudo')
        self.assertLess(content['size'][1], 1920 - C._even(1920 * comp['params']['split']))   # sobra espaço vertical
        bar_y = C._even(1920 * comp['params']['split']) + 4
        self.assertLess(out[bar_y, 20:1060].max(), 20)                                        # barra preta

    def test_blur_background_is_smooth_and_not_black(self):
        comp = C.clean(dict(layout='cinema', regions=regions_for('cinema'), params=dict(bg='blur')))
        out, plan = self.check_layers(comp)
        bar_y = C._even(1920 * comp['params']['split']) + 4
        row = out[bar_y, 20:1060]
        self.assertGreater(row.mean(), 20)
        self.assertLess(np.abs(np.diff(row, axis=0)).mean(), 4)

    def test_floating_border_is_drawn(self):
        comp = C.clean(dict(layout='cam_flutuante', regions=regions_for('cam_flutuante'), params=dict(pip_border=6, pip_border_color='#00FF00')))
        out, plan = self.check_layers(comp, tolerance=14)
        cam = next(l for l in plan['layers'] if l['role'] == 'webcam')
        x, y = cam['pos']
        self.assertGreater(out[y + 2, x + 40, 1], 200)
        self.assertLess(out[y + 2, x + 40, 0], 60)

    def test_incomplete_composition_graph_is_refused_not_guessed(self):
        comp = C.clean(dict(layout='duas_cams', regions=dict(webcam=WEBCAM)))
        with self.assertRaises(ValueError):
            C.video_graph(comp, SW, SH)


class Masks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Pixels.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def out_point(self, plan, role, sx, sy):
        layer = next(l for l in plan['layers'] if l['role'] == role)
        cx, cy, cw, ch = layer['crop']
        return int(layer['pos'][0] + (sx - cx) / cw * layer['size'][0]), int(layer['pos'][1] + (sy - cy) / ch * layer['size'][1])

    def test_validation(self):
        for bad in ('x', [dict(kind='x', region=dict(x=.1, y=.1, w=.2, h=.2))], [dict(kind='blur', region=dict(x=.1, y=.1, w=.001, h=.2))],
                    [dict(kind='cover', region=dict(x=.1, y=.1, w=.2, h=.2))] * 7):
            with self.assertRaises(ValueError, msg=str(bad)):
                C.clean(dict(layout='cam_ampliada', masks=bad))
        ok = C.clean(dict(layout='cam_ampliada', masks=[dict(kind='cover', region=dict(x=.1, y=.1, w=.2, h=.2), color='#FF0000')]))
        self.assertEqual(ok['masks'][0]['color'], '#FF0000')

    def test_cover_paints_the_marked_source_area_in_the_output(self):
        # bloco de fonte (x 480..600, y 360..480) fica dentro do recorte do conteúdo; cobre com verde
        mask = dict(kind='cover', color='#00FF00', region=dict(x=470 / SW, y=350 / SH, w=140 / SW, h=140 / SH))
        comp = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada'), masks=[mask]))
        out = render_frame(self.source, C.video_graph(comp, SW, SH))
        plan = C.resolve(comp, SW, SH)
        x, y = self.out_point(plan, 'conteudo', 540, 420)
        self.assertGreater(out[y, x, 1], 220)
        self.assertLess(out[y, x, 0], 60)
        # fora da área coberta o conteúdo continua igual ao da fonte
        ox, oy = self.out_point(plan, 'conteudo', 180, 180)
        expected = source_color(self.frame, 180, 180)
        if expected is not None:
            self.assertLessEqual(int(np.abs(out[oy, ox] - expected).max()), 14)

    def test_blur_removes_detail_only_inside_the_area(self):
        comp0 = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada')))
        mask = dict(kind='blur', region=dict(x=480 / SW, y=240 / SH, w=240 / SW, h=360 / SH))
        comp1 = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada'), masks=[mask]))
        a, b = (render_frame(self.source, C.video_graph(c, SW, SH)) for c in (comp0, comp1))
        plan = C.resolve(comp1, SW, SH)
        x0, y0 = self.out_point(plan, 'conteudo', 480, 240)
        x1, y1 = self.out_point(plan, 'conteudo', 720, 600)
        inside = np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1]).mean()
        top = np.abs(a[:C._even(1920 * comp1['params']['split'])] - b[:C._even(1920 * comp1['params']['split'])]).mean()
        self.assertGreater(inside, 4)
        self.assertLess(top, 2)                                   # a webcam (fora da área) não muda (resta só arredondamento de cor do overlay)

    def test_masks_apply_to_every_scene(self):
        mask = dict(kind='cover', color='#00FF00', region=dict(x=0, y=0, w=.5, h=.5))
        comp = C.clean(dict(layout='cam_ampliada', regions=regions_for('cam_ampliada'), masks=[mask],
                            scenes=[dict(id='a', start=1, end=2, layout='cinema')]), 3)
        graph = C.video_graph(comp, SW, SH, fps=10, segs=C.segments(comp, [(0, 1, 0, 1), (1, 2, 1, 2), (2, 3, 2, 3)], 3, 10))
        self.assertEqual(graph.count('drawbox=x=0:y=0:w=960:h=540:color=0x00FF00'), 1)   # aplicado uma vez, antes da divisão em cenas


class LiveWebcamWhileContentIsStill(unittest.TestCase):
    """Requisito central: conteúdo parado + webcam em movimento → a webcam continua se mexendo na saída."""

    def test_webcam_region_moves_while_content_region_is_frozen(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'f.mp4'
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x303060:s=1920x1080:r=10:d=2',
                            '-f', 'lavfi', '-i', 'testsrc2=s=538x324:r=10:d=2', '-filter_complex',
                            '[0:v]drawbox=x=100:y=100:w=800:h=600:color=orange:t=fill[b];[b][1:v]overlay=1344:43', '-c:v', 'libx264', '-qp', '0', str(source)], check=True)
            comp = C.clean(dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.70, y=.04, w=.28, h=.30), conteudo=dict(x=0, y=0, w=.5, h=.8))))
            graph = C.video_graph(comp, SW, SH)
            a, b = render_frame(source, graph, .2), render_frame(source, graph, 1.4)
            top = C._even(1920 * comp['params']['split'])
            self.assertGreater(np.abs(a[:top] - b[:top]).mean(), 8)             # webcam mudou
            self.assertLess(np.abs(a[top + 20:] - b[top + 20:]).mean(), .5)     # conteúdo parado continua parado


class EndToEndRender(unittest.TestCase):
    """Exportação real pelo render da aplicação: composição, áudio único, duração e prévia (draft) com a mesma composição."""

    def setUp(self):
        from tests.test_editor_pro import RealMediaTests
        self.helper = RealMediaTests('make_source')

    def render(self, mode, comp, temp, preview=False):
        source = self.helper.make_source(temp, seconds=4, size='1280x720', preset='ultrafast')
        candidate = self.helper.candidate(source, seconds=4)
        candidate['data']['project'] = project.clean(dict(composition=comp), 4)
        candidate['profile']['content_mode'] = 'video'
        return media.render(candidate, [], temp, preview, pipeline='single')

    def test_export_is_vertical_has_one_audio_stream_and_the_right_duration(self):
        comp = dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.6, y=.05, w=.35, h=.4), conteudo=dict(x=0, y=0, w=.6, h=1)))
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render('final', comp, temp)
            info = media.probe(clip)
            self.assertEqual((info['width'], info['height']), (1080, 1920))
            self.assertAlmostEqual(info['duration'], 4, delta=.15)
            data = json.loads(subprocess.run([media.tool('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json', str(clip)],
                                             capture_output=True, text=True, check=True).stdout)
            self.assertEqual(sum(1 for s in data['streams'] if s['codec_type'] == 'audio'), 1)

    def test_composition_really_changes_the_frame_and_old_projects_do_not(self):
        comp = dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.6, y=.05, w=.35, h=.4), conteudo=dict(x=0, y=0, w=.6, h=1)))
        with tempfile.TemporaryDirectory() as temp:
            with_comp = self.render('final', comp, temp + '/a') if Path(temp, 'a').mkdir() is None else None
            without = self.render('final', None, temp + '/b') if Path(temp, 'b').mkdir() is None else None
            def top_half(clip):
                raw = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-ss', '.5', '-i', str(clip), '-frames:v', '1',
                                      '-vf', 'format=gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
                return np.frombuffer(raw, np.uint8).reshape(1920, 1080).astype(int)
            self.assertGreater(np.abs(top_half(with_comp) - top_half(without)).mean(), 8)

    def test_draft_preview_uses_the_same_composition(self):
        comp = dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.6, y=.05, w=.35, h=.4), conteudo=dict(x=0, y=0, w=.6, h=1)))
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render('draft', comp, temp, preview='draft')
            info = media.probe(clip)
            self.assertEqual((info['width'], info['height']), (540, 960))


if __name__ == '__main__':
    unittest.main()
