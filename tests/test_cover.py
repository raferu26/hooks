import json
import tempfile
import unittest
from pathlib import Path

from liveclips import cover, media
from PIL import Image, ImageChops


def video(path, seconds=12):
    # 0-2 s preto, depois imagem nítida de teste; sem áudio relevante
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1080x1920:rate=15:duration={seconds}',
               '-vf', "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='lt(t,2)'", '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], timeout=120)


class Cover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.temp.name) / 'clip.mp4'
        video(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_score_penalizes_black_and_blurry(self):
        import numpy as np
        black = np.zeros((200, 100, 3), np.uint8)
        noise = (np.random.RandomState(1).rand(200, 100, 3) * 255).astype(np.uint8)
        self.assertLess(cover.score(cover.metrics(black))[0], 10)
        self.assertGreater(cover.score(cover.metrics(noise))[0], cover.score(cover.metrics(black))[0])
        self.assertIn('quadro quase uniforme ou preto', cover.score(cover.metrics(black))[1])

    def test_pick_skips_dark_start_and_keeps_alternatives_apart(self):
        options = cover.pick(self.video, 12)
        self.assertTrue(options)
        self.assertGreater(options[0]['time'], 2.0)
        self.assertGreaterEqual(options[0]['score'], options[-1]['score'])
        times = [o['time'] for o in options]
        self.assertTrue(all(abs(a - b) >= 1.0 for i, a in enumerate(times) for b in times[i + 1:]))
        self.assertTrue(options[0]['bytes'])

    def test_compose_sizes_and_safe_margins(self):
        frame = cover.pick(self.video, 12)[0]['bytes']
        for aspect, size in cover.CANVAS.items():
            image = cover.compose(frame, 'Título de teste bem comprido para quebrar em linhas', 'destaque', aspect, cover.font_path())
            self.assertEqual(image.size, size)
        base = cover.compose(frame, '', 'limpo', '9x16')
        image = cover.compose(frame, 'TÍTULO MUITO MUITO GRANDE ' * 4, 'faixa', '9x16', cover.font_path())
        diff = ImageChops.difference(base, image).convert('L').point(lambda v: 255 if v > 30 else 0)
        self.assertIsNone(diff.crop((0, 0, 1080, 150)).getbbox(), 'texto invadiu a zona superior')
        from PIL import ImageDraw
        draw = ImageDraw.Draw(Image.new('RGB', (10, 10)))
        font, lines = cover.fit_text('TÍTULO MUITO MUITO GRANDE ' * 4, cover.font_path(), 1080 - 120, draw, start=130, floor=44)
        self.assertLessEqual(len(lines), 3)
        self.assertTrue(all(draw.textlength(line, font=font) <= 1080 - 120 for line in lines))

    def test_unknown_template_or_aspect_rejected(self):
        frame = cover.pick(self.video, 12)[0]['bytes']
        with self.assertRaises(ValueError):
            cover.compose(frame, 'x', 'inexistente', '9x16')
        with self.assertRaises(ValueError):
            cover.compose(frame, 'x', 'faixa', '3x2')

    def test_make_for_export_writes_files_and_report(self):
        candidate = dict(id='abc123', data=dict(moment_label='Jogada final'), profile=dict(cover_template='faixa'))
        report = cover.make_for_export(self.video, candidate, self.temp.name)
        self.assertEqual(report['template'], 'faixa')
        for name in ('capa_9x16.jpg', 'capa_1x1.jpg', 'capa_4x5.jpg', 'capa.json'):
            self.assertTrue((self.video.parent / name).is_file(), name)
        self.assertEqual(Image.open(self.video.parent / 'capa_4x5.jpg').size, (1080, 1350))
        saved = json.loads((self.video.parent / 'capa.json').read_text(encoding='utf-8'))
        self.assertIn('não indica qual é o melhor momento', saved['note'])
        self.assertEqual(saved['title'], 'Jogada final')


if __name__ == '__main__':
    unittest.main()
