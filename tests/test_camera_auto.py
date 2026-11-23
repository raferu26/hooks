"""Webcam automática: aplica sozinha só quando é seguro, sugere nos demais casos e o render usa a webcam de AGORA."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from liveclips import media
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE,Store
from tests.helpers import candidate,setup_session


def found(level='alta'):
    return dict(found=True,rect=[0.74,0.04,0.24,0.32],level=level,hits=8,frames=9,snapped=3,reason='Rosto em 8 de 9 quadros.')


class CameraAutoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.streamer,self.sid,self.profile=setup_session(self.store,'DAVA','LIVE',durations=(60,60,60,60,60,60,60,60,60,60),status='new')
        self.store.save_profile(self.streamer,dict(self.profile,camera_rect=None,content_mode='live'))

    def rect(self):return self.store.streamer(self.streamer)['profile']['camera_rect']

    def test_high_confidence_and_nothing_analysed_is_applied_by_itself(self):
        with patch('liveclips.camera_detect.detect',return_value=found('alta')) as detect:
            self.assertTrue(self.engine._camera_step())
        self.assertEqual(self.rect(),[0.74,0.04,0.24,0.32]);self.assertEqual(detect.call_count,1)
        self.assertIn('localizada automaticamente',' '.join(e['message'] for e in self.store.rows('SELECT message FROM events')))

    def test_medium_confidence_leaves_a_suggestion_and_does_not_touch_the_profile(self):
        with patch('liveclips.camera_detect.detect',return_value=found('media')):
            self.assertTrue(self.engine._camera_step())
        self.assertIsNone(self.rect());self.assertEqual(self.store.setting('camera_sugestao:'+self.streamer)['level'],'media')
        with patch('liveclips.camera_detect.detect') as detect:
            self.assertFalse(self.engine._camera_step())          # já existe sugestão esperando: não procura de novo
        detect.assert_not_called()

    def test_already_analysed_segments_make_it_a_suggestion_even_when_confident(self):
        with self.store.connect(True) as c:c.execute("UPDATE segments SET status='done' WHERE session=? AND seq=0",(self.sid,))
        with patch('liveclips.camera_detect.detect',return_value=found('alta')):
            self.engine._camera_step()
        self.assertIsNone(self.rect());self.assertIsNotNone(self.store.setting('camera_sugestao:'+self.streamer))

    def test_not_found_retries_on_later_segments_up_to_three_times(self):
        miss=dict(found=False,level=None,hits=0,frames=9,reason='sem rosto')
        used=[]
        def detect(path):used.append(Path(path).name);return miss
        with patch('liveclips.camera_detect.detect',side_effect=detect):
            for _ in range(6):self.engine._camera_step()
        self.assertEqual(used,['segmento_00000.ts','segmento_00004.ts','segmento_00009.ts'])

    def test_streamer_with_webcam_or_video_mode_is_left_alone(self):
        self.store.save_profile(self.streamer,dict(self.profile,camera_rect=[0.7,0.1,0.2,0.3]))
        with patch('liveclips.camera_detect.detect') as detect:self.assertFalse(self.engine._camera_step())
        detect.assert_not_called()
        self.store.save_profile(self.streamer,dict(self.profile,camera_rect=None,content_mode='video'))
        with patch('liveclips.camera_detect.detect') as detect:self.assertFalse(self.engine._camera_step())
        detect.assert_not_called()

    def test_waits_until_the_target_segment_exists(self):
        s2,sid2,_=setup_session(self.store,'OUTRO','L2',durations=(60,),status='new')
        self.store.save_profile(s2,dict(self.store.streamer(s2)['profile'],camera_rect=None))
        with self.store.connect(True) as c:c.execute('UPDATE sessions SET enabled=0 WHERE id=?',(self.sid,))
        with patch('liveclips.camera_detect.detect',return_value=found()) as detect:
            self.assertTrue(self.engine._camera_step())     # a 1ª tentativa usa a 1ª peça, que existe
        self.assertEqual(detect.call_count,1)


class RenderUsesCurrentCameraTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        d=patch('liveclips.media.free_bytes',return_value=100*1024**3);d.start();self.addCleanup(d.stop)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.streamer,self.sid,self.profile=setup_session(self.store,'DAVA','LIVE')

    def test_webcam_marked_after_the_clip_exists_is_used_by_the_render(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        self.store.save_profile(self.streamer,dict(self.profile,camera_rect=[0.5,0.1,0.3,0.3]))
        with patch('liveclips.media.render',return_value=Path(self.temp.name)/'r.mp4') as render:
            self.engine.do_render(item['id'],False)
        self.assertEqual(render.call_args.args[0]['profile']['camera_rect'],[0.5,0.1,0.3,0.3])
        self.assertEqual(render.call_args.args[0]['profile']['font_size'],46)      # o resto do perfil continua congelado

    def test_blur_regions_and_brand_survive_the_caption_refinement(self):
        """Com a 2ª passagem ligada o corte é relido do banco; o borrão atual não pode se perder (vazaria o dado escondido)."""
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        region=dict(x=.1,y=.2,w=.3,h=.2,label='chat')
        self.store.save_profile(self.streamer,dict(self.profile,second_pass='small',blur_regions=[region]))
        with patch('liveclips.media.render',return_value=Path(self.temp.name)/'r.mp4') as render, \
                patch.object(self.engine,'do_refine',return_value=True) as refine:
            self.engine.do_render(item['id'],False)
        refine.assert_called_once()
        self.assertEqual(render.call_args.args[0]['profile']['blur_regions'],[region])


if __name__=='__main__':
    unittest.main()
