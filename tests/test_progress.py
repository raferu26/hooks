"""Progresso real e cancelamento do render: percentual vindo do FFmpeg, sem retrocesso, 100% só depois de entregue, cancelamento
que encerra o processo e limpa só os temporários da tarefa, nova tentativa com outro identificador."""
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from liveclips import media, progress

from tests.test_exemplo_completo import approve, build, folder_of


def ffmpeg(*args):
    return [media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *args]


class TaskRules(unittest.TestCase):
    def test_percent_never_goes_back_and_hundred_only_on_finish(self):
        task = progress.Task('c1', 'exportacao', 1, 'x')
        task.phase('A', 0, 50)
        task.report(.8)
        task.report(.2)                                   # mais baixo: ignorado
        self.assertEqual(task.percent, 40.0)
        task.phase('B', 5, 95)                            # plano B recomeça a etapa: a barra espera, não volta
        task.report(.1)
        self.assertEqual(task.percent, 40.0)
        task.report(1.0)
        self.assertEqual(task.percent, 95.0)
        task.report(1.0)
        self.assertLess(task.percent, 100.0)
        task.finish('concluido')
        self.assertEqual((task.percent, task.state), (100.0, 'concluido'))

    def test_eta_needs_a_basis(self):
        task = progress.Task('c1', 'exportacao', 1)
        task.phase('A', 0, 100)
        task.report(.02)
        self.assertIsNone(task.eta())                     # pouco trabalho medido
        task.report(.30)
        self.assertIsNone(task.eta())                     # pouco tempo desde a primeira leitura
        task.eta_base = (5.0, time.time() - 20)
        self.assertIsNotNone(task.eta())
        task.phase('Finalizando', 96, 97)                 # etapa sem medida: sem estimativa
        self.assertIsNone(task.eta())

    def test_board_keeps_only_the_latest_run_of_a_candidate(self):
        board = progress.Board()
        old = board.start('c1', 'exportacao')
        new = board.start('c1', 'exportacao')
        self.assertNotEqual(old.id, new.id)
        self.assertEqual([t['task'] for t in board.snapshot()], [new.id])
        self.assertFalse(board.cancel('outro'))
        self.assertTrue(board.cancel('c1'))
        self.assertTrue(new.cancel.is_set() and not old.cancel.is_set())


class FfmpegProgress(unittest.TestCase):
    def test_percent_comes_from_the_encoder(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'a.mp4'
            task = progress.Task('c', 'exportacao', 1)
            task.phase('Codificando', 10, 90)
            seen = []
            real = task.report
            task.report = lambda f: (seen.append(f), real(f))[1]
            with progress.scope(task), progress.expect(20.0):
                media.run(ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=1920x1080:rate=30:duration=20', '-c:v', 'libx264', '-preset', 'slow', str(out)), cwd=temp)
            self.assertTrue(out.is_file())
            self.assertGreaterEqual(len({round(x, 1) for x in seen}), 3, seen)       # várias leituras reais, não um salto
            self.assertEqual(seen, sorted(seen))
            self.assertAlmostEqual(task.percent, 90.0, places=0)
            self.assertTrue(task.determinate)

    def test_cancel_stops_the_process_and_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            task = progress.Task('c', 'exportacao', 1)
            task.phase('Codificando', 0, 100)
            result = {}

            def work():
                try:
                    with progress.scope(task), progress.expect(600.0):
                        media.run(ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=1920x1080:rate=30:duration=600', '-c:v', 'libx264', '-preset', 'slow', str(Path(temp) / 'b.mp4')), cwd=temp)
                except BaseException as exc:
                    result['exc'] = exc
            thread = threading.Thread(target=work)
            thread.start()
            for _ in range(100):
                if task.proc is not None and task.percent > 0:
                    break
                time.sleep(.1)
            pid = task.proc.pid
            started = time.time()
            task.cancel.set()
            progress.terminate(task.proc)
            thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(result.get('exc'), progress.Cancelled)
            self.assertLess(time.time() - started, 8)
            self.assertFalse(subprocess.run(['ps', '-p', str(pid)], capture_output=True).stdout.count(b'ffmpeg'))   # nenhum processo órfão

    def test_ffmpeg_error_keeps_the_message(self):
        task = progress.Task('c', 'exportacao', 1)
        with progress.scope(task), progress.expect(2.0):
            with self.assertRaises(RuntimeError) as ctx:
                media.run(ffmpeg('-i', '/nao/existe.mp4', '/tmp/x.mp4'))
        self.assertIn('nao/existe', str(ctx.exception))


class RealRender(unittest.TestCase):
    """Render real (fonte sintética): estados na ordem, percentual coerente, 100% só com arquivo entregue, cancelar e tentar de novo."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.engine, cls.item = build(cls.temp.name, export_formats=['1x1'])
        approve(cls.store, cls.item)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def poll(self, stop, log):
        while not stop.is_set():
            for snap in self.engine.renders():
                if snap['candidate'] == self.item:
                    status = self.store.candidate(self.item)
                    log.append((snap, status['status'], status.get('export_path')))
            time.sleep(.1)

    def test_a_cancel_cleans_only_its_own_temporaries_then_retry_completes_with_a_new_task(self):
        log, stop = [], threading.Event()
        poller = threading.Thread(target=self.poll, args=(stop, log))
        poller.start()
        worker = threading.Thread(target=self.engine.do_render, args=(self.item, False))
        worker.start()
        for _ in range(300):
            snap = next((s for s in self.engine.renders() if s['candidate'] == self.item), None)
            if snap and snap['percent'] > 3:
                break
            time.sleep(.1)
        self.assertEqual(self.engine.cancel_render(self.item), 'cancelando')
        worker.join(60)
        stop.set()
        poller.join()
        self.assertFalse(worker.is_alive())
        first = next(s for s in self.engine.renders() if s['candidate'] == self.item)
        self.assertEqual(first['state'], 'cancelado')
        self.assertFalse(first['can_cancel'])
        item = self.store.candidate(self.item)
        self.assertEqual(item['status'], 'error')
        self.assertIn('Cancelado', item['error'])
        cuts = Path(self.store.session(item['session'])['path']) / 'cortes'
        self.assertEqual([p.name for p in cuts.iterdir()], [])                        # só o que era da tarefa foi limpo, e sumiu
        self.assertEqual(item['data'].get('edit_plan') is not None, True)               # as escolhas continuam
        # nova tentativa pelo caminho normal da interface
        item = self.store.candidate(self.item)
        self.store.review(self.item, item['version'], item['start'], item['end'], item['parts'] if isinstance(item['parts'], list) else __import__('json').loads(item['parts']), 'retry', editorial_confirmed=True)
        log2, stop2 = [], threading.Event()
        poller = threading.Thread(target=self.poll, args=(stop2, log2))
        poller.start()
        self.engine.do_render(self.item, False)
        stop2.set()
        poller.join()
        done = self.store.candidate(self.item)
        self.assertEqual(done['status'], 'done', done.get('error'))
        last = next(s for s in self.engine.renders() if s['candidate'] == self.item)
        self.assertNotEqual(last['task'], first['task'])                                # execução nova, identificador novo
        self.assertEqual((last['state'], last['percent']), ('concluido', 100.0))
        # coerência do que foi mostrado durante a execução
        percents = [s['percent'] for s, _, _ in log2 if s['task'] == last['task']]
        self.assertEqual(percents, sorted(percents))
        states = []
        for s, _, _ in log2:
            if not states or states[-1] != s['state']:
                states.append(s['state'])
        order = ['preparando', 'processando', 'finalizando', 'concluido']
        self.assertEqual([x for x in order if x in states], [x for x in states if x in order])
        self.assertIn('processando', states)
        for snap, status, export in log2:
            if snap['percent'] >= 100:
                self.assertEqual(status, 'done')                                         # 100% só com o corte pronto...
                self.assertTrue(export and Path(export).exists())                         # ...e o arquivo disponível
            if snap['state'] in ('processando', 'finalizando'):
                self.assertLess(snap['percent'], 100)
        self.assertTrue(any(s['determinate'] and 20 < s['percent'] < 95 for s, _, _ in log2), 'sem leitura real no meio da codificação')
        self.assertTrue((folder_of(done) / 'clipe_1x1.mp4').is_file())                 # a variante também foi gerada e contada


if __name__ == '__main__':
    unittest.main()
