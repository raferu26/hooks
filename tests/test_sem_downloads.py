"""Sem downloads inesperados de modelos: onde o código pode usar a rede e o que os instaladores .bat fazem. (O runtime do modo sem IA sem rede
está em test_noai_mode.test_no_outbound_network_in_no_ai_mode.)"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NET = re.compile(r'urlopen|urlretrieve|create_connection|http\.client|HTTPSConnection|requests\.(get|post)|socket\.socket\(')
# arquivo -> motivo (cada um só age por ação do usuário/configuração, nunca no início silencioso)
ALLOWED = {
    'behavior.py': 'D2 baixar modelo facial: só por `python -m liveclips.behavior` manual (o instalador não chama mais)',
    'denoise.py': 'D5 RNNoise: só pela rota do app acionada pelo usuário',
    'ollama.py': 'D6 Ollama local (127.0.0.1) quando o usuário liga',
    'chat.py': 'chat da Twitch (IRC) quando a live tem chat ligado',
    'desktop.py': 'verifica o servidor local do app (127.0.0.1)',
    'licensing.py': 'servidor de licença, só se `cloud_config.json` existir',
    'preflight.py': 'teste de conectividade (socket) antes de baixar modelo do modo com IA',
}


class Downloads(unittest.TestCase):
    def test_network_use_is_confined_to_known_modules(self):
        found = {p.name for p in (ROOT / 'liveclips').glob('*.py') if NET.search(p.read_text(encoding='utf-8', errors='ignore'))}
        self.assertEqual(sorted(found - set(ALLOWED)), [], 'novo uso de rede: documente em ALLOWED com o motivo')

    def test_allowlist_has_no_stale_entries(self):
        found = {p.name for p in (ROOT / 'liveclips').glob('*.py') if NET.search(p.read_text(encoding='utf-8', errors='ignore'))}
        self.assertEqual(sorted(set(ALLOWED) - found), [])

    def test_installers_do_not_fetch_models(self):
        for name in ('INSTALAR.bat', 'ATUALIZAR.bat', 'ABRIR_LIVECLIPS.bat', 'CRIAR_ATALHO.bat'):
            text = (ROOT / name).read_text(encoding='utf-8', errors='ignore')
            self.assertNotRegex(text, r'liveclips\.behavior|denoise|rnnoise|huggingface|\.task\b|\.rnnn', name)

    def test_model_fetch_is_not_called_at_startup(self):
        for name in ('__main__.py', 'app.py', 'engine.py', 'desktop.py'):
            text = (ROOT / 'liveclips' / name).read_text(encoding='utf-8', errors='ignore')
            self.assertNotRegex(text, r'behavior\.(fetch|download|ensure)\(|MODEL_URL', name)


if __name__ == '__main__':
    unittest.main()
