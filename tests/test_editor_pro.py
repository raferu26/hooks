"""Editor profissional V8: curvas de zoom, looks, legendas, render em uma passada e loudness."""
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from liveclips import captions, editing, media, motion
from liveclips.store import DEFAULT_PROFILE, profile_checked

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

HAS_FFMPEG = bool(media.find_tool('ffmpeg') and media.find_tool('ffprobe') and np is not None)


def ff_eval(expression, **values):
    """Avalia em Python o subconjunto de expressões FFmpeg que o editor gera."""
    text = expression
    for name in ('if', 'lt', 'gt', 'between', 'min', 'max'):
        text = re.sub(r'\b' + name + r'\(', f'_{name}(', text)
    env = dict(_if=lambda c, a, b: a if c else b, _lt=lambda a, b: 1 if a < b else 0,
               _gt=lambda a, b: 1 if a > b else 0, _between=lambda x, a, b: 1 if a <= x <= b else 0,
               _min=min, _max=max)
    env.update(values)
    return eval(text, {'__builtins__': {}}, env)


class MotionTests(unittest.TestCase):
    punches = [{'start': 1.0, 'end': 1.85, 'zoom': 1.05}, {'start': 6.0, 'end': 6.85, 'zoom': 1.12}]

    def test_ffmpeg_expression_matches_python_for_every_curve(self):
        for curve in motion.PUNCH_CURVES:
            expression = motion.zoom_expression(self.punches, 30, curve)
            for frame in range(0, 300, 3):
                self.assertAlmostEqual(ff_eval(expression, on=frame), motion.zoom_at(self.punches, frame / 30, curve), places=9)

    def test_each_punch_keeps_its_own_target(self):
        # A V7 aplicava o MAIOR zoom a todos os punches; agora cada um chega ao seu alvo.
        peaks = []
        for punch in self.punches:
            peaks.append(max(motion.zoom_at(self.punches, punch['start'] + i / 100, 'smooth') for i in range(86)))
        self.assertAlmostEqual(peaks[0], 1.05, places=3)
        self.assertAlmostEqual(peaks[1], 1.12, places=3)

    def test_curves_start_and_end_at_neutral_and_stay_bounded(self):
        for curve in motion.PUNCH_CURVES:
            values = [motion.zoom_at(self.punches, i / 60, curve) for i in range(0, 600)]
            self.assertAlmostEqual(values[0], 1.0)
            self.assertAlmostEqual(motion.zoom_at(self.punches, 1.85, curve), 1.0, places=6)
            self.assertGreaterEqual(min(values), 1.0 - 1e-9)
            self.assertLessEqual(max(values), 1.12 * 1.02)

    def test_invalid_punches_and_easings_are_rejected(self):
        self.assertEqual(motion.zoom_expression([{'start': 1, 'end': 2, 'zoom': 1.4}], 30), '')
        self.assertEqual(motion.zoom_expression([{'start': 3, 'end': 2, 'zoom': 1.05}], 30), '')
        with self.assertRaises(ValueError):
            motion.keyframe_expression([(0, 1, 'bounce'), (1, 2)])
        with self.assertRaises(ValueError):
            motion.keyframe_expression([(0, float('nan'))])

    def test_slow_push_is_added_and_capped(self):
        expression = motion.zoom_expression([], 30, push=(1.05, 10))
        self.assertAlmostEqual(ff_eval(expression, on=0), 1.0)
        self.assertAlmostEqual(ff_eval(expression, on=300), 1.05)
        combined = motion.zoom_expression(self.punches, 30, 'smooth', push=(1.05, 10))
        self.assertLessEqual(max(ff_eval(combined, on=i) for i in range(300)), motion.MAX_ZOOM + 1e-9)


class LookTests(unittest.TestCase):
    def test_every_style_has_a_look_and_a_real_pace_parameter(self):
        for name, preset in editing.EDITOR_PRESETS.items():
            self.assertIn(name, editing.LOOKS)
            self.assertIn(editing.LOOKS[name]['curve'], motion.PUNCH_CURVES)
            self.assertIn(editing.LOOKS[name]['caption'], captions.CAPTION_STYLES)
            self.assertGreater(preset['breath'], 0)
            self.assertNotIn('reframe', preset)

    def test_grade_can_be_turned_off_and_clean_style_is_neutral(self):
        self.assertEqual(editing.grade_filters(editing.look_for({'editorial_style': 'clean'})['grade']), '')
        self.assertIsNone(editing.look_for({'editorial_style': 'hype', 'auto_grade': False})['grade'])
        self.assertIn('eq=contrast=', editing.grade_filters(editing.look_for({'editorial_style': 'hype'})['grade']))
        self.assertIn('vignette', editing.grade_filters(editing.LOOKS['cinematic']['grade']))

    def test_plan_records_look_and_old_plans_fall_back_to_the_style(self):
        plan = editing.plan_edits({'start': 0, 'end': 20}, {}, profile={'editorial_style': 'meme'})
        self.assertEqual(plan['version'], 4)
        self.assertEqual(plan['look']['curve'], 'beat')
        self.assertEqual(editing.look_of_plan({'preset': 'cinematic'})['push'], 1.05)
        self.assertEqual(editing.look_of_plan({})['curve'], 'smooth')

    def test_breath_margin_follows_the_style(self):
        words = [{'start': 1.0, 'end': 1.4, 'word': 'oi'}, {'start': 7.0, 'end': 7.4, 'word': 'então'},
                 {'start': 7.6, 'end': 8.0, 'word': 'fim'}]
        transcript = [{'start': 1, 'end': 8, 'words': words}]
        starts = {}
        for style in ('hype', 'storytelling'):
            plan = editing.plan_edits({'start': 0, 'end': 9.5}, {}, transcript, {'editorial_style': style})
            cuts = [d for d in plan['decisions'] if d['kind'] == 'silence']
            self.assertTrue(cuts, style)
            # o corte começa exatamente uma margem de respiro depois da última palavra
            self.assertAlmostEqual(cuts[0]['start'] - 1.4, editing.EDITOR_PRESETS[style]['breath'], places=2)
            starts[style] = cuts[0]['start']
        self.assertGreater(starts['storytelling'], starts['hype'])


class CaptionTests(unittest.TestCase):
    words = [dict(start=1.0, end=1.3, word='isso'), dict(start=1.5, end=1.8, word='foi'),
             dict(start=2.2, end=2.6, word='absurdo'), dict(start=2.7, end=3.0, word='meu')]
    segments = [dict(start=1, end=3, text='isso foi absurdo meu', words=words)]

    def events(self, style='dynamic', **options):
        text = captions.make_ass(self.segments, 0, 6, 46, 260, '00E8FF', style, **options)
        rows = []
        for line in text.splitlines():
            if line.startswith('Dialogue:'):
                fields = line.split(',', 9)
                rows.append((fields[1], fields[2], fields[9]))
        return text, rows

    def test_highlight_never_blinks_inside_a_phrase(self):
        _, rows = self.events()
        # entre palavras do mesmo grupo cada evento começa onde o anterior termina
        for (_, end, _text), (start, _e, _t) in zip(rows[:3], rows[1:4]):
            self.assertEqual(end, start)
        self.assertTrue(all('{\\c&H00E8FF&}' in text for _, _, text in rows))

    def test_classic_styles_keep_their_v7_geometry(self):
        for style, size, outline, shadow in (('dynamic', 46, 3, 1), ('clean', 43, 2, 1), ('bold', 51, 4, 2), ('minimal', 40, 2, 0)):
            text, _ = self.events(style)
            self.assertIn(f'Arial,{size},', text)
            self.assertIn(f',1,{outline},{shadow},2,70,90,260,1', text)

    def test_impact_is_uppercase_animated_and_emphasizes_the_peak_word(self):
        text, rows = self.events('impact', emphasis=[2.3])
        self.assertIn('ABSURDO', text)
        self.assertNotIn('absurdo', text)
        self.assertEqual(sum('\\t(0,90' in row[2] for row in rows), 2)  # um por grupo, não por palavra
        self.assertIn('\\fscx116\\fscy116', text)
        self.assertEqual(text.count('\\fscx116\\fscy116}ABSURDO'), 3)  # ênfase mantida nos 3 quadros do grupo

    def test_box_style_uses_opaque_box_and_auto_follows_the_look(self):
        text, _ = self.events('box')
        self.assertRegex(text, r'&H66101010,&H80000000,-1,0,0,0,100,100,0,0,3,9,0,2')
        self.assertEqual(captions.resolve_style('auto', {'caption': 'impact'}), 'impact')
        self.assertEqual(captions.resolve_style('auto'), 'dynamic')
        self.assertEqual(captions.resolve_style('inexistente'), 'dynamic')

    def test_emphasis_picks_only_words_near_the_peak(self):
        words = [dict(start=1.0, end=1.3), dict(start=5.0, end=5.4)]
        self.assertEqual(captions.emphasis_indexes(words, [1.1]), {0})
        self.assertEqual(captions.emphasis_indexes(words, [3.0]), set())

    def test_profile_accepts_new_caption_styles_and_grade_switch(self):
        for style in captions.STYLE_NAMES:
            self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, caption_style=style))['caption_style'], style)
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, caption_style='gigante'))
        self.assertIs(profile_checked(dict(DEFAULT_PROFILE, auto_grade=0))['auto_grade'], False)


class SourceGraphTests(unittest.TestCase):
    def test_pieces_follow_cuts_across_parts(self):
        parts = [{'path': 'A.ts', 'in': 58.0, 'out': 62.0}, {'path': 'B.ts', 'in': 0.0, 'out': 8.0}]
        pieces = media.source_pieces(parts, [(0, 3.0), (5.0, 12.0)])
        self.assertEqual(pieces, [(0, 58.0, 61.0), (1, 1.0, 8.0)])
        # um intervalo que atravessa a fronteira vira dois trechos
        crossing = media.source_pieces(parts, [(3.0, 6.0)])
        self.assertEqual(crossing, [(0, 61.0, 62.0), (1, 0.0, 2.0)])
        with self.assertRaises(ValueError):
            media.source_pieces(parts, [])

    def test_graph_scales_only_when_sizes_differ_and_adds_silence_for_silent_parts(self):
        parts = [{'path': 'A.ts', 'in': 0, 'out': 5}, {'path': 'B.ts', 'in': 0, 'out': 5}]
        infos = [dict(width=2560, height=1440, fps=60, has_audio=True, duration=60),
                 dict(width=1920, height=1080, fps=60, has_audio=False, duration=60)]
        args, graph = media.build_source(parts, infos, [(0, 0, 5), (1, 0, 5)])
        self.assertEqual(args, ['-i', 'A.ts', '-i', 'B.ts'])
        self.assertEqual(graph.count('scale=2560:1440:flags=lanczos'), 1)
        self.assertIn('anullsrc=r=48000:cl=stereo,atrim=duration=5', graph)
        self.assertIn('concat=n=2:v=1:a=1[srcv][srca]', graph)

    def test_long_local_videos_seek_the_input_and_shift_trim_times(self):
        parts = [{'path': 'ep.mp4', 'in': 2000.0, 'out': 2045.0}]
        info = [dict(width=1920, height=1080, fps=30, has_audio=True, duration=3600)]
        args, graph = media.build_source(parts, info, [(0, 2000.0, 2045.0)])
        self.assertEqual(args, ['-ss', '1995', '-i', 'ep.mp4'])
        self.assertIn('trim=start=5.0:end=50.0', graph)
        short = media.build_source(parts[:1], [dict(info[0], duration=60)], [(0, 2000.0, 2045.0)])[0]
        self.assertNotIn('-ss', short)

    def test_two_pass_loudnorm_is_linear_and_rejects_silence(self):
        report = '{"input_i":"-23.50","input_tp":"-4.10","input_lra":"6.20","input_thresh":"-34.0","target_offset":"0.30"}'
        measured = media.parse_loudness('lixo\n' + report)
        self.assertIn('linear=true', media.loudnorm_filter(measured))
        self.assertIn('measured_I=-23.5', media.loudnorm_filter(measured))
        self.assertEqual(media.loudnorm_filter(), 'loudnorm=I=-16:LRA=11:TP=-1.5')
        self.assertIsNone(media.parse_loudness('{"input_i":"-inf","input_tp":"-inf","input_lra":"0","input_thresh":"-70","target_offset":"0"}'))
        self.assertIsNone(media.parse_loudness('{"input_i":"26.4","input_tp":"76","input_lra":"40","input_thresh":"-9","target_offset":"0"}'))
        self.assertIsNone(media.parse_loudness('sem json'))


class LoudnessRuleTests(unittest.TestCase):
    def test_linear_gain_is_used_only_when_the_peak_fits(self):
        self.assertTrue(media.linear_feasible({'input_i': -24.0, 'input_tp': -12.0}))   # +8 dB → -4 dBTP
        self.assertFalse(media.linear_feasible({'input_i': -33.5, 'input_tp': -17.5}))  # +17,5 dB → 0 dBTP
        self.assertTrue(media.linear_feasible({'input_i': -10.0, 'input_tp': -1.0}))    # material já alto: só reduz


class RenderPipelineTests(unittest.TestCase):
    def candidate(self, root, **extra):
        source = Path(root) / 'source.ts'
        source.write_bytes(b'original')
        profile = dict(DEFAULT_PROFILE, camera_rect=[.7, .05, .25, .3], min_free_gb=.5, editorial_style='hype')
        parts = [{'path': str(source), 'sha': 'abc', 'seq': 0, 'in': 10, 'out': 20, 'global_start': 10,
                  'global_end': 20, 'group_id': 'g'}]
        plan = editing.plan_edits({'start': 10, 'end': 20}, {}, profile=profile)
        plan['decisions'] = [editing._decision('silence', 3, 4, True, 'teste', 'Encurtar pausa')]
        data = {'edit_plan': plan, **extra}
        return {'id': 'clip', 'start': 10, 'end': 20, 'parts': parts, 'profile': profile, 'data': data}

    def run_render(self, pipeline, fail_single=False):
        commands = []
        with tempfile.TemporaryDirectory() as temp:
            candidate = self.candidate(temp)
            info = {'width': 1920, 'height': 1080, 'duration': 60, 'fps': 30, 'has_audio': True}

            def fake_run(args, *_a, **_k):
                commands.append(args)
                if fail_single and 'srcv' in ' '.join(map(str, args)) and not any('legacy' in str(c) for c in commands[:-1]):
                    raise RuntimeError('filtro inválido')
                Path(args[-1]).write_bytes(b'video')
                return b''

            def probe(path):
                if str(path).endswith('clipe.mp4'):
                    return dict(info, width=1080, height=1920, duration=9)
                return info
            report = '{"input_i":"-20","input_tp":"-17","input_lra":"5","input_thresh":"-30","target_offset":"0.1"}'
            with patch('liveclips.media.require_space'), patch('liveclips.media.probe', side_effect=probe), \
                 patch('liveclips.media.tool', side_effect=lambda name: name), patch('liveclips.media.run', side_effect=fake_run), \
                 patch('liveclips.media.run_stderr', return_value=report), \
                 patch('liveclips.media.assemble', return_value=(Path(temp) / 'source.ts', 10, 10)), \
                 patch('liveclips.media.compact_source', return_value=(Path(temp) / 'source.ts', 10, 9)):
                result = media.render(candidate, [], temp, False, pipeline=pipeline)
            manifest = json.loads((result.parent / 'manifesto.json').read_text(encoding='utf-8'))
        return commands, manifest

    def test_single_pass_encodes_once_from_the_original_with_two_pass_loudness(self):
        commands, manifest = self.run_render('single')
        self.assertEqual(len(commands), 1)  # a medição usa run_stderr; só o render final usa run
        command = commands[0]
        self.assertEqual(sum(1 for item in command if item == '-c:v'), 1)
        self.assertNotIn('-ss', command)
        self.assertEqual(command[command.index('-t') + 1], '9.0')
        graph = command[command.index('-filter_complex') + 1]
        self.assertIn('concat=n=2:v=1:a=1[srcv][srca]', graph)
        self.assertIn('trim=start=10.0:end=13.0', graph)
        self.assertIn('trim=start=14.0:end=20.0', graph)
        self.assertIn('measured_I=-20.0', graph)
        self.assertIn('linear=true', graph)
        self.assertIn('eq=contrast=1.11:saturation=1.28', graph)  # cor do estilo hype
        self.assertEqual(manifest['pipeline'], 'single')
        self.assertEqual(manifest['loudness']['mode'], 'dois passes (linear)')
        self.assertEqual(manifest['look']['curve'], 'beat')

    def test_failed_single_pass_falls_back_to_legacy_and_records_the_reason(self):
        commands, manifest = self.run_render('auto', fail_single=True)
        self.assertEqual(manifest['pipeline'], 'legacy')
        self.assertIn('filtro inválido', manifest['fallback'])
        self.assertEqual(len(commands), 2)
        self.assertIn('-ss', commands[1])

    def test_legacy_pipeline_is_still_available_and_single_pass_in_strict_mode_raises(self):
        _, manifest = self.run_render('legacy')
        self.assertEqual(manifest['pipeline'], 'legacy')
        self.assertIsNone(manifest['fallback'])
        with self.assertRaises(RuntimeError):
            self.run_render('single', fail_single=True)
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            media.render(self.candidate(temp), [], temp, False, pipeline='turbo')

    def test_signature_changes_with_the_look_and_renderer(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = self.candidate(temp)
            before = media.signature(candidate)
            candidate['data']['edit_plan']['look'] = dict(candidate['data']['edit_plan']['look'], curve='snap')
            self.assertNotEqual(before, media.signature(candidate))
        self.assertTrue(media.RENDERER_VERSION.startswith('0.13.0'))


def ffmpeg(*args):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *args], check=True)


def gray_frames(path, width, height, vf=''):
    raw = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(path), '-vf',
                          (vf + ',' if vf else '') + f'scale={width}:{height},format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width)


@unittest.skipUnless(HAS_FFMPEG, 'FFmpeg/ffprobe ou numpy não encontrados')
class RealMediaTests(unittest.TestCase):
    def test_zoom_reaches_each_target_in_the_real_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'zoom.mp4'
            punches = [{'start': .5, 'end': 2.5, 'zoom': 1.08}]
            chain = ('color=black:s=1080x640:r=30:d=3,drawbox=x=440:y=220:w=200:h=200:color=white:t=fill,format=yuv420p'
                     + editing.camera_zoom_filter(punches, 30, curve='smooth'))
            ffmpeg('-f', 'lavfi', '-i', chain, '-c:v', 'libx264', '-crf', '12', str(out))
            frames = gray_frames(out, 1080, 640)

            def width_at(seconds):
                row = frames[int(seconds * 30)][320]
                return int((row > 128).sum())
            self.assertAlmostEqual(width_at(.2), 200, delta=3)
            self.assertAlmostEqual(width_at(1.5), 216, delta=4)
            self.assertAlmostEqual(width_at(2.9), 200, delta=3)

    def make_source(self, root, seconds=12, audio=None, size='1280x720', preset='veryfast'):
        source = Path(root) / 'fonte.ts'
        flash = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(mod(t,2),1,1.1)'"
        audio = audio or "sine=f=1000:sample_rate=48000:duration=%d,volume=volume=0:enable='not(between(mod(t,2),1,1.1))'" % seconds
        ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size={size}:rate=30:duration={seconds},{flash}', '-f', 'lavfi', '-i', audio,
               '-c:v', 'libx264', '-preset', preset, '-g', '60', '-crf', '24', '-c:a', 'aac', '-shortest', str(source))
        return source

    def flash_times(self, clip):
        frames = gray_frames(clip, 16, 30)
        level = frames.reshape(len(frames), -1).mean(axis=1)
        on = level > level.max() * .9
        return [i / 30 for i in range(1, len(on)) if on[i] and not on[i - 1]]

    def test_every_style_demo_renders_with_the_real_look(self):
        with tempfile.TemporaryDirectory() as root:
            for style in editing.EDITOR_PRESETS:
                demo = media.style_demo(root, style)
                self.assertGreater(demo.stat().st_size, 1000, style)
                self.assertEqual(media.probe(demo)['width'], 360)
            self.assertFalse(list((Path(root) / 'cache' / 'demos_editor_v2').glob('*.ass')))

    def test_long_local_video_uses_input_seek_and_stays_frame_accurate(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp, seconds=200, size='320x180', preset='ultrafast')
            candidate = self.candidate(source, seconds=10)
            candidate['start'], candidate['end'] = 100, 110
            candidate['parts'][0].update({'in': 100.0, 'out': 110.0})
            candidate['data']['edit_plan']['decisions'] = []
            clip = media.render(candidate, [], temp, False, pipeline='single')
            for found, wanted in zip(self.flash_times(clip), [1, 3, 5, 7, 9]):
                self.assertAlmostEqual(found, wanted, delta=.05)
            self.assertEqual(len(self.flash_times(clip)), 5)

    def candidate(self, source, seconds=12, cut=None, style='clean', **profile):
        base = dict(DEFAULT_PROFILE, camera_rect=[0, 0, .25, .25], min_free_gb=.1, editorial_style=style, threads=2, **profile)
        plan = editing.plan_edits({'start': 0, 'end': seconds}, {}, profile=base)
        plan['decisions'] = [editing._decision('silence', cut[0], cut[1], True, 'teste', 'Encurtar pausa')] if cut else []
        parts = [{'path': str(source), 'sha': media.sha_file(source), 'seq': 0, 'in': 0.0, 'out': float(seconds),
                  'global_start': 0, 'global_end': seconds, 'group_id': 'g'}]
        return {'id': 'real', 'start': 0, 'end': seconds, 'parts': parts, 'profile': base,
                'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}}}

    def test_single_pass_keeps_cuts_and_audio_video_sync(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            clip = media.render(self.candidate(source, cut=(4.0, 6.0)), [], temp, False, pipeline='single')
            manifest = json.loads((clip.parent / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['pipeline'], 'single')
            self.assertAlmostEqual(media.probe(clip)['duration'], 10, delta=.1)
            frames = gray_frames(clip, 16, 30)
            level = frames.reshape(len(frames), -1).mean(axis=1)
            on = level > level.max() * .9
            video = [i / 30 for i in range(1, len(on)) if on[i] and not on[i - 1]]
            raw = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(clip), '-vn', '-ac', '1', '-ar', '16000',
                                  '-f', 's16le', '-'], capture_output=True, check=True).stdout
            samples = np.frombuffer(raw, np.int16).astype(float)
            window = 160
            rms = np.sqrt((samples[:len(samples) // window * window].reshape(-1, window) ** 2).mean(axis=1))
            loud = rms > rms.max() * .25
            audio = [i * window / 16000 for i in range(1, len(loud)) if loud[i] and not loud[i - 1]]
            expected = [1, 3, 5, 7, 9]  # o flash de 5 s caiu dentro do corte de 4–6 s
            self.assertEqual(len(video), len(expected))
            for found, wanted in zip(video, expected):
                self.assertAlmostEqual(found, wanted, delta=.08)
            for found, wanted in zip(audio, expected):
                self.assertAlmostEqual(found, wanted, delta=.1)
            for v, a in zip(video, audio):
                self.assertLess(abs(v - a), .06)

    def integrated_loudness(self, path):
        text = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-nostats', '-i', str(path), '-af',
                               'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
        summary = text[text.rfind('Summary:'):]
        return (float(re.search(r'I:\s+(-?[\d.]+) LUFS', summary).group(1)),
                float(re.search(r'Peak:\s+(-?[\d.]+) dBFS', summary).group(1)))

    def render_audio(self, temp, audio):
        source = self.make_source(temp, audio=audio)
        clip = media.render(self.candidate(source), [], temp, False, pipeline='single')
        manifest = json.loads((clip.parent / 'manifesto.json').read_text(encoding='utf-8'))
        return clip, manifest

    def test_two_pass_loudness_lands_on_target_when_the_peak_allows_it(self):
        # voz sintética com variação de nível e pouca diferença entre pico e volume médio
        steady = ("sine=f=220:sample_rate=48000:duration=12,volume='0.5+0.5*sin(2*PI*3*t)':eval=frame,"
                  "volume='if(lt(t,4),0.30,if(lt(t,8),0.06,0.15))':eval=frame")
        with tempfile.TemporaryDirectory() as temp:
            clip, manifest = self.render_audio(temp, steady)
            self.assertEqual(manifest['loudness']['mode'], 'dois passes (linear)')
            integrated, true_peak = self.integrated_loudness(clip)
            self.assertAlmostEqual(integrated, -16, delta=1.0)
            self.assertLess(true_peak, -1.0)

    def test_peaky_material_keeps_the_v7_method_and_never_clips(self):
        peaky = ("anoisesrc=c=pink:r=48000:a=0.5:d=12:seed=3,volume='0.6+0.4*sin(2*PI*4*t)':eval=frame,"
                 "volume='if(lt(t,4),0.5,if(lt(t,8),0.08,0.25))':eval=frame")
        with tempfile.TemporaryDirectory() as temp:
            clip, manifest = self.render_audio(temp, peaky)
            self.assertEqual(manifest['loudness']['mode'], 'uma passada (dinâmico)')
            self.assertIn('margem de pico', manifest['loudness']['reason'])
            self.assertLess(self.integrated_loudness(clip)[1], -0.5)

    def test_real_render_applies_style_caption_and_grade(self):
        words = [dict(start=1.0 + i * .5, end=1.4 + i * .5, word=w) for i, w in enumerate(['isso', 'foi', 'incrível', 'demais'])]
        transcript = [dict(start=1.0, end=3.4, text='isso foi incrível demais', words=words)]
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            clip = media.render(self.candidate(source, style='hype', caption_style='auto'), transcript, temp, False, pipeline='single')
            ass = (clip.parent / 'legendas.ass').read_text(encoding='utf-8-sig')
            self.assertIn('INCRÍVEL', ass)  # estilo hype → legenda impact em caixa alta
            self.assertEqual(media.probe(clip)['width'], 1080)


if __name__ == '__main__':
    unittest.main()
