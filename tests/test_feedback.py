import tempfile
import unittest
from pathlib import Path

from liveclips import feedback
from liveclips.store import Store
from tests.test_second_pass import make_session


class DiffTests(unittest.TestCase):
    def kinds(self, old, new):
        return [c['kind'] for c in feedback.diff(old, new)]

    def test_added_and_removed(self):
        old = dict(cuts=[dict(start=1, end=2)], zooms=[dict(id='z', start=3, end=4)])
        new = dict(cuts=[], zooms=[dict(id='z', start=3, end=4)], replays=[dict(start=5, end=7)])
        self.assertEqual({'corte_removido', 'replay_adicionado'}, set(self.kinds(old, new)))

    def test_sfx_removed_and_softer(self):
        old = dict(sfx=[dict(id='a', kind='boom', volume=.8), dict(id='b', kind='pop', volume=.6)])
        new = dict(sfx=[dict(id='b', kind='pop', volume=.3)])
        self.assertEqual({'efeito_sonoro_removido', 'efeito_sonoro_mais_baixo'}, set(self.kinds(old, new)))

    def test_no_change_no_feedback_and_caption_text_ignored(self):
        p = dict(cuts=[dict(start=1, end=2)], captions=dict(lines=[dict(text='a')]))
        self.assertEqual([], self.kinds(p, dict(p, captions=dict(lines=[dict(text='b')]))))

    def test_flood_is_limited(self):
        new = dict(cuts=[dict(start=i, end=i + .5) for i in range(20)])
        self.assertEqual(feedback.LIMIT, len(feedback.diff({}, new)))


class SaveLearnsTests(unittest.TestCase):
    def test_save_records_local_feedback_not_a_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'd')
            streamer, _, cid = make_session(store)
            version = store.candidate(cid)['version']
            store.save_project(cid, version, dict(cuts=[dict(start=3, end=4)]), False)
            rows = store.memory.list('feedback')
            self.assertTrue(rows)
            self.assertTrue(all(r['scope'] in ('job',) for r in rows if r['key'].startswith(cid)))
            self.assertEqual({}, store.memory.streamer_prefs(streamer) or {})            # nada generalizado sem pedido
            version = store.candidate(cid)['version']
            store.save_project(cid, version, dict(cuts=[dict(start=3, end=4)]), False)   # nada mudou: nenhum registro novo
            self.assertEqual(len(rows), len(store.memory.list('feedback')))

    def test_memory_failure_does_not_break_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'd')
            _, _, cid = make_session(store)
            store.memory.learn = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('falhou'))
            version = store.candidate(cid)['version']
            self.assertEqual(version + 1, store.save_project(cid, version, dict(cuts=[dict(start=3, end=4)]), False))


if __name__ == '__main__':
    unittest.main()
