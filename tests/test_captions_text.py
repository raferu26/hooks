"""Legenda por texto colado (sem IA): distribuição no tempo de fala, toques e avisos. Sinais sintéticos com tempos conhecidos."""
import unittest

import numpy as np

from liveclips import captions_text as C
from liveclips import technical

RATE = technical.RATE


def tone_bursts(bursts, total, level_db=-20, noise_db=-60):
    """Áudio mono sintético: rajadas de 'fala' (ruído de banda larga) nos intervalos dados, silêncio quase total fora."""
    rng = np.random.default_rng(3)
    x = rng.standard_normal(int(total * RATE)).astype(np.float32) * 10 ** (noise_db / 20)
    for a, b in bursts:
        i, j = int(a * RATE), int(b * RATE)
        x[i:j] += rng.standard_normal(j - i).astype(np.float32) * 10 ** (level_db / 20)
    return x


class Phrases(unittest.TestCase):
    def test_user_lines_win_and_long_lines_break_on_words(self):
        p = C.split_phrases('Primeira linha curta\n' + 'palavra ' * 20)
        self.assertEqual(p[0], 'Primeira linha curta')
        self.assertTrue(all(len(x) <= C.MAX_CHARS for x in p))
        self.assertEqual(' '.join(p[1:]).split(), ['palavra'] * 20)        # nenhuma palavra perdida ou cortada

    def test_sentence_punctuation_splits(self):
        self.assertEqual(C.split_phrases('Oi, tudo bem? Sim, tudo ótimo.'), ['Oi, tudo bem?', 'Sim, tudo ótimo.'])

    def test_syllable_estimates_are_reasonable(self):
        self.assertEqual([C.syllables(w) for w in ('a', 'você', 'legenda', 'computador', 'ai')], [1, 2, 3, 4, 1])


class Align(unittest.TestCase):
    def _env(self, bursts, total):
        return technical.envelope_of(tone_bursts(bursts, total))

    def test_phrases_land_on_their_speech_bursts(self):
        bursts = [(1.0, 3.0), (4.5, 6.5), (8.0, 10.0)]
        db, step = self._env(bursts, 11)
        r = C.build('Isso é a primeira frase\nAgora vem a segunda fala\nE esta é a terceira parte', db, step)
        starts = [s['start'] for s in r['segments']]
        for got, (want, _) in zip(starts, bursts):
            self.assertLess(abs(got - want), .35, (starts, bursts))
        self.assertEqual(len(r['segments']), 3)

    def test_text_is_never_changed_or_dropped(self):
        db, step = self._env([(0.5, 5.0)], 6)
        text = 'Nada pode sumir aqui\ne nem mudar de lugar nunca'
        r = C.build(text, db, step)
        self.assertEqual([s['text'] for s in r['segments']], text.split('\n'))
        self.assertEqual(sum(len(s['words']) for s in r['segments']), len(text.split()))

    def test_words_are_ordered_inside_their_phrase(self):
        db, step = self._env([(0.5, 5.0)], 6)
        for s in C.build('uma frase com várias palavras seguidas', db, step)['segments']:
            ws = s['words']
            self.assertTrue(all(a['end'] <= b['start'] + 1e-6 for a, b in zip(ws, ws[1:])))
            self.assertGreaterEqual(ws[0]['start'], s['start'] - 1e-6)

    def test_offset_moves_everything(self):
        db, step = self._env([(1.0, 3.0)], 4)
        a = C.build('uma frase só aqui', db, step, offset=0)['segments'][0]['start']
        b = C.build('uma frase só aqui', db, step, offset=100)['segments'][0]['start']
        self.assertAlmostEqual(b - a, 100, places=2)


class Taps(unittest.TestCase):
    def test_taps_fix_phrase_starts_and_avoid_overlap(self):
        db, step = technical.envelope_of(tone_bursts([(0.5, 9.5)], 10))      # fala contínua: só os toques sabem onde as frases começam
        r = C.build('primeira frase de teste\nsegunda frase de teste\nterceira frase de teste', db, step, taps=[0.6, 3.5, 7.0])
        segs = r['segments']
        self.assertEqual([round(s['start'], 1) for s in segs], [0.6, 3.5, 7.0])
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(segs, segs[1:])))
        self.assertTrue(all(s['timing'] == 'toques' for s in segs))

    def test_fewer_taps_than_phrases_keeps_all_text(self):
        db, step = technical.envelope_of(tone_bursts([(0.5, 9.5)], 10))
        r = C.build('um dois três\nquatro cinco seis\nsete oito nove', db, step, taps=[0.6, 5.0])
        self.assertEqual(sum(len(s['words']) for s in r['segments']), 9)


class Warnings(unittest.TestCase):
    def test_warns_when_text_does_not_fit_the_speech_time(self):
        db, step = technical.envelope_of(tone_bursts([(0.5, 2.0)], 3))
        r = C.build('texto enorme demais ' * 40, db, step)
        self.assertTrue(any('longo demais' in w for w in r['warnings']))

    def test_empty_text_is_rejected_and_srt_is_valid(self):
        db, step = technical.envelope_of(tone_bursts([(0.5, 2.0)], 3))
        with self.assertRaises(ValueError):
            C.build('   \n ', db, step)
        srt = C.build('uma frase', db, step)['srt']
        self.assertRegex(srt, r'1\n\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}\numa frase')


class Parses(unittest.TestCase):
    def test_generated_srt_is_accepted_by_the_importer(self):
        from liveclips import subtitles
        db, step = technical.envelope_of(tone_bursts([(1.0, 3.0), (4.0, 6.0)], 7))
        srt = C.build('primeira frase aqui\nsegunda frase ali', db, step)['srt']
        got = subtitles.parse(srt.encode('utf-8'), 'legenda.srt')
        self.assertEqual([g['text'] for g in got], ['primeira frase aqui', 'segunda frase ali'])


if __name__ == '__main__':
    unittest.main()
