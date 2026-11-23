import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock

from liveclips import media
from liveclips.engine import Engine
from liveclips.capture import Capture
from liveclips.store import DEFAULT_PROFILE,Store
from liveclips.timeline import build_timeline,plan
from tests.helpers import setup_session,candidate


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.streamer,self.sid,self.profile=setup_session(self.store)
        self.engine=Engine(self.store)

    def test_paused_analysis_does_not_run_model(self):
        with patch.object(self.engine,'get_model',side_effect=AssertionError('modelo não deveria iniciar')):
            self.assertFalse(self.engine.work_once())

    def test_user_requested_preview_runs_while_analysis_paused(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'preview')
        with patch.object(self.engine,'do_render') as render:
            self.assertTrue(self.engine.work_once())
            render.assert_called_once_with(item['id'],True)

    def test_low_space_does_not_claim_or_lose_approved_task(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        with patch('liveclips.media.free_bytes',return_value=0):
            with self.assertRaises(media.LowSpace):self.engine.work_once()
        self.assertEqual(self.store.candidate(item['id'])['status'],'approved')

    def test_modified_source_blocks_export_without_retry_loop(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        Path(item['parts'][0]['path']).write_bytes(b'alterado')
        with patch('liveclips.media.render',side_effect=AssertionError('não deveria renderizar')):
            self.engine.do_render(item['id'],False)
        saved=self.store.candidate(item['id'])
        self.assertEqual(saved['status'],'error');self.assertIn('foi alterado',saved['error']);self.assertIn(Path(item['parts'][0]['path']).name,saved['error'])

    def test_missing_source_says_where_it_was_and_how_to_fix(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        Path(item['parts'][0]['path']).unlink()
        with patch('liveclips.media.render',side_effect=AssertionError('não deveria renderizar')):
            self.engine.do_render(item['id'],False)
        saved=self.store.candidate(item['id'])
        self.assertEqual(saved['status'],'error')
        self.assertIn('não está mais em',saved['error']);self.assertIn('Religar original',saved['error'])

    def test_frozen_profile_used_when_streamer_profile_changes(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        self.store.save_profile(self.streamer,dict(self.profile,font_size=60))
        with patch('liveclips.media.render',return_value=Path(self.temp.name)/'resultado.mp4') as render:
            self.engine.do_render(item['id'],False)
        self.assertEqual(render.call_args.args[0]['profile']['font_size'],46)
        self.assertEqual(self.store.candidate(item['id'])['status'],'done')

    def test_stale_preview_result_does_not_overwrite_new_edit(self):
        item,_=candidate(self.store,self.sid)
        version=self.store.review(item['id'],1,10,30,item['parts'],'preview')
        parts=plan(build_timeline(self.store.segments(self.sid)),11,31,item['group_id'])
        def render(*args,**kwargs):
            self.store.review(item['id'],version,11,31,parts,'save')
            return Path(self.temp.name)/'antiga.mp4'
        with patch('liveclips.media.render',side_effect=render):self.engine.do_render(item['id'],True)
        saved=self.store.candidate(item['id'])
        self.assertEqual(saved['start'],11);self.assertNotEqual(saved['preview_status'],'ready')

    def test_original_change_is_not_silently_registered_again(self):
        row=self.store.segments(self.sid)[0];Path(row['path']).write_bytes(b'novo')
        with self.assertRaisesRegex(ValueError,'mudou'):self.engine.scan_one(self.store.session(self.sid))

    def test_stalled_open_file_is_not_mistaken_for_completed_segment(self):
        with self.store.connect(True) as c:
            c.execute('UPDATE sessions SET closed=0 WHERE id=?',(self.sid,))
            c.execute('DELETE FROM segments WHERE session=? AND seq=1',(self.sid,))
        with patch('liveclips.media.probe',side_effect=AssertionError('último arquivo continua aberto')):
            self.assertFalse(self.engine.scan_one(self.store.session(self.sid)))
        with self.store.connect(True) as c:c.execute('UPDATE sessions SET closed=1 WHERE id=?',(self.sid,))
        with patch('liveclips.media.probe',return_value=dict(duration=58.1,signature='same-format')):
            self.assertTrue(self.engine.scan_one(self.store.session(self.sid)))

    def test_analysis_waits_for_full_transcript_and_stores_words(self):
        with self.store.connect(True) as c:c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=0",(self.sid,))
        model=MagicMock();seg=SimpleNamespace(start=1,end=3,text='meu deus',
            words=[SimpleNamespace(start=1,end=2,word='meu'),SimpleNamespace(start=2,end=3,word='deus')])
        model.transcribe.return_value=(iter([seg]),SimpleNamespace(language='pt'))
        with patch.object(self.engine,'get_model',return_value=model),patch('liveclips.engine.extrair',return_value={'audio':[],'motion':[]}):
            self.engine.analyze_one(self.store.session(self.sid),self.profile)
        data=self.store.segments(self.sid)[0]['data']
        self.assertEqual(data['segments'][0]['words'][1]['word'],'deus')
        self.assertTrue(model.transcribe.call_args.kwargs['word_timestamps'])

    def test_streamer_dictionary_guides_spelling_without_replacing_transcript(self):
        with self.store.connect(True) as c:c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=0",(self.sid,))
        profile=dict(self.profile,vocabulary='Coringa, Fortnite, Unreal Engine')
        self.store.save_profile(self.streamer,profile)
        model=MagicMock();model.transcribe.return_value=(iter([]),SimpleNamespace(language='pt'))
        with patch.object(self.engine,'get_model',return_value=model),patch('liveclips.engine.extrair',return_value={'audio':[],'motion':[]}):
            self.engine.analyze_one(self.store.session(self.sid),profile)
        prompt=model.transcribe.call_args.kwargs['initial_prompt']
        self.assertIn('Fortnite',prompt);self.assertIn('Grafias esperadas',prompt)

    def test_context_suggestions_run_before_analyzing_more_files(self):
        self.store.setting('paused',False)
        with patch.object(self.engine,'scan_one',return_value=False), \
             patch.object(self.engine,'suggest_one',return_value=True) as suggest, \
             patch.object(self.engine,'analyze_one',side_effect=AssertionError('contexto pronto tem prioridade')):
            self.assertTrue(self.engine.work_once());self.assertEqual(suggest.call_count,1)

    def test_online_video_analysis_is_not_starved_by_download_backlog(self):
        self.store.setting('paused',False)
        session_path=Path(self.store.session(self.sid)['path'])
        (session_path/'fonte.json').write_text(json.dumps({'mode':'video'}),encoding='utf-8')
        with patch.object(self.engine,'suggest_one',return_value=False), \
             patch.object(self.engine,'analyze_one',return_value=True) as analyze, \
             patch.object(self.engine,'scan_one',side_effect=AssertionError('não deve cadastrar toda a fila primeiro')):
            self.assertTrue(self.engine.work_once())
        analyze.assert_called_once()

    def test_profile_change_during_analysis_discards_old_result(self):
        with self.store.connect(True) as c:c.execute("UPDATE segments SET status='new',data='{}' WHERE session=? AND seq=0",(self.sid,))
        model=MagicMock();model.transcribe.return_value=(iter([]),SimpleNamespace(language='pt'))
        def signals(*args,**kwargs):
            self.store.save_profile(self.streamer,dict(self.profile,language='en'))
            return dict(audio=[],motion=[])
        with patch.object(self.engine,'get_model',return_value=model),patch('liveclips.engine.extrair',side_effect=signals):
            self.engine.analyze_one(self.store.session(self.sid),self.profile)
        row=self.store.segments(self.sid)[0]
        self.assertEqual(row['status'],'new');self.assertEqual(row['data'],{})

    def test_approved_caption_snapshot_survives_profile_reanalysis(self):
        item,_=candidate(self.store,self.sid)
        transcript=[dict(start=11,end=12,text='original',words=[dict(start=11,end=12,word='original')])]
        self.store.review(item['id'],1,10,30,item['parts'],'approve',transcript=transcript)
        self.store.save_profile(self.streamer,dict(self.profile,language='en'))
        self.assertTrue(all(s['status']=='new' for s in self.store.segments(self.sid)))
        with patch('liveclips.media.render',return_value=Path(self.temp.name)/'resultado.mp4') as render:
            self.engine.do_render(item['id'],False)
        self.assertEqual(render.call_args.args[1],transcript)

    def test_preview_error_after_edit_does_not_mark_new_revision_as_failed(self):
        item,_=candidate(self.store,self.sid)
        version=self.store.review(item['id'],1,10,30,item['parts'],'preview')
        parts=plan(build_timeline(self.store.segments(self.sid)),11,31,item['group_id'])
        def render(*args,**kwargs):
            self.store.review(item['id'],version,11,31,parts,'save')
            raise RuntimeError('falha da revisão antiga')
        with patch('liveclips.media.render',side_effect=render):self.engine.do_render(item['id'],True)
        saved=self.store.candidate(item['id'])
        self.assertEqual(saved['start'],11);self.assertEqual(saved['error'],'')
        self.assertEqual(saved['preview_status'],'')

    def test_rejection_during_preflight_cancels_export(self):
        item,_=candidate(self.store,self.sid)
        version=self.store.review(item['id'],1,10,30,item['parts'],'approve')
        original=media.sha_file
        def digest(path):
            self.store.review(item['id'],version,10,30,item['parts'],'reject')
            return original(path)
        with patch('liveclips.engine.media.sha_file',side_effect=digest),patch('liveclips.media.render') as render:
            self.engine.do_render(item['id'],False)
        render.assert_not_called();self.assertEqual(self.store.candidate(item['id'])['status'],'rejected')

    def test_recover_receipt_after_crash_before_database_commit(self):
        item,_=candidate(self.store,self.sid)
        self.store.review(item['id'],1,10,30,item['parts'],'approve')
        saved=self.store.candidate(item['id'])
        parent=Path(self.store.session(self.sid)['path'])/'cortes'
        folder=parent/(item['id']+'_'+media.signature(saved)[:12]);folder.mkdir(parents=True)
        video=folder/'clipe.mp4';video.write_bytes(b'exportacao ja finalizada')
        (folder/'manifesto.json').write_text(json.dumps({'signature':media.signature(saved),'video_sha':media.sha_file(video)}))
        with self.store.connect(True) as c:c.execute("UPDATE candidates SET status='exporting' WHERE id=?",(item['id'],))
        recovered=Store(self.temp.name)
        with patch('liveclips.media.run',side_effect=AssertionError('não deve gerar o mesmo vídeo outra vez')):
            Engine(recovered).do_render(item['id'],False)
        self.assertEqual(recovered.candidate(item['id'])['status'],'done')
        self.assertEqual(list(parent.iterdir()),[folder])


class MediaTests(unittest.TestCase):
    def test_probe_reads_real_fractional_frame_rate(self):
        payload={'streams':[{'codec_type':'video','codec_name':'h264','width':2560,'height':1440,
                             'avg_frame_rate':'60000/1001'},
                            {'codec_type':'audio','codec_name':'aac','sample_rate':'48000','channels':2}],
                 'format':{'duration':'60.0'}}
        with patch('liveclips.media.tool',return_value='ffprobe'),patch('liveclips.media.run',return_value=json.dumps(payload).encode()):
            info=media.probe('source.ts')
        self.assertAlmostEqual(info['fps'],59.94,places=2)

    def test_cross_file_assembly_trims_using_local_times_and_adds_silent_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=[{'path':'A.ts','in':58,'out':62.4},{'path':'B.ts','in':0,'out':7.6}]
            info=dict(width=2560,height=1440,fps=60,has_audio=False)
            with patch('liveclips.media.tool',side_effect=lambda x:x),patch('liveclips.media.probe',return_value=info), \
                 patch('liveclips.media.run') as run:
                joined,offset,duration=media.assemble(parts,Path(temp),2)
            self.assertAlmostEqual(duration,12);self.assertEqual(offset,0)
            commands=[call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0][commands[0].index('-ss')+1],'58')
            self.assertEqual(commands[1][commands[1].index('-ss')+1],'0')
            self.assertLess(commands[0].index('-i'),commands[0].index('-ss'))
            self.assertLess(commands[1].index('-i'),commands[1].index('-ss'))
            self.assertIn('anullsrc=r=48000:cl=stereo',commands[1])
            self.assertIn('scale=2560:1440:flags=lanczos,setsar=1,fps=60',commands[0])
            self.assertEqual(commands[0][commands[0].index('-crf')+1],'15')
            self.assertIn('partes.txt',commands[-1])

    def test_visual_fingerprint_uses_central_frame_and_perceptual_hash(self):
        pixels=bytes(9-col for _row in range(8) for col in range(9))
        parts=[{'path':'A.ts','in':10,'out':20},{'path':'B.ts','in':0,'out':10}]
        with patch('liveclips.media.tool',return_value='ffmpeg'),patch('liveclips.media.run',return_value=pixels) as run:
            fingerprint=media.visual_fingerprint(parts)
        self.assertEqual(fingerprint,'ffffffffffffffff')
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-ss')+1],'0.0')
        self.assertIn('scale=9:8:flags=area,format=gray',command)

    def test_final_export_targets_1080x1920_with_quality_encode(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.ts';source.write_bytes(b'original')
            profile=dict(DEFAULT_PROFILE,camera_rect=[.7,.05,.25,.3],min_free_gb=.5)
            parts=[{'path':str(source),'sha':'abc','seq':0,'in':0,'out':2,
                    'global_start':0,'global_end':2,'group_id':'g'}]
            candidate={'id':'clip','start':0,'end':2,'parts':parts,'profile':profile,'data':{}}
            commands=[]
            def fake_run(args,*_args,**_kwargs):
                commands.append(args);Path(args[-1]).write_bytes(b'video');return b''
            source_info={'width':2560,'height':1440,'duration':2,'fps':60,'has_audio':True}
            output_info={'width':1080,'height':1920,'duration':2,'fps':60,'has_audio':True}
            with patch('liveclips.media.require_space'),patch('liveclips.media.assemble',return_value=(source,0,2)), \
                 patch('liveclips.media.probe',side_effect=[source_info,output_info]), \
                 patch('liveclips.media.tool',side_effect=lambda name:name),patch('liveclips.media.run',side_effect=fake_run):
                result=media.render(candidate,[],temp,False,pipeline='legacy')
            self.assertTrue(result.is_file());command=commands[0]
            self.assertLess(command.index('-i'),command.index('-ss'))
            filters=command[command.index('-filter_complex')+1]
            self.assertIn('[0:v]fps=60',filters)
            self.assertIn('scale=1080:640',filters);self.assertIn('scale=1080:1280',filters)
            self.assertIn('vstack=inputs=2,setsar=1',filters)
            self.assertLess(filters.index('scale=1080:640'),filters.index('scale=1080:1280'))
            self.assertEqual(command[command.index('-preset')+1],'medium')
            self.assertEqual(command[command.index('-crf')+1],'18')
            self.assertEqual(command[command.index('-profile:v')+1],'high')

    def test_creative_profile_applies_only_agent_supported_camera_punches(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.ts';source.write_bytes(b'original')
            profile=dict(DEFAULT_PROFILE,camera_rect=[.7,.05,.25,.3],min_free_gb=.5,editorial_style='creative')
            parts=[{'path':str(source),'sha':'abc','seq':0,'in':0,'out':2,
                    'global_start':0,'global_end':2,'group_id':'g'}]
            candidate={'id':'creative','start':0,'end':2,'parts':parts,'profile':profile,
                       'data':{'edit_plan':{'source_start':0,'punches':[{'start':.5,'end':1.3,'zoom':1.08}]}}}
            commands=[]
            def fake_run(args,*_args,**_kwargs):commands.append(args);Path(args[-1]).write_bytes(b'video');return b''
            source_info={'width':1920,'height':1080,'duration':2,'fps':30,'has_audio':True}
            output_info={'width':1080,'height':1920,'duration':2,'fps':30,'has_audio':True}
            with patch('liveclips.media.require_space'),patch('liveclips.media.assemble',return_value=(source,0,2)), \
                 patch('liveclips.media.probe',side_effect=[source_info,output_info]), \
                 patch('liveclips.media.tool',side_effect=lambda name:name),patch('liveclips.media.run',side_effect=fake_run):
                media.render(candidate,[],temp,False,pipeline='legacy')
            filters=commands[0][commands[0].index('-filter_complex')+1]
            self.assertIn('zoompan=',filters);self.assertIn('between((on/30),0.5,1.3)',filters)

    def test_video_mode_preserves_full_frame_and_needs_no_webcam(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'podcast.mp4';source.write_bytes(b'original')
            profile=dict(DEFAULT_PROFILE,camera_rect=None,content_mode='video',min_free_gb=.5)
            parts=[{'path':str(source),'sha':'abc','seq':0,'in':0,'out':2,
                    'global_start':0,'global_end':2,'group_id':'g'}]
            candidate={'id':'video','start':0,'end':2,'parts':parts,'profile':profile,'data':{}}
            commands=[]
            def fake_run(args,*_args,**_kwargs):
                commands.append(args);Path(args[-1]).write_bytes(b'video');return b''
            source_info={'width':1920,'height':1080,'duration':2,'fps':30,'has_audio':True}
            output_info={'width':1080,'height':1920,'duration':2,'fps':30,'has_audio':True}
            with patch('liveclips.media.require_space'),patch('liveclips.media.assemble',return_value=(source,0,2)), \
                 patch('liveclips.media.probe',side_effect=[source_info,output_info]), \
                 patch('liveclips.media.tool',side_effect=lambda name:name),patch('liveclips.media.run',side_effect=fake_run):
                result=media.render(candidate,[],temp,False,pipeline='legacy')
            self.assertTrue(result.is_file());filters=commands[0][commands[0].index('-filter_complex')+1]
            self.assertIn('gblur=sigma=28',filters)
            self.assertIn('force_original_aspect_ratio=decrease',filters)
            self.assertIn('split=2[bg][fg]',filters)
            self.assertIn('[safe]setsar=1',filters)
            self.assertNotIn('[zoom]',filters)
            self.assertNotIn('[cam]',filters)

    def test_dynamic_video_mode_only_closes_in_confident_face_intervals(self):
        info={'width':1920,'height':1080}
        plan=[{'start':0,'end':1.5,'face':False,'x':.5,'scene':False},
              {'start':1.5,'end':3,'face':True,'x':.25,'scene':True},
              {'start':3,'end':4.5,'face':True,'x':.30,'scene':False},
              {'start':4.5,'end':6,'face':False,'x':.5,'scene':True}]
        filters=media.video_filters(30,info,plan)
        self.assertIn('[close]',filters)
        self.assertIn("enable='between(t,1.5,3)+between(t,3,4.5)'",filters)
        self.assertIn('[safe][close]overlay',filters)
        self.assertNotIn('between(t,0,1.5)',filters)

    def test_caption_times_crossing_boundary_are_relative_to_final_cut(self):
        from liveclips.captions import make_ass
        from liveclips.timeline import shifted_transcript
        rows=[dict(start=0,data={'segments':[dict(start=59,end=61,text='meu deus',words=[dict(start=59,end=60,word='meu'),dict(start=60,end=61,word='deus')])]}),
              dict(start=62.4,data={'segments':[dict(start=1,end=3,text='ganhamos',words=[dict(start=1,end=3,word='ganhamos')])]})]
        output=make_ass(shifted_transcript(rows),58,70,52,300,'00E8FF')
        self.assertIn('0:00:01.00,0:00:02.00',output)
        self.assertIn('0:00:05.40,0:00:07.40',output)
        self.assertIn('Arial,52,',output)

    def test_invalid_receipt_does_not_trust_partial_video(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate=dict(id='abc',start=1,end=2,parts=[],profile={})
            dest=Path(temp)/('abc_'+media.signature(candidate)[:12]);dest.mkdir()
            (dest/'clipe.mp4').write_bytes(b'incompleto')
            self.assertIsNone(media.receipt(candidate,temp))

    def test_tool_locator_accepts_verified_custom_path(self):
        with tempfile.TemporaryDirectory() as temp:
            executable=Path(temp)/'ffprobe.exe';executable.write_bytes(b'local')
            with patch.dict(media.os.environ,{'LIVECLIPS_FFPROBE':str(executable)}):
                self.assertEqual(media.find_tool('ffprobe'),str(executable.resolve()))


class CaptureTests(unittest.TestCase):
    def test_1440p_quality_has_source_only_fallbacks(self):
        from liveclips.capture import QUALITY_FALLBACKS
        order=QUALITY_FALLBACKS['1440p'].split(',')
        self.assertEqual(order[:4],['1440p','1440p60','1080p60','1080p'])
        self.assertNotIn('2160p',order)

    def test_stop_finalizes_pipe_before_closing_session(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);streamer=store.create_streamer('CORINGA')
            store.save_profile(streamer,dict(store.streamer(streamer)['profile'],min_free_gb=.5))
            producer=MagicMock();consumer=MagicMock();producer.poll.return_value=None;consumer.poll.return_value=None
            capture=Capture(store)
            with patch('liveclips.capture.media.tool',side_effect=lambda name:name), \
                 patch('liveclips.capture.subprocess.Popen',side_effect=[producer,consumer]), \
                 patch('liveclips.capture.threading.Thread.start'):
                sid=capture.start(streamer,'https://example.org/live')
                self.assertTrue(store.session(sid)['source'].startswith(str(Path(temp)/'CORINGA')))
                self.assertFalse(store.session(sid)['closed'])
                capture.stop()
            producer.terminate.assert_called_once();consumer.wait.assert_called()
            self.assertTrue(store.session(sid)['closed']);self.assertIsNone(capture.state())

    def test_capture_refuses_unsafe_url_and_low_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);streamer=store.create_streamer('CORINGA');capture=Capture(store)
            for url in ('file:///C:/secret','http://user:pass@example.org/live','não é link'):
                with self.assertRaises(ValueError):capture.start(streamer,url)
            with patch('liveclips.media.free_bytes',return_value=0),self.assertRaises(media.LowSpace):
                capture.start(streamer,'https://example.org/live')
            self.assertEqual(store.rows('SELECT * FROM sessions'),[])


if __name__=='__main__':unittest.main()
