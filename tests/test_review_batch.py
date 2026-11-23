import json
import tempfile
import unittest

from liveclips.app import App
from tests.helpers import setup_session, candidate


class BatchReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name, worker=False); self.addCleanup(self.app.close)
        self.store = self.app.store
        _, self.sid, _ = setup_session(self.store, durations=(300,))

    def clip(self, start):
        item, _ = candidate(self.store, self.sid, start, start + 30)
        return item['id']

    def status(self, cid):
        return self.store.candidate(cid)['status']

    def test_reject_many_with_one_reason(self):
        ids = [self.clip(10), self.clip(60), self.clip(120)]
        out = self.app.review_batch(dict(ids=ids, action='reject', reason='fraco'))
        self.assertEqual((out['done'], out['failed']), (3, 0))
        for cid in ids:
            row = self.store.candidate(cid)
            self.assertEqual((row['status'], row['reason']), ('rejected', 'fraco'))

    def test_approve_many_goes_through_the_normal_rules(self):
        ids = [self.clip(10), self.clip(60)]
        out = self.app.review_batch(dict(ids=ids, action='approve'))
        self.assertEqual(out['done'] + out['failed'], 2)
        for result in out['results']:
            if result['ok']:
                self.assertEqual(self.status(result['id']), 'approved')
            else:
                self.assertTrue(result['error'])
                self.assertEqual(self.status(result['id']), 'pending')

    def test_editorial_review_blocks_batch_approval_but_not_the_rest(self):
        a, b = self.clip(10), self.clip(60)
        with self.store.connect(True) as c:
            row = c.execute('SELECT data FROM candidates WHERE id=?', (a,)).fetchone()
            data = json.loads(row['data']); data['editorial_audit'] = dict(requires_review=True, checks=[])
            c.execute('UPDATE candidates SET data=? WHERE id=?', (json.dumps(data), a))
        out = self.app.review_batch(dict(ids=[a, b], action='approve'))
        by = {r['id']: r for r in out['results']}
        self.assertFalse(by[a]['ok'])
        self.assertIn('Confirme', by[a]['error'])
        self.assertEqual(self.status(a), 'pending')
        self.assertTrue(by[b]['ok'])
        self.assertEqual(self.status(b), 'approved')

    def test_unauthorized_music_is_never_batch_approved(self):
        a = self.clip(10)
        with self.store.connect(True) as c:
            data = json.loads(c.execute('SELECT data FROM candidates WHERE id=?', (a,)).fetchone()['data'])
            data['project'] = dict(version=1, music=dict(id='x', authorized=False))
            c.execute('UPDATE candidates SET data=? WHERE id=?', (json.dumps(data), a))
        out = self.app.review_batch(dict(ids=[a], action='approve'))
        self.assertFalse(out['results'][0]['ok'])
        self.assertIn('música', out['results'][0]['error'])
        self.assertEqual(self.status(a), 'pending')

    def test_already_decided_unknown_duplicates_and_limits(self):
        a = self.clip(10)
        self.app.review_batch(dict(ids=[a], action='reject'))
        out = self.app.review_batch(dict(ids=[a, a, 'nao-existe'], action='reject'))
        self.assertEqual(len(out['results']), 2)             # repetido conta uma vez
        self.assertEqual(out['done'], 0)
        for bad in (dict(ids=[], action='reject'), dict(ids='x', action='reject'), dict(ids=[1], action='reject'),
                    dict(ids=[a], action='apagar'), dict(ids=['x'] * 0 + [str(i) for i in range(51)], action='reject')):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.app.review_batch(bad)

    def test_quota_stops_batch_approval_midway_without_breaking_the_rest(self):
        ids = [self.clip(10 + 40 * i) for i in range(3)]
        original = self.app.license.check_export
        calls = []

        def limited(waiting):
            calls.append(waiting)
            if len(calls) > 1:
                raise ValueError('Cota de clipes do plano atingida.')
            return original(waiting)
        self.app.license.check_export = limited
        out = self.app.review_batch(dict(ids=ids, action='approve'))
        self.assertEqual(out['done'], 1)
        self.assertEqual(out['failed'], 2)
        self.assertTrue(all('Cota' in r['error'] for r in out['results'] if not r['ok']))


if __name__ == '__main__':
    unittest.main()
