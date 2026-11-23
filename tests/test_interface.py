from html.parser import HTMLParser
from pathlib import Path
import unittest


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[]

    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if values.get('id'):self.ids.append(values['id'])


class InterfaceStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(Path(__file__).parents[1]/'liveclips'/'static'/'index.html').read_text(encoding='utf-8')
        cls.parser=_Ids();cls.parser.feed(cls.html)

    def test_controls_keep_unique_stable_ids(self):
        self.assertEqual(len(self.parser.ids),len(set(self.parser.ids)))
        required={'captureBtn','videoBtn','liveBtn','fileBtn','profileBtn','importBtn','reclassifyBtn',
                  'sessionSelect','manualBtn','sessionToggle','openFolder','cards','detail','streamerSelect'}
        self.assertTrue(required.issubset(set(self.parser.ids)))

    def test_subscription_screen_and_login_exist(self):
        for value in ('navAccount','v-account','accBody','licenseDialog','licenseForm','licEmail','licPass','licGo','licSwap','licForgot','licTerms'):
            self.assertIn(value,self.parser.ids)
        for token in ('/api/license/login','/api/license/register','/api/license/refresh','/api/license/logout','licenseBanners','renderAccount'):
            self.assertIn(token,self.html)
        self.assertNotIn('device_token',self.html)

    def test_four_step_flow_and_dark_graphite_palette_exist(self):
        for value in ('stepSource','stepAnalyze','stepReview','stepExport'):
            self.assertIn(value,self.parser.ids)
        self.assertIn('--bg:#0e0e11',self.html)
        self.assertIn('--accent:#ff4d8d',self.html)
        self.assertIn('@media(max-width:860px)',self.html)

    def test_secondary_actions_are_grouped_without_being_removed(self):
        self.assertIn('Gerenciar ···',self.html)
        self.assertIn('capturePanel',self.parser.ids)

    def test_studio_has_editing_surface(self):
        for value in ('studio','stVideo','stLeft','stRight','stApprove','stRefresh','stUndo','stRedo','phone'):
            self.assertIn(value,self.parser.ids)
        # 0.19: as abas viraram seções do inspetor; "Agente" passou a se chamar "Sugestões" (aprovado).
        for tab in ('Estilo','Legendas','Títulos','Música','Cortes e efeitos','Layout e imagens','Sugestões','Por quê','Publicar'):
            self.assertIn(tab,self.html)
        for value in ('stQuality','stState','stPrev','stAuto','tlAll','keysDialog'):
            self.assertIn(value,self.parser.ids)
        self.assertNotIn("'Agente'",self.html)

    def test_new_editing_features_have_interface(self):
        for text in ('layout-grid','data-layout','data-fmt','addspeed','addfreeze','addsfx','imgFile','saveperf','copypub'):
            self.assertIn(text,self.html)

    def test_settings_expose_hardware_and_learning_controls(self):
        for value in ('hashtags','whisperDevice','videoEncoder','ollamaOn','ollamaModel','systemCheck','systemInfo','model'):
            self.assertIn(value,self.parser.ids)

    def test_nothing_loads_from_the_internet(self):
        for marker in ('src="http','href="http','url(http','@import'):
            self.assertNotIn(marker,self.html)


if __name__=='__main__':unittest.main()
