import json
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from liveclips.app import App,server
from tests.helpers import setup_session,candidate


class StateSpeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False);self.addCleanup(self.app.close)

    def session(self,state,sid):return next(s for s in state['sessions'] if s['id']==sid)

    def test_closed_session_numbers_follow_the_segments_even_when_cached(self):
        _,sid,_=setup_session(self.app.store,durations=(60,60,60))
        first=self.session(self.app.state(),sid)
        self.assertEqual((first['registered'],first['analyzed'],first['duration'],first['breaks']),(3,3,180,0))
        self.assertIn(sid,self.app._facts)
        with self.app.store.connect(True) as c:c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=2",(sid,))
        second=self.session(self.app.state(),sid)
        self.assertEqual((second['analyzed'],second['analyzed_until'],second['completed']),(2,120,False))
        with self.app.store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) '
                      "SELECT session,9,path,'x',30,signature,size,mtime,'done',data FROM segments WHERE session=? AND seq=0",(sid,))
        third=self.session(self.app.state(),sid)
        self.assertEqual((third['registered'],third['breaks']),(4,1))

    def test_open_session_is_never_cached(self):
        _,sid,_=setup_session(self.app.store)
        with self.app.store.connect(True) as c:c.execute('UPDATE sessions SET closed=0 WHERE id=?',(sid,))
        self.session(self.app.state(),sid)
        self.assertNotIn(sid,self.app._facts)

    def test_deleted_session_leaves_the_cache(self):
        _,sid,_=setup_session(self.app.store)
        self.app.state();self.assertIn(sid,self.app._facts)
        with self.app.store.connect(True) as c:
            c.execute('DELETE FROM segments WHERE session=?',(sid,));c.execute('DELETE FROM sessions WHERE id=?',(sid,))
        self.app.state();self.assertNotIn(sid,self.app._facts)

    def test_panel_list_is_identical_with_and_without_sqlite_json(self):
        _,sid,profile=setup_session(self.app.store)
        item,_=candidate(self.app.store,sid)
        data=item['data'];data.update(transcript_segments=[dict(start=1,end=2,text='a')],profile=profile,handoff={'a':1},
                                      intelligence=dict(dimensoes=dict(estado='tenso'),pesado='x'*500))
        with self.app.store.connect(True) as c:c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),item['id']))
        fast=self.app.store.panel_candidates()
        self.app.store.has_json=False
        slow=self.app.store.panel_candidates()
        self.assertEqual(fast,slow)
        self.assertEqual(fast[0]['data']['estado_contexto'],'tenso')
        for key in ('parts','profile'):self.assertNotIn(key,fast[0])
        for key in ('transcript_segments','profile','handoff','intelligence'):self.assertNotIn(key,fast[0]['data'])

    def test_performance_queries_only_load_clips_with_results(self):
        streamer,sid,_=setup_session(self.app.store)
        item,_=candidate(self.app.store,sid)
        with self.app.store.connect(True) as c:c.execute("UPDATE candidates SET status='done' WHERE id=?",(item['id'],))
        self.assertEqual(self.app.store.performance_samples(streamer),[])
        data=item['data'];data['performance']=dict(views=100)
        with self.app.store.connect(True) as c:c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),item['id']))
        self.assertEqual(len(self.app.store.performance_samples(streamer)),1)


class DuplicateLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False);self.addCleanup(self.app.close);self.store=self.app.store

    def propose(self,sid,start,end,**extra):
        from liveclips.timeline import build_timeline,plan
        rows=build_timeline(self.store.segments(sid))
        group=next(r['group_id'] for r in rows if r['start']<=start<r['end'])
        data=dict(start=start,end=end,group_id=group,score=5,reasons=['t'],transcript=extra.pop('transcript','fala unica '+str(start)),**extra)
        profile=self.store.streamer(self.store.session(sid)['streamer'])['profile']
        return self.store.propose(sid,data,plan(rows,start,end,group),profile)

    def test_overlap_in_same_recording_is_found_and_distant_moment_is_not(self):
        _,sid,_=setup_session(self.store,durations=(120,120))
        first,created=self.propose(sid,10,40)
        self.assertTrue(created)
        self.assertEqual(self.propose(sid,12,38),(first,False))
        self.assertTrue(self.propose(sid,150,180)[1])

    def test_same_recoded_moment_in_other_session_is_found_by_fingerprint(self):
        streamer,one,_=setup_session(self.store,durations=(120,),session_name='A')
        _,two,_=setup_session(self.store,durations=(120,),session_name='B',numbers=[0])
        words='um dois tres quatro cinco seis sete oito nove dez onze'
        first,_=self.propose(one,10,40,visual_fingerprint='0123456789abcdef',transcript=words)
        row=self.store.rows('SELECT fingerprint FROM candidates WHERE id=?',(first,))[0]
        self.assertEqual(row['fingerprint'],'0123456789abcdef')
        near,created=self.propose(two,10,40,visual_fingerprint='0123456789abcdee',transcript=words)
        self.assertEqual((near,created),(first,False))
        far,created=self.propose(two,60,90,visual_fingerprint='fedcba9876543210',transcript=words)
        self.assertTrue(created)

    def test_old_database_gets_the_new_column_and_keeps_its_candidates(self):
        import sqlite3
        _,sid,_=setup_session(self.store)
        item,_=self.propose(sid,10,40,visual_fingerprint='0123456789abcdef')
        self.app.close()
        db=self.store.db
        old=sqlite3.connect(db)
        try:
            with old:
                old.execute('DROP INDEX candidates_streamer');old.execute('DROP INDEX candidates_session')
                old.execute('ALTER TABLE candidates DROP COLUMN fingerprint')
        finally:old.close()
        from liveclips.store import Store
        reopened=Store(self.temp.name)
        row=reopened.rows('SELECT fingerprint FROM candidates WHERE id=?',(item,))[0]
        self.assertEqual(row['fingerprint'],'0123456789abcdef')
        reopened.rows('SELECT 1')


class StateTagTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False)
        self.http=server(self.app,0)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close);self.base='http://127.0.0.1:'+str(self.http.server_port)

    def close(self):
        self.http.shutdown();self.http.server_close();self.app.close();self.thread.join(2)

    def get(self,tag=None):
        headers={'X-LiveClips-Token':self.app.token}
        if tag:headers['X-State-Tag']=tag
        with urlopen(Request(self.base+'/api/state',headers=headers),timeout=10) as res:return json.loads(res.read()),res.headers

    def test_unchanged_state_is_a_tiny_answer_and_a_change_brings_it_back(self):
        full,headers=self.get();tag=headers['X-State-Tag']
        self.assertIn('sessions',full)
        small,_=self.get(tag)
        self.assertEqual(small,dict(unchanged=True,tag=tag))
        self.app.store.create_streamer('NOVO')
        again,headers=self.get(tag)
        self.assertIn('streamers',again);self.assertNotEqual(headers['X-State-Tag'],tag)


if __name__=='__main__':unittest.main()
