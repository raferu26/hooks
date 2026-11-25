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


@unittest.skipUnless(shutil.which('git') and (EP.ROOT / '.git').exists(), 'sem repositório git')
class TestPackage(unittest.TestCase):
    """Pacote de TESTE para Windows (variante sem IA): wheels offline, scripts, roteiro, commit identificado e nenhum wheel de IA."""

    def _wheels(self, names):
        d = Path(tempfile.mkdtemp(prefix='hk_whl_')); self.addCleanup(shutil.rmtree, d, True)
        for n in names:
            (d / n).write_bytes(b'PK\x03\x04fake')
        return d

    def _need_files(self):
        need = ['tools/empacotar_release.py', 'docs/WINDOWS_TESTE/LEIA-ME_TESTE_WINDOWS.txt', 'INSTALAR_TESTE.bat', 'requirements-sem-ia.txt']
        tracked = subprocess.run(['git', '-C', str(EP.ROOT), 'ls-files', *need], capture_output=True, text=True).stdout.split()
        if len(tracked) < len(need):
            self.skipTest('arquivos do pacote de teste ainda não commitados')

    def test_builds_with_all_checks_and_identifies_the_commit(self):
        self._need_files()
        out = Path(tempfile.mkdtemp(prefix='hk_t_')); self.addCleanup(shutil.rmtree, out, True)
        z, digest, checks = EP.build_test(out, self._wheels(['numpy-1.26.4-cp311-cp311-win_amd64.whl', 'idna-3.7-py3-none-any.whl', 'streamlink-8.6.3-py3-none-win_amd64.whl']),
                                          includes=['PR #3'], allow_dirty=True)
        self.assertEqual([c for c in checks if not c[1]], [])
        self.assertIn(EP.head_commit()[:10], z.name)
        with zipfile.ZipFile(z) as zf:
            prefix = zf.namelist()[0].split('/')[0] + '/'
            info = __import__('json').loads(zf.read(prefix + 'BUILD_INFO.json'))
            self.assertTrue(zf.read(prefix + 'INSTALAR_TESTE.bat').count(b'\r\n') > 20)
            self.assertIn(prefix + 'VARIANTE_SEM_IA', zf.namelist())
        self.assertEqual(info['commit'], EP.head_commit()); self.assertEqual(info['variant'], 'sem_ia'); self.assertEqual(info['includes'], ['PR #3'])

    def test_refuses_ai_wheels_and_wrong_platform_wheels(self):
        self._need_files()
        out = Path(tempfile.mkdtemp(prefix='hk_t_')); self.addCleanup(shutil.rmtree, out, True)
        with self.assertRaises(SystemExit):
            EP.build_test(out, self._wheels(['mediapipe-0.10.21-cp311-cp311-win_amd64.whl']), allow_dirty=True)
        with self.assertRaises(SystemExit):
            EP.build_test(out, self._wheels(['numpy-1.26.4-cp311-cp311-manylinux_2_17_x86_64.whl']), allow_dirty=True)

    def test_wheel_platform_rule(self):
        for ok in ('numpy-1.26.4-cp311-cp311-win_amd64.whl', 'opencv_python_headless-4.10.0.84-cp37-abi3-win_amd64.whl', 'streamlink-8.6.3-py3-none-win_amd64.whl', 'x-1-py3-none-any.whl'):
            self.assertTrue(EP.wheel_fits_windows_py311(ok), ok)
        for bad in ('numpy-2.0-cp312-cp312-win_amd64.whl', 'x-1-cp311-cp311-linux_x86_64.whl'):
            self.assertFalse(EP.wheel_fits_windows_py311(bad), bad)


class FunctionalGate(unittest.TestCase):
    """O empacotamento TERMINA COM ERRO se a versão declara recursos que o produto não tem (ou a interface não foi reconstruída)."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
        import empacotar_release
        self.pack = empacotar_release

    def test_gate_passes_on_the_current_tree(self):
        self.assertEqual(self.pack.gate_funcional(), [])

    def test_stale_html_blocks(self):
        html = Path(__file__).resolve().parent.parent / 'liveclips' / 'static' / 'index.html'
        original = html.read_bytes()
        try:
            html.write_bytes(original.replace(b'data-rxl', b'data-old'))
            problems = self.pack.gate_funcional()
        finally:
            html.write_bytes(original)
        self.assertTrue(any('NÃO corresponde' in p for p in problems), problems)
        self.assertTrue(any('layouts_8' in p for p in problems), problems)

    def test_build_test_refuses_when_gate_fails(self):
        with unittest.mock.patch.object(self.pack, 'gate_funcional', lambda: ['layouts_8: faltam']):
            with self.assertRaises(SystemExit) as ctx:
                self.pack.build_test(tempfile.mkdtemp(), tempfile.mkdtemp(), allow_dirty=True)
        self.assertIn('BLOQUEADO', str(ctx.exception))
