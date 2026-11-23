import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import media, technical


def synthetic(path):
    """20 s: vídeo animado 0-8, cinza parado 8-12 (congelado), preto 12-14, animado 14-20; áudio: tom com silêncio 5-9 e 15-17."""
    fc = ('[0:v]trim=0:8,setpts=PTS-STARTPTS[a];[1:v]trim=0:4,setpts=PTS-STARTPTS[b];[2:v]trim=0:2,setpts=PTS-STARTPTS[c];'
          '[3:v]trim=0:6,setpts=PTS-STARTPTS[d];[a][b][c][d]concat=n=4:v=1:a=0[v];'
          "[4:a]volume=0:enable='between(t,5,9)+between(t,15,17)'[au]")
    cmd = [media.tool('ffmpeg'), '-y', '-v', 'error',
           '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25:duration=8',
           '-f', 'lavfi', '-i', 'color=c=gray:s=320x180:r=25:d=4',
           '-f', 'lavfi', '-i', 'color=c=black:s=320x180:r=25:d=2',
           '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25:duration=6',
           '-f', 'lavfi', '-i', 'sine=frequency=300:sample_rate=48000:duration=20',
           '-filter_complex', fc, '-map', '[v]', '-map', '[au]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


class Envelope(unittest.TestCase):
    def test_hysteresis_ignores_short_dips_and_pads_edges(self):
        db = np.full(400, -20.0, dtype=np.float32)       # 20 s a 0,05 s
        db[100:140] = -70                                # 2,0 s de silêncio
        db[200:210] = -70                                # 0,5 s: abaixo do mínimo
        db[300:304] = -70                                # 0,2 s
        found = technical.silences(db, .05)
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0]['start'], 5.0 + .15, places=2)
        self.assertAlmostEqual(found[0]['end'], 7.0 - .15, places=2)
        self.assertTrue(found[0]['confiavel'])

    def test_no_contrast_is_marked_unreliable(self):
        rng = np.random.default_rng(1)
        db = (-30 + rng.normal(0, .4, 400)).astype(np.float32)
        db[100:140] = -38
        found = technical.silences(db, .05, floor=-39)
        for item in found:
            self.assertFalse(item['confiavel'])

    def test_empty(self):
        self.assertEqual(technical.silences(np.zeros(0, dtype=np.float32)), [])
        self.assertEqual(technical.energy_peaks(np.zeros(0, dtype=np.float32)), [])

    def test_peaks_have_refractory_gap(self):
        db = np.full(400, -40.0, dtype=np.float32)
        db[100] = -10; db[110] = -10; db[250] = -10
        peaks = technical.energy_peaks(db, .05)
        self.assertEqual([p['time'] for p in peaks], [5.0, 12.5])


class RealMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'amostra.mp4'
        synthetic(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_finds_inserted_problems_and_keeps_negatives(self):
        result = technical.analyze(self.path, 20)
        silences = result['silence']
        self.assertEqual(len(silences), 2, silences)
        self.assertTrue(4.9 < silences[0]['start'] < 5.5 and 8.5 < silences[0]['end'] < 9.1, silences[0])
        self.assertTrue(15.0 < silences[1]['start'] < 15.5, silences[1])
        self.assertEqual(len(result['black']), 1, result['black'])
        self.assertTrue(11.5 < result['black'][0]['start'] < 12.5 and 13.5 < result['black'][0]['end'] <= 14.1)
        self.assertGreaterEqual(len(result['freeze']), 1, result['freeze'])
        # parte animada (0-8 s) e final (14-20 s) não geram falso positivo de imagem parada
        for event in result['freeze']:
            self.assertGreaterEqual(event['start'], 7.5)
            self.assertLessEqual(event['end'], 14.5)
        self.assertEqual(result['unanalyzed'], [])
        self.assertIn('limits', silences[0])

    def test_silencedetect_filter_agrees_with_envelope(self):
        ref = technical.scan_silence_filter(self.path, 20)
        mine = technical.analyze(self.path, 20, scan_visual=False)['silence']
        self.assertEqual(len(ref), len(mine))
        for a, b in zip(ref, mine):
            self.assertLess(abs(a['start'] - b['start']), .4)

    def test_missing_file_is_reported_not_raised(self):
        result = technical.analyze(Path(self.temp.name) / 'nao_existe.mp4', 10)
        self.assertEqual(result['source'], {})
        self.assertEqual({u['kind'] for u in result['unanalyzed']}, {'audio', 'video'})
        self.assertEqual(result['silence'], [])


if __name__ == '__main__':
    unittest.main()
