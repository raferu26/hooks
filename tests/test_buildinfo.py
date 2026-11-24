"""Identificação do build, variante experimental sem IA e relatório de diagnóstico sem dados privados."""
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from liveclips import buildinfo, support


class Build(unittest.TestCase):
    def test_development_build_identifies_itself(self):
        with tempfile.TemporaryDirectory() as d:
            b = buildinfo.read(d)
        self.assertEqual(b['commit'], 'desenvolvimento'); self.assertEqual(b['variant'], 'referencia')

    def test_build_info_file_and_variant_flag_are_read(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'BUILD_INFO.json').write_text(json.dumps(dict(version='9.9.9-teste', commit='abcdef1234567890', includes=['PR #3'])))
            Path(d, 'VARIANTE_SEM_IA').write_text('')
            b = buildinfo.read(d)
        self.assertEqual(b['variant'], 'sem_ia'); self.assertIn('abcdef1234', b['label']); self.assertIn('sem IA', b['label'])

    def test_variant_changes_only_defaults_of_new_profiles(self):
        flag = buildinfo.ROOT / 'VARIANTE_SEM_IA'
        self.assertFalse(flag.exists(), 'o arquivo da variante não pode existir no repositório')
        from liveclips import store
        self.assertEqual(store.DEFAULT_PROFILE['ai_mode'], 'padrao')          # referência intacta
        try:
            flag.write_text('')
            importlib.reload(store)
            self.assertEqual((store.DEFAULT_PROFILE['ai_mode'], store.DEFAULT_PROFILE['second_pass']), ('sem_ia', 'off'))
        finally:
            flag.unlink(missing_ok=True)
            importlib.reload(store)
        self.assertEqual(store.DEFAULT_PROFILE['ai_mode'], 'padrao')


class Environment(unittest.TestCase):
    def test_report_has_hardware_libraries_and_build_and_no_username(self):
        text = '\n'.join(support.environment_report(None))
        for key in ('CPU:', 'Memória:', 'Placa(s) de vídeo:', 'numpy', 'Build:'):
            self.assertIn(key, text)
        for private in {os.environ.get('USER', ''), os.environ.get('USERNAME', ''), str(Path.home())}:
            if private and len(private) > 3:
                self.assertNotIn(private, text)

    def test_bundle_text_is_scrubbed_of_user_paths_and_tokens(self):
        dirty = r'C:\Users\Maria\Videos\x.mp4 token=abc123456789 /home/joao/a'
        clean = support.clean_text(dirty)
        self.assertNotIn('Maria', clean); self.assertNotIn('abc123456789', clean); self.assertNotIn('joao', clean)


if __name__ == '__main__':
    unittest.main()
