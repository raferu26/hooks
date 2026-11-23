import json
import tempfile
import unittest
from pathlib import Path

from liveclips import habits
from liveclips.store import Store
from tests.helpers import setup_session, candidate
from tests.test_judge import speech


class LearnTests(unittest.TestCase):
    def test_consistent_start_trim_becomes_a_habit(self):
        s = [dict(bounds=(2.0, 0.0), effects={}) for _ in range(4)] + [dict(bounds=(1.4, -.1), effects={})]
        out = habits.learn(s)
        self.assertTrue(out['offset_reliable'])
        self.assertGreaterEqual(out['start_offset'], 1.4)
        self.assertEqual(out['end_offset'], 0.0)
        self.assertTrue(any('começo' in n for n in out['notes']))

    def test_inconsistent_edits_do_not_create_a_habit(self):
        s = [dict(bounds=(2.0, 0), effects={}), dict(bounds=(-2.0, 0), effects={}), dict(bounds=(.1, 0), effects={}),
             dict(bounds=(1.9, 0), effects={})]
        out = habits.learn(s)
        self.assertFalse(out['offset_reliable'])
        self.assertEqual(out['start_offset'], 0.0)

    def test_two_few_samples_are_ignored(self):
        out = habits.learn([dict(bounds=(3, 0), effects={}), dict(bounds=(3, 0), effects={})])
        self.assertFalse(out['offset_reliable'])

    def test_offset_is_clamped(self):
        out = habits.learn([dict(bounds=(9.0, 0), effects={}) for _ in range(5)])
        self.assertEqual(out['start_offset'], 3.0)

    def test_repeated_correction_becomes_dictionary_suggestion(self):
        s = [dict(pairs=[('Koringa', 'Coringa')], effects={}), dict(pairs=[('Koringa', 'Coringa'), ('foi', 'fui')], effects={}),
             dict(pairs=[], effects={})]
        out = habits.learn(s, vocabulary='Valorant')
        self.assertEqual([x['term'] for x in out['dictionary_suggestions']], ['Coringa'])
        out2 = habits.learn(s, vocabulary='Valorant, Coringa')
        self.assertEqual(out2['dictionary_suggestions'], [])

    def test_deleted_effects_reduce_future_use(self):
        s = [dict(effects={'zoom': (3, 3)}), dict(effects={'zoom': (3, 2)}), dict(effects={'silence': (2, 0)})]
        out = habits.learn(s)
        self.assertEqual(out['effect_factor'], {'zoom': .5})
        light = habits.learn([dict(effects={'zoom': (3, 2)}), dict(effects={'zoom': (3, 1)})])
        self.assertEqual(light['effect_factor'], {'zoom': .75})
        self.assertEqual(habits.learn([dict(effects={'zoom': (2, 2)})])['effect_factor'], {})

    def test_caption_corrections_from_edited_lines(self):
        t = speech(['Hoje o Koringa fez uma jogada incrivel.'])
        data = dict(transcript_segments=t)
        lines = [dict(start=0, end=2, text='Hoje o Coringa fez uma jogada incrivel.', words=[])]
        pairs = habits.caption_corrections(data, 10.0, 20.0, dict(captions=dict(lines=lines)), {})
        self.assertEqual(pairs, [('Koringa', 'Coringa')])
        self.assertEqual(habits.caption_corrections(data, 10.0, 20.0, dict(captions=dict(lines=None)), {}), [])


class StoreHabitTests(unittest.TestCase):
    def test_store_collects_habits_from_approved_cuts_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            streamer, sid, _ = setup_session(store)
            for i in range(4):
                item, _ = candidate(store, sid, 5 + i * 20, 28 + i * 20)
                with store.connect(True) as c:
                    data = json.loads(c.execute('SELECT data FROM candidates WHERE id=?', (item['id'],)).fetchone()['data'])
                    data['agent_bounds'] = [item['start'] - 2.0, item['end']]
                    data['edit_plan'] = dict(decisions=[dict(id='zoom:1', kind='zoom', start=1, end=2, enabled=True)])
                    data['edit_overrides'] = {'zoom:1': False}
                    c.execute("UPDATE candidates SET data=?,status='approved' WHERE id=?", (json.dumps(data), item['id']))
            pending, _ = candidate(store, sid, 50, 58)
            out = store.habits(streamer)
            self.assertEqual(out['samples'], 4)
            self.assertTrue(out['offset_reliable'])
            self.assertAlmostEqual(out['start_offset'], 2.0, places=1)
            self.assertEqual(out['effect_factor'].get('zoom'), None)  # só 4 decisões: abaixo do mínimo de 6

    def test_accept_term_does_not_force_reanalysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            streamer, sid, _ = setup_session(store)
            item, _ = candidate(store, sid, 5, 28)
            terms = store.accept_term(streamer, 'Coringa')
            self.assertEqual(terms, 'Coringa')
            store.accept_term(streamer, 'coringa')
            self.assertEqual(store.streamer(streamer)['profile']['learned_terms'], 'Coringa')
            self.assertEqual(store.candidate(item['id'])['status'], 'pending')
            self.assertEqual(store.segments(sid)[0]['status'], 'done')


if __name__ == '__main__':
    unittest.main()
