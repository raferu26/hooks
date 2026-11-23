import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from liveclips import bench, media
from liveclips import engine as engine_module


class Pure(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(bench.parse_time('1:02:03'), 3723)
        self.assertEqual(bench.parse_time('12:34'), 754)
        self.assertEqual(bench.parse_time('754,5'), 754.5)
        for bad in ('', 'abc', '1:2:3:4', '-5'):
            with self.assertRaises(ValueError):
                bench.parse_time(bad)

    def test_gold_loading_is_tolerant_and_reports_bad_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'g.csv'
            f.write_text('Video;Inicio;Fim;Nota\nlive1.mp4;1:00;1:40;5\nlive1.mp4;10:00;10:03;3\nlive2.mp4;x;2:00;\nlive2.mp4;;;\n# comentario\nlive2.mp4;5:00;5:45;\n',
                         encoding='utf-8-sig')
            gold, warnings = bench.load_gold(f)
            self.assertEqual(gold['live1'], [(60, 100)])
            self.assertEqual(gold['live2'], [(300, 345)])
            self.assertEqual(len(warnings), 3 - 1)  # trecho curto + tempo inválido
            f.write_text('video,inicio,fim\nlive1.mp4,0:10,0:50\n', encoding='utf-8')
            self.assertEqual(bench.load_gold(f)[0]['live1'], [(10, 50)])
            f.write_text('video;inicio\nx;1\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                bench.load_gold(f)
            f.write_text('video;inicio;fim\nx;;\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                bench.load_gold(f)

    def test_template_lists_videos(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'a.mp4').write_bytes(b'x')
            (Path(tmp) / 'b.txt').write_bytes(b'x')
            out = Path(tmp) / 'g.csv'
            self.assertEqual(bench.template(tmp, out), 1)
            self.assertIn('a.mp4', out.read_text(encoding='utf-8-sig'))
            with self.assertRaises(ValueError):
                bench.template(tempfile.mkdtemp(), out)  # pasta sem vídeos

    def test_metrics(self):
        gold = {'v': [(100, 140), (300, 340), (500, 540)]}
        cands = {'v': [dict(start=102, end=138, tier='alta'), dict(start=900, end=940, tier='baixa'),
                       dict(start=298, end=345, tier='media'), dict(start=700, end=740, tier='baixa'), dict(start=10, end=50, tier='baixa')]}
        r = bench.evaluate(cands, gold, ks=(1, 3, 5))
        self.assertEqual(r['hit'], {1: .333, 3: .667, 5: .667})
        self.assertEqual(r['precision'][1], 1.0)
        self.assertAlmostEqual(r['precision'][3], .667, places=3)
        self.assertEqual(r['per_tier']['alta'], dict(hits=1, total=1, rate=1.0))
        self.assertEqual(r['per_tier']['baixa']['hits'], 0)
        self.assertFalse(r['reliable'])
        self.assertAlmostEqual(r['start_error'], 2.0, places=1)
        text = bench.as_text({'agente': r})
        self.assertIn('AVISO', text)
        self.assertIn('top3: 67%', text)

    def test_no_candidates_and_iou(self):
        r = bench.evaluate({}, {'v': [(0, 30)]})
        self.assertEqual(r['hit'][1], 0.0)
        self.assertIsNone(r['precision'][1])
        self.assertEqual(bench.iou((0, 10), (10, 20)), 0.0)
        self.assertEqual(bench.iou((0, 10), (0, 10)), 1.0)


class FakeModel:
    def transcribe(self, path, **kw):
        words, t = [], 4.0
        for i in range(60):
            words.append(NS(start=t, end=t + .35, word=' ' + ['olha', 'isso', 'aqui', 'cara', 'incrivel', 'mesmo'][i % 6], probability=.9))
            t += .45
            if i % 12 == 11:
                words[-1].word += '.'
                t += 1.2
        seg = NS(start=words[0].start, end=words[-1].end, text=' '.join(w.word for w in words), words=words)
        return iter([seg]), NS(language='pt')


class EndToEnd(unittest.TestCase):
    def test_run_on_synthetic_video_with_fake_transcription(self):
        with tempfile.TemporaryDirectory() as tmp:
            videos = Path(tmp) / 'videos'
            videos.mkdir()
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=15',
                            '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000,volume=1', '-t', '45', '-c:v', 'libx264', '-b:v', '3M',
                            '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(videos / 'teste.mp4')], check=True)
            old = time.time() - 600
            os.utime(videos / 'teste.mp4', (old, old))
            gold = Path(tmp) / 'g.csv'
            gold.write_text('video;inicio;fim\nteste.mp4;0:05;0:35\n', encoding='utf-8')
            with patch.object(engine_module.Engine, 'get_model', lambda self, profile, name=None: FakeModel()):
                logs = []
                report = bench.run(videos, gold, Path(tmp) / 'dados', compare=True, progress=logs.append)
            self.assertEqual(set(report), {'agente completo', 'só ranking básico'})
            for r in report.values():
                self.assertEqual(r['gold'], 1)
                self.assertIn(1, r['hit'])
            self.assertFalse(report['agente completo']['reliable'])
            self.assertTrue(any('análise' in l for l in logs))
            with self.assertRaises(ValueError):
                bench.run(videos, _write(tmp, 'outro.mp4'), Path(tmp) / 'd2')  # vídeo ausente
            tiny = videos / 'pequeno.mp4'
            tiny.write_bytes(b'x' * 10)
            with patch.object(engine_module.Engine, 'get_model', lambda self, profile, name=None: FakeModel()):
                with self.assertRaises((RuntimeError, ValueError)):
                    bench.run(videos, _write(tmp, 'pequeno.mp4'), Path(tmp) / 'd3', progress=lambda m: None)


def _write(tmp, name):
    f = Path(tmp) / 'g2.csv'
    f.write_text(f'video;inicio;fim\n{name};0:05;0:35\n', encoding='utf-8')
    return f


if __name__ == '__main__':
    unittest.main()
