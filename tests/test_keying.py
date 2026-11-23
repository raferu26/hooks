import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from liveclips import assets, keying, media, project
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store
from liveclips.timeline import build_timeline, plan
from tests.test_modules_combined import real_source


def green_screen(path, size=(200, 200)):
    data = np.zeros((size[1], size[0], 3), np.uint8)
    data[:] = (0, 255, 0)                       # fundo verde
    data[60:140, 60:140] = (220, 30, 30)        # objeto vermelho
    Image.fromarray(data, 'RGB').save(path)


class Keying(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def test_chroma_key_removes_background_and_keeps_object(self):
        src = self.dir / 'g.png'; green_screen(src)
        out = keying.apply(src, self.dir / 'o.png', 200, keying.check_key(dict(mode='chroma', color='#00ff00', tolerance=.2, softness=.1)))
        image = np.array(Image.open(out))
        self.assertEqual(image[5, 5, 3], 0)           # fundo transparente
        self.assertEqual(image[100, 100, 3], 255)     # objeto opaco
        self.assertGreater(image[100, 100, 0], 200)

    def test_luma_key_dark_and_light(self):
        data = np.zeros((40, 40, 3), np.uint8); data[:, 20:] = 255
        src = self.dir / 'l.png'; Image.fromarray(data, 'RGB').save(src)
        light = np.array(Image.open(keying.apply(src, self.dir / 'a.png', 40, keying.check_key(dict(mode='luma', threshold=.5, softness=.05, keep='light')))))
        self.assertEqual((light[20, 5, 3], light[20, 35, 3]), (0, 255))
        dark = np.array(Image.open(keying.apply(src, self.dir / 'b.png', 40, keying.check_key(dict(mode='luma', threshold=.5, softness=.05, keep='dark')))))
        self.assertEqual((dark[20, 5, 3], dark[20, 35, 3]), (255, 0))

    def test_circle_mask_clears_corners_not_center(self):
        src = self.dir / 'c.png'; Image.new('RGB', (100, 100), (200, 200, 200)).save(src)
        image = np.array(Image.open(keying.apply(src, self.dir / 'o.png', 100, None, keying.check_mask(dict(shape='circle', feather=.05)))))
        self.assertEqual(image[1, 1, 3], 0); self.assertEqual(image[50, 50, 3], 255)

    def test_rounded_mask_keeps_edges_middle(self):
        src = self.dir / 'r.png'; Image.new('RGB', (100, 60), (10, 200, 10)).save(src)
        image = np.array(Image.open(keying.apply(src, self.dir / 'o.png', 100, None, keying.check_mask(dict(shape='rounded', radius=.3, feather=.03)))))
        self.assertEqual(image[0, 0, 3], 0); self.assertGreater(image[30, 50, 3], 250); self.assertGreater(image[2, 50, 3], 200)

    def test_layer_neutral_background(self):
        src = self.dir / 'l.png'; Image.new('RGB', (60, 60), (255, 0, 0)).save(src)
        out = keying.layer(src, self.dir / 'layer.png', (360, 640), .5, .5, .3, 1.0, 'screen')
        image = Image.open(out).convert('RGB')
        self.assertEqual(image.size, (360, 640)); self.assertEqual(image.getpixel((2, 2)), (0, 0, 0)); self.assertEqual(image.getpixel((180, 320)), (255, 0, 0))
        white = Image.open(keying.layer(src, self.dir / 'm.png', (360, 640), .5, .5, .3, 1.0, 'multiply')).convert('RGB')
        self.assertEqual(white.getpixel((2, 2)), (255, 255, 255))

    def test_validation_rejects_bad_values(self):
        for bad in (dict(mode='chroma', color='verde'), dict(mode='chroma', tolerance=3), dict(mode='luma', keep='meio'), dict(mode='mágico'), 'x'):
            with self.assertRaises(ValueError):
                keying.check_key(bad)
        with self.assertRaises(ValueError):
            keying.check_mask(dict(shape='estrela'))
        with self.assertRaises(ValueError):
            keying.check_blend('difference')
        self.assertIsNone(keying.check_key(None)); self.assertEqual(keying.check_blend(None), 'normal')


class KeyingInRender(unittest.TestCase):
    """Imagem com chave, máscara e mistura entrando no caminho real da exportação."""
    def test_render_with_keyed_masked_and_blended_overlays(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            streamer = store.create_streamer('Key')
            store.save_profile(streamer, dict(DEFAULT_PROFILE, camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off', cover=False))
            sid = store.new_session(streamer, 's'); session = store.session(sid)
            file = Path(session['source']) / 'segmento_00000.ts'; real_source(file, 30)
            info = media.probe(file); stat = file.stat()
            with store.connect(True) as c:
                c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns, 'done', '{}'))
            green = Path(temp) / 'g.png'; green_screen(green)
            image_id = assets.import_image(temp, green, 'verde')['id']
            rows = build_timeline(store.segments(sid)); group = rows[0]['group_id']
            store.propose(sid, dict(start=3.0, end=20.0, group_id=group, score=9, reasons=['t'], transcript='x', transcript_segments=[]),
                          plan(rows, 3.0, 20.0, group), store.streamer(streamer)['profile'])
            item = store.rows('SELECT id,version,start,end,parts FROM candidates')[0]
            proj = project.empty()
            proj['overlays'] = [
                dict(id='a', image=image_id, start=1, end=6, x=.3, y=.3, scale=.3, opacity=1, key=keying.check_key(dict(mode='chroma')), mask=keying.check_mask(dict(shape='circle'))),
                dict(id='b', image=image_id, start=7, end=12, x=.5, y=.6, scale=.4, opacity=.8, blend='screen')]
            store.set_data(item['id'], 'project', proj)
            store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve', editorial_confirmed=True)
            Engine(store).do_render(item['id'], False)
            done = store.candidate(item['id'])
            self.assertEqual(done['status'], 'done', done.get('error'))
            folder = Path(done['export_path']); folder = folder if folder.is_dir() else folder.parent
            manifest = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertNotIn('recuo', manifest, manifest.get('recuo'))
            self.assertNotIn('overlay_warnings', manifest)
            self.assertEqual(manifest['pipeline'], 'auto')
            self.assertFalse(manifest.get('fallback'))

    def test_project_clean_keeps_and_validates_effects(self):
        raw = project.empty()
        raw['overlays'] = [dict(image='a' * 16, start=1, end=4, x=.5, y=.5, scale=.3, opacity=1, key=dict(mode='chroma'), mask=dict(shape='circle'), blend='multiply')]
        cleaned = project.clean(raw, 30)
        self.assertEqual(cleaned['overlays'][0]['key']['color'], '#00FF00')
        self.assertEqual(cleaned['overlays'][0]['blend'], 'multiply')
        raw['overlays'][0]['key'] = dict(mode='chroma', color='zzz')
        with self.assertRaises(ValueError):
            project.clean(raw, 30)


if __name__ == '__main__':
    unittest.main()
