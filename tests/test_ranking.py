import unittest

from liveclips.ranking import rank
from liveclips.store import same_recoded_moment


class RankingV61Tests(unittest.TestCase):
    def test_setup_payoff_and_audio_crescendo_are_explainable(self):
        segments=[
            {'start':1,'end':4,'text':'cuidado corre vai vai agora calma'},
            {'start':7,'end':12,'text':'meu deus consegui ganhei isso foi inacreditavel'},
        ]
        signals={'audio':[{'time':2,'strength':.9},{'time':10,'strength':2.1}], 'motion':[]}
        candidates=rank(segments,30,signals,max_candidates=3)
        self.assertTrue(candidates)
        best=candidates[0]
        self.assertGreater(best['components']['preparacao_e_desfecho'],0)
        self.assertGreater(best['components']['crescendo_audio'],0)
        self.assertIn('Preparação e desfecho aparecem no mesmo contexto',best['reasons'])
        self.assertEqual(best['selection_version'],'v6.8-comportamento-multimodal-narrativa')
        self.assertIn('narrative',best)
        self.assertIn('moment_type',best)

    def test_chat_never_creates_highlight_without_corroboration(self):
        segments=[{'start':1,'end':16,'text':'estamos apenas conversando normalmente sobre o jogo agora'}]
        chat={'chat':[{'time':8,'strength':3,'messages':20,'users':15}]}
        self.assertEqual(rank(segments,30,chat),[])

    def test_chat_and_facial_signal_support_a_real_reaction(self):
        segments=[{'start':1,'end':14,'text':'calma espera meu deus olha isso que aconteceu'}]
        signals={'audio':[{'time':10,'strength':1.8}],
                 'motion':[{'time':10.4,'strength':1.4}],
                 'facial':[{'time':10.2,'strength':1.5,'region':'boca'}],
                 'chat':[{'time':10.5,'strength':2,'messages':12,'users':9}]}
        best=rank(segments,30,signals)[0]
        self.assertGreater(best['components']['reacao_chat'],0)
        self.assertGreater(best['components']['movimento_facial_breve'],0)

    def test_behavior_never_decides_alone(self):
        segments=[{'start':1,'end':16,'text':'estamos apenas conversando normalmente sobre o jogo agora sem novidade'}]
        signals={'behavior':[{'time':8,'strength':3,'confidence':.95,'cue':'boca_aberta',
                              'label':'abertura rápida da boca'}]}
        self.assertEqual(rank(segments,30,signals),[])

    def test_context_fallback_is_low_confidence_and_never_pretends_to_be_strong(self):
        segments=[{'start':1,'end':8,'text':'hoje vamos conversar sobre a configuracao do computador'},
                  {'start':9,'end':17,'text':'depois vamos olhar cada parte com bastante calma e contexto'}]
        result=rank(segments,30,{},focus=(0,20),max_candidates=4)
        self.assertTrue(result)
        self.assertTrue(result[0]['fallback']);self.assertTrue(result[0]['low_confidence'])
        self.assertLessEqual(result[0]['moment_confidence'],.49)
        self.assertIn('revisão humana',' '.join(result[0]['reasons']))

    def test_behavior_is_explainable_when_another_modality_confirms(self):
        segments=[{'start':1,'end':16,'text':'calma espera meu deus olha isso que aconteceu agora'}]
        signals={'audio':[{'time':8.2,'strength':2}],
                 'behavior':[{'time':8,'strength':2.4,'confidence':.9,'cue':'boca_aberta',
                              'label':'abertura rápida da boca'}]}
        best=rank(segments,30,signals)[0]
        self.assertGreater(best['components']['comportamento_observavel'],0)
        self.assertEqual(best['behavior_evidence'][0]['cue'],'boca_aberta')

    def test_opinion_and_education_are_first_class_moments(self):
        segments=[{'start':1,'end':18,'text':'na minha opiniao o problema e este e funciona assim passo a passo voce precisa prestar atencao nisso'}]
        best=rank(segments,35,{},content_mode='video',priority='educacional')[0]
        self.assertIn(best['moment_type'],('educacional','opiniao'))
        self.assertGreater(best['components']['explicacao_util'],0)
        self.assertGreater(best['components']['afinidade_perfil'],0)

    def test_recoded_dedup_requires_both_visual_and_transcript_similarity(self):
        first={'visual_fingerprint':'0123456789abcdef',
               'transcript':'meu deus olha isso eu consegui ganhar agora'}
        recoded={'visual_fingerprint':'0123456789abcdee',
                 'transcript':'meu deus olha isso eu consegui ganhar agora mesmo'}
        other_visual={'visual_fingerprint':'fedcba9876543210',
                      'transcript':first['transcript']}
        self.assertTrue(same_recoded_moment(first,recoded,24,25))
        self.assertFalse(same_recoded_moment(first,other_visual,24,25))


if __name__ == '__main__':
    unittest.main()
