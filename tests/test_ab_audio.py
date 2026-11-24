"""Fluxo do comparativo A/B de áudio (validacao/ab_audio.py) com amostras sintéticas curtas: mesmo volume em todas as versões."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('ab_audio', Path(__file__).resolve().parent.parent / 'validacao' / 'ab_audio.py')
AB = importlib.util.module_from_spec(spec); spec.loader.exec_module(AB)


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg ausente')
class AbAudio(unittest.TestCase):
    def test_demo_generates_equal_loudness_variants_and_listening_page(self):
        out = Path(tempfile.mkdtemp(prefix='hk_ab_test_')); self.addCleanup(shutil.rmtree, out, True)
        import sys
        old = sys.argv; sys.argv = ['ab_audio', '--demo', '--segundos', '6', '--saida', str(out)]
        try:
            AB.main()
        finally:
            sys.argv = old
        metrics = json.loads((out / 'metricas.json').read_text(encoding='utf-8'))
        self.assertEqual(len(metrics), 3)
        for sample, items in metrics.items():
            self.assertEqual([i['label'] for i in items], ['1_original', '2_preset_desligado', '3_preset_natural'])
            for it in items:
                self.assertLess(abs(it['I'] - AB.TARGET), .6, (sample, it))          # volumes iguais: comparação justa
                self.assertLessEqual(it['TP'], -.8, (sample, it))
                self.assertTrue((out / it['file']).is_file())
        page = (out / 'ouvir.html').read_text(encoding='utf-8')
        self.assertEqual(page.count('<audio'), 9)
        self.assertIn('data-blind=', page)                                            # modo cego presente


if __name__ == '__main__':
    unittest.main()
