import unittest

from liveclips import caption_track as ct


def seg(words, start=0.0, end=3.0, text=''):
    return dict(start=start, end=end, text=text, words=words)


def w(word, a, b, p=None):
    return dict(word=word, start=a, end=b, p=p)


class AlignmentTests(unittest.TestCase):
    def test_clean_words_are_aligned(self):
        out = ct.words_of(seg([w('olha', 0, .4, .9), w('isso', .5, 1.0, .8)]))
        self.assertEqual(['palavra', 'palavra'], [x['alignment'] for x in out])
        self.assertEqual(.9, out[0]['confidence'])

    def test_bad_timing_falls_back_to_estimated_for_whole_segment(self):
        out = ct.words_of(seg([w('olha', 0, .4), w('isso', .5, .5)]))     # duração zero
        self.assertEqual({'estimado'}, {x['alignment'] for x in out})
        self.assertAlmostEqual(3.0, out[-1]['end'], places=3)
        self.assertLessEqual(out[0]['end'], out[1]['start'] + 1e-6)

    def test_out_of_order_words_are_not_called_aligned(self):
        out = ct.words_of(seg([w('a', 1.0, 1.4), w('b', 0.2, 0.6)]))
        self.assertEqual({'estimado'}, {x['alignment'] for x in out})

    def test_no_words_means_block(self):
        out = ct.words_of(seg([], text='frase inteira'))
        self.assertEqual(1, len(out))
        self.assertEqual('bloco', out[0]['alignment'])
        self.assertEqual([], ct.words_of(seg([], text='  ')))

    def test_summary_warns_when_not_all_aligned(self):
        words = ct.words_of(seg([w('olha', 0, .4)])) + ct.words_of(seg([], text='x'))
        s = ct.summary(words)
        self.assertEqual(1, s['alinhamento']['bloco'])
        self.assertIsNotNone(s['aviso'])
        self.assertIsNone(ct.summary(ct.words_of(seg([w('olha', 0, .4)])))['aviso'])


class DisplayTests(unittest.TestCase):
    def test_vocabulary_corrects_spelling_without_changing_literal_or_adding_words(self):
        words = ct.words_of(seg([w('valorant', 0, .5), w('boa', .6, 1.0)]))
        words, changes = ct.apply_display(words, vocabulary=['Valorant', 'Tiltado'])
        self.assertEqual('Valorant', words[0]['display'])
        self.assertEqual('valorant', words[0]['literal'])
        self.assertEqual(2, len(words))
        self.assertEqual('vocabulario', changes[0]['origem'])

    def test_vocabulary_does_not_invent_from_similar_word(self):
        words = ct.words_of(seg([w('tilt', 0, .5)]))
        words, changes = ct.apply_display(words, vocabulary=['Tiltado'])
        self.assertEqual([], changes)
        self.assertEqual('tilt', words[0]['display'])

    def test_manual_edit_wins_and_is_logged(self):
        words = ct.words_of(seg([w('oi', 0, .5)]))
        words, changes = ct.apply_display(words, manual={0: 'Oi,'})
        self.assertEqual(('Oi,', 'manual'), (words[0]['display'], words[0]['origin']))
        self.assertEqual('oi', words[0]['literal'])


class AnalysisTests(unittest.TestCase):
    def test_reading_speed(self):
        lines = [dict(start=0, end=1, text='x' * 30), dict(start=2, end=4, text='x' * 30)]
        found = ct.reading(lines)
        self.assertEqual(1, len(found))
        self.assertEqual(30.0, found[0]['cps'])

    def test_collisions_with_time_window(self):
        lines = [dict(start=1, end=2, text='a'), dict(start=5, end=6, text='b')]
        regions = [dict(name='rosto', box=(.3, .6, .7, .9), start=0, end=3)]
        hits = ct.collisions(lines, (.1, .7, .9, .85), regions)
        self.assertEqual(1, len(hits))
        self.assertEqual([], ct.collisions(lines, (.1, .1, .9, .2), regions))

    def test_review_document_shape(self):
        doc = ct.review_document([seg([w('valorant', 0, .5, .9)])], vocabulary=['Valorant'])
        self.assertEqual('liveclips.legendas', doc['schema'])
        self.assertEqual('Valorant', doc['segmentos'][0]['words'][0]['display'])
        self.assertIn('valorant', ct.dump(doc))


class MetricTests(unittest.TestCase):
    def test_wer(self):
        self.assertEqual(0.0, ct.wer('Olha isso, cara', 'olha isso cara'))
        self.assertEqual(.25, ct.wer('olha isso aí cara', 'olha isso aí caro'))
        self.assertEqual(1.0, ct.wer('', 'algo'))

    def test_timing_error(self):
        ref = [w('a', 0, .4), w('b', .5, 1.0), w('c', 1.1, 1.5)]
        hyp = [w('a', .05, .45), w('b', .8, 1.3)]
        e = ct.timing_error(ref, hyp)
        self.assertEqual(2, e['pareadas'])
        self.assertEqual(1, e['sem_par'])
        self.assertEqual(.5, e['dentro_de_100ms'])
        self.assertIsNone(ct.timing_error([], [])['mediano_ms'])


if __name__ == '__main__':
    unittest.main()
