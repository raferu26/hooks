import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import media,qc,qc_visual as qv


def ffmpeg(*args):
    cp=subprocess.run([media.tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y',*args],capture_output=True,timeout=120)
    if cp.returncode:raise RuntimeError(cp.stderr.decode()[-400:])


ASS_HEAD='''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Principal,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,40,40,%d,1
Style: Titulo,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,8,40,40,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def ass(margin,style='Principal',text='Texto de legenda de teste para medir'):
    return ASS_HEAD%margin+f'Dialogue: 0,0:00:01.00,0:00:03.00,{style},,0,0,0,,{text}\n'


class ParseTests(unittest.TestCase):
    def test_freeze_without_end_runs_to_the_end(self):
        text='lavfi.freezedetect.freeze_start: 1.5\nlavfi.freezedetect.freeze_end: 4\nlavfi.freezedetect.freeze_start: 6'
        self.assertEqual(qv.parse_freeze(text,9),[(1.5,4.0),(6.0,9.0)])

    def test_silence_and_volume_and_crop(self):
        self.assertEqual(qv.parse_silence('silence_start: 0\nsilence_end: 1.2 | silence_duration: 1.2\nsilence_start: 5',8),[(0.0,1.2),(5.0,8.0)])
        self.assertEqual(qv.parse_volume('max_volume: -0.0 dB\nhistogram_0db: 812'),dict(max_db=0.0,zero_db=812))
        self.assertIsNone(qv.parse_volume('n_samples: 0'))
        self.assertEqual(qv.parse_crop('crop=\ncrop=100:50:10:20\ncrop=200:60:5:25'),(5,20,205,85))
        self.assertIsNone(qv.parse_crop('crop=\n'))


class RuleTests(unittest.TestCase):
    def test_freeze_ignores_short_and_planned_stops(self):
        self.assertEqual(qv.freeze_check([(1,2.5)],10)['status'],'ok')
        self.assertEqual(qv.freeze_check([(2,5)],10,planned=[(2,5)])['status'],'ok')
        self.assertEqual(qv.freeze_check([(2,5)],10)['status'],'atencao')
        self.assertEqual(qv.freeze_check([(0,8)],10)['status'],'erro')

    def test_start_check(self):
        self.assertEqual(qv.start_check([],[],10)['status'],'ok')
        self.assertEqual(qv.start_check([],[(0,1.4)],10)['status'],'atencao')
        self.assertEqual(qv.start_check([(0,3)],[(0,2.5)],10)['status'],'erro')
        self.assertEqual(qv.start_check([(4,8)],[(5,8)],10)['status'],'ok')    # parado no meio não é "começo"

    def test_clipping_levels(self):
        self.assertEqual(qv.clipping_check(None)['status'],'ok')
        self.assertEqual(qv.clipping_check(dict(max_db=-3,zero_db=0))['status'],'ok')
        self.assertEqual(qv.clipping_check(dict(max_db=0,zero_db=40))['status'],'atencao')
        self.assertEqual(qv.clipping_check(dict(max_db=0,zero_db=900))['status'],'erro')

    def test_sync_check(self):
        v=dict(start=0,duration=10)
        self.assertEqual(qv.sync_check(v,dict(start=.02,duration=9.98))['status'],'ok')
        self.assertEqual(qv.sync_check(v,dict(start=.3,duration=10))['status'],'atencao')
        self.assertEqual(qv.sync_check(v,dict(start=0,duration=8.5))['status'],'erro')
        self.assertEqual(qv.sync_check(v,None)['status'],'ok')

    def test_face_on_the_edge_is_flagged_and_no_face_says_nothing(self):
        self.assertIsNone(qv.face_edge_check([[],[]]))
        ok=qv.face_edge_check([[(.3,.2,.3,.3)],[(.35,.25,.3,.3)]])
        self.assertEqual(ok['status'],'ok')
        some=qv.face_edge_check([[(.3,.2,.3,.3)],[(.0,.2,.3,.3)],[(.3,.2,.3,.3)]])
        self.assertEqual(some['status'],'atencao')
        every=qv.face_edge_check([[(.5,-.1,.3,.3)]]*4)
        self.assertEqual(every['status'],'erro')

    def test_caption_render_zones(self):
        zones=qc.ZONAS;canvas=(1080,1920)
        self.assertEqual(qv.caption_render_check((200,1300,880,1440),canvas,zones)[0]['status'],'ok')
        low=qv.caption_render_check((200,1700,880,1800),canvas,zones)[0]
        self.assertEqual(low['status'],'atencao');self.assertIn('120 px do fim',low['detail'])
        right=qv.caption_render_check((300,1000,1000,1100),canvas,zones)[0]
        self.assertIn('borda direita',right['detail'])
        self.assertEqual(qv.caption_render_check(None,canvas,zones)[0]['status'],'atencao')
        self.assertEqual(qv.caption_render_check(None,canvas,zones,captions=False),[])


class RealVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.dir=Path(cls.temp.name)
        d=cls.dir
        # vídeo bom: movimento o tempo todo + tom moderado
        ffmpeg('-f','lavfi','-i','testsrc2=s=1080x1920:r=30:d=6','-f','lavfi','-i','sine=frequency=300:duration=6','-af','volume=-10dB',
               '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(d/'bom.mp4'))
        # começo parado + mudo, e áudio estourado no fim
        ffmpeg('-f','lavfi','-i','color=c=0x303030:s=1080x1920:r=30:d=3','-f','lavfi','-i','testsrc2=s=1080x1920:r=30:d=3',
               '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(d/'v_parado.mp4'))
        ffmpeg('-f','lavfi','-i','sine=frequency=440:duration=6','-af','volume=35dB,adelay=2500|2500','-c:a','aac',str(d/'a_estourado.m4a'))
        ffmpeg('-i',str(d/'v_parado.mp4'),'-i',str(d/'a_estourado.m4a'),'-c','copy','-shortest',str(d/'ruim.mp4'))

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def ids(self,items):return {i['id']:i for i in items}

    def test_clean_video_has_no_visual_warnings(self):
        items,samples=qv.visual_checks(self.dir/'bom.mp4',6.0,samples_dir=self.dir/'am_bom')
        got=self.ids(items)
        for key in ('congelado','estouro','sincronia','comeco'):self.assertEqual(got[key]['status'],'ok',got[key])
        self.assertEqual(len(samples),3)
        for name in samples:self.assertGreater((self.dir/'am_bom'/name).stat().st_size,1000)

    def test_bad_video_is_flagged_for_freeze_start_and_clipping(self):
        items,_=qv.visual_checks(self.dir/'ruim.mp4',6.0)
        got=self.ids(items)
        self.assertEqual(got['congelado']['status'],'atencao')
        self.assertIn(got['estouro']['status'],('atencao','erro'))
        self.assertEqual(got['comeco']['status'],'erro')      # parado e mudo por ~2,5 s e 3 s

    def test_planned_freeze_is_not_reported(self):
        items,_=qv.visual_checks(self.dir/'ruim.mp4',6.0,planned_freezes=[(0,3)])
        self.assertEqual(self.ids(items)['congelado']['status'],'ok')

    def test_caption_is_measured_by_drawing_it(self):
        bbox_low=qv.render_caption_bbox(ass(30),(1080,1920),4)
        bbox_ok=qv.render_caption_bbox(ass(400),(1080,1920),4)
        self.assertIsNotNone(bbox_low)
        self.assertGreater(bbox_low[3],1800)             # quase colada no fim do quadro
        self.assertLess(bbox_ok[3],1600)
        self.assertIsNone(qv.render_caption_bbox(ass(300,style='Titulo'),(1080,1920),4))   # título não conta como legenda

    def test_a_caption_that_runs_under_the_side_buttons_is_flagged(self):
        got=qv.caption_render_check(qv.render_caption_bbox(ass(420),(1080,1920),4),(1080,1920),qc.ZONAS)[0]
        self.assertIn('borda direita',got['detail'])

    def test_visual_checks_use_the_drawn_caption_in_the_report(self):
        (self.dir/'baixa.ass').write_text(ass(30),encoding='utf-8-sig')
        report=qc.check_export(self.dir/'bom.mp4',self.dir/'baixa.ass',samples_dir=self.dir/'am_rel')
        got=self.ids(report['items'])
        self.assertEqual(got['legenda_render']['status'],'atencao')
        self.assertNotIn('zona_inferior',got)             # a medida real substitui a estimativa
        self.assertEqual(len(report['samples']),3)
        self.assertIn(report['level'],('atencao','erro'))   # o tom de teste é baixo demais para o alvo de volume
        (self.dir/'alta.ass').write_text(ass(420,text='Legenda curta'),encoding='utf-8-sig')
        report=qc.check_export(self.dir/'bom.mp4',self.dir/'alta.ass')
        self.assertEqual(self.ids(report['items'])['legenda_render']['status'],'ok')

    def test_old_behaviour_is_still_available_without_the_visual_layer(self):
        report=qc.check_export(self.dir/'bom.mp4',visual=False)
        self.assertNotIn('congelado',self.ids(report['items']))
        self.assertEqual(report['samples'] if 'samples' in report else [],[])

    def test_a_missing_tool_never_raises(self):
        items,samples=qv.visual_checks(self.dir/'nao_existe.mp4',5.0,samples_dir=self.dir/'x')
        self.assertTrue(all(i['status']!='erro' for i in items))
        self.assertEqual(samples,[])


if __name__=='__main__':unittest.main()
