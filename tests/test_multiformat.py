import json
import tempfile
import unittest
from pathlib import Path

from liveclips import media, multiformat
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store, profile_checked
from liveclips.timeline import build_timeline, plan

ASS = """[Script Info]
PlayResX: 1080
PlayResY: 1920
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\an2}Olha isso
Dialogue: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,{\\an2}Olha isso
Dialogue: 0,0:00:04.00,0:00:05.50,Default,,0,0,0,,{\\b1}outra fala
"""


class Pure(unittest.TestCase):
    def test_formats_validation_and_union(self):
        self.assertEqual(multiformat.clean_formats(['16x9', '1x1', '1x1']), ['1x1', '16x9'])
        self.assertEqual(multiformat.clean_formats(None), [])
        with self.assertRaises(ValueError):
            multiformat.clean_formats(['3x4'])
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, export_formats='1x1'))
        self.assertEqual(multiformat.selected(dict(export_formats=['4x5']), dict(formats=['1x1'])), ['1x1', '4x5'])
        self.assertEqual(multiformat.selected({}, None), [])

    def test_srt_merges_repeats_and_formats_time(self):
        srt = multiformat.srt_from_ass(ASS)
        self.assertIn('00:00:01,000 --> 00:00:03,000\nOlha isso', srt)
        self.assertIn('00:00:04,000 --> 00:00:05,500\noutra fala', srt)
        self.assertEqual(srt.count('-->'), 2)

    def test_check_variant_rules(self):
        main = dict(duration=10.0, has_audio=True)
        good = dict(width=1080, height=1080, video_codec='h264', pix_fmt='yuv420p', has_audio=True, duration=10.1)
        self.assertEqual(multiformat.check_variant('x', '1x1', main, lambda p: good), ([], []))
        bad = dict(good, width=1920, pix_fmt='yuv444p', has_audio=False)
        errors, _ = multiformat.check_variant('x', '1x1', main, lambda p: bad)
        self.assertEqual(len(errors), 3)
        _, warnings = multiformat.check_variant('x', '1x1', main, lambda p: dict(good, duration=11.0))
        self.assertEqual(len(warnings), 1)
        errors, _ = multiformat.check_variant('x', '1x1', main, lambda p: (_ for _ in ()).throw(RuntimeError('quebrado')))
        self.assertTrue(errors)


def real_source(path, seconds=30):
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}',
               '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}:sample_rate=48000', '-c:v', 'libx264', '-preset', 'veryfast',
               '-pix_fmt', 'yuv420p', '-g', '30', '-c:a', 'aac', '-b:a', '96k', '-f', 'mpegts', str(path)], timeout=240)


class RealRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.delivery = Path(cls.temp.name) / 'entrega'
        cls.delivery.mkdir()
        cls.store = Store(cls.temp.name + '/dados')
        cls.streamer = cls.store.create_streamer('Formatos')
        cls.store.save_profile(cls.streamer, dict(DEFAULT_PROFILE, camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off',
                                                  export_formats=['1x1', '16x9'], export_srt=True, delivery_folder=str(cls.delivery)))
        cls.sid = cls.store.new_session(cls.streamer, 'formatos')
        session = cls.store.session(cls.sid)
        file = Path(session['source']) / 'segmento_00000.ts'
        real_source(file)
        info = media.probe(file)
        stat = file.stat()
        with cls.store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (cls.sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns,
                       'done', json.dumps({'segments': [], 'signals': {'audio': [], 'motion': [], 'warnings': []}})))
        rows = build_timeline(cls.store.segments(cls.sid))
        group = next(r['group_id'] for r in rows if r['start'] <= 5 < r['end'])
        words = [dict(start=6 + i * .5, end=6.4 + i * .5, word=w) for i, w in enumerate(['olha', 'isso', 'aqui', 'cara', 'incrivel', 'mesmo'])]
        data = dict(start=5.0, end=20.0, group_id=group, score=9.0, reasons=['teste'], transcript=' '.join(w['word'] for w in words),
                    transcript_segments=[dict(start=6, end=9.4, text=' '.join(w['word'] for w in words), words=words)])
        cls.store.propose(cls.sid, data, plan(rows, 5.0, 20.0, group), cls.store.streamer(cls.streamer)['profile'])
        item = cls.store.rows('SELECT id,version,start,end,parts FROM candidates WHERE streamer=?', (cls.streamer,))[0]
        cls.store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve', editorial_confirmed=True)
        cls.unrelated = cls.delivery / 'qualquer.txt'
        cls.unrelated.write_text('não mexa', encoding='utf-8')
        Engine(cls.store).do_render(item['id'], False)
        cls.done = cls.store.candidate(item['id'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def folder(self):
        path = Path(self.done['export_path'])
        return path if path.is_dir() else path.parent

    def test_variants_made_from_profile_without_studio(self):
        self.assertEqual(self.done['status'], 'done', self.done.get('error'))
        manifest = json.loads((self.folder() / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['variants'], {'1x1': 'ok', '16x9': 'ok'})
        self.assertFalse((self.folder() / 'clipe_4x5.mp4').exists())
        main = media.probe(self.folder() / 'clipe.mp4')
        for fmt, size in (('1x1', (1080, 1080)), ('16x9', (1920, 1080))):
            info = media.probe(self.folder() / f'clipe_{fmt}.mp4')
            self.assertEqual((info['width'], info['height']), size)
            self.assertEqual((info['video_codec'], info['pix_fmt']), ('h264', 'yuv420p'))
            self.assertTrue(info['has_audio'])
            self.assertAlmostEqual(info['duration'], main['duration'], delta=.35)

    def test_layout_is_recalculated_not_the_same_crop(self):
        import re
        def head(name):
            text = (self.folder() / name).read_text(encoding='utf-8-sig')
            res = (int(re.search(r'PlayResX: (\d+)', text).group(1)), int(re.search(r'PlayResY: (\d+)', text).group(1)))
            style = next(line for line in text.splitlines() if line.startswith('Style:')).split(',')
            return res, int(style[2]), int(style[-3])          # resolução do script, tamanho da fonte, margem vertical
        main, wide, square = head('legendas.ass'), head('legendas_16x9.ass'), head('legendas_1x1.ass')
        self.assertAlmostEqual(main[0][0] / main[0][1], 9 / 16, delta=.01)
        self.assertAlmostEqual(wide[0][0] / wide[0][1], 16 / 9, delta=.01)
        self.assertAlmostEqual(square[0][0] / square[0][1], 1.0, delta=.01)
        self.assertNotEqual((main[1], main[2]), (wide[1], wide[2]))      # tipografia e margem próprias da proporção

    def test_srt_and_covers_per_format(self):
        srt = (self.folder() / 'legendas_1x1.srt').read_text(encoding='utf-8')
        self.assertIn('-->', srt)
        self.assertTrue((self.folder() / 'capa_16x9.jpg').is_file())
        self.assertTrue((self.folder() / 'capa_1x1.jpg').is_file())

    def test_delivery_has_stable_names_and_does_not_touch_unrelated_files(self):
        names = sorted(p.name for p in self.delivery.iterdir())
        self.assertEqual(self.unrelated.read_text(encoding='utf-8'), 'não mexa')
        stem = next(n[:-4] for n in names if n.endswith('.mp4') and '_1x1' not in n and '_16x9' not in n)
        for suffix in ('_1x1.mp4', '_16x9.mp4', '_capa_1x1.jpg', '_capa_16x9.jpg', '_1x1.srt'):
            self.assertIn(stem + suffix, names)
        self.assertFalse(any('4x5' in n for n in names))

    def test_interchange_keeps_cuts_and_duration_of_the_real_export(self):
        """P26 no caminho real: pacote + OTIO lido pela biblioteca oficial têm a duração do vídeo exportado."""
        try:
            import opentimelineio as lib
        except ImportError:
            self.skipTest('opentimelineio não instalado')
        from liveclips import export_pack, studio_api
        result = studio_api.build_package(self.store, self.done['id'])
        self.assertIn('nao_transportado', result['manifest'])
        timeline = lib.adapters.read_from_file(str(self.folder() / 'linha_do_tempo.otio'))
        track = timeline.video_tracks()[0]
        main = media.probe(self.folder() / 'clipe.mp4')
        self.assertAlmostEqual(track.duration().to_seconds(), main['duration'], delta=.2)
        plan = json.loads((self.folder() / 'plano.json').read_text(encoding='utf-8'))
        self.assertEqual(len(list(track.find_clips())), len(plan['segments']))
        report = studio_api.save_project(self.store, self.done['id'], include_sources=False)
        self.assertTrue(report['gravado'])
        again = export_pack.reopen(self.folder() / export_pack.PROJECT_DIR)
        self.assertTrue(again['ok'], again)
        self.assertEqual(again['segmentos'], len(plan['segments']))
        dry = studio_api.save_project(self.store, self.done['id'], include_sources=True, dry_run=True)
        self.assertGreater(dry['bytes_referencias_somente'], 0)


if __name__ == '__main__':
    unittest.main()
