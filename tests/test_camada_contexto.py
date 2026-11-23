import json
import tempfile
import unittest
from pathlib import Path

from liveclips import handoff
from liveclips.camada_contexto import Intelligence, face_for
from liveclips.context_store import ContextStore


def beh(t, cue='sorriso', strength=2.4):
    return dict(time=t, apex=t, onset=t - .4, offset=t + .4, strength=strength, confidence=.8, duration=.8, cue=cue, label=cue, samples=3)


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.intel = Intelligence(self.tmp.name)
        self.text = [dict(start=0, end=6, text='eu garanto que passo essa fase'), dict(start=18, end=21, text='perdi')]

    def test_face_unknown_without_meta_and_aggregated_with_meta(self):
        self.assertIsNone(face_for({}))
        f = face_for(dict(behavior_meta=[dict(frames=100, faces=95, face_px=150, sampling_fps=4)]))
        self.assertEqual('alta', f['level'])
        self.assertFalse(f['fine_motion_ok'])

    def test_annotate_adds_dimensions_handoff_and_never_raises(self):
        self.intel.prepare('s1', self.text, creator='c')
        cand = dict(start=5, end=30, score=10.0, transcript='perdi', moment_confidence=.6, components={})
        out = self.intel.annotate(cand, 's1', self.text, dict(behavior=[beh(24)]), None, creator='c')
        self.assertIn('dimensoes', out['intelligence'])
        self.assertTrue(out['intelligence']['dimensoes']['nota_nao_e_probabilidade'])
        self.assertEqual('liveclips.editor_handoff', out['handoff']['contract'])

    def test_annotate_failure_is_contained(self):
        out = self.intel.annotate({'start': 'x'}, 's1', [], {}, None)
        self.assertIn('erro', out['intelligence'])

    def test_missing_context_keeps_the_handoff_waiting(self):
        self.intel.prepare('s1', self.text, creator='c')
        cand = dict(start=17, end=30, score=10.0, transcript='perdi', moment_confidence=.6, components={})
        out = self.intel.annotate(cand, 's1', self.text, dict(behavior=[]), None, creator='c')
        h = out['handoff']
        if h['required_intervals']:
            self.assertEqual('aguardando_contexto', h['state'])
            self.assertTrue(h['missing_context'])

    def test_silent_candidates_respect_budget_and_profile_switch(self):
        sig = dict(behavior=[beh(24), beh(60, strength=2.6), beh(100, strength=2.6)])
        c, _ = self.intel.silent(sig, self.text, 120, 's1', focus=(0, 120), face=None, profile={}, mode='live')
        self.assertLessEqual(len(c), 2)
        c, _ = self.intel.silent(sig, self.text, 120, 's1', focus=(0, 120), face=None, profile={'silent_reactions': False}, mode='live')
        self.assertEqual([], c)


class HandoffTests(unittest.TestCase):
    def cand(self):
        return dict(start=10, end=40, transcript='texto real', function_map={'protected': []})

    def test_placeholders_are_rejected_and_real_text_is_kept(self):
        for bad in ('Título aqui', 'lorem ipsum', 'TODO', 'xxx', '  ', '---'):
            self.assertIsNone(handoff.clean_text(bad), bad)
        self.assertEqual('perdi a fase', handoff.clean_text('perdi a fase'))

    def test_missing_required_context_blocks_ready_states(self):
        h = handoff.build(self.cand(), required=dict(intervalos=[dict(start=2, end=5, quote='q', motivo='m')], notas=[]))
        self.assertEqual('aguardando_contexto', h['state'])
        with self.assertRaises(handoff.HandoffError):
            handoff.transition(h, 'pronto_para_revisar')

    def test_full_path_and_invalid_jump(self):
        h = handoff.build(self.cand(), required=dict(intervalos=[], notas=[]))
        self.assertEqual('pronto_para_revisar', h['state'])
        with self.assertRaises(handoff.HandoffError):
            handoff.transition(h, 'renderizado')
        for to in ('aprovado_para_edicao', 'renderizado', 'pronto_para_distribuicao'):
            h = handoff.transition(h, to)
        self.assertEqual(4, len(h['history']))

    def test_editor_feedback_adds_context_and_stops_after_two_rounds(self):
        h = handoff.build(self.cand(), required=dict(intervalos=[], notas=[]))
        h = handoff.editor_feedback(h, 'falta_contexto', dict(start=3, end=8), 'faltou a promessa')
        self.assertEqual(('aguardando_contexto', 1), (h['state'], h['revisions']))
        self.assertTrue(h['missing_context'])
        h = handoff.editor_feedback(h, 'borda_ruim')
        h = handoff.editor_feedback(h, 'borda_ruim')
        self.assertEqual('revisao_humana', h['state'])
        with self.assertRaises(handoff.HandoffError):
            handoff.editor_feedback(h, 'outro')


if __name__ == '__main__':
    unittest.main()


class SuggestIntegrationTests(unittest.TestCase):
    def setUp(self):
        from liveclips.engine import Engine
        from liveclips.store import Store
        from tests.helpers import setup_session
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.streamer, self.sid, self.profile = setup_session(self.store)
        self.engine = Engine(self.store)
        words = lambda a, b, t: dict(start=a, end=b, text=t, words=[dict(start=a, end=b, word=t)])
        segs0 = [words(2, 8, 'eu garanto que passo essa fase hoje'), words(30, 34, 'vou tentar de novo')]
        segs1 = [words(5, 9, 'perdi de novo que absurdo')]
        meta = dict(frames=240, faces=230, face_px=150, sampling_fps=4)
        signals0 = dict(audio=[], motion=[], facial=[], warnings=[], behavior=[dict(time=40, apex=40, onset=39.6, offset=40.4, strength=2.6,
                        confidence=.8, duration=.8, cue='sorriso', label='sorriso', samples=3)], behavior_meta=meta)
        with self.store.connect(True) as c:
            for seq, segs, sig in ((0, segs0, signals0), (1, segs1, dict(audio=[], motion=[], facial=[], warnings=[], behavior=[], behavior_meta=meta))):
                row = c.execute('SELECT data FROM segments WHERE session=? AND seq=?', (self.sid, seq)).fetchone()
                c.execute('UPDATE segments SET data=? WHERE session=? AND seq=?',
                          (json.dumps(dict(segments=segs, signals=sig)), self.sid, seq))
            c.execute('UPDATE sessions SET closed=1 WHERE id=?', (self.sid,))

    def test_suggest_one_annotates_every_candidate_and_stores_context(self):
        self.assertTrue(self.engine.suggest_one(self.store.session(self.sid), self.profile))
        items = [self.store.candidate(r['id']) for r in self.store.rows('SELECT id FROM candidates WHERE session=?', (self.sid,))]
        self.assertTrue(items, 'deveria ter sugerido algo')
        for item in items:
            data = item.get('data') or item
            intel = data.get('intelligence')
            self.assertIsNotNone(intel, item.get('id'))
            self.assertNotIn('erro', intel)
            self.assertEqual('liveclips.editor_handoff', data['handoff']['contract'])
        self.assertTrue(ContextStore(self.tmp.name).episodes(self.sid))


class ContextApiTests(unittest.TestCase):
    def setUp(self):
        from liveclips.store import Store
        from tests.helpers import setup_session, candidate
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.streamer, self.sid, self.profile = setup_session(self.store)
        self.item, _ = candidate(self.store, self.sid)

    def test_missed_moment_is_stored_with_the_human_interval_and_listed(self):
        from liveclips import studio_api
        out = studio_api.context_action(self.store, '/api/context/missed', dict(session=self.sid, start=50, end=70, reason='risada depois da queda'))
        cases = studio_api.context_action(self.store, '/api/context/cases', dict(session=self.sid, kind='missed'))['casos']
        self.assertEqual(out['caso'], cases[0]['id'])
        self.assertEqual([[50.0, 70.0]], cases[0]['human_intervals'])
        with self.assertRaises(ValueError):
            studio_api.context_action(self.store, '/api/context/missed', dict(session=self.sid, start=70, end=50))

    def test_fact_scope_is_validated_and_correction_keeps_history(self):
        from liveclips import studio_api
        with self.assertRaises(ValueError):
            studio_api.context_action(self.store, '/api/context/fact', dict(session=self.sid, text='x', scope='global'))
        fid = studio_api.context_action(self.store, '/api/context/fact', dict(session=self.sid, text='o amigo se chama Zé', scope='session', start=10, end=12))['id']
        out = studio_api.context_action(self.store, '/api/context/correct', dict(id=fid, text='o amigo se chama Zeca', why='errei o nome'))
        self.assertIn('novo', out)

    def test_plan_view_exposes_context_and_handoff_keys(self):
        from liveclips import studio_api
        view = studio_api.plan_view(self.store, self.item['id'])
        self.assertIn('contexto', view)
        self.assertIn('entrega', view)


class WaitingNoteTests(unittest.TestCase):
    def test_note_names_the_waiting_live_only_for_closed_sessions(self):
        from liveclips.engine import Engine
        from liveclips.store import Store
        from tests.helpers import setup_session
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(tmp.name)
        streamer, old, _ = setup_session(store)
        live = store.new_session(streamer, 'AO_VIVO', closed=False)
        engine = Engine(store)
        self.assertIn('AO_VIVO', engine.waiting_note(store.session(old)))
        self.assertEqual('', engine.waiting_note(store.session(live)))


class RegistryTests(unittest.TestCase):
    def test_all_32_items_have_an_honest_state_and_proof_for_usable_ones(self):
        from liveclips import capabilities
        rows = capabilities.intelligence_rows()
        self.assertEqual(['N%02d' % i for i in range(1, 33)], [r['id'] for r in rows])
        for r in rows:
            self.assertIn(r['status'], capabilities.STATES)
            if r['status'] != capabilities.AUSENTE:
                self.assertTrue(r['evidencia'], r['id'])
        self.assertEqual(32, sum(capabilities.intelligence_summary().values()))

    def test_every_listed_module_exists(self):
        import importlib
        from liveclips import capabilities
        for name in ('context_store', 'episodes', 'context_search', 'fusion', 'dimensions', 'silent_path', 'face_quality', 'handoff',
                     'clockmap', 'retention', 'calibration', 'replay', 'camada_contexto'):
            importlib.import_module('liveclips.' + name)


class HandoffProtectedTests(unittest.TestCase):
    def test_protected_accepts_dicts_and_pairs_and_ignores_junk(self):
        c = dict(start=10, end=40, function_map=dict(protected=[dict(start=12, end=14, function='climax'), (20, 22), 'lixo', dict(function='x')]))
        h = handoff.build(c, required=dict(intervalos=[], notas=[]))
        self.assertEqual([(12.0, 14.0), (20.0, 22.0)], [(p['start'], p['end']) for p in h['protected_intervals']])


class CudaFallbackTests(unittest.TestCase):
    def setUp(self):
        from liveclips.engine import Engine
        from liveclips.store import Store
        from tests.helpers import setup_session
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.streamer, self.sid, self.profile = setup_session(self.store)
        self.engine = Engine(self.store)

    def test_cuda_dll_error_at_transcribe_time_falls_back_to_cpu_once(self):
        from unittest.mock import patch, MagicMock
        profile = dict(self.profile, whisper_device='cuda')
        calls = []

        def call(model):
            calls.append(model)
            if len(calls) == 1:
                raise RuntimeError('Library cublas64_12.dll is not found or cannot be loaded')
            return 'ok'
        with patch.object(self.engine, 'get_model', return_value=MagicMock()):
            self.assertEqual('ok', self.engine.run_transcribe(profile, call))
        self.assertEqual(2, len(calls))
        self.assertTrue(self.engine.cuda_broken)

    def test_other_errors_and_cpu_errors_are_not_swallowed(self):
        from unittest.mock import patch, MagicMock
        with patch.object(self.engine, 'get_model', return_value=MagicMock()):
            with self.assertRaises(ValueError):
                self.engine.run_transcribe(dict(self.profile, whisper_device='cuda'), lambda m: (_ for _ in ()).throw(ValueError('outro erro')))
            with self.assertRaises(RuntimeError):
                self.engine.run_transcribe(dict(self.profile, whisper_device='cpu'), lambda m: (_ for _ in ()).throw(RuntimeError('cublas64_12.dll')))

    def test_after_the_fallback_the_model_is_built_for_cpu(self):
        import sys
        import types
        from unittest.mock import MagicMock, patch
        self.engine.cuda_broken = True
        wm = MagicMock()
        fake = types.SimpleNamespace(WhisperModel=wm)
        with patch.dict(sys.modules, {'faster_whisper': fake}):
            self.engine.get_model(dict(self.profile, whisper_device='cuda'))
        self.assertEqual('cpu', wm.call_args.kwargs['device'])


class LiveFirstTests(unittest.TestCase):
    def test_open_live_is_worked_before_closed_sessions(self):
        from unittest.mock import patch
        from liveclips.engine import Engine
        from liveclips.store import Store
        from tests.helpers import setup_session
        with tempfile.TemporaryDirectory() as d:
            store = Store(d)
            streamer, old, _ = setup_session(store)
            live = store.new_session(streamer, 'AO_VIVO', closed=False)
            store.setting('paused', False)
            engine = Engine(store)
            order = []

            def scan(session):
                order.append(session['id'])
                return True
            with patch.object(engine, 'scan_one', side_effect=scan), patch.object(engine, 'suggest_one', return_value=False), \
                    patch.object(engine, 'analyze_one', return_value=False):
                for _ in range(4):
                    engine.turn = 0
                    engine.work_once()
            self.assertEqual({live}, set(order))

    def test_old_session_works_when_the_live_has_nothing_to_do(self):
        from unittest.mock import patch
        from liveclips.engine import Engine
        from liveclips.store import Store
        from tests.helpers import setup_session
        with tempfile.TemporaryDirectory() as d:
            store = Store(d)
            streamer, old, _ = setup_session(store)
            live = store.new_session(streamer, 'AO_VIVO', closed=False)
            store.setting('paused', False)
            engine = Engine(store)
            seen = []
            with patch.object(engine, 'scan_one', return_value=False), patch.object(engine, 'suggest_one', return_value=False), \
                    patch.object(engine, 'analyze_one', side_effect=lambda s, p: seen.append(s['id']) or s['id'] == old):
                self.assertTrue(engine.work_once())
            self.assertEqual([live, old], seen)


class CaptureEndTests(unittest.TestCase):
    def test_automatic_end_is_recorded_and_exposed_in_state(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from liveclips.capture import Capture
        from liveclips.store import Store
        from liveclips.app import App
        from tests.helpers import setup_session
        with tempfile.TemporaryDirectory() as d:
            store = Store(d)
            streamer, sid, _ = setup_session(store)
            cap = Capture(store)
            current = dict(session=sid, streamer=streamer, producer=SimpleNamespace(returncode=0), consumer=SimpleNamespace(returncode=0),
                           chat=MagicMock(), log=MagicMock(), stopping=True, auto=True)
            cap.current = current
            cap.finish(current, 'A gravação parou sozinha', False)
            end = App.capture_end(store.session(sid))
            self.assertEqual(('automatico', False), (end['by'], end['error']))
            self.assertIsNone(App.capture_end(dict(path=d)))


class FailurePolicyTests(unittest.TestCase):
    def setUp(self):
        from liveclips.engine import Engine
        from liveclips.store import Store
        from tests.helpers import setup_session
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.streamer, self.old, _ = setup_session(self.store)
        self.live = self.store.new_session(self.streamer, 'AO_VIVO', closed=False)
        self.store.setting('paused', False)
        self.engine = Engine(self.store)

    def test_analysis_failure_retries_then_errors_but_the_live_keeps_registering_segments(self):
        from unittest.mock import patch
        scanned = []
        with patch.object(self.engine, 'scan_one', side_effect=lambda s: scanned.append(s['id']) or False), \
                patch.object(self.engine, 'suggest_one', return_value=False), \
                patch.object(self.engine, 'analyze_one', side_effect=RuntimeError('cublas64_12.dll')):
            for _ in range(4):
                if self.live in self.engine.failures:
                    self.engine.failures[self.live]['next_at'] = 0
                self.engine.work_once()
            self.assertEqual('error', self.store.session(self.live)['status'])
            scanned.clear()
            self.engine.work_once()
        # com a sessão em erro, a gravação ainda é cadastrada (a live aberta continua sendo escaneada)
        self.assertIn(self.live, scanned)

    def test_success_clears_the_failure_counter(self):
        from unittest.mock import patch
        self.engine.failures[self.live] = dict(count=2, next_at=0, message='x')
        with patch.object(self.engine, 'scan_one', return_value=True):
            self.engine.work_once()
        self.assertNotIn(self.live, self.engine.failures)

    def test_progress_reports_how_long_the_current_step_has_been_running(self):
        import time
        self.engine.progress('Transcrevendo', 'A / s · segmento 0 · 10%')
        self.engine.lane_info["analise"]["since"] = time.time() - 700
        self.engine.progress('Transcrevendo', 'A / s · segmento 0 · 20%')       # o % muda; a etapa é a mesma
        self.assertGreaterEqual(self.engine.state()['elapsed_s'], 699)
        self.engine.progress('Transcrevendo', 'A / s · segmento 1 · 0%')        # etapa nova zera o relógio
        self.assertLess(self.engine.state()['elapsed_s'], 5)
