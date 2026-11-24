"""Autoteste, medição e relatório dos testes físicos (rodam em Linux com mídia sintética; o Windows real só se prova no roteiro W01–W10)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from liveclips import selftest


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg ausente')
class SelfTest(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd(); self.tmp = tempfile.mkdtemp(prefix='hk_st_'); os.chdir(self.tmp)
        self.addCleanup(lambda: (os.chdir(self.cwd), shutil.rmtree(self.tmp, ignore_errors=True)))

    def test_selfcheck_passes_and_writes_a_json_report(self):
        self.assertEqual(selftest.selfcheck(self.tmp), 0)
        r = json.loads(Path(self.tmp, 'relatorio_autoteste.json').read_text(encoding='utf-8'))
        names = [x['passo'] for x in r['resultados']]
        for need in ('modulos', 'ffmpeg', 'codificacao_cpu', 'servidor', 'legenda_libass', 'gpu'):
            self.assertIn(need, names)
        self.assertTrue(all(x['ok'] for x in r['resultados'] if x['passo'] in selftest.CRITICAL))

    def test_sampler_reports_cpu_and_memory_of_a_child_process(self):
        p = subprocess.Popen([sys.executable, '-c', 'import time\nx=bytearray(30_000_000)\nt=time.time()\nwhile time.time()-t<1.2: pass'])
        s = selftest.Sampler(p.pid, .1); s.start(); p.wait(); s.stop_flag.set(); s.join(2)
        out = s.summary()
        self.assertGreater(out['memoria_pico_mb'], 20)
        self.assertIsNotNone(out['cpu_sistema_media_pct'])

    def test_report_zip_contains_only_the_expected_files_and_hides_the_user(self):
        user = Path.home().name
        Path('instalacao_teste.log').write_text(f'caminho {Path.home()}/x token=abc123456789 usuario {user}')
        Path('video_pessoal.mp4').write_bytes(b'0' * 100)
        root = Path(self.tmp, 'dados'); root.mkdir()
        target, included = selftest.relatorio(root)
        with zipfile.ZipFile(target) as z:
            names = z.namelist(); text = ' '.join(z.read(n).decode('utf-8', 'replace') for n in names)
        self.assertIn('instalacao_teste.log', names)
        self.assertFalse([n for n in names if n.endswith(('.mp4', '.sqlite3', '.db'))])
        self.assertNotIn('abc123456789', text)
        if len(str(Path.home())) > 3:
            self.assertNotIn(str(Path.home()), text)


if __name__ == '__main__':
    unittest.main()
