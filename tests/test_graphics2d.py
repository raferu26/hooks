import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from liveclips import graphics2d as motion, media, project
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store, profile_checked
from liveclips.timeline import build_timeline, plan


def item(**kw):
    base = dict(template='titulo_animado', start=1.0, duration=3.0, text='Olha só', accent='#FFD600', ink='#FFFFFF')
    base.update(kw)
    return motion.clean(base, 30)


class Validation(unittest.TestCase):
    def test_clean_keeps_only_known_fields_and_limits_text(self):
        got = motion.clean(dict(template='barra_nome', text='x' * 200, subtitle='y', accent='ff0000', script='__import__("os")', expr='1+1'), 30)
        self.assertEqual(len(got['text']), 60)
        self.assertEqual(got['accent'], '#FF0000')
        self.assertNotIn('script', got)
        self.assertNotIn('expr', got)

    def test_rejects_bad_inputs(self):
        for bad in (dict(template='explosao'), dict(template='contador', value='abc'), dict(template='contador', value=-1),
                    dict(template='titulo_animado', text='ok', accent='vermelho'), dict(template='titulo_animado'),
                    dict(template='titulo_animado', text='ok', duration=99), dict(template='titulo_animado', text='ok', start=float('nan'))):
            with self.assertRaises(motion.MotionError, msg=str(bad)):
                motion.clean(bad, 30)
        with self.assertRaises(motion.MotionError):
            motion.clean('texto solto', 30)

    def test_time_is_clamped_to_the_cut(self):
        got = motion.clean(dict(template='titulo_animado', text='a', start=28, duration=5), 30)
        self.assertLessEqual(got['start'] + got['duration'], 30 + 1e-6)

    def test_profile_and_project_validation(self):
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, motion_level='leve'))['motion_level'], 'leve')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, motion_level='insano'))
        cleaned = project.clean(dict(motion=[dict(template='contador', value=10, start=1, duration=2)]), 20)
        self.assertEqual(cleaned['motion'][0]['template'], 'contador')
        self.assertNotIn('motion', project.clean({}, 20))              # projetos sem gráfico ficam idênticos
        with self.assertRaises(ValueError):
            project.clean(dict(motion=[dict(template='x')]), 20)
        with self.assertRaises(ValueError):
            project.clean(dict(motion=[dict(template='contador', value=1)] * 5), 20)


class Budget(unittest.TestCase):
    def test_short_cut_gets_no_graphics(self):
        accepted, why = motion.apply_budget([item()], 6.0, 'completo')
        self.assertEqual(accepted, [])
        self.assertIn('curto demais', why[0]['motivo'])

    def test_limits_share_gap_and_level(self):
        items = [item(start=1, duration=2), item(start=2.5, duration=2), item(start=10, duration=2), item(start=20, duration=2, template='pulso_audio', text='')]
        accepted, decisions = motion.apply_budget(items, 40.0, 'completo')
        self.assertEqual([a['start'] for a in accepted], [1, 10])                       # o 2º colide com o 1º; o 4º passaria do máximo de 2
        self.assertIn('intervalo', decisions[1]['motivo'])
        self.assertIn('no máximo', decisions[3]['motivo'])
        share, why = motion.apply_budget([item(start=1, duration=6)], 20.0, 'completo')
        self.assertEqual(share, [])
        self.assertIn('%', why[0]['motivo'])
        cheap, why = motion.apply_budget([item(template='pulso_audio', text='', start=1, duration=2)], 40.0, 'leve')
        self.assertEqual(cheap, [])
        self.assertIn('custo', why[0]['motivo'])
        off, why = motion.apply_budget([item()], 40.0, 'off')
        self.assertEqual(off, [])
        self.assertIn('configuração', why[0]['motivo'])

    def test_automatic_item_respects_titles_and_length(self):
        self.assertEqual(motion.automatic_items(dict(streamer='Canal'), 30.0)[0]['template'], 'barra_nome')
        self.assertEqual(motion.automatic_items(dict(streamer='Canal'), 30.0, has_title_at_start=True), [])
        self.assertEqual(motion.automatic_items(dict(streamer='Canal'), 5.0), [])
        self.assertEqual(motion.automatic_items({}, 30.0), [])


class Drawing(unittest.TestCase):
    canvas = (1080, 1920)

    def test_two_variants_of_a_template_differ_by_data_only(self):
        a = motion.draw_frame(item(template='barra_nome', text='Canal A', subtitle='um'), 1.5, self.canvas)
        b = motion.draw_frame(item(template='barra_nome', text='Outro Nome', subtitle='dois', accent='#00AAFF'), 1.5, self.canvas)
        self.assertEqual(a.size, b.size)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        arr_a, arr_b = np.asarray(a).astype(int), np.asarray(b).astype(int)
        self.assertTrue(((arr_a[:, :, 0] > 240) & (arr_a[:, :, 1] > 190) & (arr_a[:, :, 2] < 30) & (arr_a[:, :, 3] > 240)).any())   # amarelo
        self.assertTrue(((arr_b[:, :, 2] > 240) & (arr_b[:, :, 0] < 30) & (arr_b[:, :, 3] > 240)).any())                             # azul

    def test_transparent_background_and_animation_over_time(self):
        first = np.asarray(motion.draw_frame(item(template='barra_nome', text='Canal'), 0.0, self.canvas))
        mid = np.asarray(motion.draw_frame(item(template='barra_nome', text='Canal'), 1.5, self.canvas))
        self.assertEqual(first[:, :, 3].max(), 0)                  # no instante 0 nada aparece
        self.assertGreater(mid[:, :, 3].max(), 200)
        self.assertEqual(mid[0, -1, 3], 0)                         # fora do painel continua transparente

    def test_counter_progress_and_number_format(self):
        self.assertEqual(motion.fmt_number(1500), '1.500')
        self.assertEqual(motion.fmt_number(1234.5, 1), '1.234,5')
        c = item(template='contador', value=1500, text='seguidores', duration=3)
        early = np.asarray(motion.draw_frame(c, .5, self.canvas))[:, :, 3].sum()
        late = np.asarray(motion.draw_frame(c, 2.3, self.canvas))[:, :, 3].sum()
        self.assertGreater(late, early)                            # mais dígitos visíveis no fim da contagem

    def test_audio_bands_follow_the_tone(self):
        rate = 16000
        t = np.arange(rate * 4) / rate
        samples = np.where(t < 2, np.sin(2 * np.pi * 150 * t), np.sin(2 * np.pi * 2500 * t)).astype('float32') * .5
        low = motion.band_levels(samples, 0.2, 1.0)
        high = motion.band_levels(samples, 2.4, 1.0)
        self.assertLess(low.mean(axis=0).argmax(), 3)
        self.assertGreater(high.mean(axis=0).argmax(), 5)
        self.assertTrue(((low >= 0) & (low <= 1)).all())

    def test_pulse_frames_react_to_levels(self):
        pulse = item(template='pulso_audio', text='', duration=2)
        quiet = np.asarray(motion.draw_frame(pulse, 1.0, self.canvas, bands=[.1] * 9))[:, :, 3].sum()
        loud = np.asarray(motion.draw_frame(pulse, 1.0, self.canvas, bands=[.9] * 9))[:, :, 3].sum()
        self.assertGreater(loud, quiet * 3)


class CacheAndEncoding(unittest.TestCase):
    def test_cache_by_params_version_and_canvas(self):
        with tempfile.TemporaryDirectory() as root:
            a = motion.render_item(item(), (1080, 1920), root, 'completo')
            self.assertFalse(a['cached'])
            again = motion.render_item(item(), (1080, 1920), root, 'completo')
            self.assertTrue(again['cached'])
            self.assertEqual(a['path'], again['path'])
            other = motion.render_item(item(text='Outro texto'), (1080, 1920), root, 'completo')
            self.assertNotEqual(a['path'], other['path'])
            square = motion.render_item(item(), (1080, 1080), root, 'completo')
            self.assertNotEqual(a['path'], square['path'])
            old = motion.VERSION
            try:
                motion.VERSION = old + 1
                self.assertNotEqual(motion.render_item(item(), (1080, 1920), root, 'completo')['path'], a['path'])
            finally:
                motion.VERSION = old

    def test_output_has_alpha_and_exact_duration(self):
        with tempfile.TemporaryDirectory() as root:
            made = motion.render_item(item(duration=2.0), (1080, 1920), root, 'completo')
            info = media.run([media.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,pix_fmt,width,height,duration',
                              '-of', 'json', made['path']], 60)
            stream = json.loads(info)['streams'][0]
            self.assertEqual(stream['codec_name'], 'png')
            self.assertIn('a', stream['pix_fmt'])                 # rgba
            self.assertEqual((stream['width'], stream['height']), made['box'][2:])
            self.assertAlmostEqual(float(stream['duration']), 2.0, delta=.1)

    def test_light_level_is_a_single_cheap_image_and_pulse_refuses(self):
        with tempfile.TemporaryDirectory() as root:
            made = motion.render_item(item(), (1080, 1920), root, 'leve')
            self.assertEqual(made['kind'], 'image')
            self.assertTrue(made['path'].endswith('.png'))
            with self.assertRaises(motion.MotionError):
                motion.render_item(item(template='pulso_audio', text=''), (1080, 1920), root, 'leve')
            with self.assertRaises(motion.MotionError):
                motion.render_item(item(template='pulso_audio', text=''), (1080, 1920), root, 'completo')    # sem áudio


def real_source(path, seconds=40):
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}',
               '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}:sample_rate=48000', '-c:v', 'libx264', '-preset', 'veryfast',
               '-pix_fmt', 'yuv420p', '-g', '30', '-c:a', 'aac', '-b:a', '96k', '-f', 'mpegts', str(path)], timeout=240)


def render_cut(tmp, level, motion_items, streamer='Canal Teste'):
    store = Store(str(tmp))
    sid_streamer = store.create_streamer(streamer)
    store.save_profile(sid_streamer, dict(DEFAULT_PROFILE, camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off', cover=False,
                                          motion_level=level))
    sid = store.new_session(sid_streamer, 'g')
    session = store.session(sid)
    file = Path(session['source']) / 'segmento_00000.ts'
    real_source(file)
    info = media.probe(file)
    stat = file.stat()
    with store.connect(True) as c:
        c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns,
                   'done', json.dumps({'segments': [], 'signals': {'audio': [], 'motion': [], 'warnings': []}})))
    rows = build_timeline(store.segments(sid))
    group = next(r['group_id'] for r in rows if r['start'] <= 5 < r['end'])
    data = dict(start=5.0, end=35.0, group_id=group, score=9.0, reasons=['teste'], transcript='fala',
                transcript_segments=[dict(start=6, end=9, text='uma fala curta', words=[])])
    if motion_items:
        data['project'] = project.clean(dict(motion=motion_items), 30)
    store.propose(sid, data, plan(rows, 5.0, 35.0, group), store.streamer(sid_streamer)['profile'])
    cand = store.rows('SELECT id,version,start,end,parts FROM candidates WHERE streamer=?', (sid_streamer,))[0]
    store.review(cand['id'], cand['version'], cand['start'], cand['end'], json.loads(cand['parts']), 'approve', editorial_confirmed=True)
    Engine(store).do_render(cand['id'], False)
    done = store.candidate(cand['id'])
    path = Path(done['export_path'])
    return done, (path if path.is_dir() else path.parent), store


def frame_at(video, t, out):
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-ss', str(t), '-i', str(video), '-frames:v', '1', str(out)], 60)
    return np.asarray(Image.open(out).convert('RGB')).astype(int)


class RealRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        cls.plain, cls.plain_dir, _ = render_cut(base / 'a', 'off', [])
        cls.items = [dict(template='contador', start=2.0, duration=2.5, value=1500, text='seguidores', accent='#FFD600'),
                     dict(template='contador', start=10.0, duration=2.5, value=98, suffix='%', text='aprovação', accent='#00D0FF'),
                     dict(template='titulo_animado', start=20.0, duration=2.0, text='terceiro')]
        cls.rich, cls.rich_dir, _ = render_cut(base / 'b', 'completo', cls.items)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_two_variants_are_integrated_and_the_third_is_refused_with_reason(self):
        self.assertEqual(self.rich['status'], 'done', self.rich.get('error'))
        manifest = json.loads((self.rich_dir / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertNotIn('recuo', manifest)
        self.assertEqual([a['template'] for a in manifest['motion']['aplicados']], ['contador', 'contador'])
        refused = [d for d in manifest['motion']['decisoes'] if not d['aceito']]
        self.assertEqual(sorted(d['template'] for d in refused), ['barra_nome', 'titulo_animado'])    # o terceiro explícito e a barra automática
        self.assertTrue(all('no máximo' in d['motivo'] for d in refused))
        self.assertEqual(manifest['motion']['avisos'], [])

    def test_duration_is_unchanged(self):
        a = media.probe(self.plain_dir / 'clipe.mp4')['duration']
        b = media.probe(self.rich_dir / 'clipe.mp4')['duration']
        self.assertAlmostEqual(a, b, delta=.05)

    def test_graphic_appears_only_in_its_window_and_colors_elsewhere_are_untouched(self):
        tmp = Path(self.temp.name)
        y0, y1 = int(1920 * .38), int(1920 * .58)                      # caixa do contador
        inside = frame_at(self.rich_dir / 'clipe.mp4', 3.9, tmp / 'in.png')
        plain_inside = frame_at(self.plain_dir / 'clipe.mp4', 3.9, tmp / 'pin.png')
        box = inside[y0:y1]
        yellow = (box[:, :, 0] > 220) & (box[:, :, 1] > 170) & (box[:, :, 2] < 90)
        plain_yellow = (plain_inside[y0:y1, :, 0] > 220) & (plain_inside[y0:y1, :, 1] > 170) & (plain_inside[y0:y1, :, 2] < 90)
        self.assertGreater(int(yellow.sum()), int(plain_yellow.sum()) + 300)
        # fora da caixa o vídeo é o mesmo (só ruído de codificação)
        outside_rich = np.concatenate([inside[:y0 - 10], inside[y1 + 10:1500]])
        outside_plain = np.concatenate([plain_inside[:y0 - 10], plain_inside[y1 + 10:1500]])
        self.assertLess(np.abs(outside_rich - outside_plain).mean(), 1.5)
        # antes e depois da janela do gráfico, a caixa é igual à do corte sem gráfico
        for t in (0.8, 6.5):
            rich_t = frame_at(self.rich_dir / 'clipe.mp4', t, tmp / f'r{t}.png')[y0:y1]
            plain_t = frame_at(self.plain_dir / 'clipe.mp4', t, tmp / f'p{t}.png')[y0:y1]
            self.assertLess(np.abs(rich_t - plain_t).mean(), 1.5, t)

    def test_second_variant_has_its_own_color_and_number(self):
        tmp = Path(self.temp.name)
        y0, y1 = int(1920 * .38), int(1920 * .58)
        frame = frame_at(self.rich_dir / 'clipe.mp4', 12.1, tmp / 'v2.png')[y0:y1]
        blue = (frame[:, :, 2] > 200) & (frame[:, :, 0] < 60) & (frame[:, :, 1] > 150)
        self.assertGreater(int(blue.sum()), 300)

    def test_cache_was_filled_and_reused(self):
        files = list((Path(self.temp.name) / 'a' / 'cache' / 'motion').glob('*')) if (Path(self.temp.name) / 'a' / 'cache' / 'motion').exists() else []
        self.assertEqual(files, [])                                    # o corte sem gráfico não gerou nada
        cached = list((Path(self.temp.name) / 'b' / 'cache' / 'motion').glob('*.mov'))
        self.assertEqual(len(cached), 2)


class AutomaticAndAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.done, cls.folder, cls.store = render_cut(Path(cls.temp.name) / 'c', 'completo',
                                                     [dict(template='pulso_audio', start=12.0, duration=3.0, accent='#FF3366')])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_automatic_name_bar_and_audio_pulse(self):
        self.assertEqual(self.done['status'], 'done', self.done.get('error'))
        manifest = json.loads((self.folder / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(a['template'] for a in manifest['motion']['aplicados']), ['barra_nome', 'pulso_audio'])
        self.assertNotIn('recuo', manifest)
        y0, y1 = int(1920 * .72), int(1920 * .82)
        frame = frame_at(self.folder / 'clipe.mp4', 13.5, Path(self.temp.name) / 'pulso.png')[y0:y1]
        pink = (frame[:, :, 0] > 200) & (frame[:, :, 1] < 90) & (frame[:, :, 2] > 70) & (frame[:, :, 2] < 160)
        self.assertGreater(int(pink.sum()), 400)
        bar = frame_at(self.folder / 'clipe.mp4', 3.0, Path(self.temp.name) / 'barra.png')[int(1920 * .60):int(1920 * .715)]
        yellow = (bar[:, :, 0] > 220) & (bar[:, :, 1] > 170) & (bar[:, :, 2] < 90)
        self.assertGreater(int(yellow.sum()), 100)


class LightLevel(unittest.TestCase):
    def test_light_level_uses_still_overlay_and_keeps_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            done, folder, _ = render_cut(Path(tmp) / 'd', 'leve', [dict(template='titulo_animado', start=15.0, duration=2.5, text='Olha só')])
            self.assertEqual(done['status'], 'done', done.get('error'))
            manifest = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
            kinds = {a['template']: a['kind'] for a in manifest['motion']['aplicados']}
            self.assertEqual(kinds, {'titulo_animado': 'image', 'barra_nome': 'image'})
            self.assertEqual(list((Path(tmp) / 'd' / 'cache' / 'motion').glob('*.mov')), [])
            self.assertNotIn('recuo', manifest)


if __name__ == '__main__':
    unittest.main()
