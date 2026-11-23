import tempfile
import unittest

from liveclips.app import App
from liveclips.store import REJECT_REASONS
from tests.helpers import setup_session,candidate


class RejectReasonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False);self.addCleanup(self.app.close)
        self.store=self.app.store
        _,self.sid,_=setup_session(self.store,durations=(120,120))

    def clip(self,start,end):
        item,_=candidate(self.store,self.sid,start,end)
        return item

    def review(self,item,action,**extra):
        item=self.store.candidate(item['id'])
        return self.app.review(dict(id=item['id'],version=item['version'],start=item['start'],end=item['end'],action=action,**extra))

    def stats(self):return self.app.state()['sessions'][0]['review']

    def test_reason_is_saved_with_the_rejection_and_cleared_when_reopened(self):
        item=self.clip(10,40)
        self.review(item,'reject',reason='comeco_ruim')
        row=self.store.candidate(item['id'])
        self.assertEqual((row['status'],row['reason']),('rejected','comeco_ruim'))
        self.review(item,'save')    # reabrir sem mudar de decisão mantém o motivo enquanto estiver rejeitado
        self.assertEqual(self.store.candidate(item['id'])['reason'],'comeco_ruim')

    def test_approving_after_rejecting_clears_the_reason(self):
        item=self.clip(10,40)
        self.review(item,'reject',reason='fraco')
        with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='pending' WHERE id=?",(item['id'],))
        self.review(item,'save')
        self.assertEqual(self.store.candidate(item['id'])['reason'],'')

    def test_rejection_without_reason_still_works(self):
        item=self.clip(10,40)
        self.review(item,'reject')
        self.assertEqual(self.store.candidate(item['id'])['status'],'rejected')
        self.assertEqual(self.stats()['reasons'],{})

    def test_unknown_reason_is_refused_and_nothing_changes(self):
        item=self.clip(10,40)
        with self.assertRaises(ValueError):self.review(item,'reject',reason='porque sim')
        self.assertEqual(self.store.candidate(item['id'])['status'],'pending')

    def test_reason_sent_with_other_actions_is_ignored(self):
        item=self.clip(10,40)
        self.review(item,'save',reason='fraco')
        self.assertEqual(self.store.candidate(item['id'])['reason'],'')

    def test_acceptance_rate_per_live(self):
        a=self.clip(10,40);b=self.clip(50,80);c=self.clip(90,118);d=self.clip(125,155)
        self.assertEqual(self.stats()['rate'],None)
        self.review(a,'reject',reason='fraco');self.review(b,'reject',reason='fraco');self.review(c,'reject',reason='repetido')
        with self.store.connect(True) as cx:cx.execute("UPDATE candidates SET status='done' WHERE id=?",(d['id'],))
        stats=self.stats()
        self.assertEqual((stats['accepted'],stats['rejected'],stats['pending']),(1,3,0))
        self.assertEqual(stats['rate'],0.25)
        self.assertEqual(stats['reasons'],{'fraco':2,'repetido':1})

    def test_state_lists_the_reasons_for_the_panel_buttons(self):
        self.assertEqual(self.app.state()['reject_reasons'],REJECT_REASONS)
        self.assertIn('outro',REJECT_REASONS)

    def test_panel_candidate_carries_its_reason(self):
        item=self.clip(10,40);self.review(item,'reject',reason='sensivel')
        shown=next(x for x in self.app.state()['candidates'] if x['id']==item['id'])
        self.assertEqual(shown['reason'],'sensivel')


if __name__=='__main__':unittest.main()
