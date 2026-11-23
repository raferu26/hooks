from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

from liveclips import media
from liveclips.capture import Capture,CaptureManager
from liveclips.engine import Engine
from liveclips.store import Store
from tests.helpers import setup_session,candidate


def process():
    result=MagicMock();result.poll.return_value=None;result.returncode=0
    return result


class MultiCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        # Estes testes validam concorrência, não a capacidade do disco real da
        # máquina onde a suíte está rodando.
        disk=patch('liveclips.media.free_bytes',return_value=100*1024**3)
        disk.start();self.addCleanup(disk.stop)
        self.store=Store(self.temp.name);self.manager=CaptureManager(self.store)
        self.streamers=[self.store.create_streamer(name) for name in ('CORINGA','ALAN','GAULES','PAULINHO','STREAMER5')]
        self.addCleanup(self.manager.stop_all)

    def test_five_parallel_starts_have_isolated_sessions_and_stop_one_keeps_others(self):
        processes=[process() for _ in range(10)]
        with patch('liveclips.capture.media.tool',side_effect=lambda n:n), \
             patch('liveclips.capture.subprocess.Popen',side_effect=processes),patch.object(Capture,'monitor'):
            with ThreadPoolExecutor(max_workers=5) as pool:
                sessions=list(pool.map(lambda sid:self.manager.start(sid,'https://example.org/live'),self.streamers))
        self.assertEqual(len(set(sessions)),5);self.assertEqual(len(self.manager.state()),5)
        for sid,streamer in zip(sessions,self.streamers):
            session=self.store.session(sid)
            self.assertEqual(session['streamer'],streamer)
            self.assertIn(self.store.streamer(streamer)['name'],Path(session['path']).parts)
        self.manager.stop(sessions[0])
        self.assertEqual(len(self.manager.state()),4)
        self.assertNotIn(sessions[0],{s['session'] for s in self.manager.state()})
        self.assertTrue(self.store.session(sessions[0])['closed'])
        for sid in sessions[1:]:self.assertFalse(self.store.session(sid)['closed'])
        self.manager.stop_all()
        self.assertEqual(self.manager.state(),[])
        self.assertTrue(all(self.store.session(s)['closed'] for s in sessions))

    def test_duplicate_profile_and_slot_limit_preserve_existing_live(self):
        self.manager.set_limit(1)
        with patch('liveclips.capture.media.tool',side_effect=lambda n:n), \
             patch('liveclips.capture.subprocess.Popen',side_effect=[process(),process()]),patch.object(Capture,'monitor'):
            first=self.manager.start(self.streamers[0],'https://example.org/live')
            with self.assertRaisesRegex(ValueError,'já está'):self.manager.start(self.streamers[0],'https://example.org/live')
            with self.assertRaisesRegex(ValueError,'Limite'):self.manager.start(self.streamers[1],'https://example.org/live')
        self.assertEqual(self.manager.state(),[dict(session=first,streamer=self.streamers[0],chat='indisponível')])
        self.assertFalse(self.store.session(first)['closed'])

    def test_failure_starting_second_live_keeps_first_running(self):
        with patch('liveclips.capture.media.tool',side_effect=lambda n:n), \
             patch('liveclips.capture.subprocess.Popen',side_effect=[process(),process(),OSError('falha isolada')]),patch.object(Capture,'monitor'):
            first=self.manager.start(self.streamers[0],'https://example.org/live')
            with self.assertRaisesRegex(OSError,'isolada'):self.manager.start(self.streamers[1],'https://example.org/live')
        self.assertEqual(len(self.manager.state()),1)
        self.assertEqual(self.manager.state()[0]['session'],first)
        errors=self.store.rows("SELECT * FROM sessions WHERE status='error'")
        self.assertEqual(len(errors),1);self.assertTrue(errors[0]['closed'])

    def test_lowering_limit_cannot_silently_stop_existing_lives(self):
        with patch('liveclips.capture.media.tool',side_effect=lambda n:n), \
             patch('liveclips.capture.subprocess.Popen',side_effect=[process() for _ in range(4)]),patch.object(Capture,'monitor'):
            self.manager.start(self.streamers[0],'https://example.org/live')
            self.manager.start(self.streamers[1],'https://example.org/live')
        with self.assertRaisesRegex(ValueError,'Encerre'):self.manager.set_limit(1)
        self.assertEqual(len(self.manager.state()),2);self.assertEqual(self.manager.limit(),5)

    def test_failed_live_finishes_only_its_own_session_and_releases_slot(self):
        with patch('liveclips.capture.media.tool',side_effect=lambda n:n), \
             patch('liveclips.capture.subprocess.Popen',side_effect=[process() for _ in range(4)]),patch.object(Capture,'monitor'):
            first=self.manager.start(self.streamers[0],'https://example.org/live')
            second=self.manager.start(self.streamers[1],'https://example.org/live')
        failed=self.manager.captures[self.streamers[0]]
        failed.stop('Live caiu',error=True)
        self.assertEqual(self.store.session(first)['status'],'capture_error')
        self.assertIn(first,{row['id'] for row in self.store.rows("SELECT id FROM sessions WHERE enabled=1 AND status!='error'")})
        self.assertEqual(self.manager.state(),[dict(session=second,streamer=self.streamers[1],chat='indisponível')])
        self.assertFalse(self.store.session(second)['closed'])


class FairQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.a,self.sa,self.pa=setup_session(self.store,'CORINGA','LIVE_A')
        self.b,self.sb,self.pb=setup_session(self.store,'ALAN','LIVE_B')

    def test_approved_exports_alternate_streamers(self):
        ids=[]
        for sid,start,end in ((self.sa,0,15),(self.sa,35,50),(self.sb,10,30)):
            item,_=candidate(self.store,sid,start,end)
            self.store.review(item['id'],1,start,end,item['parts'],'approve');ids.append(item['id'])
        seen=[]
        def render(key,preview):
            item=self.store.candidate(key);seen.append(item['streamer'])
            with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='done' WHERE id=?",(key,))
        with patch.object(self.engine,'do_render',side_effect=render):
            for _ in range(3):self.assertTrue(self.engine.work_once())
        self.assertEqual(set(seen[:2]),{self.a,self.b});self.assertEqual(len(seen),3)

    def test_analysis_rotates_sessions(self):
        self.store.setting('paused',False);seen=[]
        with patch.object(self.engine,'scan_one',side_effect=lambda session:seen.append(session['streamer']) or True):
            for _ in range(4):self.engine.work_once()
        self.assertEqual(seen,[self.a,self.b,self.a,self.b])

    def test_low_space_for_one_profile_does_not_block_another_export(self):
        for sid in (self.sa,self.sb):
            item,_=candidate(self.store,sid)
            self.store.review(item['id'],1,10,30,item['parts'],'approve')
        completed=[]
        def render(key,preview):
            item=self.store.candidate(key)
            if item['streamer']==self.a:raise media.LowSpace('reserva alta no perfil A')
            completed.append(key)
        self.engine.task_streamer=self.b
        with patch.object(self.engine,'do_render',side_effect=render):self.assertTrue(self.engine.work_once())
        self.assertEqual(len(completed),1)
        self.assertEqual(self.store.candidate(completed[0])['streamer'],self.b)

    def test_failed_session_does_not_stop_other_streamer_analysis(self):
        self.store.setting('paused',False)
        def scan(session):
            if session['id']==self.sa:raise ValueError('origem A indisponível')
            return True
        with patch.object(self.engine,'scan_one',side_effect=scan):
            self.assertTrue(self.engine.work_once());self.assertTrue(self.engine.work_once())
            # A primeira falha NÃO derruba a sessão: ela entra em espera e a outra segue trabalhando.
            self.assertEqual(self.store.session(self.sa)['status'],'idle')
            self.assertEqual(self.engine.failures[self.sa]['count'],1)
            for _ in range(3):
                self.engine.failures[self.sa]['next_at']=0
                self.engine.turn=0
                self.engine.work_once()
        self.assertEqual(self.store.session(self.sa)['status'],'error')   # só depois das tentativas esgotarem
        self.assertEqual(self.store.session(self.sb)['status'],'idle')

if __name__=='__main__':unittest.main()
