import unittest
from liveclips.narrative import story_plan


class StoryPlanTests(unittest.TestCase):
    def test_climax_reaction_and_alternative_bounds_follow_whole_phrases(self):
        rows=[{'start':i*5,'end':i*5+3,'text':text} for i,text in enumerate([
            'hoje vamos começar', 'quando eu entrei no jogo', 'calma espera cuidado',
            'agora vou tentar', 'meu deus ganhei consegui', 'não acredito que aconteceu',
            'no final deu certo', 'essa foi a história', 'obrigado por assistir',
            'vamos falar de outra coisa', 'outro assunto começa', 'continuamos depois',
            'mais um trecho', 'até amanhã'])]
        plan=story_plan({'start':11,'end':32,'moment_type':'jogada'},rows,
                        {'audio':[{'time':21,'strength':2}], 'motion':[{'time':21,'strength':2}]},0,70)
        self.assertEqual(plan['beats']['climax']['start'],20)
        self.assertGreaterEqual(plan['beats']['encerramento']['end'],33)
        self.assertIn('continua',plan['warning'])
        self.assertTrue(plan['alternatives'])
        for variant in plan['alternatives']:
            self.assertLessEqual(variant['actual_seconds'],variant['seconds']+1.5)
            self.assertLessEqual(variant['start'],plan['beats']['preparacao']['start'])
            self.assertGreaterEqual(variant['end'],plan['beats']['encerramento']['end'])

    def test_no_fabricated_variants_when_context_is_short(self):
        rows=[{'start':1,'end':4,'text':'calma espera'},
              {'start':7,'end':10,'text':'meu deus consegui'}]
        plan=story_plan({'start':0,'end':11,'moment_type':'reacao'},rows,{},0,12)
        self.assertEqual(plan['alternatives'],[])


if __name__=='__main__':unittest.main()
