import tempfile
import unittest
from pathlib import Path

from liveclips import media
from liveclips.store import DEFAULT_PROFILE, profile_checked


class VoiceChain(unittest.TestCase):
    def test_off_changes_nothing(self):
        self.assertEqual(media.voice_filters(dict(voice_preset='off')), '')
        self.assertEqual(media.voice_filters({}), '')

    def test_natural_has_eq_deesser_compressor(self):
        text = media.voice_filters(dict(voice_preset='natural'))
        for part in ('equalizer=', 'deesser=', 'acompressor='):
            self.assertIn(part, text)
        self.assertTrue(text.startswith(','))

    def test_missing_filter_is_skipped_and_reported(self):
        saved = dict(media._FILTERS)
        try:
            media._FILTERS.clear()
            media._FILTERS.update({'equalizer': True, 'acompressor': True})      # sem deesser neste FFmpeg
            meta = {}
            text = media.voice_filters(dict(voice_preset='forte'), meta)
            self.assertNotIn('deesser', text)
            self.assertEqual(meta['voice_skipped'], ['deesser'])
        finally:
            media._FILTERS.clear(); media._FILTERS.update(saved)

    def test_chain_runs_in_ffmpeg_and_keeps_peak_under_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'a.wav'
            graph = media.audio_chain('0:a', [], dict(voice_preset='forte'), 4, media.loudnorm_filter())
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i',
                       'sine=f=180:d=4:sample_rate=48000,volume=0.9', '-filter_complex', graph, '-map', '[aout]', str(out)], timeout=60)
            self.assertGreater(out.stat().st_size, 1000)
            import re
            import subprocess
            report = subprocess.run([media.tool('ffmpeg'), '-hide_banner', '-nostats', '-i', str(out), '-af', 'volumedetect', '-f', 'null', '-'],
                                    stderr=subprocess.PIPE, timeout=60).stderr.decode('utf-8', 'replace')
        peak = float(re.search(r'max_volume: (-?[\d.]+) dB', report).group(1))
        self.assertLessEqual(peak, -0.5)

    def test_profile_validation(self):
        good = profile_checked(dict(DEFAULT_PROFILE, voice_preset='natural'))
        self.assertEqual(good['voice_preset'], 'natural')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, voice_preset='robo'))


if __name__ == '__main__':
    unittest.main()
