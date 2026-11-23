import unittest

from liveclips import editing
from liveclips.store import DEFAULT_PROFILE


def sil(a, b, **k):
    return dict(start=a, end=b, method='teste', confiavel=True, **k)


class AudioSilences(unittest.TestCase):
    def run_policy(self, items, policy='pausas_longas', spans=(), start=100.0, end=140.0, enabled=True):
        return editing._audio_silences(items, start, end, policy, enabled, spans)

    def test_long_silence_keeps_a_residual_pause(self):
        out = self.run_policy([sil(110, 113)])
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]['end'] - out[0]['start'], 3 - .55, places=2)
        self.assertAlmostEqual(out[0]['start'], 10.275, places=2)
        self.assertTrue(out[0]['enabled'])

    def test_short_silence_and_clip_edges_are_left_alone(self):
        self.assertEqual(self.run_policy([sil(110, 111)]), [])                  # < 1,5 s no padrão
        self.assertEqual(self.run_policy([sil(100.2, 103)]), [])                # colado no começo do corte
        self.assertEqual(self.run_policy([sil(137, 139.8)]), [])                # colado no fim

    def test_protected_span_blocks_the_cut(self):
        self.assertEqual(self.run_policy([sil(110, 114)], spans=[(113.0, 116.0)]), [])
        self.assertEqual(len(self.run_policy([sil(110, 114)], spans=[(130.0, 133.0)])), 1)

    def test_unreliable_measure_is_off_and_asks_review(self):
        out = self.run_policy([dict(sil(110, 114), confiavel=False)])
        self.assertFalse(out[0]['enabled'])
        self.assertTrue(out[0]['requires_review'])

    def test_policies_differ(self):
        item = [sil(110, 111.2)]
        self.assertEqual(self.run_policy(item, 'pausas_longas'), [])
        self.assertEqual(len(self.run_policy(item, 'dinamica')), 1)
        edge = [sil(100.1, 102.0)]
        self.assertEqual(len(self.run_policy(edge, 'bordas')), 1)               # 'bordas' mexe só no começo/fim do corte
        self.assertEqual(self.run_policy([sil(115, 119)], 'bordas'), [])        # e nunca no meio

    def test_disabled_profile_keeps_decisions_visible_but_off(self):
        out = self.run_policy([sil(110, 113)], enabled=False)
        self.assertFalse(out[0]['enabled'])

    def test_plan_edits_uses_measured_silence_without_transcript_and_cuts_apply(self):
        cand = dict(start=100.0, end=140.0, score=5, reasons=['x'], transcript='', group_id='g', protected=[[120.0, 126.0]])
        signals = dict(audio=[], motion=[], facial=[], behavior=[], chat=[], warnings=[],
                       technical=dict(silence=[sil(108, 112), sil(121, 125)], black=[], freeze=[]))
        plan = editing.plan_edits(cand, signals, transcript=[], profile=dict(DEFAULT_PROFILE), habits=None)
        kinds = [(d['kind'], round(d['start'], 1)) for d in plan['decisions']]
        self.assertEqual(kinds, [('silence', 8.3)])       # o silêncio dentro do trecho protegido ficou de fora
        item = dict(cand, data=dict(edit_plan=plan))
        cuts = editing.cuts_for(item)
        self.assertEqual(len(cuts), 1)
        kept = editing.keep_intervals(40.0, cuts)
        self.assertEqual(len(kept), 2)

    def test_transcript_path_is_unchanged(self):
        cand = dict(start=100.0, end=140.0, score=5, reasons=['x'], transcript='', group_id='g')
        signals = dict(audio=[], motion=[], facial=[], behavior=[], chat=[], warnings=[],
                       technical=dict(silence=[sil(108, 112)], black=[], freeze=[]))
        words = [dict(start=100.5, end=101.0, text='a', words=[dict(word='a', start=100.5, end=101.0)])]
        plan = editing.plan_edits(cand, signals, transcript=words, profile=dict(DEFAULT_PROFILE), habits=None)
        self.assertFalse(any(d.get('origin') == 'medida_de_audio' for d in plan['decisions']))


if __name__ == '__main__':
    unittest.main()
