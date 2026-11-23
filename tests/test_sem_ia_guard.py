"""Guarda da decisão 'Hook's sem IA': nenhum módulo NOVO pode usar modelo de ML/pré-treinado.
Os usos herdados estão na lista abaixo (docs/SEM_IA_MIGRACAO.md). Ao migrar um componente, REMOVA-O da lista;
adicionar arquivo à lista exige aprovação do Rafael."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'liveclips'
TOKENS = re.compile(r'faster_whisper|WhisperModel|mediapipe|CascadeClassifier|haarcascade|cv2\.dnn|onnxruntime|\btorch\b|'
                    r'tensorflow|tflite|arnndn|\.rnnn|huggingface|ollama', re.I)
# arquivo -> motivo (dependência herdada ainda não migrada)
ALLOWED = {
    'engine.py': 'D1 Whisper, D6 Ollama', 'preflight.py': 'D1 download do modelo Whisper',
    'behavior.py': 'D2 MediaPipe landmarks', 'camera_detect.py': 'D3 MediaPipe + Haar',
    'media.py': 'D4 Haar (reenquadramento) e D5 arnndn', 'speaker.py': 'D4 Haar',
    'denoise.py': 'D5 RNNoise', 'ollama.py': 'D6 Ollama', 'app.py': 'D5/D6 (denoise, lista de modelos Ollama)',
    'store.py': 'D1/D6 campos de perfil (whisper_device, ollama*)', 'bench.py': 'campo de perfil ollama',
    'capabilities.py': 'texto descritivo (N22)',
}


class SemIaGuard(unittest.TestCase):
    def test_no_new_ml_usage(self):
        found = {p.name for p in ROOT.glob('*.py') if TOKENS.search(p.read_text(encoding='utf-8', errors='ignore'))}
        new = sorted(found - set(ALLOWED))
        self.assertEqual(new, [], 'Uso novo de componente de ML/modelo (decisão "sem IA"): %s' % new)

    def test_allowlist_has_no_stale_entries(self):
        found = {p.name for p in ROOT.glob('*.py') if TOKENS.search(p.read_text(encoding='utf-8', errors='ignore'))}
        stale = sorted(set(ALLOWED) - found)
        self.assertEqual(stale, [], 'Já migrado? Remova da lista: %s' % stale)


if __name__ == '__main__':
    unittest.main()
