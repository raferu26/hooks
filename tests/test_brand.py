import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import assets as library, brand, editing, media
from liveclips.store import DEFAULT_PROFILE, profile_checked


def ffmpeg(*args):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', *args], check=True)


def pixel(video, second, x, y):
    """Cor média de um bloco 24x24 do quadro (1080x1920) naquele segundo."""
    out = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-ss', str(second), '-i', str(video), '-frames:v', '1',
                          '-vf', f'crop=24:24:{x}:{y},scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    return tuple(out[:3])


class Rules(unittest.TestCase):
    def test_clean_defaults_and_limits(self):
        kit = brand.clean(None)
        self.assertFalse(brand.active(kit))
        self.assertEqual(kit['logo']['corner'], 'tl')
        for bad in (dict(logo=dict(corner='meio')), dict(logo=dict(image='../x')), dict(logo=dict(scale=3)), dict(intro=dict(seconds=99)),
                    dict(title_color='vermelho'), dict(title_position='lado'), dict(caption_font='a;b{c}')):
            with self.assertRaises(ValueError, msg=str(bad)):
                brand.clean(bad)
        self.assertEqual(brand.clean(dict(title_color='ff0000'))['title_color'], '#FF0000')

    def test_profile_keeps_a_clean_brand(self):
        profile = profile_checked(dict(DEFAULT_PROFILE, brand=dict(caption_font='Anton', logo=dict(corner='br'))))
        self.assertEqual(profile['brand']['caption_font'], 'Anton')
        self.assertEqual(profile['brand']['logo']['corner'], 'br')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, brand=dict(logo=dict(corner='x'))))

    def test_logo_stays_inside_the_safe_area_in_every_corner(self):
        for corner in brand.CORNERS:
            x, y = brand.logo_center(corner, .16, .5)
            left, top = (x - .08) * 1080, (y - .0225) * 1920
            right, bottom = (x + .08) * 1080, (y + .0225) * 1920
            self.assertGreaterEqual(left, brand.SAFE['left'] - 1)
            self.assertLessEqual(right, 1080 - brand.SAFE['right'] + 1)
            self.assertGreaterEqual(top, brand.SAFE['top'] - 1)
            self.assertLessEqual(bottom, 1920 - brand.SAFE['bottom'] + 1)

    def test_titles_only_change_when_left_at_the_default(self):
        kit = brand.clean(dict(title_color='#00FF00', title_position='bottom'))
        titles = [dict(text='a', color='#FFFFFF', position='top'), dict(text='b', color='#FF0000', position='center')]
        out = brand.apply_titles(titles, kit)
        self.assertEqual((out[0]['color'], out[0]['position']), ('#00FF00', 'bottom'))
        self.assertEqual((out[1]['color'], out[1]['position']), ('#FF0000', 'center'))
        self.assertEqual(brand.apply_titles(titles, brand.clean(None)), titles)

    def test_missing_library_image_is_a_warning_not_a_crash(self):
        with tempfile.TemporaryDirectory() as root:
            kit = brand.clean(dict(logo=dict(image='a' * 16)))
            items, warnings = brand.assets(kit, root, 10)
            self.assertEqual(items, [])
            self.assertEqual(len(warnings), 1)

    def test_fonts_listing_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'fontes').mkdir()
            (Path(root) / 'fontes' / 'nota.txt').write_text('x')
            self.assertEqual(brand.fonts(root), [])


class Render(unittest.TestCase):
    def test_logo_intro_and_outro_appear_when_they_should(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'fonte.ts'
            ffmpeg('-f', 'lavfi', '-i', 'color=c=0x303030:size=320x180:rate=30:duration=8', '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000:duration=8',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source))
            logo_file, card_file = root / 'logo.png', root / 'cartao.png'
            ffmpeg('-f', 'lavfi', '-i', 'color=c=0xFF0000:size=400x200', '-frames:v', '1', str(logo_file))
            ffmpeg('-f', 'lavfi', '-i', 'color=c=0x00FF00:size=1080x1920', '-frames:v', '1', str(card_file))
            logo, card = library.import_image(root, logo_file, 'logo'), library.import_image(root, card_file, 'cartao')
            kit = brand.clean(dict(logo=dict(image=logo['id'], corner='tl', scale=.2, opacity=1), intro=dict(image=card['id'], seconds=1), outro=dict(image=card['id'], seconds=1)))
            profile = dict(DEFAULT_PROFILE, camera_rect=[0, 0, .25, .25], min_free_gb=.1, threads=2, brand=kit)
            plan = editing.plan_edits({'start': 0, 'end': 8}, {}, profile=profile)
            plan['decisions'] = []
            parts = [{'path': str(source), 'sha': media.sha_file(source), 'seq': 0, 'in': 0.0, 'out': 8.0, 'global_start': 0, 'global_end': 8, 'group_id': 'g'}]
            candidate = {'id': 'brand1', 'start': 0, 'end': 8, 'parts': parts, 'profile': profile,
                         'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}, 'project': dict(version=1)}}
            clip = media.render(candidate, [], temp, False, pipeline='single', root=temp)
            cx, cy = brand.logo_center('tl', .2, .5)
            r, g, b = pixel(clip, 3, int(cx * 1080) - 12, int(cy * 1920) - 12)
            self.assertGreater(r, 200)
            self.assertLess(g, 60)
            r, g, b = pixel(clip, .4, 540, 960)
            self.assertGreater(g, 200)       # cartão de abertura cobre o quadro
            self.assertLess(r, 60)
            r, g, b = pixel(clip, 3, 540, 960)
            self.assertLess(g, 120)          # no meio do clipe o cartão sumiu
            r, g, b = pixel(clip, 7.5, 540, 960)
            self.assertGreater(g, 200)       # cartão de encerramento

    def test_caption_font_and_custom_font_folder_do_not_break_the_render(self):
        found = next(iter(sorted(Path('/usr/share/fonts').rglob('*.ttf'))), None)
        if not found:
            self.skipTest('sem fonte no sistema')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'fontes').mkdir()
            (root / 'fontes' / found.name).write_bytes(found.read_bytes())
            family = brand.fonts(root)[0]['family']
            source = root / 'fonte.ts'
            ffmpeg('-f', 'lavfi', '-i', 'color=c=0x303030:size=320x180:rate=30:duration=4', '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000:duration=4',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source))
            profile = dict(DEFAULT_PROFILE, camera_rect=[0, 0, .25, .25], min_free_gb=.1, threads=2, brand=brand.clean(dict(caption_font=family)))
            plan = editing.plan_edits({'start': 0, 'end': 4}, {}, profile=profile)
            plan['decisions'] = []
            parts = [{'path': str(source), 'sha': media.sha_file(source), 'seq': 0, 'in': 0.0, 'out': 4.0, 'global_start': 0, 'global_end': 4, 'group_id': 'g'}]
            candidate = {'id': 'brand2', 'start': 0, 'end': 4, 'parts': parts, 'profile': profile,
                         'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}, 'project': dict(version=1)}}
            transcript = [dict(start=.5, end=3, text='olá mundo isso é um teste', words=[])]
            clip = media.render(candidate, transcript, temp, False, pipeline='single', root=temp)
            self.assertTrue(Path(clip).is_file())
            written = list(Path(temp).rglob('legendas.ass'))
            self.assertTrue(written)
            self.assertIn(f',{family},', written[0].read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
