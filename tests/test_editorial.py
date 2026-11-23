import tempfile
import unittest

from liveclips.editorial import audit
from liveclips.editing import EDITOR_PRESETS
from liveclips.ranking import rank
from liveclips.store import DEFAULT_PROFILE,Store,profile_checked
from tests.helpers import setup_session,candidate


class EditorialTests(unittest.TestCase):
    def test_blocked_policy_blocks_audit(self):
        profile=dict(DEFAULT_PROFILE,permission_policy='blocked')
        result=audit({'transcript':'meu deus consegui ganhar agora','components':{'reacao_na_fala':4}},profile,
                     {'url':'https://example.com/live','title':'Live','author':'Canal'})
        self.assertEqual(result['status'],'block')
        self.assertTrue(any(x['key']=='rights' and x['status']=='block' for x in result['checks']))

    def test_profile_accepts_editorial_presets_and_rejects_unknown(self):
        checked=profile_checked(dict(DEFAULT_PROFILE,editorial_style='funny',clip_format='narrative',
                                     priority='educacional',behavior_sensitivity='precise',
                                     vocabulary='Coringa, Fortnite, Unreal Engine'))
        self.assertEqual(checked['editorial_style'],'funny')
        self.assertEqual(checked['priority'],'educacional')
        self.assertIn('Fortnite',checked['vocabulary'])
        for style in EDITOR_PRESETS:
            self.assertEqual(profile_checked(dict(DEFAULT_PROFILE,editorial_style=style))['editorial_style'],style)
        with self.assertRaises(ValueError):profile_checked(dict(DEFAULT_PROFILE,editorial_style='viral-magico'))
        with self.assertRaises(ValueError):profile_checked(dict(DEFAULT_PROFILE,reframe_mode='corta-tudo'))
        with self.assertRaises(ValueError):profile_checked(dict(DEFAULT_PROFILE,behavior_sensitivity='le-mente'))

    def test_music_requires_explicit_authorization(self):
        with self.assertRaisesRegex(ValueError,'autorizado'):
            profile_checked(dict(DEFAULT_PROFILE,auto_music=True,music_path=r'C:\Recursos\musica.mp3'))
        accepted=profile_checked(dict(DEFAULT_PROFILE,auto_music=True,music_authorized=True,
                                      music_path=r'C:\Recursos\musica.mp3'))
        self.assertTrue(accepted['music_authorized'])

    def test_narrative_profile_can_select_longer_context(self):
        segments=[{'start':0,'end':12,'text':'calma espera cuidado isso vai acontecer'},
                  {'start':36,'end':50,'text':'meu deus consegui ganhei isso foi inacreditavel'}]
        result=rank(segments,90,{'audio':[{'time':45,'strength':2}], 'motion':[]},
                    clip_format='narrative')
        self.assertTrue(result)
        self.assertEqual(result[0]['clip_format'],'narrative')

    def test_blocked_profile_cannot_export(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);streamer,session,_=setup_session(store,'TESTE','LIVE')
            profile=store.streamer(streamer)['profile'];profile['permission_policy']='blocked'
            store.save_profile(streamer,profile)
            item,_=candidate(store,session)
            with self.assertRaisesRegex(ValueError,'bloqueia'):
                store.review(item['id'],1,item['start'],item['end'],item['parts'],'approve',profile)

    def test_video_mode_can_approve_without_webcam(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);_,session,_=setup_session(store,'VIDEO','EPISODIO')
            item,_=candidate(store,session)
            profile=dict(DEFAULT_PROFILE,camera_rect=None,content_mode='video',min_free_gb=.5,
                         permission_policy='allowed')
            version=store.review(item['id'],1,item['start'],item['end'],item['parts'],'approve',profile)
            self.assertEqual(version,2)


if __name__=='__main__':unittest.main()
