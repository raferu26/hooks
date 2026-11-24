"""Verificações ESTÁTICAS de compatibilidade com Windows (feitas em Linux). Não substituem o teste físico (docs/WINDOWS_BETA.md)."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sorted((ROOT / 'liveclips').glob('*.py'))


class WindowsStatic(unittest.TestCase):
    def test_every_subprocess_call_hides_the_console_window(self):
        """Sem `creationflags`, cada chamada ao FFmpeg/streamlink faria uma janela preta piscar no Windows."""
        bad = []
        for p in PY:
            for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess'
                        and n.func.attr in ('run', 'Popen', 'check_output', 'check_call', 'call')):
                    if not any(k.arg == 'creationflags' or k.arg is None for k in n.keywords):
                        bad.append(f'{p.name}:{n.lineno}')
        self.assertEqual(bad, [])

    def test_posix_only_modules_are_guarded_by_os_name(self):
        for p in PY:
            text = p.read_text(encoding='utf-8')
            for m in re.finditer(r'^\s*import fcntl', text, re.M):
                before = text[:m.start()].splitlines()[-4:]
                self.assertTrue(any("os.name" in l and ('nt' in l) for l in before) or 'else:' in ''.join(before), f'{p.name}: fcntl sem proteção de os.name')

    def test_no_hardcoded_unix_temp_paths_in_product_code(self):
        for p in PY:
            for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
                if re.search(r"['\"]/(tmp|home|usr|var)/", line) and not re.search(r'fonts|machine-id', line) and 'LINUX' not in line.upper():   # caminhos do Linux dentro de ramos específicos (fontes, id da máquina)
                    self.fail(f'{p.name}:{i}: caminho Unix fixo: {line.strip()[:80]}')

    def test_batch_files_are_crlf_and_use_utf8_codepage(self):
        for b in sorted(ROOT.glob('*.bat')):
            raw = b.read_bytes()
            self.assertNotRegex(raw, rb'(?<!\r)\n', f'{b.name}: finais de linha não são CRLF')
        self.assertIn(b'chcp 65001', (ROOT / 'INSTALAR.bat').read_bytes())

    def test_requirements_are_pinned_or_bounded_for_reproducible_install(self):
        for line in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                self.assertRegex(line, r'(==|>=)', f'dependência sem versão: {line}')


if __name__ == '__main__':
    unittest.main()
