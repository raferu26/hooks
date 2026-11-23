"""Pistas de trabalho: exportar não pode segurar análise nem prévia, e nenhum corte é processado duas vezes."""
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from liveclips.engine import Engine,ModelGate
from liveclips.store import Store
from tests.helpers import candidate,setup_session


def wait_for(cond,timeout=8):
    end=time.time()+timeout
    while time.time()<end:
        if cond():return True
        time.sleep(0.02)
    return cond()


class PistasBase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        disk=patch('liveclips.media.free_bytes',return_value=100*1024**3);disk.start();self.addCleanup(disk.stop)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.a,self.sa,self.pa=setup_session(self.store,'CORINGA','LIVE_A')
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.engine.stop.set()
        for t in self.engine.threads:t.join(5)

    def approved(self,start,end):
        item,_=candidate(self.store,self.sa,start,end)
        self.store.review(item['id'],1,start,end,item['parts'],'approve')
        return item['id']

    def status(self,cid):
        return self.store.candidate(cid)['status']


class GateTests(unittest.TestCase):
    def test_high_priority_goes_before_low_while_the_model_is_busy(self):
        gate=ModelGate();order=[];gate.acquire(True)
        def waiter(name,high):
            gate.acquire(high);order.append(name);gate.release()
        low=threading.Thread(target=waiter,args=('refino',False));low.start();time.sleep(0.2)
        high=threading.Thread(target=waiter,args=('analise',True));high.start();time.sleep(0.2)
        gate.release();low.join(5);high.join(5)
        self.assertEqual(order,['analise','refino'])

    def test_only_one_user_at_a_time(self):
        gate=ModelGate();inside=[];peak=[0]
        def work():
            gate.acquire(True);inside.append(1);peak[0]=max(peak[0],len(inside));time.sleep(0.03);inside.pop();gate.release()
        threads=[threading.Thread(target=work) for _ in range(6)]
        [t.start() for t in threads];[t.join(5) for t in threads]
        self.assertEqual(peak[0],1)


class LaneTests(PistasBase):
    def test_a_long_export_does_not_hold_back_previews_or_analysis(self):
        export_id=self.approved(10,30)
        item,_=candidate(self.store,self.sa,35,50)
        preview_id=item['id']
        with self.store.connect(True) as c:c.execute("UPDATE candidates SET preview_status='queued' WHERE id=?",(preview_id,))
        self.store.setting('paused',False)
        release=threading.Event();seen=[];analysis=[]
        def render(key,preview):
            seen.append((key,preview))
            if not preview:
                release.wait(10)
                with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='done' WHERE id=?",(key,))
            else:
                with self.store.connect(True) as c:c.execute("UPDATE candidates SET preview_status='ready' WHERE id=?",(key,))
        def session_step(blocked):
            analysis.append(time.time());time.sleep(0.05);return False
        with patch.object(self.engine,'do_render',side_effect=render),patch.object(self.engine,'_session_step',side_effect=session_step):
            self.engine.start()
            self.assertTrue(wait_for(lambda:(export_id,False) in seen),'a exportação não começou')
            # a exportação está presa; mesmo assim a prévia sai e a análise continua girando
            self.assertTrue(wait_for(lambda:(preview_id,True) in seen),'a prévia ficou esperando a exportação')
            before=len(analysis)
            self.assertTrue(wait_for(lambda:len(analysis)>before+1),'a análise parou durante a exportação')
            release.set()
            self.assertTrue(wait_for(lambda:self.status(export_id)=='done'))

    def test_state_lists_each_lane_with_its_own_message(self):
        self.engine.start()
        self.assertTrue(wait_for(lambda:{l['lane'] for l in self.engine.state()['lanes']}>={'analise','edicao','exportacao','refino'}))
        labels={l['lane']:l['label'] for l in self.engine.state()['lanes']}
        self.assertEqual(labels['exportacao'],'Exportação')

    def test_every_candidate_is_rendered_exactly_once_even_with_two_export_workers(self):
        self.store.setting('export_workers',2)
        ids=[self.approved(s,s+12) for s in (5,20,35)]
        calls=[];lock=threading.Lock()
        def render(key,preview):
            with lock:calls.append(key)
            time.sleep(0.15)
            with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='done' WHERE id=?",(key,))
        with patch.object(self.engine,'do_render',side_effect=render):
            self.engine.start()
            self.assertTrue(wait_for(lambda:all(self.status(i)=='done' for i in ids)))
        self.assertEqual(sorted(calls),sorted(ids))

    def test_preview_and_export_of_the_same_candidate_never_overlap(self):
        cid=self.approved(10,30)
        with self.store.connect(True) as c:c.execute("UPDATE candidates SET preview_status='queued' WHERE id=?",(cid,))
        active=[];peak=[0];lock=threading.Lock();done=[]
        def render(key,preview):
            with lock:active.append(key);peak[0]=max(peak[0],len(active))
            time.sleep(0.2)
            with lock:active.remove(key)
            with self.store.connect(True) as c:
                if preview:c.execute("UPDATE candidates SET preview_status='ready' WHERE id=?",(key,))
                else:c.execute("UPDATE candidates SET status='done' WHERE id=?",(key,))
            done.append(preview)
        with patch.object(self.engine,'do_render',side_effect=render):
            self.engine.start()
            self.assertTrue(wait_for(lambda:len(done)==2))
        self.assertEqual(peak[0],1)

    def test_single_lane_mode_uses_only_the_main_worker(self):
        self.store.setting('lanes','unico')
        cid=self.approved(10,30);threads=set()
        def render(key,preview):
            threads.add(threading.current_thread().name)
            with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='done' WHERE id=?",(key,))
        with patch.object(self.engine,'do_render',side_effect=render):
            self.engine.start()
            self.assertTrue(wait_for(lambda:self.status(cid)=='done'))
        self.assertEqual(threads,{'LiveClips-principal'})
        self.assertEqual(self.engine.mode(),'unico')

    def test_lane_error_does_not_kill_the_other_lanes(self):
        cid=self.approved(10,30);self.store.setting('paused',False)
        calls=[]
        def boom(blocked):
            calls.append(1);raise RuntimeError('falha de análise simulada')
        def render(key,preview):
            with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='done' WHERE id=?",(key,))
        with patch.object(self.engine,'_session_step',side_effect=boom),patch.object(self.engine,'do_render',side_effect=render):
            self.engine.start()
            self.assertTrue(wait_for(lambda:len(calls)>=1))
            self.assertTrue(wait_for(lambda:self.status(cid)=='done'))

    def test_claim_blocks_second_taker_until_released(self):
        self.assertTrue(self.engine._claim(('c','x')));self.assertFalse(self.engine._claim(('c','x')))
        self.engine._release(('c','x'));self.assertTrue(self.engine._claim(('c','x')))


class CapacityTests(PistasBase):
    def test_capacity_unknown_until_there_are_measurements(self):
        self.assertIsNone(self.engine.capacity()['rtf'])

    def test_capacity_flags_when_the_pc_cannot_keep_up_with_four_lives(self):
        for name in ('ALAN','GAULES','PAULINHO'):setup_session(self.store,name,'LIVE_'+name)
        with self.store.connect(True) as c:c.execute('UPDATE sessions SET closed=0')
        self.engine.rtf.extend([0.4,0.4,0.4])      # 24 s de transcrição por minuto de live
        cap=self.engine.capacity()
        self.assertEqual(cap['lives'],4);self.assertAlmostEqual(cap['needed'],1.6)
        self.assertFalse(cap['ok'])
        self.engine.rtf.clear();self.engine.rtf.extend([0.15,0.15])
        self.assertTrue(self.engine.capacity()['ok'])       # 4 × 0,15 = 0,6


if __name__=='__main__':
    unittest.main()
