import unittest

from liveclips import editing, safety
from tests.test_judge import speech


def words_of(lines, gap=.5):
    return speech(lines, gap)


class SafetyTests(unittest.TestCase):
    def test_removing_a_negation_is_blocked(self):
        t = words_of(['Eu nao quero ir la hoje.'])
        w = t[0]['words'][1]
        issues = safety.check_cut(safety._word_rows(t, 0, 60), w['start'] - .01, w['end'] + .01)
        self.assertEqual(safety.verdict(issues), 'bloqueado')
        self.assertTrue(any(i['kind'] == 'remove_negacao' for i in issues))

    def test_numbers_are_protected(self):
        t = words_of(['Foram 300 pessoas na sala.'])
        w = t[0]['words'][1]
        issues = safety.check_cut(safety._word_rows(t, 0, 60), w['start'], w['end'])
        self.assertTrue(any(i['kind'] == 'remove_numero' for i in issues))

    def test_cut_through_a_word_is_flagged(self):
        t = words_of(['Isso foi absolutamente incrivel mesmo.'])
        w = t[0]['words'][2]
        mid = (w['start'] + w['end']) / 2
        issues = safety.check_cut(safety._word_rows(t, 0, 60), mid - .1, w['end'] + .5)
        self.assertTrue(any(i['kind'] == 'palavra_cortada' for i in issues))

    def test_silence_between_words_and_filler_repetition_are_safe(self):
        t = words_of(['Eu fui ate la.', 'Depois voltei para casa.'], gap=2.0)
        a = t[0]['end'] + .2
        b = t[1]['start'] - .2
        self.assertEqual(safety.check_cut(safety._word_rows(t, 0, 80), a, b), [])
        r = words_of(['Entao entao voce viu aquilo.'])
        w = r[0]['words'][0]
        self.assertEqual(safety.verdict(safety.check_cut(safety._word_rows(r, 0, 60), w['start'] - .04, w['end'] + .04)), 'ok')

    def test_manual_cut_warnings_for_the_editor(self):
        t = words_of(['Eu nunca disse isso para ninguem aqui.'])
        w = t[0]['words'][1]
        out = safety.analyze_cuts(t, 10.0, 20.0, [dict(start=w['start'] - 10, end=w['end'] - 10)])
        self.assertEqual(out[0]['level'], 'bloqueado')
        self.assertIn('negação', out[0]['messages'][0])

    def test_filter_decisions_blocks_and_marks_only_cut_kinds(self):
        t = words_of(['Eu nao quero ir la hoje.'])
        w = t[0]['words'][1]
        decisions = [dict(id='silence:1', kind='silence', start=w['start'] - 10, end=w['end'] - 10, enabled=True,
                          reason='Pausa.', confidence=.9),
                     dict(id='zoom:1', kind='zoom', start=0, end=1, enabled=True, reason='z', confidence=.8)]
        out = safety.filter_decisions(decisions, t, 10.0, 20.0)
        self.assertFalse(out[0]['enabled'])
        self.assertEqual(out[0]['safety'], 'bloqueado')
        self.assertTrue(out[1]['enabled'])
        self.assertNotIn('safety', out[1])


class BudgetTests(unittest.TestCase):
    def decisions(self, n, step=1.0, zoom=1.06):
        items, punches = [], []
        for i in range(n):
            d = dict(id=f'zoom:{i}', kind='zoom', start=i * step, end=i * step + .8, enabled=True, reason='ok',
                     confidence=.9 - i * .01, zoom=zoom)
            items.append(d)
            punches.append(dict(start=d['start'], end=d['end'], zoom=zoom, decision_id=d['id']))
        return punches, items

    def test_budget_limits_effects_per_window(self):
        preset = editing.EDITOR_PRESETS['clean']
        punches, items = self.decisions(6)
        _, out = editing.apply_budget(punches, items, 30, 'clean', preset)
        on = [d for d in out if d['enabled']]
        self.assertLessEqual(len(on), 2)
        off = [d for d in out if not d['enabled']]
        self.assertTrue(all(d.get('budget') and 'orçamento' in d['reason'] for d in off))

    def test_cinematic_is_more_restrained_than_hype(self):
        for name, expected in (('cinematic', 1), ('hype', 3)):
            punches, items = self.decisions(6, step=.9)
            _, out = editing.apply_budget(punches, items, 30, name, editing.EDITOR_PRESETS[name])
            self.assertEqual(len([d for d in out if d['enabled']]), expected)

    def test_effects_in_different_windows_are_all_kept(self):
        punches, items = self.decisions(3, step=12)
        _, out = editing.apply_budget(punches, items, 40, 'clean', editing.EDITOR_PRESETS['clean'])
        self.assertEqual(len([d for d in out if d['enabled']]), 3)

    def test_habit_of_deleting_zooms_reduces_budget(self):
        punches, items = self.decisions(6, step=.9)
        _, out = editing.apply_budget(punches, items, 30, 'hype', editing.EDITOR_PRESETS['hype'],
                                      habits=dict(effect_factor=dict(zoom=.5)))
        self.assertEqual(len([d for d in out if d['enabled']]), 2)

    def test_consecutive_zooms_get_varied_strength(self):
        punches, items = self.decisions(3, step=12)
        out_p, out = editing.apply_budget(punches, items, 40, 'hype', editing.EDITOR_PRESETS['hype'])
        values = [d['zoom'] for d in sorted(out, key=lambda d: d['start'])]
        self.assertTrue(all(abs(a - b) >= .008 for a, b in zip(values, values[1:])))
        self.assertEqual([p['zoom'] for p in out_p], values)
        self.assertTrue(all(v <= editing.EDITOR_PRESETS['hype']['zoom_max'] + .021 for v in values))

    def test_plan_edits_blocks_silence_that_hides_a_negation(self):
        t = []
        words = []
        times = [(10.0, 10.3, 'Eu'), (10.4, 10.7, 'nao'), (12.9, 13.2, 'quero'), (13.3, 13.6, 'ir')]
        for a, b, w in times:
            words.append(dict(start=a, end=b, word=w))
        t.append(dict(start=10, end=13.6, text='Eu nao quero ir', words=words))
        cand = dict(start=9.0, end=20.0, profile={})
        plan = editing.plan_edits(cand, {}, transcript=t, profile=dict(editorial_style='podcast', auto_silence=True))
        sil = [d for d in plan['decisions'] if d['kind'] == 'silence']
        self.assertTrue(sil)
        self.assertTrue(all(d.get('safety') == 'ok' for d in sil))


if __name__ == '__main__':
    unittest.main()
