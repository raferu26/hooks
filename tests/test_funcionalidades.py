"""O produto DECLARA os recursos e os tem: catálogo, interface distribuída, rotas, FFmpeg; diagnóstico sem segredos; identidade da tela."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import buildinfo, composition, funcionalidades as F
from liveclips.app import App

HTML = Path(__file__).resolve().parent.parent / 'liveclips' / 'static' / 'index.html'


class Declared(unittest.TestCase):
    def test_every_declared_feature_has_markers_and_all_are_in_the_shipped_html(self):
        self.assertEqual(set(F.EXPECTED), set(F.UI_MARKERS))
        self.assertTrue(F.check_ui()[0], F.check_ui()[1])

    def test_missing_control_fails_naming_the_feature(self):
        with tempfile.TemporaryDirectory() as t:
            broken = Path(t) / 'index.html'
            broken.write_text(HTML.read_text(encoding='utf-8').replace('data-rxl', 'data-x'), encoding='utf-8')
            ok, detail = F.check_ui(broken)
            self.assertFalse(ok)
            self.assertIn('layouts_8', detail)
            broken.write_text(HTML.read_text(encoding='utf-8').replace('rxCanvas', 'zz'), encoding='utf-8')
            self.assertIn('previa_imediata', F.check_ui(broken)[1])

    def test_missing_html_fails(self):
        self.assertFalse(F.check_ui('/nao/existe.html')[0])

    def test_catalog_must_have_exactly_the_eight_layouts_three_main(self):
        self.assertTrue(F.check_catalog()[0])
        cat = composition.catalog()
        with mock.patch.object(composition, 'catalog', lambda: dict(cat, layouts=cat['layouts'][:-1])):
            self.assertFalse(F.check_catalog()[0])
        swapped = [dict(l, group='main' if l['id'] == 'cinema' else l['group']) for l in cat['layouts']]
        with mock.patch.object(composition, 'catalog', lambda: dict(cat, layouts=swapped)):
            self.assertFalse(F.check_catalog()[0])

    def test_routes_and_presets_and_render_of_all_eight_layouts(self):
        self.assertTrue(F.check_routes()[0])
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(F.check_presets(t)[0])
        ok, detail = F.check_render()
        self.assertTrue(ok, detail)

    def test_unknown_declared_feature_is_flagged_by_selfcheck_step(self):
        from liveclips import selftest
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(buildinfo, 'read', lambda *a: dict(version='x', commit='y', variant='sem_ia', includes=[], funcionalidades_esperadas=['voo'])):
                ok, detail = selftest._features(Path(t))
            self.assertFalse(ok)
            self.assertIn('voo', detail)

    def test_selfcheck_step_passes_in_the_repository(self):
        from liveclips import selftest
        with tempfile.TemporaryDirectory() as t:
            ok, detail = selftest._features(Path(t))
            self.assertTrue(ok, detail)
        self.assertIn('funcionalidades', selftest.CRITICAL)


class UiIdentity(unittest.TestCase):
    def test_ui_build_id_matches_content_and_detects_edits(self):
        self.assertTrue(buildinfo.ui_build()['confere'])
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / 'i.html'
            f.write_text(HTML.read_text(encoding='utf-8').replace('</body>', '<!-- x --></body>'), encoding='utf-8')
            self.assertFalse(buildinfo.ui_build(f)['confere'])

    def test_state_carries_build_ui_and_install(self):
        with tempfile.TemporaryDirectory() as t:
            app = App(t, worker=False)
            try:
                b = app.state()['build']
                self.assertTrue(b['ui']['confere'])
                self.assertTrue(b['install'])
            finally:
                app.close()


class Diagnostico(unittest.TestCase):
    def test_diagnostic_has_the_essentials_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as t:
            app = App(t, worker=False)
            try:
                d = app.action('/api/diagnostico', {})
                text = json.dumps(d, ensure_ascii=False)
                self.assertNotIn(app.token, text)
                self.assertEqual(sorted(d['catalogo_layouts']), sorted(F.LAYOUT_IDS))
                self.assertTrue(d['interface']['confere'])
                self.assertIn('ffmpeg', d['ffmpeg'].lower())
                self.assertEqual(set(d['recursos_declarados']), set(F.EXPECTED))
                self.assertTrue(all(v['ok'] for v in d['verificacoes']), d['verificacoes'])
                for key in ('versao_backend', 'commit', 'instalacao', 'python', 'dependencias_ausentes'):
                    self.assertIn(key, d)
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()
