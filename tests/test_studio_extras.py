"""Extras do estúdio: layouts, velocidade, congelar quadro, imagens, versões 1:1/4:5/16:9 e placa de vídeo."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from liveclips import assets, editing, hardware, media, project
from tests.test_editor_pro import HAS_FFMPEG, ffmpeg, gray_frames, np
from tests.test_studio import StudioRenderTests


def pixel(clip, at, x, y, width, height):
    """Cor (r, g, b) do pixel (x, y) de um quadro, em coordenadas do vídeo."""
    raw = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-ss', str(at), '-i', str(clip), '-frames:v', '1',
                          '-vf', f'scale={width}:{height},format=rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    frame = np.frombuffer(raw, np.uint8).reshape(height, width, 3)
    return tuple(int(v) for v in frame[y, x])


def is_color(value, name):
    r, g, b = value
    return {'green': g > 150 and r < 110 and b < 110, 'blue': b > 150 and r < 110 and g < 110,
            'red': r > 150 and g < 110 and b < 110}[name]


class RemapExtraTests(unittest.TestCase):
    def test_speed_and_freeze_move_later_times(self):
        remap = editing.Remap(20, [], speeds=[(2, 4, 2.0)], freezes=[(10, 1.5)])
        self.assertAlmostEqual(remap.map(1), 1)
        self.assertAlmostEqual(remap.map(3), 2.5)
        self.assertAlmostEqual(remap.map(10), 9)
        self.assertAlmostEqual(remap.map(10.5), 10.5 + 1.5 - 1.0, places=2)
        self.assertAlmostEqual(remap.length, 20 - 1 + 1.5)

    def test_freeze_inside_a_cut_is_ignored(self):
        remap = editing.Remap(20, [dict(start=8, end=12)], freezes=[(10, 2)])
        self.assertAlmostEqual(remap.length, 16)

    def test_slow_motion_lengthens_the_clip(self):
        self.assertAlmostEqual(editing.Remap(10, [], speeds=[(0, 4, .5)]).length, 14)


class ProjectExtraTests(unittest.TestCase):
    def test_clean_accepts_and_limits_new_fields(self):
        value = project.clean(dict(layout=dict(mode='game_pip', pip='bl', pip_size=9, focus=4),
                                   speeds=[dict(start=2, end=4, rate=99)], freezes=[dict(at=5, duration=99)],
                                   overlays=[dict(image='a' * 16, start=1, end=3, x=2, y=-1, scale=9, opacity=0)],
                                   formats=['16x9', '1x1']), 20, image_exists=lambda _i: True)
        self.assertEqual(value['layout'], dict(mode='game_pip', pip='bl', focus=1.0, pip_size=.5))
        self.assertEqual(value['speeds'][0]['rate'], 4.0)
        self.assertEqual(value['freezes'][0]['duration'], 3.0)
        self.assertEqual((value['overlays'][0]['x'], value['overlays'][0]['y'], value['overlays'][0]['scale'],
                          value['overlays'][0]['opacity']), (1.0, 0.0, 1.0, .1))
        self.assertEqual(value['formats'], ['1x1', '16x9'])

    def test_clean_rejects_bad_new_fields(self):
        for bad in (dict(layout=dict(mode='diagonal')), dict(layout=dict(mode='split', pip='meio')),
                    dict(speeds=[dict(start=1, end=4, rate=2), dict(start=3, end=6, rate=1.5)]),
                    dict(overlays=[dict(image='../../etc', start=1, end=3)]), dict(formats=['3x2']),
                    dict(overlays=[dict(image='b' * 16, start=1, end=3)])):
            with self.assertRaises(ValueError, msg=str(bad)):
                project.clean(bad, 20, image_exists=lambda _i: False)

    def test_rebase_moves_the_new_items(self):
        base = project.clean(dict(speeds=[dict(start=4, end=8, rate=2)], freezes=[dict(at=5, duration=1)],
                                  overlays=[dict(image='c' * 16, start=2, end=6)]), 20, image_exists=lambda _i: True)
        moved = project.rebase(base, -3, 17)
        self.assertEqual((moved['speeds'][0]['start'], moved['speeds'][0]['end']), (1.0, 5.0))
        self.assertEqual(moved['freezes'][0]['at'], 2.0)
        self.assertEqual((moved['overlays'][0]['start'], moved['overlays'][0]['end']), (0.0, 3.0))


class PieceTests(unittest.TestCase):
    def test_tempo_chain_stays_inside_the_safe_range(self):
        self.assertEqual(media.tempo_chain(1.5), 'atempo=1.500000')
        self.assertEqual(media.tempo_chain(3.0), 'atempo=2.0,atempo=1.500000')
        self.assertEqual(media.tempo_chain(.3), 'atempo=0.5,atempo=0.600000')

    def test_plan_pieces_marks_speed_and_freeze(self):
        parts = [dict(path='a', **{'in': 10.0, 'out': 30.0})]
        remap = editing.Remap(20, [], speeds=[(2, 4, 2.0)], freezes=[(10, 1.5)])
        pieces = media.plan_pieces(parts, remap)
        rates = [(round(a, 2), round(b, 2), r, h) for _, a, b, r, h in pieces]
        self.assertIn((12.0, 14.0, 2.0, 0.0), rates)
        self.assertTrue(any(h == 1.5 for *_, h in pieces))

    def test_encoder_choice_prefers_cpu_unless_asked_and_tested(self):
        self.assertEqual(hardware.choose('cpu')[0], 'cpu')
        self.assertEqual(hardware.choose('auto', draft=True)[0], 'cpu')
        original = hardware.detect
        try:
            hardware.detect = lambda runner=None: ['nvenc']
            self.assertEqual(hardware.choose('auto')[0], 'nvenc')
            self.assertEqual(hardware.choose('qsv')[0], 'cpu')  # escolhido mas não passou no teste
            self.assertEqual(hardware.choose('auto', force_cpu=True)[0], 'cpu')
            self.assertIn('h264_nvenc', hardware.choose('nvenc')[1])
        finally:
            hardware.detect = original

    def test_detect_requires_a_real_test_encode(self):
        def runner(args, timeout=60):
            if '-encoders' in args:
                return ' V....D h264_nvenc NVIDIA\n V....D h264_qsv Intel\n V....D libx264 x264'
            if 'h264_nvenc' in args:
                raise RuntimeError('Cannot load libcuda')
            return ''
        self.assertEqual(hardware.listed(runner(['-encoders'])), ['nvenc', 'qsv'])
        self.assertEqual(hardware.detect(runner), ['qsv'])


@unittest.skipUnless(HAS_FFMPEG, 'FFmpeg/ffprobe ou numpy não encontrados')
class ExtrasRenderTests(unittest.TestCase):
    make_source = StudioRenderTests.make_source
    candidate = StudioRenderTests.candidate
    flashes = StudioRenderTests.flashes
    rms_between = StudioRenderTests.rms_between

    def color_source(self, root, seconds=4):
        """Câmera (canto superior esquerdo, 25%) verde; jogo azul à direita da emenda e vermelho à esquerda."""
        source = Path(root) / 'cores.ts'
        chain = (f'color=c=blue:s=1280x720:r=30:d={seconds},drawbox=x=0:y=180:w=640:h=540:color=red:t=fill,'
                 'drawbox=x=0:y=0:w=320:h=180:color=0x00FF00:t=fill')
        ffmpeg('-f', 'lavfi', '-i', chain, '-f', 'lavfi', '-i', f'sine=f=440:duration={seconds}', '-c:v', 'libx264',
               '-preset', 'veryfast', '-crf', '14', '-c:a', 'aac', '-shortest', str(source))
        return source

    def render(self, temp, source, proj, seconds=4, mode=False, **profile):
        cand = self.candidate(source, proj, seconds=seconds, **profile)
        return media.render(cand, [], temp, mode, pipeline='single', root=temp)

    def test_speed_up_shortens_and_keeps_sync(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render(temp, self.make_source(temp), dict(speeds=[dict(start=4, end=8, rate=2)]), seconds=12)
            self.assertAlmostEqual(media.probe(clip)['duration'], 10, delta=.12)
            self.assertAlmostEqual(media.audio_duration(clip), 10, delta=.15)
            for found, wanted in zip(self.flashes(clip), [1, 3, 4.5, 5.5, 7, 9]):
                self.assertAlmostEqual(found, wanted, delta=.12)

    def test_slow_motion_lengthens(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render(temp, self.make_source(temp), dict(speeds=[dict(start=0, end=2, rate=.5)]), seconds=12)
            self.assertAlmostEqual(media.probe(clip)['duration'], 14, delta=.15)
            self.assertAlmostEqual(self.flashes(clip)[0], 2.0, delta=.12)

    def test_freeze_frame_stops_picture_and_silences_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render(temp, self.make_source(temp), dict(freezes=[dict(at=4, duration=2)]), seconds=12)
            self.assertAlmostEqual(media.probe(clip)['duration'], 14, delta=.15)
            frames = gray_frames(clip, 64, 36).astype(float)
            still = np.abs(np.diff(frames[int(4.3 * 30):int(5.8 * 30)], axis=0)).mean()
            moving = np.abs(np.diff(frames[int(8 * 30):int(8.7 * 30)], axis=0)).mean()
            self.assertLess(still, .05)
            self.assertGreater(moving, still + .3)
            self.assertLess(self.rms_between(clip, 5.0, 5.2), .002)   # onde estaria o beep de 5 s (que passou para 7 s)
            self.assertGreater(self.rms_between(clip, 7.0, 7.1), .01)

    def test_live_layouts_place_camera_and_game(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.color_source(temp)
            cases = {
                'cam_top': [((540, 300), 'green'), ((300, 1500), 'red'), ((800, 1500), 'blue')],
                'split': [((540, 900), 'green'), ((300, 1500), 'red'), ((800, 1500), 'blue')],
                'cam_full': [((540, 960), 'green'), ((540, 100), 'green')],
                'game_pip': [((846, 347), 'green'), ((200, 1500), 'red'), ((1000, 1500), 'blue')],
            }
            for mode, checks in cases.items():
                with self.subTest(layout=mode):
                    clip = self.render(temp, source, dict(layout=dict(mode=mode, focus=.5)))
                    self.assertEqual((media.probe(clip)['width'], media.probe(clip)['height']), (1080, 1920))
                    for (x, y), name in checks:
                        self.assertTrue(is_color(pixel(clip, 1.5, x, y, 1080, 1920), name), msg=f'{mode} {x},{y} {name}')

    def test_game_focus_chooses_which_side_of_the_game_is_shown(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.color_source(temp)
            left = self.render(temp, source, dict(layout=dict(mode='cam_top', focus=0)))
            self.assertTrue(is_color(pixel(left, 1.5, 1000, 1500, 1080, 1920), 'red'))
            right = self.render(temp, source, dict(layout=dict(mode='cam_top', focus=1)))
            self.assertTrue(is_color(pixel(right, 1.5, 100, 1500, 1080, 1920), 'blue'))

    def test_video_fill_crops_and_fit_keeps_the_whole_frame(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.color_source(temp)
            fit = self.render(temp, source, dict(layout=dict(mode='fit')), content_mode='video')
            fill = self.render(temp, source, dict(layout=dict(mode='fill', focus=0)), content_mode='video')
            # fit: a imagem inteira cabe na largura (barras desfocadas em cima e embaixo); o centro mostra a emenda vermelho/azul
            self.assertTrue(is_color(pixel(fit, 1.5, 100, 960, 1080, 1920), 'red'))
            self.assertTrue(is_color(pixel(fit, 1.5, 1000, 960, 1080, 1920), 'blue'))
            # fill com foco à esquerda: só vê a parte esquerda do vídeo (câmera verde no topo, vermelho no resto)
            self.assertTrue(is_color(pixel(fill, 1.5, 1000, 1500, 1080, 1920), 'red'))

    def test_image_overlay_appears_only_in_its_interval(self):
        with tempfile.TemporaryDirectory() as temp:
            picture = Path(temp) / 'meme.png'
            ffmpeg('-f', 'lavfi', '-i', 'color=c=yellow:s=300x300', '-frames:v', '1', str(picture))
            item = assets.import_image(temp, picture, 'meme')
            source = self.color_source(temp, 6)
            proj = dict(overlays=[dict(image=item['id'], start=2, end=4, x=.5, y=.7, scale=.4, opacity=1)])
            clip = self.render(temp, source, proj, seconds=6)
            def yellow(value):
                return value[0] > 180 and value[1] > 180 and value[2] < 120
            self.assertFalse(yellow(pixel(clip, 1.0, 540, 1344, 1080, 1920)))
            self.assertTrue(yellow(pixel(clip, 3.0, 540, 1344, 1080, 1920)))
            self.assertFalse(yellow(pixel(clip, 5.0, 540, 1344, 1080, 1920)))
            manifest = json.loads((clip.parent / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['project']['overlays'][0]['image'], item['id'])

    def test_missing_overlay_image_gives_a_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.color_source(temp)
            cand = self.candidate(source, None, seconds=4)
            cand['data']['project'] = project.clean(dict(overlays=[dict(image='d' * 16, start=1, end=2)]), 4, image_exists=lambda _i: True)
            with self.assertRaisesRegex(ValueError, 'biblioteca'):
                media.render(cand, [], temp, False, pipeline='single', root=temp)

    def test_extra_formats_are_delivered_with_the_right_sizes(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render(temp, self.color_source(temp), dict(formats=['1x1', '4x5', '16x9'],
                                                                   titles=[dict(text='Olha isso', start=0, end=2)]))
            folder = clip.parent
            expected = {'1x1': (1080, 1080), '4x5': (1080, 1350), '16x9': (1920, 1080)}
            for name, size in expected.items():
                info = media.probe(folder / f'clipe_{name}.mp4')
                self.assertEqual((info['width'], info['height']), size, name)
                self.assertAlmostEqual(info['duration'], media.probe(clip)['duration'], delta=.2)
            manifest = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['variants'], {'1x1': 'ok', '4x5': 'ok', '16x9': 'ok'})
            self.assertTrue(is_color(pixel(folder / 'clipe_16x9.mp4', 1.5, 100, 600, 1920, 1080), 'red'))
            self.assertTrue(is_color(pixel(folder / 'clipe_1x1.mp4', 1.5, 540, 100, 1080, 1080), 'green'))

    def test_draft_does_not_render_extra_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = self.render(temp, self.color_source(temp), dict(formats=['1x1']), mode='draft')
            self.assertFalse((clip.parent / 'clipe_1x1.mp4').exists())

    def test_hardware_failure_falls_back_to_cpu(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            original_choose, original_run = hardware.choose, media.run
            def fake_choose(preference='auto', draft=False, force_cpu=False, mode='equilibrado'):
                if force_cpu or draft:
                    return 'cpu', list(hardware.CPU_FINAL if not draft else hardware.CPU_DRAFT)
                calls.append('hw')
                return 'nvenc', ['-c:v', 'h264_nvenc_inexistente']
            hardware.choose = fake_choose
            try:
                clip = self.render(temp, self.color_source(temp), None, video_encoder='auto')
            finally:
                hardware.choose = original_choose
            manifest = json.loads((clip.parent / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertEqual(calls, ['hw'])
            self.assertEqual(manifest['encoder'], 'cpu')
            self.assertIn('nvenc', manifest['encoder_fallback'])


if __name__ == '__main__':
    unittest.main()
