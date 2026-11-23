import unittest

from liveclips import perception as pc


def seg(a, b, text='fala', words=None):
    return dict(start=a, end=b, text=text, words=words or [])


class ObservationTests(unittest.TestCase):
    def test_emotion_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            pc.observation('comportamento_observavel', 1, 1, 'rosto', .5, detail=dict(sinal='felicidade 80%'))
        with self.assertRaises(ValueError):
            pc.observation('humor', 1, 1, 'x', .5)

    def test_confidence_clamped_and_fact_flag(self):
        o = pc.observation('pausa', 1, 2, 'transcricao', 4)
        self.assertEqual(1.0, o['confidence'])
        self.assertTrue(o['fact'])

    def test_small_face_lowers_confidence_and_freezes_layout(self):
        self.assertEqual((.28, True), pc.face_confidence(.7, 30))
        self.assertEqual((.7, False), pc.face_confidence(.7, 120))
        self.assertEqual((.28, True), pc.face_confidence(.7, None))


class FromSignalsTests(unittest.TestCase):
    def test_speech_pause_audio_and_coverage(self):
        words = [dict(start=1.0, end=1.4), dict(start=3.0, end=3.4)]
        obs = pc.from_signals(dict(audio=[dict(time=3.6, strength=2.5)]), [seg(1, 3.5, words=words)], 0, 10)
        kinds = [o['kind'] for o in obs]
        self.assertIn('fala', kinds)
        self.assertIn('pausa', kinds)
        self.assertIn('energia_sonora', kinds)

    def test_nothing_inferred_outside_analysed_window(self):
        sig = dict(motion=[dict(time=50, strength=3, kind='rajada')], behavior=[dict(time=60, strength=2, cue='boca_aberta')], behavior_ok=True)
        obs = pc.from_signals(sig, [], 0, 100, analysed_until=20)
        visual = [o for o in obs if o['kind'] == 'evento_visual'][0]
        self.assertEqual(0.0, visual['coverage'])
        behavior = [o for o in obs if o['kind'] == 'comportamento_observavel'][0]
        self.assertEqual(.2, behavior['coverage'])

    def test_behavior_without_validated_model_has_low_quality(self):
        obs = pc.from_signals(dict(behavior=[dict(time=2, strength=2, cue='boca_aberta')], behavior_ok=False), [], 0, 10)
        self.assertEqual('baixa', obs[0]['quality'])


class AttentionTests(unittest.TestCase):
    def kinds(self, obs):
        return [p['kind'] for p in pc.attention_points(obs)]

    def test_silent_reaction(self):
        beh = pc.observation('comportamento_observavel', 5, 5, 'rosto_geometria', .6)
        self.assertEqual(['reacao_silenciosa'], self.kinds([beh]))
        talk = pc.observation('fala', 4.5, 6, 'transcricao', .8)
        self.assertEqual([], self.kinds([beh, talk]))

    def test_play_without_reaction(self):
        ev = pc.observation('evento_visual', 8, 8, 'quadro', .7)
        self.assertEqual(['jogada_sem_reacao'], self.kinds([ev]))

    def test_loud_sound_without_event_is_a_counterexample(self):
        loud = pc.observation('energia_sonora', 2, 2, 'audio', .9, quality='alta')
        point = pc.attention_points([loud])[0]
        self.assertEqual('som_alto_sem_evento', point['kind'])
        self.assertTrue(point['contraexemplo'])
        ev = pc.observation('evento_visual', 3, 3, 'quadro', .7)
        self.assertNotIn('som_alto_sem_evento', self.kinds([loud, ev]))

    def test_comic_setup_pause(self):
        obs = [pc.observation('fala', 0, 3, 'transcricao', .8), pc.observation('pausa', 3, 4.5, 'transcricao', .7), pc.observation('fala', 4.5, 6, 'transcricao', .8)]
        self.assertIn('preparacao_comica', self.kinds(obs))

    def test_all_points_are_hypotheses_and_report_lists_limits(self):
        beh = pc.observation('comportamento_observavel', 5, 5, 'rosto_geometria', .6)
        points = pc.attention_points([beh])
        self.assertTrue(all(p['hipotese'] for p in points))
        r = pc.report([beh], points)
        self.assertTrue(r['limites'])
        self.assertEqual({'comportamento_observavel': 1}, r['observacoes'])


if __name__ == '__main__':
    unittest.main()
