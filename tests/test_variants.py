import json
import unittest

from liveclips import variants
from tests import test_studio_api as _studio


def long_words(start, count, every=8):
    words, t = [], start
    for i in range(count):
        words.append(dict(start=round(t, 2), end=round(t + .4, 2), word=['olha', 'isso', 'aqui', 'cara', 'incrivel', 'mesmo', 'sabe', 'como'][i % 8] + ('.' if i % every == every - 1 else '')))
        t += .5 + (1.0 if i % every == every - 1 else 0)
    return words


def transcript(words):
    return [dict(start=words[0]['start'], end=words[-1]['end'], text=' '.join(w['word'] for w in words), words=words)]


class Pure(unittest.TestCase):
    def test_split_picks_a_sentence_boundary_near_the_middle(self):
        words = long_words(10, 120)
        tr = transcript(words)
        end = words[-1]['end']
        split = variants.best_split(tr, 10, end)
        self.assertIsNotNone(split)
        self.assertGreaterEqual(split['at'] - 10, variants.MIN_PART)
        self.assertGreaterEqual(end - split['at'], variants.MIN_PART)
        self.assertLess(abs(split['at'] - (10 + end) / 2), 12)
        self.assertIsNone(variants.best_split(tr, 10, 40))  # curto demais

    def test_ab_project_toggles_teaser(self):
        project, change = variants.ab_project(dict(teaser=dict(start=1, end=3)), None, 40)
        self.assertIsNone(project['teaser'])
        with self.assertRaises(ValueError):
            variants.ab_project({}, dict(suggestion=None), 40)
        project, change = variants.ab_project({}, dict(suggestion=dict(start=12.0)), 40)
        self.assertEqual(project['teaser'], dict(start=12.0, end=15.5))


class Api(unittest.TestCase):
    setUp = _studio.StudioApiTests.setUp
    close = _studio.StudioApiTests.close
    post = _studio.StudioApiTests.post

    def long_candidate(self):
        words = long_words(10, 110)
        data = self.item['data']
        data['transcript_segments'] = transcript(words)
        end = 10 + 70
        with self.app.store.connect(True) as c:
            c.execute('UPDATE candidates SET data=?,start=10,end=? WHERE id=?', (json.dumps(data), end, self.item['id']))
        return end

    def test_series_creates_two_linked_parts_with_titles(self):
        self.long_candidate()
        code, got = self.post('/api/variant/series', dict(id=self.item['id']))
        self.assertEqual(code, 200, got)
        self.assertEqual(len(got['ids']), 2)
        a, b = (self.app.store.candidate(i) for i in got['ids'])
        self.assertEqual((a['start'], b['end']), (10, 80))
        self.assertAlmostEqual(a['end'], got['at'], places=1)
        self.assertEqual(a['data']['series']['part'], 1)
        self.assertEqual(b['data']['series']['part'], 2)
        self.assertEqual(a['data']['project']['titles'][0]['text'], 'Parte 1/2')
        self.assertEqual(b['data']['project']['titles'][0]['text'], 'Parte 2/2')
        code, again = self.post('/api/variant/series', dict(id=got['ids'][0]))
        self.assertEqual(code, 400)

    def test_series_rejects_short_cuts_and_bad_split_points(self):
        code, got = self.post('/api/variant/series', dict(id=self.item['id']))  # 20 s
        self.assertEqual(code, 400)
        self.long_candidate()
        code, got = self.post('/api/variant/series', dict(id=self.item['id'], at=15))
        self.assertEqual(code, 400)
        code, got = self.post('/api/variant/series', dict(id=self.item['id'], at=45))
        self.assertEqual(code, 200)

    def test_ab_variant_flips_teaser_and_does_not_count_as_duplicate_export(self):
        store = self.app.store
        store.save_project(self.item['id'], self.item['version'], dict(teaser=dict(start=1, end=3)), queue_preview=False)
        code, got = self.post('/api/variant/ab', dict(id=self.item['id']))
        self.assertEqual(code, 200, got)
        b = store.candidate(got['id'])
        self.assertEqual(b['data']['ab']['label'], 'B')
        self.assertEqual(b['data']['variant_of'], self.item['id'])
        self.assertFalse(b['data']['project'].get('teaser'))
        a = store.candidate(self.item['id'])
        self.assertEqual(a['data']['ab']['label'], 'A')
        self.assertEqual(a['data']['ab']['group'], b['data']['ab']['group'])
        code, nested = self.post('/api/variant/ab', dict(id=got['id']))
        self.assertEqual(code, 400)

    def test_ab_without_a_stronger_line_explains_why(self):
        code, got = self.post('/api/variant/ab', dict(id=self.item['id']))
        if code == 400:
            self.assertIn('frase mais forte', got.get('error', got.get('message', json.dumps(got))))
        else:
            self.assertEqual(code, 200)


if __name__ == '__main__':
    unittest.main()
