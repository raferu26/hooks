import tempfile
import unittest
from pathlib import Path

from liveclips import media
from liveclips.store import DEFAULT_PROFILE, profile_checked


class CutFade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.file = Path(cls.temp.name) / 's.mp4'
        media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=15:d=12',
                   '-f', 'lavfi', '-i', 'sine=f=300:d=12:sample_rate=48000', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(cls.file)], timeout=60)
        cls.parts = [dict(path=str(cls.file))]
        cls.infos = [media.probe(cls.file)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_default_has_no_fades(self):
        _, graph = media.build_source(self.parts, self.infos, [(0, 0, 3), (0, 5, 8), (0, 9, 11)], audio=True)
        self.assertNotIn('afade', graph)

    def test_fades_only_on_inner_edges(self):
        _, graph = media.build_source(self.parts, self.infos, [(0, 0, 3), (0, 5, 8), (0, 9, 11)], audio=True, fade=.02)
        first, middle, last = [line for line in graph.split(';') if line.endswith(('[a0]', '[a1]', '[a2]'))]
        self.assertNotIn('t=in', first); self.assertIn('t=out', first)
        self.assertIn('t=in', middle); self.assertIn('t=out', middle)
        self.assertIn('t=in', last); self.assertNotIn('t=out', last)

    def test_single_piece_or_tiny_piece_untouched(self):
        _, one = media.build_source(self.parts, self.infos, [(0, 0, 5)], audio=True, fade=.04)
        self.assertNotIn('afade', one)
        _, tiny = media.build_source(self.parts, self.infos, [(0, 0, .1), (0, 5, 8)], audio=True, fade=.04)
        first = [line for line in tiny.split(';') if line.endswith('[a0]')][0]
        self.assertNotIn('afade', first)      # trecho de 0,1 s é curto demais para fade de 40 ms

    def test_duration_unchanged_and_ffmpeg_runs(self):
        durations = []
        for fade in (0.0, .04):
            args, graph = media.build_source(self.parts, self.infos, [(0, 0, 3), (0, 5, 8), (0, 9, 11)], video=False, audio=True, fade=fade)
            out = Path(self.temp.name) / f'o{fade}.wav'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', *args, '-filter_complex', graph, '-map', '[srca]', str(out)], timeout=60)
            durations.append(out.stat().st_size)
        self.assertLess(abs(durations[0] - durations[1]), 4 * 48000 * 0.02)   # menos de 20 ms de diferença (WAV estéreo 16 bits)

    def test_profile_validation(self):
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, cut_fade='suave'))['cut_fade'], 'suave')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, cut_fade='enorme'))
        self.assertEqual(media.cut_fade(dict(cut_fade='media')), .04)
        self.assertEqual(media.cut_fade({}), 0.0)


if __name__ == '__main__':
    unittest.main()


class SlowInterp(unittest.TestCase):
    def test_graph_and_ffmpeg(self):
        from liveclips.store import DEFAULT_PROFILE, profile_checked
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, slow_interp='mistura'))['slow_interp'], 'mistura')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, slow_interp='fantasia'))
        self.assertIsNone(media.slow_interp({})); self.assertEqual(media.slow_interp(dict(slow_interp='movimento')), 'mci')
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 's.mp4'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x90:r=15:d=6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(file)], timeout=60)
            parts, infos = [dict(path=str(file))], [media.probe(file)]
            plain = media.build_source(parts, infos, [(0, 0, 2, .5, 0.0)], audio=False)[1]
            smooth = media.build_source(parts, infos, [(0, 0, 2, .5, 0.0)], audio=False, interp='blend')[1]
            self.assertNotIn('minterpolate', plain); self.assertIn('minterpolate=fps=30:mi_mode=blend', smooth)
            long = media.build_source(parts, infos, [(0, 0, 5, .5, 0.0)], audio=False, interp='blend')[1]
            self.assertNotIn('minterpolate', long)        # 10 s de câmera lenta passa do limite
            args, graph = media.build_source(parts, infos, [(0, 0, 2, .5, 0.0)], audio=False, interp='blend')
            out = Path(temp) / 'o.mp4'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', *args, '-filter_complex', graph, '-map', '[srcv]', '-c:v', 'libx264', str(out)], timeout=120)
            self.assertAlmostEqual(media.probe(out)['duration'], 4.0, delta=.3)


class FilterStrings(unittest.TestCase):
    """Todo texto de filtro fixo do programa precisa ser aceito pelo FFmpeg (um valor inválido só aparece em execução)."""
    def test_stabilize_presets_run(self):
        for mode, text in media.STABILIZE.items():
            if not text:
                continue
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=15:d=1', '-vf', text, '-f', 'null', '-'], timeout=60)

    def test_voice_presets_run(self):
        for name, items in media.VOICE_PRESETS.items():
            if not items:
                continue
            chain = ','.join(text for _, text in items)
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=f=300:d=1', '-af', chain, '-f', 'null', '-'], timeout=60)
