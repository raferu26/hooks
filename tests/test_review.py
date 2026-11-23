import unittest

from liveclips import plan as planlib, review


def make_plan(pieces, project=None, duration=20.0):
    parts = [{'in': 0, 'out': duration, 'sha': 'abc'}]
    return planlib.build('c1', parts, pieces, duration, project=project)


WORDS = [dict(word='nossa', start=1.0, end=1.4), dict(word='olha', start=1.5, end=2.0), dict(word='isso', start=4.0, end=4.5)]


class TechnicalTests(unittest.TestCase):
    def test_planned_freeze_is_not_black_failure(self):
        plan = make_plan([(0, 0, 5, 1.0, 0), (0, 5, 5.05, 1.0, 1.0), (0, 5, 10, 1.0, 0)])
        freeze = [s for s in plan['segments'] if s['kind'] == 'freeze'][0]
        a, b = planlib.seconds(freeze['out_start']), planlib.seconds(freeze['out_end'])
        self.assertEqual([], review.technical(plan, black=[(a, b)]))

    def test_unplanned_black_is_flagged(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        issues = review.technical(plan, black=[(3.0, 4.0)])
        self.assertEqual(1, len(issues))
        self.assertEqual('alta', issues[0]['severity'])
        self.assertEqual('render_incompleto', issues[0]['defect'])

    def test_invalid_plan_is_critical_and_blocks(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        plan['output']['duration_ticks'] += 9000
        result = review.report(review.technical(plan))
        self.assertEqual('bloqueado', result['veredito'])
        self.assertTrue(result['bloqueia_pronto'])

    def test_duration_delta_over_tolerance(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        self.assertEqual([], review.technical(plan, plan_delta_frames=1.0))
        self.assertEqual('duracao_incorreta', review.technical(plan, plan_delta_frames=5.0)[0]['defect'])

    def test_qc_error_in_audio_is_critical(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        qc = dict(items=[dict(id='audio', label='Faixa de áudio', status='erro', detail='sem áudio')])
        self.assertEqual('critica', review.technical(plan, qc_report=qc)[0]['severity'])


class EditorialTests(unittest.TestCase):
    def test_word_cut_at_boundary_is_flagged(self):
        plan = make_plan([(0, 0, 1.2, 1.0, 0), (0, 3.0, 8.0, 1.0, 0)])   # corta "nossa" ao meio
        found = [i for i in review.editorial(plan, words=WORDS) if i['defect'] == 'fala_truncada']
        self.assertEqual(1, len(found))
        self.assertIn('nossa', found[0]['observation'])

    def test_word_across_contiguous_segments_is_not_truncated(self):
        plan = make_plan([(0, 0, 1.2, 1.0, 0), (0, 1.2, 8.0, 1.0, 0)])    # dois trechos contínuos
        self.assertEqual([], [i for i in review.editorial(plan, words=WORDS) if i['defect'] == 'fala_truncada'])

    def test_word_fully_removed_is_not_truncated(self):
        plan = make_plan([(0, 0, 0.9, 1.0, 0), (0, 2.5, 8.0, 1.0, 0)])
        self.assertEqual([], [i for i in review.editorial(plan, words=WORDS) if i['defect'] == 'fala_truncada'])

    def test_missing_context_requests_human(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        issues = review.editorial(plan, function_map=dict(request_more_context=True, why=['Resolução fora do corte.']))
        self.assertTrue(issues[0]['needs_human'])
        self.assertEqual('contexto_insuficiente', issues[0]['defect'])

    def test_loud_sfx_over_speech_is_flagged_and_quiet_is_not(self):
        project = dict(sfx=[dict(id='s1', kind='pop', at=4.1, volume=.9), dict(id='s2', kind='pop', at=4.1, volume=.2)])
        plan = make_plan([(0, 0, 10, 1.0, 0)], project=project)
        found = review.editorial(plan, words=WORDS)
        ids = [i['id'] for i in found if i['defect'] == 'voz_mascarada']
        self.assertEqual(['sfx_voz:s1'], ids)

    def test_fast_caption_is_low_and_needs_human(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        lines = [dict(start=1.0, end=1.5, text='x' * 30)]
        found = review.editorial(plan, lines=lines)
        self.assertEqual('baixa', found[0]['severity'])
        self.assertTrue(found[0]['needs_human'])

    def test_cut_over_protected_pause_is_reported(self):
        plan = make_plan([(0, 0, 10, 1.0, 0)])
        fm = dict(protected=[dict(function='pausa_narrativa', start=110.0, end=112.0)])
        found = review.editorial(plan, function_map=fm, cuts=[dict(start=10.5, end=11.5)], clip_start=100.0)
        self.assertEqual('payoff_cortado', found[0]['defect'])
        self.assertEqual([], review.editorial(plan, function_map=fm, cuts=[dict(start=3, end=4)], clip_start=100.0))


class WordsTests(unittest.TestCase):
    def test_session_words_become_part_local(self):
        segs = [dict(words=[dict(word='a', start=105.0, end=105.4), dict(word='b', start=115.0, end=115.5), dict(word='c', start=50.0, end=50.2)])]
        parts = [dict(path='x', **{'in': 100.0, 'out': 110.0}), dict(path='y', **{'in': 7.0, 'out': 20.0})]
        words = review.words_for_plan(segs, 100.0, 123.0, parts)
        self.assertEqual(('a', 105.0, 0), (words[0]['word'], words[0]['start'], words[0]['part']))
        self.assertEqual(('b', 12.0, 1), (words[1]['word'], words[1]['start'], words[1]['part']))
        self.assertEqual(['a'], [w['word'] for w in words if w['part'] == 0])
        self.assertNotIn('c', [w['word'] for w in words])


class ReportTests(unittest.TestCase):
    def test_clean_report_never_says_approved(self):
        result = review.report([])
        self.assertEqual('revisao_humana', result['veredito'])
        self.assertFalse(result['bloqueia_pronto'])
        self.assertTrue(result['nao_verificado'])

    def test_ordering_and_verdicts(self):
        low = review.issue('a', 'x', 'baixa', 'o')
        high = review.issue('b', 'x', 'alta', 'o')
        crit = review.issue('c', 'x', 'critica', 'o')
        self.assertEqual(['c', 'b', 'a'], [i['id'] for i in review.report([low, high, crit])['problemas']])
        self.assertEqual('corrigir', review.report([low, high])['veredito'])


class LoopTests(unittest.TestCase):
    def loop(self, outcomes):
        calls = []

        def render_and_review(project):
            calls.append(project)
            return outcomes[min(len(calls) - 1, len(outcomes) - 1)](project)
        return review.correct(render_and_review, dict(sfx=[dict(id='s1', kind='pop', at=1, volume=.9)]), limit=2), calls

    def bad(self, project):
        fix = dict(kind='baixar_efeito', id='s1', volume=.3)
        return review.report([review.issue('x', 'audio', 'alta', 'alto', 1, 2, fix=fix)])

    def good(self, project):
        return review.report([])

    def test_fix_applied_once_then_stops_when_clean(self):
        result, calls = self.loop([self.bad, self.good])
        self.assertEqual(2, len(calls))
        self.assertEqual(.3, calls[1]['sfx'][0]['volume'])
        self.assertEqual(.9, calls[0]['sfx'][0]['volume'])        # original intacto
        self.assertEqual(1, result['tentativas'])
        self.assertEqual('revisao_humana', result['final']['report']['veredito'])

    def test_stops_at_limit(self):
        result, calls = self.loop([self.bad, self.bad, self.bad, self.bad])
        self.assertLessEqual(len(calls), 3)

    def test_backs_off_when_worse(self):
        def worse(project):
            return review.report([review.issue('y', 'x', 'critica', 'pior')])
        result, calls = self.loop([self.bad, worse])
        self.assertEqual(.9, result['final']['project']['sfx'][0]['volume'])   # fica com a melhor versão
        self.assertEqual(2, len(result['versoes']))

    def test_human_only_issue_is_not_auto_fixed(self):
        fix = dict(kind='restaurar_trecho', start=1, end=2)
        outcome = lambda p: review.report([review.issue('z', 'ritmo', 'alta', 'o', fix=fix, human=True)])
        result, calls = self.loop([outcome])
        self.assertEqual(1, len(calls))

    def test_unknown_fix_does_not_loop(self):
        outcome = lambda p: review.report([review.issue('z', 'ritmo', 'alta', 'o', fix=dict(kind='mover_corte'))])
        result, calls = self.loop([outcome])
        self.assertEqual(1, len(calls))


class EngineIntegration(unittest.TestCase):
    def test_run_qc_writes_review_and_blocks_on_invalid_plan(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        from liveclips import engine as engine_module, media
        from liveclips.store import Store
        from tests.test_second_pass import make_session
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'd')
            _, _, cid = make_session(store)
            eng = engine_module.Engine(store)
            video = Path(tmp) / 'saida.mp4'
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=15',
                            '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000,volume=2', '-t', '4', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True)
            good = make_plan([(0, 0, 4, 1.0, 0)])
            (Path(tmp) / 'plano.json').write_text(json.dumps(good), encoding='utf-8')
            eng.run_qc(cid, video)
            qc_data = store.candidate(cid)['data']['qc']
            self.assertIn('review', qc_data)
            self.assertFalse(qc_data['review']['bloqueia_pronto'])
            self.assertTrue((Path(tmp) / 'revisao.json').is_file())
            bad = dict(good)
            bad['output'] = dict(good['output'], duration_ticks=good['output']['duration_ticks'] + 5000)
            (Path(tmp) / 'plano.json').write_text(json.dumps(bad), encoding='utf-8')
            eng.run_qc(cid, video)
            review_ = store.candidate(cid)['data']['qc']['review']
            self.assertTrue(review_['bloqueia_pronto'])
            self.assertEqual('bloqueado', review_['veredito'])
            (Path(tmp) / 'plano.json').write_text('{quebrado', encoding='utf-8')
            eng.run_qc(cid, video)                      # JSON ilegível não derruba a checagem
            self.assertEqual('indisponivel', store.candidate(cid)['data']['qc']['review']['veredito'])


if __name__ == '__main__':
    unittest.main()
