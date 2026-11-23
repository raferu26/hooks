"""Aprendizado por desempenho, pacote de publicação, avaliador local e escolha de processador da transcrição."""
import json
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from liveclips import engine, learning, ollama, publish
from liveclips.app import App, server
from tests.helpers import candidate, setup_session


def perf(views, likes=0, comments=0, shares=0, saves=0):
    return dict(views=views, likes=likes, comments=comments, shares=shares, saves=saves)


class LearningTests(unittest.TestCase):
    def test_clean_rejects_inconsistent_numbers(self):
        with self.assertRaises(ValueError):
            learning.clean(dict(views=0))
        with self.assertRaises(ValueError):
            learning.clean(dict(views=100, likes=1000))
        with self.assertRaises(ValueError):
            learning.clean(dict(views=100, watch_pct=140))
        self.assertEqual(learning.clean(dict(views='1500', likes='90', watch_pct='41.26'))['watch_pct'], 41.3)

    def test_needs_enough_clips_before_learning(self):
        samples = [(dict(humor_na_fala=1), perf(1000, 80)) for _ in range(3)]
        self.assertEqual(learning.weights(samples), {})
        self.assertEqual(learning.summary(samples)['needed'], 1)

    def test_component_that_performs_better_gets_a_higher_weight_within_limits(self):
        good = [(dict(humor_na_fala=1.0, opiniao_na_fala=0), perf(5000, 600, 60, 90, 120)) for _ in range(4)]
        bad = [(dict(humor_na_fala=0, opiniao_na_fala=1.0), perf(400, 12, 1, 0, 1)) for _ in range(4)]
        weights = learning.weights(good + bad)
        self.assertGreater(weights['humor_na_fala'], 1.05)
        self.assertLess(weights['opiniao_na_fala'], .95)
        for value in weights.values():
            self.assertTrue(.8 <= value <= 1.25)

    def test_one_viral_post_does_not_dominate(self):
        samples = [(dict(a=1), perf(1_000_000, 90000, 9000, 9000, 9000))] + [(dict(b=1), perf(1000, 60)) for _ in range(5)]
        weights = learning.weights(samples)
        self.assertTrue(all(.8 <= v <= 1.25 for v in weights.values()))

    def test_clips_below_minimum_views_are_ignored(self):
        samples = [(dict(a=1), perf(20, 20)) for _ in range(8)]
        self.assertEqual(learning.weights(samples), {})

    def test_merge_stays_inside_the_ranking_limits(self):
        merged = learning.merge(dict(a=1.3, b=.75), dict(a=1.25, b=.8, c=1.1))
        self.assertEqual(merged['a'], 1.3)
        self.assertEqual(merged['b'], .75)
        self.assertEqual(merged['c'], 1.1)


class PublishTests(unittest.TestCase):
    def test_package_has_caption_hashtags_credits_and_music_warning(self):
        words = [dict(start=1 + i * .4, end=1.3 + i * .4, word=w) for i, w in enumerate(
            'Gente olha essa partida incrivel, essa partida foi insana demais'.split())]
        transcript = [dict(start=1, end=5.6, text='Gente olha essa partida incrivel, essa partida foi insana demais', words=words)]
        cand = dict(start=0, end=20, profile=dict(hashtags='fyp #games', credit_note='Clipe com autorização do canal'),
                    data=dict(transcript_segments=transcript, project=dict(titles=[dict(text='Partida insana')]),
                              editorial_audit=dict(source=dict(author='Canal X', title='Live de sábado', url='https://exemplo.com/v'))))
        text = publish.build(cand, [dict(kind='music', title='Som Livre', uploader='Autor', url='https://x.y/m')], ['1x1'])
        self.assertIn('Partida insana', text)
        self.assertIn('#fyp', text)
        self.assertIn('#games', text)
        self.assertIn('#partida', text)
        self.assertIn('Canal X', text)
        self.assertIn('Som Livre', text)
        self.assertIn('silenciar', text)
        self.assertIn('clipe_1x1.mp4', text)


class OllamaTests(unittest.TestCase):
    def test_only_local_addresses_are_accepted(self):
        self.assertEqual(ollama.checked_url(''), 'http://127.0.0.1:11434')
        self.assertEqual(ollama.checked_url('http://localhost:11434/'), 'http://localhost:11434')
        for bad in ('http://192.168.0.5:11434', 'https://exemplo.com', 'http://127.0.0.1.evil.com'):
            with self.assertRaises(ValueError):
                ollama.checked_url(bad)

    def candidates(self):
        return [dict(score=10.0, transcript='um', reasons=[]), dict(score=9.5, transcript='dois', reasons=[])]

    def test_rerank_is_off_by_default_and_only_moves_scores_by_ten_percent(self):
        base = self.candidates()
        self.assertEqual(ollama.rerank(base, dict(ollama=False)), base)
        notes = {'um': 2, 'dois': 9}

        def generate(body):
            text = body['prompt'].split('Transcrição:\n')[1]
            return dict(response=json.dumps(dict(nota=notes[text], motivo='gancho forte')))
        result = ollama.rerank(base, dict(ollama=True, ollama_model='qwen', editorial_style='funny'), generate)
        self.assertEqual([c['transcript'] for c in result], ['dois', 'um'])
        self.assertTrue(all(.89 <= c['score'] / o['score'] <= 1.11 for c, o in zip(
            sorted(result, key=lambda c: c['transcript'], reverse=True), base)))
        self.assertIn('modelo local', result[0]['reasons'][-1])

    def test_failures_keep_the_normal_ranking(self):
        def broken(body):
            raise OSError('sem conexão')
        base = self.candidates()
        result = ollama.rerank(base, dict(ollama=True, ollama_model='qwen'), broken)
        self.assertEqual([c['score'] for c in result], [10.0, 9.5])
        self.assertIsNone(ollama.evaluate('x', model='m', generate=lambda body: dict(response='não é json')))
        self.assertIsNone(ollama.evaluate('x', model='m', generate=lambda body: dict(response=json.dumps(dict(nota=99)))))

    def test_prompt_never_sends_more_than_the_text_limit(self):
        prompt = ollama.prompt_for('a' * 10000, 'clean')
        self.assertEqual(prompt.split('Transcrição:\n')[1], 'a' * ollama.MAX_TEXT)
        self.assertLessEqual(len(prompt), ollama.MAX_TEXT + 700)


class WhisperPlanTests(unittest.TestCase):
    def test_auto_uses_gpu_only_when_one_exists(self):
        self.assertEqual(engine.whisper_plan(dict(whisper_device='auto'), devices=1), ('cuda', 'float16'))
        self.assertEqual(engine.whisper_plan(dict(whisper_device='auto'), devices=0), ('cpu', 'int8'))
        self.assertEqual(engine.whisper_plan(dict(whisper_device='cpu'), devices=2), ('cpu', 'int8'))
        self.assertEqual(engine.whisper_plan(dict(), devices=0), ('cpu', 'int8'))


class PerformanceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name, worker=False)
        self.http = server(self.app, 0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.base = 'http://127.0.0.1:' + str(self.http.server_port)
        self.streamer, self.sid, _ = setup_session(self.app.store)
        self.item, _ = candidate(self.app.store, self.sid)

    def close(self):
        self.http.shutdown(); self.http.server_close(); self.app.close(); self.thread.join(2)

    def post(self, path, data):
        try:
            with urlopen(Request(self.base + path, json.dumps(data).encode(), headers={'X-LiveClips-Token': self.app.token}), timeout=20) as res:
                return res.status, json.loads(res.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_performance_requires_an_approved_clip_and_is_stored_without_changing_the_version(self):
        code, body = self.post('/api/performance/save', dict(id=self.item['id'], views=1200, likes=90))
        self.assertEqual(code, 400)
        with self.app.store.connect(True) as c:
            c.execute("UPDATE candidates SET status='done' WHERE id=?", (self.item['id'],))
        before = self.app.store.candidate(self.item['id'])['version']
        code, body = self.post('/api/performance/save', dict(id=self.item['id'], views=1200, likes=90, saves=30))
        self.assertEqual(code, 200)
        row = self.app.store.candidate(self.item['id'])
        self.assertEqual(row['version'], before)
        self.assertEqual(row['data']['performance']['views'], 1200)
        self.assertEqual(body['summary']['recorded'], 1)
        self.assertEqual(body['summary']['needed'], 3)
        code, bad = self.post('/api/performance/save', dict(id=self.item['id'], views=100, likes=900))
        self.assertEqual(code, 400)

    def test_performance_feeds_the_ranking_preferences(self):
        samples = [(dict(humor_na_fala=1.0), perf(4000, 400, 40, 60, 80)) for _ in range(4)] + \
                  [(dict(jogada_na_fala=1.0), perf(300, 6)) for _ in range(4)]
        weights = learning.merge({}, learning.weights(samples))
        self.assertGreater(weights['humor_na_fala'], weights['jogada_na_fala'])

    def test_profile_accepts_new_settings_and_rejects_remote_ollama(self):
        profile = dict(self.app.store.streamer(self.streamer)['profile'])
        code, _ = self.post('/api/profile', dict(streamer=self.streamer, profile=dict(profile, video_encoder='nvenc', whisper_device='cuda',
                                                                                         model='medium', hashtags='#fyp', ollama=True, ollama_model='qwen2.5')))
        self.assertEqual(code, 200)
        code, body = self.post('/api/profile', dict(streamer=self.streamer, profile=dict(profile, ollama_url='http://10.0.0.7:11434')))
        self.assertEqual(code, 400)
        code, body = self.post('/api/profile', dict(streamer=self.streamer, profile=dict(profile, video_encoder='xyz')))
        self.assertEqual(code, 400)

    def test_system_check_reports_without_crashing_when_nothing_is_installed(self):
        code, body = self.post('/api/system/check', dict())
        self.assertEqual(code, 200)
        self.assertIn('encoders', body)
        self.assertIn('ollama', body)


if __name__ == '__main__':
    unittest.main()
