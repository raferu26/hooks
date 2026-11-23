import unittest

from liveclips.behavior import behavior_events,observable_cues
from liveclips.intelligence import narrative_scores,text_evidence


class BehaviorIntelligenceTests(unittest.TestCase):
    def test_blendshapes_are_reported_as_observable_cues(self):
        cues=observable_cues({'mouthSmileLeft':.8,'mouthSmileRight':.6,
                              'cheekSquintLeft':.4,'cheekSquintRight':.4,
                              'jawOpen':.9,'browInnerUp':.7})
        self.assertGreater(cues['sorriso'],.5)
        self.assertGreater(cues['boca_aberta'],.2)
        self.assertGreater(cues['sobrancelhas_elevadas'],.2)

    def test_events_use_personal_baseline_and_keep_no_emotion_label(self):
        frames=[]
        for index in range(16):
            peak=.9 if index in (8,9,10) else .08
            frames.append({'time':index*.25,'scores':{
                'mouthSmileLeft':peak,'mouthSmileRight':peak,
                'cheekSquintLeft':peak,'cheekSquintRight':peak}})
        events=behavior_events(frames)
        smile=next(item for item in events if item['cue']=='sorriso')
        self.assertGreaterEqual(smile['confidence'],.6)
        self.assertEqual(smile['label'],'elevação dos cantos da boca')
        self.assertNotIn('feliz',str(events).casefold())

    def test_single_frame_artifact_has_lower_confidence_than_persistent_motion(self):
        def sample(active):
            return behavior_events([{'time':i*.25,'scores':{'jawOpen':.9 if i in active else .05}}
                                    for i in range(20)])
        one=next(x for x in sample({8}) if x['cue']=='boca_aberta')
        persistent=next(x for x in sample({8,9,10}) if x['cue']=='boca_aberta')
        self.assertLess(one['confidence'],persistent['confidence'])

    def test_narrative_scores_are_separate_and_boundary_hurts_closure(self):
        complete=narrative_scores('presta atencao deixa eu contar cuidado',
            'meu deus no final consegui ganhou',.8,crescendo=True,corroborated=True,
            boundary_warning=False,has_outcome=True)
        cut=narrative_scores('presta atencao deixa eu contar cuidado',
            'meu deus no final consegui ganhou',.8,crescendo=True,corroborated=True,
            boundary_warning=True,has_outcome=True)
        self.assertGreaterEqual(complete['climax'],7)
        self.assertGreater(complete['encerramento'],cut['encerramento'])

    def test_taxonomy_covers_more_than_reactions_and_gameplay(self):
        evidence=text_evidence('na minha opiniao o problema e que funciona assim passo a passo')
        self.assertTrue(evidence['opiniao'])
        self.assertTrue(evidence['educacional'])


if __name__=='__main__':unittest.main()
