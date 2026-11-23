import unittest

from liveclips import dimensions, face_quality, fusion, silent_path
from liveclips.behavior import behavior_events


def beh(t, cue='sorriso', strength=2.4, conf=.8, duration=.75, **extra):
    return dict(time=t, apex=t, onset=t - duration / 2, offset=t + duration / 2, strength=strength, confidence=conf,
                duration=duration, cue=cue, label=cue, samples=3, **extra)


FACE_OK = dict(level='alta', coverage=.95, face_px=140, sampling_fps=4, fine_motion_ok=False, nao_observavel=False, limits=[])
TEXT = [dict(start=0, end=6, text='eu garanto que passo essa fase'), dict(start=18, end=21, text='perdi')]


class BehaviorTimingTests(unittest.TestCase):
    def frames(self, lost=None, shift=False):
        out = []
        for i in range(24):
            peak = .9 if i in (12, 13, 14) else .08
            out.append(dict(time=i * .25, scores=dict(mouthSmileLeft=peak, mouthSmileRight=peak, cheekSquintLeft=peak, cheekSquintRight=peak),
                            pose=(0.0, 0.0, 0.0) if i < 16 or not shift else (30.0, 0.0, 0.0)))
        return [f for f in out if not (lost and lost[0] <= f['time'] <= lost[1])]

    def test_event_has_onset_apex_offset_direction_and_uncertainty(self):
        e = next(x for x in behavior_events(self.frames()) if x['cue'] == 'sorriso')
        self.assertLessEqual(e['onset'], e['apex'])
        self.assertLessEqual(e['apex'], e['offset'])
        self.assertEqual('aumento', e['direction'])
        self.assertEqual(.25, e['time_uncertainty_s'])
        self.assertEqual('webcam_pixels', e['lineage'])

    def test_pose_is_not_carried_across_a_face_loss_so_no_fake_head_spike(self):
        # rosto some por 2 s e volta em outra posição de cabeça: sem a correção, viraria um "salto" artificial
        frames = self.frames(lost=(3.0, 5.0), shift=True)
        head = [x for x in behavior_events(frames) if x['cue'] == 'virada_cabeca']
        self.assertEqual([], head)

    def test_real_head_turn_without_a_gap_is_still_detected(self):
        frames = self.frames(shift=True)
        self.assertTrue([x for x in behavior_events(frames) if x['cue'] == 'virada_cabeca'])

    def test_baseline_by_activity_separates_speaking_from_listening(self):
        frames = []
        for i in range(40):
            talking = i < 20
            v = .5 if talking else .05          # falando: boca sempre mais aberta (baseline próprio mais alto)
            if i == 30:
                v = .6                          # ouvindo: .6 é evento; falando, .5 é rotina
            frames.append(dict(time=i * .25, scores=dict(jawOpen=v)))
        plain = [e for e in behavior_events(frames) if e['cue'] == 'boca_aberta']
        split = [e for e in behavior_events(frames, speech=[(0, 4.9)]) if e['cue'] == 'boca_aberta']
        self.assertTrue(any(e.get('activity') == 'ouvindo' and abs(e['apex'] - 7.5) < .3 for e in split))
        self.assertFalse(any(e.get('activity') == 'falando' for e in split))
        self.assertFalse(any(abs(e['apex'] - 7.5) < .3 for e in plain))   # sem baseline por atividade o evento some


class FaceQualityTests(unittest.TestCase):
    def test_low_visibility_is_not_observable_instead_of_certain(self):
        q = face_quality.assess(dict(frames=100, faces=20))
        self.assertEqual('insuficiente', q['level'])
        self.assertTrue(q['nao_observavel'])
        self.assertTrue(q['limits'])

    def test_small_face_and_4fps_forbid_fine_motion_claims(self):
        q = face_quality.assess(dict(frames=100, faces=95, face_px=50, face_ratio=.95))
        self.assertFalse(q['fine_motion_ok'])
        self.assertTrue(any('250 ms' in l for l in q['limits']))
        self.assertTrue(any('Rosto pequeno' in l for l in q['limits']))

    def test_fine_motion_needs_dense_sampling_and_big_face(self):
        q = face_quality.assess(dict(frames=300, faces=290, face_px=160, sampling_fps=12))
        self.assertTrue(q['fine_motion_ok'])
        self.assertEqual('alta', q['level'])

    def test_no_frames_is_not_observable(self):
        self.assertTrue(face_quality.assess({})['nao_observavel'])

    def test_gaps_are_listed(self):
        self.assertEqual([[1.25, 4.0]], face_quality.gaps_from_times([0, .25, 1.0, 4.0, 4.25], .25)[:1] and [[1.25, 4.0]])
        self.assertEqual(1, len(face_quality.gaps_from_times([0, .25, 1.0, 4.0, 4.25], .25)))


class FusionTests(unittest.TestCase):
    def test_three_webcam_modalities_count_as_one_independent_source(self):
        sig = dict(motion=[dict(time=10, strength=2)], facial=[dict(time=10.1, strength=2)], behavior=[beh(10)])
        a = fusion.assess((5, 15), sig, [], face=FACE_OK)
        self.assertEqual(['webcam_pixels'], a['linhagens'])
        self.assertEqual(1, a['fontes_independentes'])
        self.assertTrue(a['somente_dependentes'])
        self.assertTrue(any('UMA fonte' in n for n in a['notas']))

    def test_independent_lineages_add_up_but_same_lineage_does_not(self):
        one = fusion.assess((5, 15), dict(behavior=[beh(10)], motion=[dict(time=10, strength=3)]), [], face=FACE_OK)
        two = fusion.assess((5, 15), dict(behavior=[beh(10)], visual=[dict(time=9, strength=3, kind='flash')]), [], face=FACE_OK)
        self.assertEqual(2, two['fontes_independentes'])
        self.assertGreater(two['forca_observacao'], one['forca_observacao'])

    def test_game_sound_with_shaking_camera_is_not_human_confirmation(self):
        sig = dict(audio=[dict(time=10, strength=3)], motion=[dict(time=10, strength=2.5)],
                   behavior=[beh(10.1, 'virada_cabeca', strength=2.5)])
        a = fusion.assess((5, 15), sig, [], face=FACE_OK)
        self.assertIn('movimento_global_possivel', a['conflitos'])
        self.assertIn('som_sem_evidencia_humana', a['conflitos'])
        webcam = [e for e in a['evidencias'] if e['lineage'] == 'webcam_pixels']
        self.assertTrue(all(e['weight'] == .5 for e in webcam))
        self.assertEqual('nao_verificada', a['estados']['atribuicao_ao_streamer'])

    def test_unobservable_face_zeroes_webcam_weight_and_abstains(self):
        bad = dict(face_quality.assess(dict(frames=50, faces=5)))
        a = fusion.assess((5, 15), dict(behavior=[beh(10)]), [], face=bad)
        self.assertEqual('nao_observavel', a['abstencao'])
        self.assertEqual(0.0, a['forca_observacao'])
        self.assertIn('rosto_nao_observavel', a['conflitos'])

    def test_missing_modality_is_unknown_not_a_negative(self):
        a = fusion.assess((5, 15), {}, [], face=None)
        self.assertEqual('desconhecido', a['abstencao'])
        self.assertEqual('desconhecido', a['estados']['rosto'])
        self.assertFalse(a['escore_calibrado'])

    def test_pending_episode_waits(self):
        a = fusion.assess((5, 15), dict(behavior=[beh(10)]), [], face=FACE_OK, episode_pending=True)
        self.assertEqual('aguardando_contexto', a['abstencao'])

    def test_chat_alone_has_lower_weight_and_declares_time_uncertainty(self):
        a = fusion.assess((5, 15), dict(chat=[dict(time=10, strength=3)]), [], chat_uncertainty_s=4)
        e = a['evidencias'][0]
        self.assertEqual((.6, 4.0), (e['weight'], e['time_uncertainty_s']))

    def test_association_never_claims_causality_and_lists_alternatives(self):
        links = fusion.associate([dict(apex=10)], [dict(time=8, kind='visual'), dict(time=9, kind='fala_desfecho')])
        self.assertFalse(links[0]['causal'])
        self.assertTrue(links[0]['incerta'])
        self.assertEqual(1, len(links[0]['alternativas']))
        self.assertEqual(1.0, links[0]['atraso_s'])

    def test_reaction_without_prior_event_is_flagged(self):
        l = fusion.associate([dict(apex=10)], [dict(time=40, kind='visual')])[0]
        self.assertEqual('sem_evento_anterior', l['estado'])

    def test_a_late_event_beyond_window_is_not_linked(self):
        l = fusion.associate([dict(apex=100)], [dict(time=90, kind='visual')])[0]
        self.assertIsNone(l['evento'])


class SilentPathTests(unittest.TestCase):
    def run_path(self, behavior, signals=None, transcript=None, face=FACE_OK, **kw):
        sig = dict(behavior=behavior, **(signals or {}))
        return silent_path.propose(sig, TEXT if transcript is None else transcript, 120, focus=(0, 120), face=face, **kw)

    def test_discreet_smile_after_a_failure_is_proposed_as_exploratory_with_setup(self):
        c, rej = self.run_path([beh(24)])
        self.assertEqual(1, len(c))
        x = c[0]
        self.assertEqual('reacao_silenciosa', x['origin'])
        self.assertTrue(x['exploratory'] and x['low_confidence'] and x['fallback'])
        self.assertFalse(x['isolated_cue'])
        self.assertEqual('desfecho_falado', x['triggers'][0]['kind'])
        self.assertLess(x['start'], 21)
        self.assertGreaterEqual(x['end'] - x['start'], silent_path.MIN_LEN_S)
        self.assertNotIn('felicidade', ' '.join(x['reasons']).lower())

    def test_yawn_is_rejected(self):
        c, rej = self.run_path([beh(24, 'boca_aberta', duration=2.0)])
        self.assertEqual([], c)
        self.assertEqual('bocejo_provavel', rej[0]['motivo'])

    def test_short_open_mouth_with_brow_is_not_a_yawn(self):
        c, _ = self.run_path([beh(24, 'boca_aberta', duration=1.5), beh(24.2, 'sobrancelhas_elevadas')])
        self.assertTrue(c)

    def test_blink_like_single_sample_is_rejected_at_4fps_but_allowed_dense(self):
        one = dict(beh(24), samples=1)
        self.assertEqual('amostra_unica_possivel_artefato', self.run_path([one])[1][0]['motivo'])
        dense = dict(face_quality.assess(dict(frames=300, faces=290, face_px=150, sampling_fps=12)))
        self.assertTrue(self.run_path([one], face=dense)[0])

    def test_chair_or_camera_movement_is_rejected(self):
        sig = dict(motion=[dict(time=24, strength=2.5)])
        c, rej = self.run_path([beh(24), beh(24.1, 'virada_cabeca', strength=2.5)], sig)
        self.assertEqual([], c)
        self.assertEqual('movimento_global_cabeca_ou_camera', rej[0]['motivo'])

    def test_smile_while_talking_is_left_to_the_main_path(self):
        talk = [dict(start=20, end=30, text='e então eu estava rindo muito disso')]
        self.assertEqual('durante_fala', self.run_path([beh(24)], transcript=talk)[1][0]['motivo'])

    def test_isolated_cue_needs_strength_and_is_labeled_isolated(self):
        weak = self.run_path([beh(60, strength=1.4)], transcript=[])
        self.assertEqual([], weak[0])
        self.assertEqual('pista_isolada_sem_gatilho', weak[1][0]['motivo'])
        strong = self.run_path([beh(60, strength=2.6)], transcript=[])[0]
        self.assertTrue(strong[0]['isolated_cue'])
        self.assertLessEqual(strong[0]['score'], 1.6)

    def test_unobservable_face_proposes_nothing(self):
        bad = face_quality.assess(dict(frames=50, faces=5))
        c, rej = self.run_path([beh(24)], face=bad)
        self.assertEqual(([], 'rosto_nao_observavel'), (c, rej[0]['motivo']))

    def test_game_event_is_a_trigger_even_without_words(self):
        c, _ = self.run_path([beh(60)], dict(visual=[dict(time=57, strength=2, kind='flash')]), transcript=[])
        self.assertEqual('evento_visual', c[0]['triggers'][0]['kind'])
        self.assertFalse(c[0]['isolated_cue'])

    def test_only_game_sound_is_not_a_trigger(self):
        c, _ = self.run_path([beh(60, strength=2.6)], dict(audio=[dict(time=58, strength=3)]), transcript=[])
        self.assertTrue(c[0]['isolated_cue'])

    def test_resolved_episode_is_a_trigger(self):
        c, _ = self.run_path([beh(60)], episodes=[dict(kind='promessa', text='vou passar', resolved=57.0)], transcript=[])
        self.assertEqual('episodio', c[0]['triggers'][0]['kind'])

    def test_focus_limits_to_the_center_segment_and_budget_limits_count(self):
        c, _ = silent_path.propose(dict(behavior=[beh(24), beh(90), beh(110)]), TEXT, 120, focus=(80, 120), face=FACE_OK,
                                   max_candidates=1, episodes=[dict(kind='x', text='y', resolved=88.0), dict(kind='x', text='z', resolved=108.0)])
        self.assertEqual(1, len(c))
        self.assertGreaterEqual(c[0]['start'], 70)

    def test_start_does_not_cut_a_sentence_in_half_by_a_little(self):
        talk = [dict(start=20.0, end=23.5, text='e então perdi feio')]
        c, _ = silent_path.propose(dict(behavior=[beh(27)]), talk, 120, focus=(0, 120), face=FACE_OK)
        self.assertTrue(c[0]['start'] <= 20.0 or c[0]['start'] >= 23.5)


class DimensionTests(unittest.TestCase):
    def cand(self, **kw):
        base = dict(start=10, end=40, score=12.0, transcript='perdi a fase de novo', moment_confidence=.7, components={})
        base.update(kw)
        return base

    def test_dimensions_are_separate_and_not_a_probability(self):
        a = fusion.assess((10, 40), dict(behavior=[beh(20)], visual=[dict(time=19, strength=2, kind='flash')]), [], face=FACE_OK)
        d = dimensions.compute(self.cand(), a, episodes=[dict(kind='promessa', status='resolvido')], creator_signal=.8)
        self.assertTrue(d['nota_nao_e_probabilidade'])
        self.assertEqual('heuristico_nao_calibrado', d['base'])
        self.assertEqual(1.0, d['prontidao_do_episodio'])
        self.assertEqual(.8, d['afinidade_com_criador'])
        self.assertEqual('pronto_para_revisar', d['estado'])

    def test_open_episode_makes_the_candidate_wait_with_reason(self):
        d = dimensions.compute(self.cand(), None, episodes=[dict(kind='promessa', status='aberto')])
        self.assertEqual('aguardando_contexto', d['estado'])
        self.assertIn('promessa', d['aguardando'][0])

    def test_unknown_stays_unknown(self):
        d = dimensions.compute(self.cand(moment_confidence=0), None)
        self.assertIsNone(d['suporte_da_interpretacao'])
        self.assertIsNone(d['prontidao_do_episodio'])
        self.assertIsNone(d['afinidade_com_criador'])
        self.assertIsNone(d['forca_da_observacao'])

    def test_exploratory_label_wins_and_conflicts_force_review(self):
        self.assertEqual('exploratorio', dimensions.compute(self.cand(exploratory=True), None)['estado'])
        a = fusion.assess((10, 40), dict(audio=[dict(time=20, strength=3)]), [], face=FACE_OK)
        self.assertEqual('revisao_necessaria', dimensions.compute(self.cand(), a)['estado'])

    def test_novelty_drops_for_same_event_but_not_for_a_distinct_one(self):
        same = dict(start=12, end=42, transcript='perdi a fase de novo')
        other = dict(start=300, end=330, transcript='agora vamos falar de outra coisa')
        self.assertLess(dimensions.novelty(self.cand(), [same]), .2)
        self.assertGreater(dimensions.novelty(self.cand(), [other]), .9)


if __name__ == '__main__':
    unittest.main()
