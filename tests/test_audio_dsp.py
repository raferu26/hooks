"""Áudio clássico (sem modelo): a cadeia do app tem que superar a anterior em medições sintéticas com referência limpa.
Usa as funções de validacao/medir_audio.py (sinais de 12 s). Sintético ≠ fala real: o teste protege contra regressão, não prova qualidade percebida."""
import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import media

spec = importlib.util.spec_from_file_location('medir_audio', Path(__file__).resolve().parent.parent / 'validacao' / 'medir_audio.py')
MA = importlib.util.module_from_spec(spec); spec.loader.exec_module(MA)


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg ausente')
class Dsp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='hk_dsp_'))
        cls.voice, cls.mask = MA.voice_signal(12); cls.noise = MA.noise_signal(12); cls.music = MA.music_signal(12)
        MA.wav(cls.tmp / 'voz.wav', cls.voice); MA.wav(cls.tmp / 'mix.wav', cls.voice + cls.noise); MA.wav(cls.tmp / 'musica.wav', cls.music)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _noise_floor(self, chain):
        MA.ff(['-i', str(self.tmp / 'mix.wav'), '-af', chain, '-ar', str(MA.SR), str(self.tmp / 'o.wav')])
        return MA.evaluate(MA.read(self.tmp / 'o.wav'), self.voice, self.mask)

    def _app_denoise(self):
        g = media.audio_chain('0:a', [], {}, 12, 'anull', True, {})
        return re.search(r'\[0:a\](aresample=48000,highpass=f=70,[^\[;]+)\[voice\]', g).group(1)

    def test_app_denoise_beats_previous_afftdn_without_hurting_speech(self):
        old = self._noise_floor('aresample=48000,highpass=f=70,afftdn=nr=12:nf=-45:tn=1')
        new = self._noise_floor(self._app_denoise())
        self.assertLess(new['piso_ruido_dBFS'], old['piso_ruido_dBFS'] - 4, (old, new))      # >= 4 dB mais ruído removido (clipe de 12 s)
        self.assertGreater(new['SDR_dB'], old['SDR_dB'] - 1.0, (old, new))                    # fala não piora mais de 1 dB

    def test_falls_back_to_afftdn_when_wavelet_filter_is_missing(self):
        with mock.patch.object(media, 'has_filter', return_value=False):
            self.assertEqual(media.denoise_filter(), 'afftdn=nr=12:nf=-45:tn=1')
        with mock.patch.object(media, 'has_filter', return_value=True):
            self.assertTrue(media.denoise_filter().startswith('afftdn') and 'afwtdn' in media.denoise_filter())

    def test_ducking_lowers_music_under_speech_by_at_least_6_db(self):
        g = media.audio_chain('0:a', [(1, dict(kind='music', volume=.12, duck=True))], {}, 12, 'anull', False, {})
        sc = re.search(r'sidechaincompress=([^\[;]+)', g).group(1)
        MA.ff(['-i', str(self.tmp / 'musica.wav'), '-i', str(self.tmp / 'voz.wav'), '-filter_complex', f'[0:a][1:a]sidechaincompress={sc}[d]', '-map', '[d]', str(self.tmp / 'd.wav')])
        d = MA.read(self.tmp / 'd.wav'); n = min(len(d), len(self.mask)); m = self.mask[:n]
        drop = MA.db(MA.rms(d[:n][~m])) - MA.db(MA.rms(d[:n][m]))
        self.assertGreaterEqual(drop, 6.0, drop)

    def test_final_chain_respects_true_peak_limit(self):
        meta = {}
        g = media.audio_chain('0:a', [(1, dict(kind='music', volume=.12, duck=True))], {}, 12, media.loudnorm_filter(), True, meta)
        MA.ff(['-i', str(self.tmp / 'mix.wav'), '-i', str(self.tmp / 'musica.wav'), '-filter_complex', g, '-map', '[aout]', '-ar', str(MA.SR), str(self.tmp / 'f.wav')])
        _, tp = MA.ebur(self.tmp / 'f.wav')
        self.assertLessEqual(tp, -1.0, tp)


if __name__ == '__main__':
    unittest.main()
