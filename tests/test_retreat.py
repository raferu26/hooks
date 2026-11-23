import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import media, qc


class Ladder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name)
        (self.target / 'sobra.tmp').write_text('x')

    def candidate(self, **profile):
        return dict(profile=dict(dict(voice_preset='off', auto_color='off', lut=''), **profile))

    def test_success_first_try_has_no_retreat(self):
        calls = []
        def fake(candidate, *a):
            calls.append(candidate['profile']['voice_preset']); return 'ok'
        meta = {}
        with mock.patch.object(media, '_render_single', fake):
            self.assertEqual(media._single_ladder(self.candidate(voice_preset='natural'), [], None, self.target, None, [], {}, meta), 'ok')
        self.assertEqual(calls, ['natural']); self.assertNotIn('recuo', meta)

    def test_failure_with_modules_retries_without_and_records(self):
        def fake(candidate, *a):
            if candidate['profile']['voice_preset'] != 'off':
                raise RuntimeError('filtro quebrado')
            return 'ok'
        meta = {}
        with mock.patch.object(media, '_render_single', fake):
            result = media._single_ladder(self.candidate(voice_preset='forte', auto_color='histograma'), [], None, self.target, None, [], {}, meta)
        self.assertEqual(result, 'ok')
        self.assertEqual(meta['recuo']['modulos'], ['tratamento de voz', 'cor automática'])
        self.assertIn('filtro quebrado', meta['recuo']['motivo'])
        self.assertFalse((self.target / 'sobra.tmp').exists())

    def test_failure_without_optional_modules_propagates(self):
        with mock.patch.object(media, '_render_single', side_effect=RuntimeError('falha real')):
            with self.assertRaises(RuntimeError):
                media._single_ladder(self.candidate(), [], None, self.target, None, [], {}, {})

    def test_failure_that_also_fails_without_modules_raises_original(self):
        with mock.patch.object(media, '_render_single', side_effect=RuntimeError('quebra geral')):
            with self.assertRaisesRegex(RuntimeError, 'quebra geral'):
                media._single_ladder(self.candidate(voice_preset='natural'), [], None, self.target, None, [], {}, {})

    def test_gpu_failure_is_left_to_the_cpu_retry(self):
        with mock.patch.object(media, '_render_single', side_effect=RuntimeError('nvenc')) as render:
            with self.assertRaises(RuntimeError):
                media._single_ladder(self.candidate(voice_preset='natural'), [], None, self.target, None, [], {}, {'encoder': 'nvenc'})
        self.assertEqual(render.call_count, 1)


class ManifestChecks(unittest.TestCase):
    def test_items_from_manifest_and_cover(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'manifesto.json').write_text(json.dumps(dict(recuo=dict(modulos=['LUT de cor'], motivo='x'), voice_skipped=['deesser'])), encoding='utf-8')
            (folder / 'capa.json').write_text(json.dumps(dict(weak=True)), encoding='utf-8')
            ids = [i['id'] for i in qc.manifest_checks(folder)]
        self.assertEqual(ids, ['recuo', 'voz_filtro', 'capa'])

    def test_empty_folder_gives_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(qc.manifest_checks(temp), [])


if __name__ == '__main__':
    unittest.main()
