import unittest

from liveclips import editing


class Director(unittest.TestCase):
    def signals(self):
        audio = [dict(time=10 + i, strength=3.0 - i * .1) for i in range(6)]
        motion = [dict(time=10 + i, strength=2.0) for i in range(6)]
        return dict(audio=audio, motion=motion, behavior=[])

    def test_plan_carries_director_report(self):
        plan = editing.plan_edits(dict(start=5.0, end=40.0, id='x'), self.signals(), profile=dict(auto_zoom=True, editorial_style='hype'))
        self.assertEqual(plan['director']['preset'], 'hype')
        self.assertEqual(plan['director']['accepted'].get('zoom'), len([d for d in plan['decisions'] if d['kind'] == 'zoom' and d['enabled']]))

    def test_budget_refusals_are_logged_with_cause(self):
        decisions = [editing._decision('zoom', 10 + i * .5, 11 + i * .5, True, 'Áudio e imagem.', 'Zoom', .9 - i * .1, extra={'zoom': 1.06}) for i in range(5)]
        preset = editing.EDITOR_PRESETS['gameplay']
        editing.apply_budget([], decisions, 40, 'gameplay', preset)
        report = editing.director_report(decisions, 'gameplay', editing.EFFECT_BUDGET['gameplay'])
        self.assertTrue(report['refused'])
        self.assertTrue(all(r['cause'] == 'orçamento' and 'orçamento' in r['reason'] for r in report['refused']))
        self.assertEqual(report['accepted']['zoom'] + report['refused_total'], 5)
        self.assertLessEqual(report['accepted']['zoom'], report['budget_per_window'])

    def test_disabled_by_style_is_explained(self):
        plan = editing.plan_edits(dict(start=5.0, end=40.0, id='x'), self.signals(), profile=dict(auto_zoom=True, editorial_style='clean'))
        refused = plan['director']['refused']
        self.assertTrue(refused)
        self.assertTrue(all(r['cause'] == 'configuração' and 'Desligado' in r['reason'] for r in refused))

    def test_protected_pause_shows_as_refusal(self):
        report = editing.director_report([], 'clean', 2, shielded=[dict(id='s1', motivo='protegido: pausa narrativa')])
        self.assertEqual(report['refused'][0]['cause'], 'proteção'); self.assertEqual(report['refused_total'], 1)

    def test_report_does_not_mutate_decisions(self):
        decisions = [dict(kind='zoom', enabled=True, start=1, reason='a'), dict(kind='zoom', enabled=False, budget=True, start=2, reason='b')]
        before = [dict(d) for d in decisions]
        editing.director_report(decisions, 'clean', 2)
        self.assertEqual(decisions, before)


if __name__ == '__main__':
    unittest.main()
