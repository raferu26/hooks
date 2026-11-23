import unittest
import tempfile

from liveclips.capture import streamlink_options
from liveclips.editing import (EDITOR_PRESETS,camera_zoom_filter,cuts_for,plan_edits,punches_for,
                               retime_points,retime_transcript)
from liveclips.media import signature
from liveclips.store import Store
from liveclips.timeline import build_timeline,plan
from tests.helpers import setup_session


class AgentEditingTests(unittest.TestCase):
    def test_punches_require_two_modalities_and_spacing(self):
        candidate={'start':10,'end':32}
        signals={'audio':[{'time':12,'strength':2},{'time':13,'strength':2},{'time':22,'strength':2}],
                 'motion':[{'time':12.2,'strength':1.5},{'time':13.2,'strength':1.5},
                           {'time':22.2,'strength':1.5}]}
        plan=plan_edits(candidate,signals)
        self.assertEqual(len(plan['punches']),2)
        self.assertEqual(plan_edits(candidate,{'audio':signals['audio']})['punches'],[])

    def test_trim_rebases_plan_and_signature_changes_with_edit(self):
        candidate={'id':'x','start':12,'end':20,'profile':{},'parts':[],
                   'data':{'edit_plan':{'source_start':10,'punches':[{'start':3,'end':4,'zoom':1.08}]}}}
        self.assertEqual(punches_for(candidate)[0]['start'],1)
        before=signature(candidate);candidate['data']['edit_plan']['punches']=[]
        self.assertNotEqual(before,signature(candidate))
        before=signature(candidate);candidate['data']['edit_overrides']={'zoom:1.000:2.000':False}
        self.assertNotEqual(before,signature(candidate))

    def test_zoom_expression_is_bounded_and_absent_without_plan(self):
        self.assertEqual(camera_zoom_filter([],30),'')
        value=camera_zoom_filter([{'start':1,'end':1.8,'zoom':1.08}],30)
        self.assertIn('between((on/30),1,1.8)',value)
        self.assertIn('1.08',value)
        self.assertEqual(camera_zoom_filter([{'start':1,'end':1.8,'zoom':1.5}],30),'')

    def test_every_professional_style_builds_an_explainable_plan(self):
        candidate={'start':10,'end':35}
        signals={'audio':[{'time':15,'strength':2}],
                 'motion':[{'time':15.2,'strength':1.6,'confidence':.9}]}
        for style in EDITOR_PRESETS:
            result=plan_edits(candidate,signals,profile={'editorial_style':style,'auto_zoom':True})
            self.assertEqual(result['preset'],style)
            self.assertTrue(result['preset_label'])
            self.assertTrue(all({'id','label','reason','enabled'}<=set(row) for row in result['decisions']))
        self.assertFalse(plan_edits(candidate,signals,profile={'editorial_style':'clean'})['decisions'][0]['enabled'])

    def test_silence_and_repetition_are_safe_reversible_and_retimed(self):
        transcript=[{'start':10,'end':18,'text':'né né depois',
                     'words':[{'start':11,'end':11.2,'word':'né'},
                              {'start':11.25,'end':11.45,'word':'né'},
                              {'start':13.5,'end':14,'word':'depois'}]}]
        plan=plan_edits({'start':10,'end':18},{},transcript,
                        {'editorial_style':'podcast','auto_silence':True,'auto_repetition':True})
        candidate={'start':10,'end':18,'data':{'edit_plan':plan,'edit_overrides':{}}}
        cuts=cuts_for(candidate)
        self.assertEqual({row['kind'] for row in cuts},{'repetition','silence'})
        repetition=next(row for row in plan['decisions'] if row['kind']=='repetition')
        self.assertTrue(repetition['requires_review'])
        candidate['data']['edit_overrides']={repetition['id']:False}
        self.assertEqual({row['kind'] for row in cuts_for(candidate)},{'silence'})
        shifted=retime_points([{'start':3,'end':4}],cuts_for(candidate))
        self.assertLess(shifted[0]['start'],3)
        words=retime_transcript(transcript,10,18,cuts_for(candidate))[0]['words']
        self.assertTrue(all(word['end']>=word['start'] for word in words))

    def test_capture_prefers_ipv4_and_retries_segments(self):
        options=streamlink_options('https://www.twitch.tv/coringa')
        self.assertIn('--ipv4',options);self.assertIn('--retry-open',options)
        self.assertIn('--stream-segment-attempts',options);self.assertIn('--http-timeout',options)
        self.assertTrue(any('twitch-supported-codecs' in value for value in options))

    def test_only_five_best_exploratory_candidates_remain_visible(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);_,sid,profile=setup_session(store,durations=(180,))
            timeline=build_timeline(store.segments(sid))
            for index,score in enumerate((1,2,3,4,5,9)):
                start=index*20;end=start+12;parts=plan(timeline,start,end)
                data={'start':start,'end':end,'group_id':parts[0]['group_id'],'score':score,
                      'reasons':['exploratório'],'transcript':'fala completa para revisar',
                      'fallback':True,'low_confidence':True}
                store.propose(sid,data,parts,profile);store.trim_fallbacks(sid,5)
            active=store.rows("SELECT score FROM candidates WHERE session=? AND status='pending'",(sid,))
            self.assertEqual(len(active),5)
            self.assertNotIn(1,{row['score'] for row in active})


if __name__=='__main__':unittest.main()
