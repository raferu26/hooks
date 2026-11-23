import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import grade, media
from liveclips.editing import grade_filters
from liveclips.store import DEFAULT_PROFILE, profile_checked


def cube(path, size=2, invert=False):
    rows = []
    for b in range(size):
        for g in range(size):
            for r in range(size):
                v = [r / (size - 1), g / (size - 1), b / (size - 1)]
                rows.append(' '.join(f'{(1 - x) if invert else x:.6f}' for x in v))
    Path(path).write_text('TITLE "t"\nLUT_3D_SIZE %d\n%s\n' % (size, '\n'.join(rows)), encoding='utf-8')


def image(value, size=(90, 160), tint=(0, 0, 0)):
    base = np.full((size[1], size[0], 3), value, np.uint8)
    return np.clip(base.astype(int) + np.array(tint), 0, 255).astype(np.uint8)


class Decide(unittest.TestCase):
    def test_dark_image_gets_bounded_gamma(self):
        stats = grade.measure_frames([image(45)])
        decided, reasons = grade.decide(stats)
        self.assertIn('gamma', decided)
        self.assertLessEqual(decided['gamma'], grade.LIMITS['gamma'][1])
        self.assertTrue(any('escura' in r for r in reasons))

    def test_balanced_image_untouched_and_explained(self):
        rng = np.random.RandomState(3)
        frame = (rng.rand(160, 90, 3) * 180 + 35).astype(np.uint8)
        decided, reasons = grade.decide(grade.measure_frames([frame]))
        self.assertNotIn('gamma', decided)
        self.assertTrue(reasons)

    def test_cast_only_for_neutral_video_content(self):
        stats = dict(p2=30, p50=125, p98=210, saturation=30, mean_r=140, mean_g=120, mean_b=100, frames=3)
        self.assertIn('cast', grade.decide(stats, 'video')[0])
        self.assertNotIn('cast', grade.decide(stats, 'live')[0])
        colorful = dict(stats, saturation=120)
        self.assertNotIn('cast', grade.decide(colorful, 'video')[0])

    def test_no_frames_keeps_style(self):
        self.assertEqual(grade.decide(None)[0], {})

    def test_merge_multiplies_style_and_auto(self):
        merged = grade.merge(dict(contrast=1.05, saturation=1.1), dict(contrast=1.1, gamma=1.1))
        self.assertAlmostEqual(merged['contrast'], 1.155, places=3)
        self.assertEqual(merged['gamma'], 1.1)
        self.assertIn('eq=gamma=1.1', grade_filters(merged))


class Lut(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def test_valid_cube_and_listing(self):
        cube(self.dir / 'luts_a.cube')
        (self.dir / 'luts').mkdir()
        cube(self.dir / 'luts' / 'bom.cube')
        (self.dir / 'luts' / 'ruim.cube').write_text('LUT_3D_SIZE 3\n0 0 0\n', encoding='utf-8')
        self.assertEqual([x['file'] for x in grade.luts(self.dir)], ['bom.cube'])

    def test_rejects_1d_wrong_count_and_non_finite(self):
        bad = self.dir / 'x.cube'
        bad.write_text('LUT_1D_SIZE 4\n', encoding='utf-8')
        with self.assertRaises(grade.LutError):
            grade.read_cube(bad)
        bad.write_text('LUT_3D_SIZE 2\n' + '0 0 0\n' * 8 + '', encoding='utf-8')
        self.assertEqual(grade.read_cube(bad)[0], 2)
        bad.write_text('LUT_3D_SIZE 2\n' + 'nan 0 0\n' * 8, encoding='utf-8')
        with self.assertRaises(grade.LutError):
            grade.read_cube(bad)
        bad.write_text('LUT_3D_SIZE 200\n', encoding='utf-8')
        with self.assertRaises(grade.LutError):
            grade.read_cube(bad)

    def test_strength_zero_is_identity_and_one_is_full(self):
        source = self.dir / 'inv.cube'
        cube(source, invert=True)
        out0 = grade.prepare_lut(source, self.dir / 'o0.cube', 0.0).read_text().split('\n')[1]
        out1 = grade.prepare_lut(source, self.dir / 'o1.cube', 1.0).read_text().split('\n')[1]
        self.assertEqual(out0, '0.000000 0.000000 0.000000')
        self.assertEqual(out1, '1.000000 1.000000 1.000000')

    def test_ffmpeg_applies_lut_filter(self):
        cube(self.dir / 'look.cube', invert=True)
        out = self.dir / 'o.png'
        media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=1', '-vf',
                   grade_filters(dict(lut='look.cube')), '-frames:v', '1', str(out)], cwd=str(self.dir), timeout=60)
        from PIL import Image
        self.assertGreater(Image.open(out).convert('L').getpixel((5, 5)), 200)      # preto invertido vira branco

    def test_profile_fields_validated(self):
        ok = profile_checked(dict(DEFAULT_PROFILE, auto_color='histograma', lut='C:/x/y/forte.cube', lut_strength=5))
        self.assertEqual(ok['lut'], 'forte.cube'); self.assertEqual(ok['lut_strength'], 1.0)
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, lut='x.png'))
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, auto_color='ia'))


class LutUpload(unittest.TestCase):
    def test_upload_validates_and_lists(self):
        import io
        from liveclips.app import App
        with tempfile.TemporaryDirectory() as temp:
            app = App(temp, worker=False); self.addCleanup(app.close)
            good = Path(temp) / 'src.cube'; cube(good)
            data = good.read_bytes()
            item = app.receive_upload('lut', 'Quente.cube', io.BytesIO(data), len(data))['item']
            self.assertEqual(item['file'], 'Quente.cube')
            self.assertEqual([x['file'] for x in grade.luts(temp)], ['Quente.cube'])
            with self.assertRaises(ValueError):
                app.receive_upload('lut', 'ruim.cube', io.BytesIO(b'oi'), 2)
            with self.assertRaises(ValueError):
                app.receive_upload('lut', 'x.png', io.BytesIO(data), len(data))
            self.assertEqual([x['file'] for x in grade.luts(temp)], ['Quente.cube'])


class WithColor(unittest.TestCase):
    def test_dark_video_gets_gamma_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / 'v.mp4'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x181818:s=320x180:r=10:d=6',
                       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], timeout=60)
            meta = {}
            look = media._with_color(dict(grade=dict(contrast=1.05)), dict(auto_color='histograma'), [(str(video), 0.0, 6.0)], temp, meta)
            self.assertIn('gamma', look['grade'])
            self.assertGreaterEqual(look['grade']['contrast'], 1.05)
            self.assertTrue(meta['color_report'])
            same = media._with_color(dict(grade=None), dict(auto_color='off'), [], temp, {})
            self.assertEqual(same, dict(grade=None))

    def test_missing_lut_is_reported_not_fatal(self):
        meta = {'root': tempfile.gettempdir()}
        look = media._with_color(dict(grade=None), dict(lut='nao_existe.cube'), [], tempfile.gettempdir(), meta)
        self.assertTrue(any('não encontrada' in x for x in meta['color_report']))
        self.assertNotIn('lut', (look.get('grade') or {}))


if __name__ == '__main__':
    unittest.main()
