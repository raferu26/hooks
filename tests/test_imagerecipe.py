import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from liveclips import assets, brand, imagerecipe, media
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store
from liveclips.timeline import build_timeline, plan


def logo_png(path, size=(400, 200)):
    """Logo vermelho com borda suave e fundo transparente."""
    image = Image.new('RGBA', size, (255, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, size[0] - 20, size[1] - 20), fill=(255, 0, 0, 255))
    from PIL import ImageFilter
    alpha = image.getchannel('A').filter(ImageFilter.GaussianBlur(2))
    image.putalpha(alpha)
    image.save(path)
    return path


class Recipes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.temp.name)
        cls.logo = logo_png(cls.dir / 'logo.png')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_contain_does_not_distort(self):
        image = imagerecipe.load(self.logo)                       # 400x200, elipse
        out = imagerecipe.fit_to(image, 100, 100, 'contain')
        self.assertEqual(out.size, (100, 100))
        alpha = np.asarray(out.getchannel('A'))
        rows = np.where(alpha.max(axis=1) > 128)[0]
        cols = np.where(alpha.max(axis=0) > 128)[0]
        self.assertAlmostEqual((cols.max() - cols.min()) / max(1, rows.max() - rows.min()), 360 / 160, delta=.25)   # elipse 360×160 mantém a proporção
        self.assertEqual(alpha[0, 0], 0)                            # faixa de cima/baixo transparente

    def test_cover_fills_the_canvas(self):
        image = Image.new('RGBA', (400, 200), (10, 200, 30, 255))
        out = imagerecipe.fit_to(image, 90, 160, 'cover')
        self.assertEqual(out.size, (90, 160))
        self.assertEqual(np.asarray(out.getchannel('A')).min(), 255)

    def test_resize_has_no_dark_halo(self):
        image = imagerecipe.load(self.logo)
        out = imagerecipe.fit_to(image, 120, 60, 'contain')
        arr = np.asarray(out).astype(int)
        edge = (arr[:, :, 3] > 10) & (arr[:, :, 3] < 245)
        self.assertTrue(edge.any())
        # pixels de borda parcialmente transparentes mantêm o vermelho do logo (sem escurecer em direção ao preto)
        self.assertGreater(arr[edge][:, 0].min(), 200)
        self.assertLess(arr[edge][:, 1].max(), 60)

    def test_shadow_and_outline_grow_canvas_and_keep_alpha(self):
        image = imagerecipe.load(self.logo)
        shadowed = imagerecipe.shadow(image, 0, 8, 10, .5)
        self.assertGreater(shadowed.width, image.width)
        self.assertTrue(imagerecipe.alpha_of(shadowed))
        outlined = imagerecipe.outline(image, 4, (0, 0, 0))
        self.assertGreater(outlined.width, image.width)
        arr = np.asarray(outlined)
        self.assertTrue(((arr[:, :, 3] > 200) & (arr[:, :, 0] < 30)).any())     # existe contorno escuro opaco

    def test_key_uniform_background_and_refusal(self):
        flat = Image.new('RGBA', (200, 120), (255, 255, 255, 255))
        ImageDraw.Draw(flat).rectangle((60, 30, 140, 90), fill=(20, 60, 200, 255))
        keyed = imagerecipe.key_uniform_background(flat, 12)
        a = np.asarray(keyed.getchannel('A'))
        self.assertEqual(a[2, 2], 0)
        self.assertEqual(a[60, 100], 255)
        noise = Image.fromarray(np.random.default_rng(1).integers(0, 255, (120, 200, 3), dtype=np.uint8)).convert('RGBA')
        with self.assertRaises(imagerecipe.RecipeError):
            imagerecipe.key_uniform_background(noise, 12)

    def test_provided_mask_and_crop(self):
        photo = Image.new('RGBA', (100, 100), (200, 50, 50, 255))
        mask = Image.new('L', (50, 50), 0)
        ImageDraw.Draw(mask).ellipse((5, 5, 45, 45), fill=255)
        mask_path = self.dir / 'mascara.png'
        mask.save(mask_path)
        out = imagerecipe.apply_mask(photo, mask_path)
        a = np.asarray(out.getchannel('A'))
        self.assertEqual(a[0, 0], 0)
        self.assertEqual(a[50, 50], 255)
        cropped = imagerecipe.crop_region(photo, [0, 0, .5, .25])
        self.assertEqual(cropped.size, (50, 25))

    def test_recipe_validation(self):
        for bad in (dict(fit='esticar'), dict(format='bmp'), dict(width=5), dict(margin=999), dict(crop=[.5, .5, .9, .9]), dict(key_bg=500),
                    dict(bg='vermelho'), dict(shadow=dict(blur=500))):
            with self.assertRaises(imagerecipe.RecipeError, msg=str(bad)):
                imagerecipe.clean(bad)
        self.assertEqual(imagerecipe.clean({})['format'], 'png')

    def test_jpg_flattens_transparency_and_says_so(self):
        recipe = imagerecipe.clean(dict(format='jpg', bg='#00ff00'))
        out, _ = imagerecipe.run(imagerecipe.load(self.logo), recipe)
        target = self.dir / 'saida.jpg'
        self.assertTrue(imagerecipe.save(out, target, recipe))
        self.assertEqual(Image.open(target).getpixel((1, 1))[1] > 200, True)       # fundo verde no lugar da transparência

    def test_batch_mixed_unicode_isolated_errors_sources_untouched(self):
        src = self.dir / 'fontes'
        src.mkdir()
        a = logo_png(src / 'logô_ção 1.png')
        Image.new('RGB', (300, 300), (30, 30, 200)).save(src / 'foto.jpg')
        Image.new('RGBA', (100, 50), (0, 200, 0, 128)).save(src / 'sel.webp')
        (src / 'quebrado.png').write_bytes(b'nao sou imagem')
        before = {p.name: media.sha_file(p) for p in src.iterdir()}
        out = self.dir / 'lote'
        report = imagerecipe.batch(sorted(src.iterdir()), dict(width=64, height=64, fit='contain', format='png'), out)
        self.assertEqual([r['ok'] for r in report].count(False), 1)
        self.assertTrue(next(r for r in report if r['name'] == 'quebrado.png')['error'])
        ok = [r for r in report if r['ok']]
        self.assertEqual(len(ok), 3)
        for r in ok:
            self.assertEqual((r['width'], r['height']), (64, 64))
            self.assertTrue(Path(r['output']).is_file())
        self.assertTrue(any('logô_ção' in r['output'] for r in ok))
        self.assertEqual(before, {p.name: media.sha_file(p) for p in src.iterdir()})        # fontes intactas
        again = imagerecipe.batch([a], dict(width=64, height=64), out)                      # não sobrescreve a saída anterior
        self.assertNotEqual(again[0]['output'], next(r['output'] for r in ok if 'logô_ção' in r['output']))

    def test_variant_catalog_cache_and_invalidation(self):
        root = self.dir / 'dados'
        root.mkdir()
        item = assets.import_image(root, self.logo, 'logo')
        first = imagerecipe.variant(root, item['id'], 'logo', (1080, 1920), scale=.2, style='sombra')
        self.assertFalse(first['cached'])
        self.assertTrue(first['alpha'])
        self.assertEqual(first['width'] % 2, 0)
        second = imagerecipe.variant(root, item['id'], 'logo', (1080, 1920), scale=.2, style='sombra')
        self.assertTrue(second['cached'])
        self.assertEqual(first['path'], second['path'])
        # outra receita (sem sombra) gera outra variante
        plain = imagerecipe.variant(root, item['id'], 'logo', (1080, 1920), scale=.2, style='none')
        self.assertNotEqual(plain['path'], first['path'])
        self.assertLess(plain['width'], first['width'])
        # formato do quadro muda o tamanho
        wide = imagerecipe.variant(root, item['id'], 'logo', (1920, 1080), scale=.2, style='none')
        self.assertGreater(wide['width'], plain['width'])
        frame = imagerecipe.variant(root, item['id'], 'moldura', (1080, 1920))
        self.assertEqual((frame['width'], frame['height']), (1080, 1920))
        card = imagerecipe.variant(root, item['id'], 'cartao', (1080, 1920), fit='contain')
        self.assertEqual((card['width'], card['height']), (1080, 1920))
        # asset trocado no mesmo id → conteúdo diferente → variante refeita, a antiga some
        original = assets.path_of(root, item['id'])
        Image.new('RGBA', (400, 200), (0, 0, 255, 255)).save(original, format='PNG')
        third = imagerecipe.variant(root, item['id'], 'logo', (1080, 1920), scale=.2, style='sombra')
        self.assertFalse(third['cached'])
        self.assertNotEqual(third['path'], first['path'])
        self.assertFalse(Path(first['path']).exists())
        # fonte removida → prune limpa o catálogo
        assets.remove(root, item['id'])
        self.assertGreaterEqual(imagerecipe.prune(root), 1)
        self.assertEqual(imagerecipe.catalog(root), [])

    def test_original_source_is_never_modified_by_variants(self):
        root = self.dir / 'dados2'
        root.mkdir()
        item = assets.import_image(root, self.logo, 'logo')
        path = assets.path_of(root, item['id'])
        before = media.sha_file(path)
        imagerecipe.variant(root, item['id'], 'logo', (1080, 1920), scale=.3, style='contorno')
        self.assertEqual(media.sha_file(path), before)


class BrandIntegration(unittest.TestCase):
    def test_brand_validation_and_assets_use_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = assets.import_image(root, logo_png(root / 'l.png'), 'logo')
            frame_img = Image.new('RGBA', (270, 480), (0, 0, 0, 0))
            ImageDraw.Draw(frame_img).rectangle((0, 0, 269, 479), outline=(255, 0, 0, 255), width=6)
            frame_img.save(root / 'm.png')
            frame = assets.import_image(root, root / 'm.png', 'moldura')
            kit = brand.clean(dict(logo=dict(image=item['id'], style='sombra', cover=True, scale=.2), frame=dict(image=frame['id']),
                                   intro=dict(image=item['id']), card_fit='contain'))
            self.assertEqual(kit['logo']['style'], 'sombra')
            items, warnings = brand.assets(kit, root, 10.0)
            self.assertEqual(warnings, [])
            ids = [i['id'] for i in items]
            self.assertEqual(ids[0], 'brand:frame')                                  # moldura por baixo do logo
            self.assertIn('brand:logo', ids)
            logo = next(i for i in items if i['id'] == 'brand:logo')
            self.assertIn('variantes', logo['path'])
            self.assertGreater(logo['scale'], .2)                                    # inclui a folga da sombra
            intro = next(i for i in items if i['id'] == 'brand:intro')
            self.assertIn('variantes', intro['path'])
            with self.assertRaises(ValueError):
                brand.clean(dict(logo=dict(style='neon')))
            with self.assertRaises(ValueError):
                brand.clean(dict(card_fit='esticar'))
            # a imagem sumiu: aviso, sem erro
            assets.remove(root, frame['id'])
            _, warnings = brand.assets(kit, root, 10.0)
            self.assertTrue(any('moldura' in w for w in warnings))

    def test_default_brand_unchanged_without_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = assets.import_image(root, logo_png(root / 'l.png'), 'logo')
            items, _ = brand.assets(brand.clean(dict(logo=dict(image=item['id']))), root, 8.0)
            self.assertEqual([i['id'] for i in items], ['brand:logo'])
            self.assertNotIn('variantes', items[0]['path'])                          # comportamento anterior preservado


def real_source(path, seconds=30):
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}',
               '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}:sample_rate=48000', '-c:v', 'libx264', '-preset', 'veryfast',
               '-pix_fmt', 'yuv420p', '-g', '30', '-c:a', 'aac', '-b:a', '96k', '-f', 'mpegts', str(path)], timeout=240)


class RealRender(unittest.TestCase):
    """Moldura, logo com sombra e logo na capa no caminho real de exportação."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(cls.temp.name)
        root = Path(cls.store.root)
        tmp = Path(cls.temp.name)
        logo = assets.import_image(root, logo_png(tmp / 'logo.png'), 'logo')
        border = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        ImageDraw.Draw(border).rectangle((0, 0, 1079, 1919), outline=(255, 0, 255, 255), width=24)
        border.save(tmp / 'moldura.png')
        frame = assets.import_image(root, tmp / 'moldura.png', 'moldura')
        kit = brand.clean(dict(logo=dict(image=logo['id'], style='sombra', cover=True, scale=.25, corner='tl'), frame=dict(image=frame['id'])))
        cls.streamer = cls.store.create_streamer('Marca')
        cls.store.save_profile(cls.streamer, dict(DEFAULT_PROFILE, camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off', brand=kit,
                                                  cover=True))
        cls.sid = cls.store.new_session(cls.streamer, 'marca')
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
        data = dict(start=5.0, end=20.0, group_id=group, score=9.0, reasons=['teste'], transcript='fala',
                    transcript_segments=[dict(start=6, end=9, text='uma fala curta', words=[])])
        cls.store.propose(cls.sid, data, plan(rows, 5.0, 20.0, group), cls.store.streamer(cls.streamer)['profile'])
        item = cls.store.rows('SELECT id,version,start,end,parts FROM candidates WHERE streamer=?', (cls.streamer,))[0]
        cls.store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve', editorial_confirmed=True)
        Engine(cls.store).do_render(item['id'], False)
        cls.done = cls.store.candidate(item['id'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def folder(self):
        path = Path(self.done['export_path'])
        return path if path.is_dir() else path.parent

    def test_done_and_frame_visible_in_video(self):
        self.assertEqual(self.done['status'], 'done', self.done.get('error'))
        out = Path(self.temp.name) / 'quadro.png'
        media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-ss', '3', '-i', str(self.folder() / 'clipe.mp4'), '-frames:v', '1', str(out)], 60)
        px = Image.open(out).convert('RGB')
        r, g, b = px.getpixel((6, 960))                    # borda da moldura (magenta) no meio da lateral esquerda
        self.assertGreater(r, 180)
        self.assertLess(g, 90)
        self.assertGreater(b, 180)

    def test_logo_variant_used_and_catalogued(self):
        names = [i['destination'] for i in imagerecipe.catalog(self.store.root)]
        self.assertIn('logo', names)
        self.assertIn('moldura', names)
        manifest = json.loads((self.folder() / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertNotIn('recuo', manifest)

    def test_cover_has_logo(self):
        cover = self.folder() / 'capa_9x16.jpg'
        self.assertTrue(cover.is_file())
        px = np.asarray(Image.open(cover).convert('RGB')).astype(int)
        top_left = px[40:260, 40:420]
        reddish = (top_left[:, :, 0] > 200) & (top_left[:, :, 1] < 70) & (top_left[:, :, 2] < 70)
        self.assertGreater(reddish.sum(), 500)
        self.assertIn('catalogo', json.dumps(sorted(p.name for p in (Path(self.store.root) / 'imagens' / 'variantes').iterdir())))
        self.assertTrue(any(i['destination'] == 'capa_logo' for i in imagerecipe.catalog(self.store.root)))


if __name__ == '__main__':
    unittest.main()
