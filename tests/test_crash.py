"""Queda no meio do trabalho: o processo é morto à força (SIGKILL), como numa queda de energia, e o que sobra tem que se recuperar."""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from liveclips import media
from liveclips.app import App
from liveclips.store import DEFAULT_PROFILE
from liveclips.timeline import build_timeline, plan
from liveclips.editing import plan_edits

ROOT = Path(__file__).resolve().parents[1]


def build_env(root, seconds=24):
    """Streamer + sessão de vídeo real (FFmpeg) + um corte aprovado, pronto para exportar."""
    app = App(root, worker=False)
    store = app.store
    streamer = store.create_streamer('QUEDA')
    profile = dict(DEFAULT_PROFILE, min_free_gb=.5, content_mode='video', second_pass='off', threads=2)
    store.save_profile(streamer, profile)
    sid = store.new_session(streamer, 'VIDEO')
    session = store.session(sid)
    file = Path(session['source']) / 'segmento_00000.ts'
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=s=1280x720:r=30:d={seconds}',
                    '-f', 'lavfi', '-i', f'sine=frequency=300:duration={seconds}', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-c:a', 'aac', '-shortest', str(file)], check=True)
    (Path(session['path']) / 'fonte.json').write_text(json.dumps(dict(mode='video', reframe_mode='conservative', url='', title='t', author='q', file=str(file))))
    info = media.probe(file)
    with store.connect(True) as c:
        c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], file.stat().st_size, file.stat().st_mtime_ns, 'done',
                   json.dumps(dict(transcript=[dict(start=2, end=9, text='frase de teste da queda', words=[])], signals={}))))
    rows = build_timeline(store.segments(sid))
    group = rows[0]['group_id']
    data = dict(start=2, end=seconds - 2, group_id=group, score=8, reasons=['teste'], components={}, transcript='frase de teste',
                transcript_segments=[dict(start=2, end=9, text='frase de teste da queda', words=[])])
    data['edit_plan'] = plan_edits(data, {}, transcript=data['transcript_segments'], profile=profile)
    parts = plan(rows, 2, seconds - 2, group)
    store.propose(sid, data, parts, dict(profile))
    item = store.rows('SELECT id,version,start,end FROM candidates')[0]
    store.review(item['id'], item['version'], item['start'], item['end'], parts, 'approve', profile, None, True)
    return app, item['id'], session


CHILD = textwrap.dedent('''
    import sys
    sys.path.insert(0, {root!r})
    from liveclips.app import App
    app = App({data!r}, worker=False)
    print("PRONTO", flush=True)
    app.engine.do_render({cid!r}, False)
''')


class KillDuringExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.data = str(Path(self.temp.name) / 'dados')
        self.app, self.cid, self.session = build_env(self.data)
        self.app.close()
        self.cortes = Path(self.session['path']) / 'cortes'

    def kill_child_mid_render(self):
        code = CHILD.format(root=str(ROOT), data=self.data, cid=self.cid)
        child = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.assertIn('PRONTO', child.stdout.readline())
        deadline = time.time() + 40
        while time.time() < deadline:
            if self.cortes.exists() and any(p.name.startswith('render_') for p in self.cortes.iterdir()):
                time.sleep(1.0)       # deixa o FFmpeg começar a escrever
                break
            time.sleep(.1)
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
        try:
            subprocess.run(['pkill', '-9', '-f', 'ffmpeg.*render_'], check=False)
        except OSError:
            pass

    def test_export_killed_midway_is_recovered_and_finishes(self):
        self.kill_child_mid_render()
        state = sqlite3.connect(Path(self.data) / 'liveclips_v8.sqlite3').execute('SELECT status FROM candidates WHERE id=?', (self.cid,)).fetchone()[0]
        self.assertEqual(state, 'exporting')                                   # ficou preso no meio
        self.assertTrue(any(p.name.startswith('render_') for p in self.cortes.iterdir()))
        app = App(self.data, worker=False); self.addCleanup(app.close)           # nova partida
        self.assertEqual(app.store.candidate(self.cid)['status'], 'approved')    # voltou para a fila
        self.assertEqual([p.name for p in self.cortes.iterdir() if p.name.startswith('render_')], [])   # restos limpos
        self.assertEqual([p for p in self.cortes.iterdir() if p.is_dir()], [])   # nenhum corte "pela metade" visível
        app.engine.do_render(self.cid, False)
        row = app.store.candidate(self.cid)
        self.assertEqual(row['status'], 'done', row.get('error'))
        video = Path(row['export_path'])
        self.assertTrue(video.is_file())
        self.assertGreater(media.probe(video)['duration'], 10)
        self.assertEqual(len([p for p in self.cortes.iterdir() if p.is_dir()]), 1)

    def test_killed_after_the_file_was_finished_does_not_redo_the_work(self):
        app = App(self.data, worker=False); self.addCleanup(app.close)
        app.engine.do_render(self.cid, False)
        first = app.store.candidate(self.cid)
        self.assertEqual(first['status'], 'done')
        # queda depois de renomear a pasta final e antes de gravar "pronto" no banco
        with app.store.connect(True) as c:
            c.execute("UPDATE candidates SET status='exporting',export_path='',error='' WHERE id=?", (self.cid,))
        app.close()
        again = App(self.data, worker=False); self.addCleanup(again.close)
        self.assertEqual(again.store.candidate(self.cid)['status'], 'approved')
        before = (Path(first['export_path']).stat().st_mtime_ns, media.sha_file(first['export_path']))
        again.engine.do_render(self.cid, False)
        row = again.store.candidate(self.cid)
        self.assertEqual(row['status'], 'done', row.get('error'))
        self.assertEqual(row['export_path'], first['export_path'])
        after = (Path(row['export_path']).stat().st_mtime_ns, media.sha_file(row['export_path']))
        self.assertEqual(before, after)                                          # reaproveitou o arquivo pronto, sem recodificar
        self.assertEqual(len([p for p in self.cortes.iterdir() if p.is_dir()]), 1)


HAMMER = textwrap.dedent('''
    import sys, time, json
    sys.path.insert(0, {root!r})
    from liveclips.store import Store
    store = Store({data!r})
    print("PRONTO", flush=True)
    n = 0
    while True:
        store.event("teste", "evento " + str(n))
        store.setting("contador", n)
        n += 1
''')


class KillDuringDatabaseWrites(unittest.TestCase):
    def test_database_stays_consistent_after_sigkill(self):
        with tempfile.TemporaryDirectory() as temp:
            child = subprocess.Popen([sys.executable, '-c', HAMMER.format(root=str(ROOT), data=temp)], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
            self.assertIn('PRONTO', child.stdout.readline())
            time.sleep(1.5)
            os.kill(child.pid, signal.SIGKILL); child.wait()
            db = Path(temp) / 'liveclips_v8.sqlite3'
            conn = sqlite3.connect(db)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            events = conn.execute("SELECT COUNT(*) FROM events WHERE kind='teste'").fetchone()[0]
            conn.close()
            self.assertGreater(events, 10)
            from liveclips.store import Store
            store = Store(temp)                                                   # reabre e continua usável
            store.event('depois', 'ok')
            self.assertEqual(store.setting('contador') is not None, True)


if __name__ == '__main__':
    unittest.main()
