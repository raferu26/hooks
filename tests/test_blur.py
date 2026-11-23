import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import editing, media
from liveclips.store import DEFAULT_PROFILE, profile_checked


def ffmpeg(*args):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', *args], check=True)


def gray_frame(video, second, width, height, scale=None):
    vf = f'scale={scale[0]}:{scale[1]},format=gray' if scale else 'format=gray'
    out = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-ss', str(second), '-i', str(video), '-frames:v', '1',
                          '-vf', vf, '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(height, width).astype(float)


def sharpness(block):
    return float(np.var(block[1:-1, 1:-1] * 4 - block[:-2, 1:-1] - block[2:, 1:-1] - block[1:-1, :-2] - block[1:-1, 2:]))


class Rules(unittest.TestCase):
    def test_default_has_no_regions_and_roundtrips(self):
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE))['blur_regions'], [])
        profile = profile_checked(dict(DEFAULT_PROFILE, blur_regions=[dict(x=.1, y=.2, w=.3, h=.1, label='  chat   da live ')]))
        self.assertEqual(profile['blur_regions'], [dict(x=.1, y=.2, w=.3, h=.1, label='chat da live')])

    def test_invalid_regions_are_errors_not_silently_dropped(self):
        for bad in ('x', [dict(x=.1, y=.1, w=.3)], [dict(x=.9, y=.1, w=.3, h=.1)], [dict(x=.1, y=.1, w=.01, h=.1)],
                    [dict(x=-.1, y=.1, w=.3, h=.1)], [dict(x=float('nan'), y=.1, w=.3, h=.1)], [dict(x=.1, y=.1, w=.1, h=.1)] * 7):
            with self.assertRaises(ValueError, msg=str(bad)):
                profile_checked(dict(DEFAULT_PROFILE, blur_regions=bad))

    def test_graph_is_empty_without_regions_and_skips_tiny_ones(self):
        self.assertEqual(media.blur_graph([], 1280, 720, '0:v', 'o'), '')
        self.assertEqual(media.blur_graph([dict(x=.1, y=.1, w=.001, h=.001)], 1280, 720, '0:v', 'o'), '')
        self.assertEqual(media.blur_graph([dict(x='a')], 1280, 720, '0:v', 'o'), '')

    def test_graph_chains_regions_and_ends_on_the_requested_label(self):
        graph = media.blur_graph([dict(x=.1, y=.1, w=.3, h=.2), dict(x=.6, y=.6, w=.3, h=.3)], 1280, 720, 'srcv', 'srcb')
        self.assertEqual(graph.count('boxblur'), 2)
        self.assertTrue(graph.startswith('[srcv]split=2'))
        self.assertTrue(graph.endswith('[srcb]'))

    def test_boxes_stay_even_and_inside_the_frame(self):
        graph = media.blur_graph([dict(x=.9, y=.9, w=.1, h=.1), dict(x=.123, y=.321, w=.777, h=.5)], 1281, 721, '0:v', 'o')
        import re
        for w, h, x, y in re.findall(r'crop=(\d+):(\d+):(\d+):(\d+)', graph):
            w, h, x, y = map(int, (w, h, x, y))
            self.assertTrue(all(v % 2 == 0 for v in (w, h, x, y)))
            self.assertLessEqual(x + w, 1281)
            self.assertLessEqual(y + h, 721)


class Pixels(unittest.TestCase):
    def test_only_the_marked_area_loses_detail(self):
        with tempfile.TemporaryDirectory() as temp:
            source, out = Path(temp) / 'in.mp4', Path(temp) / 'out.mp4'
            ffmpeg('-f', 'lavfi', '-i', 'testsrc2=s=640x360:d=1:r=10', '-c:v', 'libx264', '-preset', 'ultrafast', '-qp', '0', str(source))
            graph = media.blur_graph([dict(x=0, y=0, w=.5, h=1)], 640, 360, '0:v', 'o')
            ffmpeg('-i', str(source), '-filter_complex', graph, '-map', '[o]', '-qp', '0', '-c:v', 'libx264', str(out))
            before, after = gray_frame(source, 0, 640, 360), gray_frame(out, 0, 640, 360)
            self.assertLess(sharpness(after[:, :320]), sharpness(before[:, :320]) * .02)
            self.assertAlmostEqual(sharpness(after[:, 320:]), sharpness(before[:, 320:]), delta=sharpness(before[:, 320:]) * .02)


def candidate_for(root, profile, name):
    source = root / 'fonte.ts'
    if not source.exists():
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=s=640x360:d=4:r=30', '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000:duration=4',
               '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source))
    plan = editing.plan_edits({'start': 0, 'end': 4}, {}, profile=profile)
    plan['decisions'] = []
    parts = [{'path': str(source), 'sha': media.sha_file(source), 'seq': 0, 'in': 0.0, 'out': 4.0, 'global_start': 0, 'global_end': 4, 'group_id': 'g'}]
    return {'id': name, 'start': 0, 'end': 4, 'parts': parts, 'profile': profile,
            'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}, 'project': dict(version=1)}}


class Render(unittest.TestCase):
    """O borrão tem que valer em TODOS os caminhos de render, inclusive no plano B: um caminho sem ele vaza o dado escondido."""

    def check(self, preview, pipeline, scale, size):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = dict(DEFAULT_PROFILE, content_mode='video', min_free_gb=.1, threads=2, auto_zoom=False)
            plain = media.render(candidate_for(root, base, 'sem'), [], temp, preview, pipeline=pipeline, root=temp)
            hidden = media.render(candidate_for(root, dict(base, blur_regions=[dict(x=0, y=0, w=.5, h=1)]), 'com'), [], temp, preview,
                                  pipeline=pipeline, root=temp)
            a, b = gray_frame(plain, 1, *size), gray_frame(hidden, 1, *size)
            y0, y1 = scale
            left, right = slice(0, size[0] // 2 - 20), slice(size[0] // 2 + 20, size[0])
            self.assertLess(sharpness(b[y0:y1, left]), sharpness(a[y0:y1, left]) * .1)
            self.assertGreater(sharpness(b[y0:y1, right]), sharpness(a[y0:y1, right]) * .8)

    def test_single_pipeline(self):
        # 640x360 encaixado em 1080 de largura: o vídeo ocupa y≈656..1263
        self.check(False, 'single', (700, 1220), (1080, 1920))

    def test_legacy_pipeline(self):
        self.check(False, 'legacy', (700, 1220), (1080, 1920))

    def test_original_review_copy(self):
        # revisão em 1280 de largura (720 de altura)
        self.check(True, 'auto', (40, 680), (1280, 720))


if __name__ == '__main__':
    unittest.main()
