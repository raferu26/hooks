import unittest

from liveclips import judge


def speech(lines, gap=.5):
    """lines: [(texto)] -> transcrição com palavras de 0,35s e pausas de `gap` segundos entre frases."""
    t, segments = 10.0, []
    for text in lines:
        words = []
        start = t
        for w in text.split():
            words.append(dict(start=round(t, 2), end=round(t + .33, 2), word=w))
            t += .35
        segments.append(dict(start=start, end=words[-1]['end'], text=text, words=words))
        t += gap
    return segments


LINES = [
    'Eu estava jogando ontem com o time inteiro.',
    'Então ele simplesmente desapareceu do mapa!',
    'Nunca vi uma coisa tão maluca na minha vida inteira.',
    'Presta atenção porque agora vem a parte mais engraçada de toda a live.',
    'Eu morri de rir e perdi a rodada toda por causa disso.',
    'Foi isso que aconteceu, pronto, acabou a história.',
]


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.t = speech(LINES)
        self.starts = [s['start'] for s in self.t]

    def test_dependent_opening_is_detected_and_pulled_back(self):
        # começa em "Então ele simplesmente desapareceu" (depende da frase anterior)
        scores = judge.edge_scores(self.t, self.starts[1] - .2, self.t[4]['end'] + .3)
        self.assertGreaterEqual(scores['dependency'], 1)
        self.assertTrue(any('continuando' in i for i in scores['issues']))
        cand = dict(start=self.starts[1] - .2, end=self.t[4]['end'] + .3, score=10, transcript='x',
                    components={'reacao_na_fala': 4}, moment_confidence=.6)
        out = judge.refine(cand, self.t, (0, 80), 'short')
        self.assertNotAlmostEqual(out['start'], cand['start'], places=1)
        self.assertEqual(out['edges']['dependency'], 0)
        self.assertTrue(out['refinement']['changed'])

    def test_clean_opening_has_good_edges(self):
        scores = judge.edge_scores(self.t, self.starts[0] - .25, self.t[5]['end'] + .35)
        self.assertGreater(scores['open'], 4)
        self.assertGreater(scores['close'], 8)
        self.assertEqual(scores['issues'], [])

    def test_cut_in_the_middle_of_a_sentence_is_fixed(self):
        mid = self.t[3]['words'][5]['end']
        cand = dict(start=self.starts[2] - .25, end=mid, score=10, transcript='x', components={},
                    moment_confidence=.5)
        before = judge.edge_scores(self.t, cand['start'], cand['end'])
        self.assertTrue(before['flags']['mid_end'])
        out = judge.refine(cand, self.t, (0, 80), 'short')
        after = judge.edge_scores(self.t, out['start'], out['end'])
        self.assertFalse(after['flags']['mid_end'])
        self.assertGreaterEqual(out['end'], self.t[3]['end'])

    def test_dangling_end_is_penalised(self):
        t = speech(['Eu fui até a loja comprar pão e', 'Depois voltei para casa.'], gap=1.2)
        scores = judge.edge_scores(t, t[0]['start'] - .2, t[0]['end'] + .1)
        self.assertTrue(scores['flags']['dangling'])
        self.assertLess(scores['close'], 8)

    def test_limits_and_session_bounds_are_respected(self):
        cand = dict(start=self.starts[0] - .25, end=self.t[5]['end'] + .35, score=10, transcript='x',
                    components={}, moment_confidence=.5)
        out = judge.refine(cand, self.t, (self.starts[0] - .25, self.t[5]['end'] + .35), 'short')
        self.assertGreaterEqual(out['start'], self.starts[0] - .25 - 1e-6)
        self.assertLessEqual(out['end'], self.t[5]['end'] + .35 + 1e-6)
        self.assertGreaterEqual(out['end'] - out['start'], 12)

    def test_without_word_timing_candidate_is_untouched(self):
        plain_t = [dict(start=10, end=20, text='sem palavras temporizadas aqui'), ]
        cand = dict(start=9, end=30, score=5, transcript='x', components={})
        out = judge.refine(cand, plain_t, (0, 60), 'short')
        self.assertEqual((out['start'], out['end']), (9, 30))
        self.assertFalse(out['refinement']['known'])

    def test_learned_offsets_move_the_bounds_only_when_reliable(self):
        self.t = speech(['Hoje vou mostrar uma jogada muito difícil de fazer.', 'Primeiro eu espero o inimigo chegar bem perto de mim.',
                         'Depois eu viro a câmera rápido para o lado errado.', 'Aí ele cai direto na minha armadilha preparada.',
                         'Olha só que coisa linda que aconteceu agora mesmo!', 'Eu não acredito que isso funcionou de verdade, caramba.'])
        cand = dict(start=self.starts[0] - .25, end=self.t[5]['end'] + .35, score=10, transcript='x',
                    components={}, moment_confidence=.5)
        free = (0, 200)
        plain_out = judge.refine(cand, self.t, free, 'short')
        unreliable = judge.refine(cand, self.t, free, 'short', habits=dict(start_offset=2, end_offset=0, offset_reliable=False))
        self.assertEqual(plain_out['start'], unreliable['start'])
        reliable = judge.refine(cand, self.t, free, 'short', habits=dict(start_offset=3.3, end_offset=0, offset_reliable=True))
        self.assertGreater(reliable['start'], plain_out['start'])
        self.assertTrue(any('aprendida' in n for n in reliable['refinement']['notes']))

    def test_diversify_removes_near_duplicates_by_time_and_text(self):
        a = dict(start=10, end=40, score=9, transcript='o jogador desapareceu do mapa completamente')
        b = dict(start=12, end=41, score=8.8, transcript='o jogador desapareceu do mapa completamente')
        c = dict(start=100, end=130, score=7, transcript='outra conversa totalmente diferente sobre carros')
        d = dict(start=200, end=230, score=6, transcript='o jogador desapareceu do mapa completamente de novo')
        out = judge.diversify([a, b, c, d], 4)
        self.assertEqual([x['start'] for x in out], [10, 100])

    def test_confidence_tiers_and_abstention_order(self):
        strong = dict(start=10, end=40, score=20, transcript='forte aqui', moment_confidence=.9,
                      components={'reacao_na_fala': 5, 'humor_na_fala': 4, 'crescendo_audio': 2.5,
                                  'coincidencia_audio_webcam': 4, 'preparacao_e_desfecho': 5},
                      narrative=dict(historia_completa=8), edges=dict(open=9, close=9, known=True))
        weak = dict(start=100, end=130, score=3, transcript='fraco aqui', moment_confidence=.3, components={},
                    narrative=dict(historia_completa=2), edges=dict(open=3, close=3, known=True), fallback=True)
        a = judge.confidence(strong, margin=.8)
        b = judge.confidence(weak, margin=0)
        self.assertEqual(a['tier'], 'alta')
        self.assertEqual(b['tier'], 'baixa')
        self.assertTrue(b['reasons'])

    def test_calibration_blends_with_real_approval_rate(self):
        table = [dict(low=.66, high=1.01, rate=.2, n=12), dict(low=0, high=.45, rate=.9, n=3)]
        self.assertAlmostEqual(judge.calibrate(.8, table), .5, places=2)
        self.assertEqual(judge.calibrate(.2, table), .2)

    def test_curate_puts_low_confidence_last(self):
        good = dict(start=self.starts[0] - .25, end=self.t[5]['end'] + .35, score=12, transcript='x',
                    components={'reacao_na_fala': 5, 'humor_na_fala': 4, 'crescendo_audio': 2, 'coincidencia_audio_webcam': 4},
                    moment_confidence=.9, narrative=dict(historia_completa=8))
        out = judge.curate([good], self.t, (0, 80), limit=4)
        self.assertEqual(len(out), 1)
        self.assertIn('confidence', out[0])
        self.assertIn(out[0]['confidence']['tier'], ('alta', 'média', 'baixa'))


if __name__ == '__main__':
    unittest.main()
