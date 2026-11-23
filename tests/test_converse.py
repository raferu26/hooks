import unittest

from liveclips import converse, project as projectlib


def conv(duration=40):
    return converse.Conversation(projectlib.empty(), duration)


class InterpretTests(unittest.TestCase):
    def one(self, text, duration=40):
        return converse.interpret(text, duration)

    def test_cut_range(self):
        c = self.one('corta de 8 a 11')['changes'][0]
        self.assertEqual(('cortar', 8, 11), (c['op'], c['args']['start'], c['args']['end']))

    def test_time_formats(self):
        self.assertEqual(65.0, converse.seconds('1:05'))
        c = self.one('remove do 1:05 ao 1:10 segundos')['changes'][0]
        self.assertEqual((65.0, 70.0), (c['args']['start'], c['args']['end']))

    def test_cut_without_range_asks(self):
        r = self.one('corta isso aí')
        self.assertEqual([], r['changes'])
        self.assertIn('Qual trecho cortar', r['questions'][0])

    def test_big_cut_is_destructive(self):
        self.assertTrue(self.one('corta de 5 a 25')['changes'][0]['destructive'])
        self.assertFalse(self.one('corta de 5 a 8')['changes'][0]['destructive'])

    def test_replay_slow_and_freeze_and_speed(self):
        r = self.one('replay de 12 a 15 em câmera lenta')['changes'][0]
        self.assertEqual(('replay', .5), (r['op'], r['args']['rate']))
        f = self.one('congela aos 14 segundos por 2 s')['changes'][0]
        self.assertEqual(('congelar', 14.0, 2.0), (f['op'], f['args']['at'], f['args']['duration']))
        v = self.one('câmera lenta de 10 a 13')['changes'][0]
        self.assertEqual(('velocidade', .5), (v['op'], v['args']['rate']))

    def test_multiple_clauses(self):
        r = self.one('corta de 2 a 3; sem zoom')
        self.assertEqual(['cortar', 'limpar_zooms'], [c['op'] for c in r['changes']])

    def test_unknown_is_a_question_not_a_guess(self):
        r = self.one('deixa mais bonito')
        self.assertEqual([], r['changes'])
        self.assertTrue(r['questions'])

    def test_shell_text_is_just_text(self):
        r = self.one('rm -rf / ; corta de 1 a 2')
        self.assertEqual(['cortar'], [c['op'] for c in r['changes']])     # só a parte entendida vira operação tipada
        self.assertTrue(r['questions'])


class ConversationTests(unittest.TestCase):
    def test_apply_and_undo(self):
        c = conv()
        r = c.say('corta de 8 a 11')
        self.assertEqual(1, len(r['aplicado']))
        self.assertEqual([dict(start=8.0, end=11.0)], c.project['cuts'])
        self.assertEqual([], c.undo()['recusado'])
        self.assertEqual([], c.project['cuts'])
        self.assertIn('Não há o que desfazer', c.undo()['recusado'][0])

    def test_undo_by_phrase(self):
        c = conv()
        c.say('replay de 5 a 7')
        self.assertTrue(c.project['replays'])
        c.say('desfaz')
        self.assertEqual([], c.project['replays'])

    def test_big_cut_waits_for_confirmation(self):
        c = conv()
        r = c.say('corta de 5 a 25')
        self.assertEqual([], r['aplicado'])
        self.assertEqual(1, len(r['aguardando_confirmacao']))
        self.assertEqual([], c.project['cuts'])
        c.confirm()
        self.assertEqual(1, len(c.project['cuts']))

    def test_editor_limits_still_apply(self):
        c = conv(40)
        r = c.say('replay de 5 a 20')            # passa de 8 s de fonte
        self.assertEqual([], r['aplicado'])
        self.assertIn('recusou', r['recusado'][0])
        self.assertEqual([], c.project['replays'])

    def test_overlapping_speed_is_rejected(self):
        c = conv()
        c.say('câmera lenta de 10 a 14')
        r = c.say('câmera lenta de 12 a 16')
        self.assertTrue(r['recusado'])

    def test_sfx_softer_keeps_original_in_history(self):
        base = projectlib.clean(dict(sfx=[dict(id='s1', kind='pop', at=3, volume=.8)]), 40)
        c = converse.Conversation(base, 40)
        c.say('deixa os efeitos sonoros mais baixos')
        self.assertLess(c.project['sfx'][0]['volume'], .8)
        c.undo()
        self.assertEqual(.8, c.project['sfx'][0]['volume'])

    def test_original_project_not_mutated(self):
        base = projectlib.empty()
        c = converse.Conversation(base, 40)
        c.say('corta de 1 a 2')
        self.assertEqual([], base['cuts'])


    def test_redo_and_new_change_clears_redo(self):
        c = conv()
        c.say('corta de 1 a 2')
        c.undo()
        self.assertEqual([], c.project['cuts'])
        c.say('refaz')
        self.assertEqual(1, len(c.project['cuts']))
        c.undo()
        c.say('replay de 5 a 7')
        self.assertIn('Não há o que refazer', c.redo()['recusado'][0])


if __name__ == '__main__':
    unittest.main()
