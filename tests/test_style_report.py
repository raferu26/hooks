import unittest
from liveclips import learning


def perf(views, likes=0, shares=0):
    return dict(views=views, likes=likes, comments=0, shares=shares, saves=0)


def sample(style, views, likes, moment='humor', hook=5):
    return dict(style=style, moment=moment, hook=hook, perf=perf(views, likes))


class StyleReportTests(unittest.TestCase):
    def test_too_few_clips_gives_no_groups(self):
        r = learning.style_report([sample('clean', 500, 20)])
        self.assertEqual(r['styles'], [])
        self.assertIsNone(r['suggestion'])
        self.assertFalse(r['enough'])

    def test_groups_below_minimum_are_hidden(self):
        s = [sample('funny', 1000, 120)] * 3 + [sample('clean', 400, 10)] * 3 + [sample('hype', 900, 100)]
        r = learning.style_report(s)
        self.assertEqual({x['id'] for x in r['styles']}, {'funny', 'clean'})
        self.assertEqual(r['styles'][0]['id'], 'funny')

    def test_suggestion_requires_volume_and_lift(self):
        few = [sample('funny', 1000, 120)] * 3 + [sample('clean', 400, 10)] * 3
        self.assertIsNone(learning.style_report(few, 'clean')['suggestion'])  # só 6 clipes
        many = [sample('funny', 1000, 120)] * 5 + [sample('clean', 400, 10)] * 5
        r = learning.style_report(many, 'clean')
        self.assertEqual(r['suggestion']['style'], 'funny')
        self.assertGreaterEqual(r['suggestion']['lift'], 1.2)
        self.assertIsNone(learning.style_report(many, 'funny')['suggestion'])  # já usa o melhor

    def test_similar_styles_do_not_trigger_a_suggestion(self):
        same = [sample('funny', 500, 40)] * 5 + [sample('clean', 500, 39)] * 5
        self.assertIsNone(learning.style_report(same, 'clean')['suggestion'])

    def test_low_view_clips_are_ignored_and_hook_bands(self):
        s = [sample('clean', 50, 40)] * 5 + [sample('clean', 800, 80, hook=8)] * 3 + [sample('clean', 300, 5, hook=2)] * 3
        r = learning.style_report(s)
        self.assertEqual(r['total'], 6)
        labels = {x['label'] for x in r['hooks']}
        self.assertEqual(labels, {'gancho forte (7–10)', 'gancho fraco (0–4)'})
        self.assertEqual(r['hooks'][0]['label'], 'gancho forte (7–10)')


if __name__ == '__main__':
    unittest.main()


class AbReport(unittest.TestCase):
    def pair(self, va, la, vb, lb, group='g'):
        return [dict(group=group, label='A', change='x', perf=perf(va, la)), dict(group=group, label='B', change='sem abertura', perf=perf(vb, lb))]

    def test_needs_enough_views_and_a_real_difference(self):
        r = learning.ab_report(self.pair(100, 5, 120, 6))
        self.assertEqual(r['pairs'][0]['verdict'], 'sem dados suficientes')
        r = learning.ab_report(self.pair(1000, 50, 1000, 52))
        self.assertEqual(r['pairs'][0]['verdict'], 'empate técnico')
        r = learning.ab_report(self.pair(1000, 50, 2500, 200))
        self.assertEqual(r['pairs'][0]['winner'], 'B')
        self.assertIn('Um único par', r['note'])

    def test_incomplete_pairs_are_ignored(self):
        self.assertEqual(learning.ab_report([dict(group='g', label='A', change='', perf=perf(900, 10))])['tested'], 0)
