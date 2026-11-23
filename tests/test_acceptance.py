import datetime
import tempfile
import unittest

from liveclips.store import Store
from tests.helpers import setup_session, candidate


def stamp(y, m, d):
    return datetime.datetime(y, m, d, 12).timestamp()


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.streamer, self.sid, _ = setup_session(self.store)
        self.base, _ = candidate(self.store, self.sid)
        with self.store.connect(True) as c:
            c.execute('UPDATE candidates SET created=0 WHERE id=?', (self.base['id'],))

    def add(self, status, when, n=1):
        with self.store.connect(True) as c:
            for _ in range(n):
                self.count = getattr(self, 'count', 0) + 1
                c.execute("INSERT INTO candidates(id,session,streamer,start,end,group_id,score,status,data,parts,profile,created) "
                          "SELECT ?,session,streamer,start,end,group_id,score,?,data,parts,profile,? FROM candidates WHERE id=?",
                          (f'x{self.count}', status, when, self.base['id']))

    def test_rate_per_week_ignores_pending_and_empty_weeks(self):
        self.add('done', stamp(2026, 11, 2), 3)       # semana de 02/11
        self.add('rejected', stamp(2026, 11, 4), 1)
        self.add('pending', stamp(2026, 11, 5), 5)    # não decidido: fora
        self.add('approved', stamp(2026, 11, 18), 1)  # semana de 16/11
        result = self.store.acceptance_history(self.streamer, weeks=8, now=stamp(2026, 11, 22))
        weeks = {w['week']: w for w in result['weeks']}
        self.assertEqual(sorted(weeks), ['2026-11-02', '2026-11-16'])
        self.assertEqual((weeks['2026-11-02']['approved'], weeks['2026-11-02']['rejected']), (3, 1))
        self.assertEqual(weeks['2026-11-02']['rate'], 0.75)
        self.assertEqual(weeks['2026-11-16']['rate'], 1.0)
        self.assertEqual((result['approved'], result['decided']), (4, 5))
        self.assertEqual(result['rate'], 0.8)

    def test_old_weeks_are_left_out_and_empty_history_has_no_rate(self):
        self.add('done', stamp(2026, 1, 5), 2)
        result = self.store.acceptance_history(self.streamer, weeks=4, now=stamp(2026, 11, 22))
        self.assertEqual(result['weeks'], [])
        self.assertIsNone(result['rate'])

    def test_other_streamers_do_not_leak(self):
        self.add('done', stamp(2026, 11, 18), 2)
        other = self.store.create_streamer('Outro')
        self.assertEqual(self.store.acceptance_history(other, now=stamp(2026, 11, 22))['decided'], 0)


if __name__ == '__main__':
    unittest.main()
