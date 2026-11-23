import unittest

from liveclips import evalkit as ev


def case(i, streamer='s1', session='x1', family='reacao_forte'):
    return dict(id=f'c{i}', family=family, streamer=streamer, session=session, source='f.mp4', context='ctx', important_regions=['rosto'],
                defects_that_matter=['fala_truncada'], authorized=True, transcript_reviewed=True)


def rate(case_id, evaluator, overall, dims=None, why='o corte preservou a piada'):
    return dict(case=case_id, evaluator=evaluator, overall=overall, dims=dims or {}, justification=why if overall != 'empate' else '')


class CaseTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        self.assertEqual([], ev.validate_case(case(1)))
        bad = dict(case(1), authorized=False, transcript_reviewed=False, family='x')
        self.assertEqual(3, len(ev.validate_case(bad)))
        self.assertIn('falta context', ev.validate_case(dict(case(1), context='')))

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(1.0, sum(ev.DIMENSIONS.values()))


class SplitTests(unittest.TestCase):
    def test_no_session_in_both_sides(self):
        cases = [case(i, streamer=f's{i % 4}', session=f'x{i % 8}') for i in range(40)]
        dev, test = ev.split(cases)
        self.assertTrue(dev and test)
        self.assertFalse(ev.leakage(dev, test)['vazou'])
        self.assertEqual(40, len(dev) + len(test))

    def test_leakage_detected(self):
        a, b = [case(1)], [case(2)]
        self.assertTrue(ev.leakage(a, b)['vazou'])

    def test_deterministic(self):
        cases = [case(i, session=f'x{i}') for i in range(10)]
        self.assertEqual(ev.split(cases, seed=3), ev.split(cases, seed=3))


class BlindTests(unittest.TestCase):
    def test_balanced_and_reproducible(self):
        ids = [f'c{i}' for i in range(20)]
        a = ev.blind_pairs(ids, seed=5)
        self.assertEqual(a, ev.blind_pairs(ids, seed=5))
        shown = list(a['chave_A'].values())
        self.assertEqual(10, shown.count('baseline'))
        self.assertEqual(set(ids), set(a['ordem']))


class RatingTests(unittest.TestCase):
    def test_preference_requires_justification(self):
        self.assertFalse(ev.valid_rating(dict(case='c1', evaluator='e', overall='A', justification='')))
        self.assertTrue(ev.valid_rating(dict(case='c1', evaluator='e', overall='empate')))
        self.assertFalse(ev.valid_rating(dict(case='c1', evaluator='e', overall='A', justification='porque sim, melhor', dims={'cor': 'A'})))

    def test_kappa(self):
        self.assertEqual(1.0, ev.kappa([('a', 'a'), ('b', 'b'), ('a', 'a'), ('b', 'b')]))
        self.assertLess(ev.kappa([('a', 'b'), ('b', 'a'), ('a', 'b'), ('b', 'a')]), 0)
        self.assertIsNone(ev.kappa([]))


class EvaluateTests(unittest.TestCase):
    def setup(self, n, favor):
        cases = [case(i) for i in range(n)]
        key = ev.blind_pairs([c['id'] for c in cases])['chave_A']
        ratings = []
        for c in cases:
            a_is = key[c['id']]
            pick = 'A' if (a_is == 'candidata') == favor else 'B'      # escolhe a candidata (favor) ou a baseline
            for e in ('e1', 'e2'):
                ratings.append(rate(c['id'], e, pick, dims={d: pick for d in ev.DIMENSIONS}))
        return cases, key, ratings

    def test_clear_win_keeps(self):
        cases, key, ratings = self.setup(60, True)
        r = ev.evaluate(ratings, key, cases)
        self.assertEqual('manter', r['decisao'])
        self.assertEqual(1.0, r['concordancia']['concordancia'])
        self.assertAlmostEqual(1.0, r['vantagem_ponderada'])

    def test_clear_loss_rolls_back(self):
        cases, key, ratings = self.setup(60, False)
        self.assertEqual('recuar', ev.evaluate(ratings, key, cases)['decisao'])

    def test_small_sample_is_inconclusive_even_if_unanimous(self):
        cases, key, ratings = self.setup(10, True)
        r = ev.evaluate(ratings, key, cases)
        self.assertEqual('inconclusivo', r['decisao'])
        self.assertIn('insuficiente', r['motivos'][0])

    def test_all_ties_inconclusive(self):
        cases = [case(i) for i in range(60)]
        key = ev.blind_pairs([c['id'] for c in cases])['chave_A']
        ratings = [rate(c['id'], e, 'empate') for c in cases for e in ('e1', 'e2')]
        r = ev.evaluate(ratings, key, cases)
        self.assertEqual('inconclusivo', r['decisao'])
        self.assertEqual(0.0, r['vantagem_ponderada'])

    def test_critical_failure_on_candidate_overrides_average(self):
        cases, key, ratings = self.setup(60, True)
        r = ev.evaluate(ratings, key, cases, critical={'c3': 'candidata'})
        self.assertEqual('recuar', r['decisao'])

    def test_invalid_ratings_are_discarded_and_counted(self):
        cases, key, ratings = self.setup(60, True)
        ratings.append(dict(case='c1', evaluator='e3', overall='A', justification=''))
        r = ev.evaluate(ratings, key, cases)
        self.assertEqual(1, r['notas_descartadas'])

    def test_never_declares_professional(self):
        cases, key, ratings = self.setup(60, True)
        r = ev.evaluate(ratings, key, cases)
        self.assertNotIn('profissional', str(r['decisao']).lower())
        self.assertTrue(any('VMAF' in x for x in r['limites']))

    def test_family_breakdown_and_ablation_and_digest(self):
        cases, key, ratings = self.setup(60, True)
        self.assertIn('reacao_forte', ev.evaluate(ratings, key, cases)['por_familia'])
        plan = ev.ablation_plan(['punch_in', 'sfx'])
        self.assertEqual(['tudo', 'sem_punch_in', 'sem_sfx'], [p['id'] for p in plan])
        self.assertEqual(ev.report_digest('0.13', cases, ratings), ev.report_digest('0.13', cases, list(reversed(ratings))))


if __name__ == '__main__':
    unittest.main()
