import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import cache, technical
from liveclips.engine import Engine
from liveclips.store import Store


class Cache(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name

    def test_roundtrip_and_param_change_misses(self):
        self.assertTrue(cache.put(self.root, 'k', 'sha1', dict(a=1), dict(v=1)))
        self.assertEqual(cache.get(self.root, 'k', 'sha1', dict(v=1)), dict(a=1))
        self.assertIsNone(cache.get(self.root, 'k', 'sha1', dict(v=2)))
        self.assertIsNone(cache.get(self.root, 'k', 'sha2', dict(v=1)))
        self.assertIsNone(cache.get(self.root, 'outro', 'sha1', dict(v=1)))

    def test_corrupt_file_is_a_miss_not_an_error(self):
        cache.put(self.root, 'k', 'sha1', dict(a=1))
        for file in Path(self.root).rglob('*.json'):
            file.write_text('{quebrado', encoding='utf-8')
        self.assertIsNone(cache.get(self.root, 'k', 'sha1'))

    def test_oversized_not_stored_and_clear(self):
        self.assertFalse(cache.put(self.root, 'k', 's', 'x' * (cache.MAX_BYTES + 10)))
        cache.put(self.root, 'k', 's', 1); cache.put(self.root, 'k', 't', 2)
        self.assertEqual(cache.clear(self.root), 2)
        self.assertIsNone(cache.get(self.root, 'k', 's'))

    def test_trim_keeps_newest(self):
        with mock.patch.object(cache, 'MAX_ITEMS', 3):
            import os, time
            for i in range(6):
                cache.put(self.root, 'k', f's{i}', i)
                for f in Path(self.root).rglob('*.json'):
                    pass
                time.sleep(.01)
            files = list((Path(self.root) / 'cache' / 'k').glob('*.json'))
            self.assertEqual(len(files), 3)
            self.assertEqual(cache.get(self.root, 'k', 's5'), 5)
            self.assertIsNone(cache.get(self.root, 'k', 's0'))
            self.assertTrue(os.path.isdir(self.root))


class EngineTechnicalCache(unittest.TestCase):
    def test_second_analysis_of_same_content_is_cached(self):
        with tempfile.TemporaryDirectory() as temp:
            engine = Engine(Store(temp))
            row = dict(path='x.ts', duration=30.0, sha='abc')
            with mock.patch.object(technical, 'analyze', return_value=dict(silence=[(1, 2)])) as analyze:
                first = engine.cached_technical(row)
                second = engine.cached_technical(dict(row, path='outro_nome.ts'))      # mesmo conteúdo, outro caminho
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(second['silence'], [[1, 2]])         # veio do cache (JSON)
            with mock.patch.object(technical, 'VERSION', 99), mock.patch.object(technical, 'analyze', return_value=dict(silence=[])) as analyze:
                engine.cached_technical(row)
            self.assertEqual(analyze.call_count, 1)             # versão nova do algoritmo invalida


if __name__ == '__main__':
    unittest.main()
