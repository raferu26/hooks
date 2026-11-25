"""DIAGNOSTICO_WINDOWS: legível, sem segredos, aponta outra instalação rodando e arquivos divergentes."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import desktop, diagnostico, funcionalidades

BASE = Path(__file__).resolve().parent.parent


class Diag(unittest.TestCase):
    def test_report_has_all_sections_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / 'servidor.json').write_text(json.dumps(dict(pid=1, port=1, token='SEGREDO123456789')), encoding='utf-8')
            text = diagnostico.build(t)
        for title in ('Identidade desta instalação', 'Arquivos', 'Ferramentas', 'Filtros de renderização', 'Recursos declarados', 'Servidor, portas e processos',
                      'Erros recentes'):
            self.assertIn(title, text)
        self.assertNotIn('SEGREDO123456789', text)
        self.assertIn('8 layouts no catálogo', text)
        self.assertIn('Nada foi enviado', text)

    def test_missing_feature_shows_as_failure(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(funcionalidades, 'check_ui', lambda *a: (False, 'faltam na interface: layouts_8')):
            self.assertIn('[FALHA] interface_com_controles', diagnostico.build(t))

    def test_other_install_running_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / 'servidor.json').write_text(json.dumps(dict(pid=1, port=9, token='x', versao='0.20.0-beta.1')), encoding='utf-8')
            with mock.patch.object(desktop, 'alive', lambda info: True):
                ok, text = diagnostico.running_server(Path(t))
            self.assertIs(ok, False)
            self.assertIn('OUTRA INSTALAÇÃO', text)

    def test_integrity_detects_changed_and_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'a.py').write_text('x', encoding='utf-8')
            (root / 'MANIFESTO.sha256').write_text(f'{hashlib.sha256(b"x").hexdigest()}  a.py\n{hashlib.sha256(b"y").hexdigest()}  falta.py\n', encoding='utf-8')
            with mock.patch.object(diagnostico, 'ROOT', root):
                ok, detail = diagnostico.integrity()
                self.assertFalse(ok)
                self.assertIn('falta.py (ausente)', detail)
                (root / 'a.py').write_text('alterado', encoding='utf-8')
                self.assertIn('a.py (diferente)', diagnostico.integrity()[1])

    def test_bat_exists_with_crlf_and_calls_the_module(self):
        raw = (BASE / 'DIAGNOSTICO_WINDOWS.bat').read_bytes()
        self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))
        self.assertIn(b'-m liveclips diagnostico', raw)
        self.assertNotIn(b'http', raw)                      # não envia nada pela rede


if __name__ == '__main__':
    unittest.main()
