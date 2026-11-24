"""Empacotamento da beta para Windows: o ZIP sai do git, é verificável e não carrega lixo, segredos nem vídeos."""
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('empacotar', Path(__file__).resolve().parent.parent / 'tools' / 'empacotar_release.py')
EP = importlib.util.module_from_spec(spec); spec.loader.exec_module(EP)


@unittest.skipUnless(shutil.which('git') and (EP.ROOT / '.git').exists(), 'sem repositório git')
class Pack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix='hk_rel_'))
        tracked = subprocess.run(['git', '-C', str(EP.ROOT), 'ls-files', 'tools/empacotar_release.py', 'docs/WINDOWS_BETA.md'], capture_output=True, text=True).stdout.split()
        if len(tracked) < 2:
            raise unittest.SkipTest('arquivos do empacotamento ainda não commitados')
        cls.zip, cls.digest, cls.checks = EP.build(cls.out, allow_dirty=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_all_verifications_pass(self):
        self.assertEqual([c for c in self.checks if not c[1]], [])

    def test_zip_has_installer_with_crlf_and_no_model_download(self):
        with zipfile.ZipFile(self.zip) as z:
            data = z.read([n for n in z.namelist() if n.endswith('/INSTALAR.bat')][0])
        self.assertIn(b'\r\n', data)
        self.assertNotIn(b'liveclips.behavior', data)                    # o instalador não baixa modelo (decisão sem IA)

    def test_excludes_tests_validation_ui_sources_and_videos(self):
        with zipfile.ZipFile(self.zip) as z:
            names = z.namelist()
        self.assertFalse([n for n in names if '/tests/' in n or '/validacao/' in n or '/ui/' in n or n.endswith(('.mp4', '.wav', '.bundle'))])

    def test_secret_scanner_flags_real_looking_tokens_but_not_documentation_mentions(self):
        self.assertTrue(EP.SECRET.search(b'token=ghp_' + b'a' * 30))
        self.assertTrue(EP.SECRET.search(b'github_pat_' + b'A1_' * 12))
        self.assertTrue(EP.SECRET.search(b'-----BEGIN RSA PRIVATE KEY-----'))
        self.assertFalse(EP.SECRET.search('padrões (ghp_, github_pat_, AKIA, sk-) procurados na auditoria'.encode()))

    def test_sha256_file_matches(self):
        import hashlib
        line = (self.out / (self.zip.name + '.sha256')).read_text().split()[0]
        self.assertEqual(line, hashlib.sha256(self.zip.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
