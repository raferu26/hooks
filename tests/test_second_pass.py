import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from liveclips import engine as engine_module, media
from liveclips.store import Store, DEFAULT_PROFILE
from liveclips.timeline import build_timeline, plan


def make_session(store, seconds=40):
    streamer = store.create_streamer('CORINGA')
    profile = dict(DEFAULT_PROFILE, min_free_gb=.5, content_mode='video', second_pass='small')
    store.save_profile(streamer, profile)
    sid = store.new_session(streamer, 'TESTE')
    session = store.session(sid)
    f = Path(session['source']) / 'segmento_00000.ts'
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'sine=f=300:duration={seconds}',
                    '-f', 'lavfi', '-i', f'color=c=black:s=320x180:r=15:d={seconds}', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-c:a', 'aac', '-shortest', str(f)], check=True)
    info = media.probe(f)
    st = f.stat()
    words = [dict(start=10 + i * .4, end=10.35 + i * .4, word=w, p=.9) for i, w in enumerate('hoje o Koringa fez uma jogada incrivel mesmo'.split())]
    far = [dict(start=2.0, end=2.4, word='antes', p=.9)]
    segs = [dict(start=2.0, end=2.4, text='antes', words=far), dict(start=10, end=13.5, text='hoje o Koringa fez uma jogada incrivel mesmo', words=words)]
    with store.connect(True) as c:
        c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (sid, 0, str(f.resolve()), media.sha_file(f), info['duration'], info['signature'], st.st_size, st.st_mtime_ns, 'done',
                   json.dumps(dict(segments=segs, signals=dict(audio=[], motion=[], warnings=[])))))
    rows = build_timeline(store.segments(sid))
    parts = plan(rows, 8, 20, rows[0]['group_id'])
    data = dict(start=8, end=20, group_id=rows[0]['group_id'], score=9, reasons=['t'], transcript='x', transcript_segments=segs,
                content_mode='video')
    key, _ = store.propose(sid, data, parts, dict(profile))
    return streamer, sid, key


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kw):
        self.calls.append((path, kw))
        words = [NS(start=2.0 + i * .4, end=2.35 + i * .4, word=' ' + w, probability=p) for i, (w, p) in enumerate(
            [('hoje', .95), ('o', .9), ('Coringa', .4), ('fez', .9), ('uma', .9), ('jogada', .95), ('incrível', .9), ('mesmo', .9)])]
        seg = NS(start=2.0, end=5.3, text=' hoje o Coringa fez uma jogada incrível mesmo', words=words)
        return iter([seg]), NS(language='pt')


class SecondPassTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.streamer, self.sid, self.cid = make_session(self.store)
        self.engine = engine_module.Engine(self.store)
        self.fake = FakeModel()
        self.engine.get_model = lambda profile, name=None: self.fake

    def tearDown(self):
        self.tmp.cleanup()

    def test_serialize_keeps_word_confidence(self):
        seg = NS(start=0, end=1, text=' oi ', words=[NS(start=0, end=.5, word=' oi', probability=.42), NS(start=.5, end=1, word=' lá')])
        out = engine_module.serialize([seg])
        self.assertEqual(out[0]['words'][0]['p'], .42)
        self.assertEqual(out[0]['words'][1]['p'], 1.0)

    def test_second_pass_replaces_only_the_clip_range(self):
        before = self.store.candidate(self.cid)
        self.assertTrue(self.engine.do_refine(self.cid, 'small'))
        after = self.store.candidate(self.cid)
        data = after['data']
        self.assertEqual(data['refine']['status'], 'done')
        self.assertEqual(data['refine']['model'], 'small')
        self.assertGreaterEqual(data['refine']['changed'], 2)
        self.assertEqual(after['version'], before['version'] + 1)
        text = ' '.join(w['word'] for s in data['transcript_segments'] for w in s['words'])
        self.assertIn('Coringa', text)
        self.assertNotIn('Koringa', text)
        self.assertIn('antes', text)  # fala fora do corte permanece
        # os tempos novos voltam para o relógio da sessão (começo do corte = 8 s; áudio extraído a partir de 0)
        inside = [w for s in data['transcript_segments'] for w in s['words'] if w['word'] == 'Coringa'][0]
        self.assertAlmostEqual(inside['start'], 8 + 2.0 + 2 * .4, places=2)
        self.assertLess(inside['p'], .5)
        self.assertEqual(self.fake.calls[0][1]['word_timestamps'], True)
        self.assertFalse(any(Path(self.store.session(self.sid)['path'], 'tmp_legenda').glob('*.wav')))

    def test_failure_is_recorded_and_does_not_break_the_cut(self):
        class Broken:
            def transcribe(self, *a, **k):
                raise RuntimeError('sem modelo')
        self.engine.get_model = lambda profile, name=None: Broken()
        self.assertFalse(self.engine.do_refine(self.cid, 'small'))
        data = self.store.candidate(self.cid)['data']
        self.assertEqual(data['refine']['status'], 'error')
        self.assertIn('Koringa', ' '.join(w['word'] for s in data['transcript_segments'] for w in s['words']))

    def test_off_does_nothing_and_manual_request_defaults_to_small(self):
        profile = dict(self.store.streamer(self.streamer)['profile'], second_pass='off')
        self.store.save_profile(self.streamer, profile)
        self.assertFalse(self.engine.do_refine(self.cid))
        self.engine.queue_refine(self.cid)
        self.assertEqual(self.engine.refine_queue, [(self.cid, 'small')])
        self.assertEqual(self.store.candidate(self.cid)['data']['refine']['status'], 'queued')

    def test_user_edited_caption_lines_survive_the_second_pass(self):
        from liveclips.project import empty
        proj = empty()
        proj['captions']['lines'] = [dict(start=2.0, end=3.0, text='texto meu', words=[])]
        v = self.store.candidate(self.cid)['version']
        self.store.save_project(self.cid, v, proj, queue_preview=False)
        self.engine.do_refine(self.cid, 'small')
        item = self.store.candidate(self.cid)
        self.assertEqual(item['data']['project']['captions']['lines'][0]['text'], 'texto meu')

    def test_invalid_second_pass_model_is_rejected(self):
        profile = dict(self.store.streamer(self.streamer)['profile'], second_pass='gigante')
        with self.assertRaises(ValueError):
            self.store.save_profile(self.streamer, profile)


if __name__ == '__main__':
    unittest.main()


class OllamaRubricTests(unittest.TestCase):
    def setUp(self):
        from liveclips import ollama
        self.ollama = ollama
        ollama._CACHE.clear()

    def test_rubric_weights_and_legacy_score(self):
        o = self.ollama
        good = lambda body: dict(response=json.dumps(dict(gancho=10, autonomia=10, clareza=10, emocao=10, fechamento=10, motivo='ok')))
        r = o.evaluate('texto', model='m', generate=good)
        self.assertIsNotNone(r)
        self.assertEqual(r['nota'] if 'nota' in r else r['score'], 10)
        legacy = o.evaluate('texto', model='m', generate=lambda b: dict(response=json.dumps(dict(nota=6, motivo='x'))))
        self.assertIsNotNone(legacy)
        self.assertIsNone(o.evaluate('x', model='m', generate=lambda b: dict(response=json.dumps(dict(gancho=99, autonomia=1)))))

    def test_temperature_zero_and_cache_only_without_injected_generate(self):
        o = self.ollama
        bodies = []

        def gen(body):
            bodies.append(body)
            return dict(response=json.dumps(dict(nota=7, motivo='x')))
        o.evaluate('texto igual', model='m', generate=gen)
        o.evaluate('texto igual', model='m', generate=gen)
        self.assertEqual(len(bodies), 2)  # injected generate nunca usa cache
        self.assertEqual(bodies[0]['options']['temperature'], 0)
        self.assertEqual(bodies[0]['options']['seed'], 7)

    def test_titles_reject_invented_content(self):
        o = self.ollama
        text = 'o jogador acertou a jogada incrivel no ultimo minuto da partida'
        out = o.titles(text, model='m', generate=lambda b: dict(response=json.dumps(dict(titulos=[
            'Jogada incrível no último minuto', 'Presidente anuncia nova lei de impostos hoje', 'Oi', 'Jogador acertou jogada incrível']))))
        self.assertTrue(out)
        self.assertLessEqual(len(out), 3)
        for t in out:
            self.assertLessEqual(len(t), 44)
            self.assertNotIn('Presidente', t)
        self.assertEqual(o.titles(text, model='m', generate=lambda b: dict(response='lixo')), [])


class ConfidenceTableTests(unittest.TestCase):
    def test_table_reflects_real_approval_by_band(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(Path(tmp.name))
        streamer, sid, cid = make_session(store)
        with store.connect(True) as c:
            row = dict(c.execute('SELECT * FROM candidates WHERE id=?', (cid,)).fetchone())
            data = json.loads(row['data'])
            data['confidence'] = dict(value=.8)
            c.execute("UPDATE candidates SET data=?,manual=1,status='approved' WHERE id=?", (json.dumps(data), cid))
        table = store.confidence_table(streamer)
        self.assertTrue(table)
