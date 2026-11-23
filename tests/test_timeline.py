import copy
import json
import tempfile
import unittest

from liveclips.engine import Engine
from liveclips.store import Store
from liveclips.timeline import build_timeline,contexts,plan,shifted_transcript,expand_context
from tests.helpers import setup_session


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.streamer,self.sid,self.profile=setup_session(self.store)
        self.timeline=build_timeline(self.store.segments(self.sid))

    def test_actual_durations_and_cross_file_plan(self):
        parts=plan(self.timeline,58,70,self.timeline[0]['group_id'])
        self.assertEqual(len(parts),2)
        self.assertAlmostEqual(parts[0]['out'],62.4)
        self.assertAlmostEqual(parts[1]['out'],7.6)
        self.assertAlmostEqual(sum(p['out']-p['in'] for p in parts),12)

    def test_missing_file_is_discontinuity(self):
        rows=copy.deepcopy(self.timeline);rows[1]['seq']=2
        rows=build_timeline(rows)
        self.assertTrue(rows[1]['discontinuity'])
        with self.assertRaisesRegex(ValueError,'continuidade|lacuna'):plan(rows,58,70,rows[0]['group_id'])

    def test_codec_change_is_not_silently_joined(self):
        rows=copy.deepcopy(self.timeline);rows[1]['signature']='other-resolution'
        rows=build_timeline(rows)
        with self.assertRaises(ValueError):plan(rows,58,70)

    def test_tail_waits_next_until_session_is_closed(self):
        one=self.timeline[:1]
        self.assertEqual(list(contexts(one,False)),[])
        self.assertEqual(len(list(contexts(one,True))),1)

    def test_unanalyzed_next_is_not_used_as_context(self):
        rows=copy.deepcopy(self.timeline);rows[1]['status']='new'
        self.assertEqual(list(contexts(rows,False)),[])

    def test_words_shift_by_real_offset_without_mutation(self):
        rows=copy.deepcopy(self.timeline)
        rows[1]['data']['segments']=[{'start':1,'end':3,'text':'meu deus',
            'words':[{'start':1,'end':2,'word':'meu'},{'start':2,'end':3,'word':'deus'}]}]
        original=copy.deepcopy(rows)
        shifted=shifted_transcript(rows)
        self.assertAlmostEqual(shifted[0]['words'][0]['start'],63.4)
        self.assertEqual(rows,original)

    def test_interval_cannot_read_unavailable_future(self):
        with self.assertRaises(ValueError):plan(self.timeline,110,140)

    def test_last_closed_segment_is_suggested(self):
        with self.store.connect(True) as c:
            data={'segments':[{'start':45,'end':58,'text':'meu deus nao acredito ganhamos essa jogada olha isso agora'}],
                  'signals':{'audio':[],'motion':[],'warnings':[]}}
            c.execute('UPDATE segments SET data=? WHERE session=? AND seq=1',(json.dumps(data),self.sid))
        engine=Engine(self.store)
        for _ in range(5):engine.suggest_one(self.store.session(self.sid),self.profile)
        proposals=self.store.rows('SELECT * FROM candidates WHERE session=?',(self.sid,))
        self.assertTrue(any(r['start']>62.4 for r in proposals))

    def test_reaction_across_boundary_produces_two_file_candidate(self):
        values=[{'start':53,'end':62,'text':'olha isso meu deus que jogada estamos quase ganhando agora'},
                {'start':0,'end':14,'text':'nao acredito ganhamos essa jogada impossivel que momento caraca'}]
        with self.store.connect(True) as c:
            for i,seg in enumerate(values):
                data={'segments':[seg],'signals':{'audio':[],'motion':[],'warnings':[]}}
                c.execute('UPDATE segments SET data=? WHERE session=? AND seq=?',(json.dumps(data),self.sid,i))
        engine=Engine(self.store)
        for _ in range(5):engine.suggest_one(self.store.session(self.sid),self.profile)
        candidates=[self.store.decode(r) for r in self.store.rows('SELECT * FROM candidates WHERE session=?',(self.sid,))]
        crossing=[r for r in candidates if r['start']<62.4<r['end']]
        self.assertTrue(crossing)
        self.assertEqual(len(crossing[0]['parts']),2)
        before=len(candidates)
        for _ in range(3):engine.suggest_one(self.store.session(self.sid),self.profile)
        self.assertEqual(len(self.store.rows('SELECT * FROM candidates')),before)


if __name__=='__main__':unittest.main()
