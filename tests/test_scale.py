"""Live longa: 8 h de gravação (480 segmentos de 1 min) + centenas de cortes não podem deixar o painel lento ou pesado."""
import hashlib
import json
import random
import sqlite3
import tempfile
import time
import unittest

from liveclips.app import App
from liveclips.store import DEFAULT_PROFILE, uid


class LongLive(unittest.TestCase):
    def test_panel_stays_light_with_eight_hours_and_many_clips(self):
        with tempfile.TemporaryDirectory() as temp:
            app = App(temp, worker=False); self.addCleanup(app.close)
            store = app.store
            streamer = store.create_streamer('LONGA')
            words = 'nossa mano olha isso que foi isso cara nao acredito gente vamos la'.split()
            random.seed(7)
            sid = uid()
            path = f'{temp}/s'
            with store.connect(True) as c:
                c.execute('INSERT INTO sessions(id,streamer,name,source,path,closed,created) VALUES(?,?,?,?,?,?,?)',
                          (sid, streamer, 'live', path + '/source', path, 1, time.time()))
                for q in range(480):
                    segs = [dict(start=i * 3.0, end=i * 3.0 + 3, text=' '.join(random.choices(words, k=8)), words=[]) for i in range(20)]
                    c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                              (sid, q, f'{path}/{q}.ts', hashlib.sha1(str(q).encode()).hexdigest(), 60.0, json.dumps(['ts', 1920, 1080, 30]), 1, 1, 'done',
                               json.dumps(dict(segments=segs, signals=dict(audio=[0.1] * 60, motion=[0.1] * 60, warnings=[])))))
                for k in range(600):
                    data = dict(start=k * 40, end=k * 40 + 30, score=random.random() * 10, reasons=['a'], transcript=' '.join(random.choices(words, k=60)),
                                components={}, intelligence=dict(extra='y' * 3000))
                    parts = [dict(path='p', sha='s', seq=k % 480, **{'in': 0, 'out': 30}, global_start=0, global_end=60, group_id='g')]
                    c.execute('INSERT INTO candidates(id,session,streamer,start,end,group_id,score,status,data,parts,profile,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                              (uid(), sid, streamer, k * 40, k * 40 + 30, 'g', data['score'], random.choice(['pending', 'rejected', 'done']),
                               json.dumps(data), json.dumps(parts), json.dumps(DEFAULT_PROFILE), time.time()))
            app.state()                                  # aquece
            times = []
            for _ in range(20):
                t = time.time(); state = app.state(); times.append(time.time() - t)
            self.assertLess(sorted(times)[10], 1.0)      # mediana (folga larga: medi ~0,05 s)
            self.assertLess(len(json.dumps(state)), 3_000_000)
            self.assertLessEqual(len(state['candidates']), 500)
            self.assertEqual(sqlite3.connect(store.db).execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
