import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from liveclips.app import App,server
from tests.helpers import setup_session,candidate


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False)
        self.http=server(self.app,0)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.base='http://127.0.0.1:'+str(self.http.server_port)

    def close(self):
        self.http.shutdown();self.http.server_close();self.app.close();self.thread.join(2)

    def request(self,path,data=None,headers=None):
        headers=headers or {}
        body=json.dumps(data).encode() if data is not None else None
        try:
            with urlopen(Request(self.base+path,body,headers=headers),timeout=10) as res:
                return res.status,res.read(),res.headers
        except HTTPError as exc:return exc.code,exc.read(),exc.headers

    def test_home_and_api_require_local_token(self):
        code,body,headers=self.request('/')
        self.assertEqual(code,200);self.assertNotIn(b'__BOOT_TOKEN__',body)
        self.assertIn('<title>Hook’s</title>'.encode(),body);self.assertIn('Estúdio de edição'.encode(),body)
        self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/state')[0],403)
        self.assertEqual(self.request('/api/state',headers={'X-LiveClips-Token':self.app.token})[0],200)

    def test_a_second_server_cannot_share_the_same_port(self):
        with self.assertRaises(OSError):server(self.app,self.http.server_port)

    def test_browser_state_omits_word_snapshots_but_preserves_them_in_database(self):
        streamer,sid,profile=setup_session(self.app.store)
        item,_=candidate(self.app.store,sid)
        data=item['data'];data['transcript_segments']=[dict(start=11,end=12,text='teste')];data['profile']=profile
        with self.app.store.connect(True) as c:c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),item['id']))
        code,body,_=self.request('/api/state',headers={'X-LiveClips-Token':self.app.token})
        self.assertEqual(code,200);state=json.loads(body)
        self.assertNotIn('transcript_segments',state['candidates'][0]['data'])
        self.assertNotIn('profile',state['candidates'][0]['data'])
        self.assertEqual(self.app.store.candidate(item['id'])['data'],data)

    def test_state_reports_real_source_and_camera_crop_resolution(self):
        streamer,sid,_profile=setup_session(self.app.store)
        signature=json.dumps(['h264',2560,1440,'60/1','aac','48000',2])
        with self.app.store.connect(True) as c:
            c.execute('UPDATE segments SET signature=? WHERE session=?',(signature,sid))
        state=self.app.state();session=next(s for s in state['sessions'] if s['id']==sid)
        self.assertEqual(session['source_resolution'],'2560×1440')
        self.assertEqual(session['camera_source_resolution'],'640×432')
        self.assertTrue(session['camera_upscale'])

    def test_cross_site_post_and_forged_host_are_rejected(self):
        payload={'name':'CORINGA'}
        self.assertEqual(self.request('/api/streamer',payload)[0],403)
        self.assertEqual(self.request('/api/streamer',payload,{'X-LiveClips-Token':self.app.token,'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/',headers={'Host':'evil.example'})[0],403)

    def test_create_streamer_and_import_do_not_copy_videos(self):
        legacy=Path(self.temp.name)/'segmentos/2026-TESTE';legacy.mkdir(parents=True)
        source=legacy/'segmento_00000.ts';source.write_bytes(b'original')
        headers={'X-LiveClips-Token':self.app.token}
        code,body,_=self.request('/api/streamer',{'name':'CORINGA'},headers);self.assertEqual(code,200)
        streamer=json.loads(body)['id']
        code,body,_=self.request('/api/import',{'streamer':streamer,'name':'2026-TESTE','closed':True},headers)
        self.assertEqual(code,200)
        session=self.app.store.session(json.loads(body)['id'])
        self.assertEqual(source.read_bytes(),b'original')
        self.assertEqual(list((Path(session['path'])/'segmentos').iterdir()),[])
        self.assertEqual(session['source'],str(legacy.resolve()))

    def test_video_mode_links_file_without_copying_it(self):
        source=Path(self.temp.name)/'episodio.mp4';source.write_bytes(b'video-original')
        streamer=self.app.store.create_streamer('PODCAST')
        with patch('liveclips.app.media.probe',return_value={'duration':120,'width':1920,'height':1080}):
            result=self.app.action('/api/video/import',{'streamer':streamer,'path':str(source),
                                                        'name':'EPISODIO 01','title':'Entrevista',
                                                        'reframe_mode':'dynamic'})
        session=self.app.store.session(result['id'])
        self.assertEqual(session['source'],str(source.resolve()))
        self.assertEqual(source.read_bytes(),b'video-original')
        state=next(x for x in self.app.state()['sessions'] if x['id']==session['id'])
        self.assertEqual(state['content_mode'],'video')
        self.assertEqual(state['reframe_mode'],'dynamic')

    def test_video_url_reuses_capture_pipeline_in_video_mode(self):
        streamer=self.app.store.create_streamer('CANAL')
        inspected={'title':'Episódio','author':'Canal','plugin':'youtube','category':'Podcast'}
        with patch.object(self.app.capture,'inspect',return_value=inspected), \
             patch.object(self.app.capture,'start',return_value='sessao-url') as start:
            result=self.app.action('/api/video/url',{'streamer':streamer,'url':'https://example.com/video',
                                                      'reframe_mode':'dynamic'})
        self.assertEqual(result['id'],'sessao-url')
        meta=start.call_args.args[2]
        self.assertEqual(meta['mode'],'video');self.assertEqual(meta['title'],'Episódio')
        self.assertEqual(meta['reframe_mode'],'dynamic')

    def test_reclassify_backup_archive_and_retry_actions_preserve_reviewed_data(self):
        streamer,sid,_profile=setup_session(self.app.store);item,_=candidate(self.app.store,sid)
        result=self.app.action('/api/regenerate',{'streamer':streamer})
        self.assertEqual(result['replaced'],1);self.assertEqual(self.app.store.candidate(item['id'])['status'],'replaced')
        backup=Path(self.app.action('/api/backup/create',{})['path'])
        self.assertTrue(backup.is_file())
        self.app.action('/api/session/archive',{'session':sid,'archived':True})
        self.assertEqual(self.app.store.session(sid)['status'],'archived')
        self.app.action('/api/session/archive',{'session':sid,'archived':False})
        with self.app.store.connect(True) as c:c.execute("UPDATE sessions SET status='error',error='teste' WHERE id=?",(sid,))
        self.app.action('/api/session/retry',{'session':sid})
        saved=self.app.store.session(sid)
        self.assertEqual(saved['status'],'idle');self.assertEqual(saved['error'],'');self.assertTrue(saved['enabled'])

    def test_manual_cut_opens_analyzed_interval_without_agent_suggestion(self):
        streamer,sid,_profile=setup_session(self.app.store)
        data={'segments':[{'start':5,'end':12,'text':'trecho escolhido pelo usuário','words':[]}],
              'signals':{'audio':[],'motion':[],'facial':[],'warnings':[]}}
        with self.app.store.connect(True) as c:
            c.execute('UPDATE segments SET data=? WHERE session=? AND seq=0',(json.dumps(data),sid))
        result=self.app.action('/api/manual',{'session':sid,'start':5,'end':25})
        item=self.app.store.candidate(result['id'])
        self.assertTrue(result['created']);self.assertEqual(item['manual'],1)
        self.assertEqual(item['data']['reasons'],['Corte manual criado por você'])
        self.assertIn('trecho escolhido',item['data']['transcript'])
        state=next(x for x in self.app.state()['sessions'] if x['id']==sid)
        self.assertGreater(state['analyzed_until'],120)

    def test_manual_cut_rejects_interval_not_yet_analyzed(self):
        _streamer,sid,_profile=setup_session(self.app.store)
        with self.app.store.connect(True) as c:
            c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=1",(sid,))
        with self.assertRaisesRegex(ValueError,'já esteja analisado'):
            self.app.action('/api/manual',{'session':sid,'start':70,'end':85})

    def test_video_range_requests_support_scrubbing(self):
        streamer,sid,profile=setup_session(self.app.store)
        item,_=candidate(self.app.store,sid)
        file=Path(self.app.store.session(sid)['path'])/'previa.mp4';file.write_bytes(b'0123456789')
        with self.app.store.connect(True) as c:c.execute("UPDATE candidates SET preview_status='ready',preview_version=1,preview_path=? WHERE id=?",(str(file),item['id']))
        headers={'Cookie':'lc_session='+self.app.token,'Range':'bytes=2-5'}
        code,body,response=self.request('/media/preview?id='+item['id'],headers=headers)
        self.assertEqual((code,body),(206,b'2345'));self.assertEqual(response['Content-Range'],'bytes 2-5/10')
        headers['Range']='bytes=-3'
        self.assertEqual(self.request('/media/preview?id='+item['id'],headers=headers)[1],b'789')
        headers['Range']='bytes=90-100'
        self.assertEqual(self.request('/media/preview?id='+item['id'],headers=headers)[0],416)

    def test_media_cannot_escape_data_root(self):
        streamer,sid,profile=setup_session(self.app.store);item,_=candidate(self.app.store,sid)
        with tempfile.NamedTemporaryFile(suffix='.mp4',delete=False) as other:other.write(b'privado');outside=Path(other.name)
        self.addCleanup(outside.unlink)
        with self.app.store.connect(True) as c:c.execute("UPDATE candidates SET preview_status='ready',preview_version=1,preview_path=? WHERE id=?",(str(outside),item['id']))
        code,body,_=self.request('/media/preview?id='+item['id'],headers={'Cookie':'lc_session='+self.app.token})
        self.assertEqual(code,400);self.assertNotIn(b'privado',body)

    def test_review_edited_limits_roundtrip_and_approval_queue(self):
        streamer,sid,profile=setup_session(self.app.store);item,_=candidate(self.app.store,sid,50,78)
        edit_id='zoom:2.000:2.800';stored=item['data'];stored['edit_plan']={'decisions':[{'id':edit_id}]}
        with self.app.store.connect(True) as c:
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(stored),item['id']))
        headers={'X-LiveClips-Token':self.app.token}
        data=dict(id=item['id'],version=1,start=57,end=72,action='preview',edit_overrides={edit_id:False})
        code,body,_=self.request('/api/review',data,headers);self.assertEqual(code,200)
        saved=self.app.store.candidate(item['id']);self.assertEqual(len(saved['parts']),2)
        self.assertEqual(saved['data']['edit_overrides'],{edit_id:False})
        self.assertEqual(saved['preview_status'],'queued')
        data.update(version=saved['version'],action='approve')
        self.assertEqual(self.request('/api/review',data,headers)[0],200)
        self.assertEqual(self.app.store.candidate(item['id'])['status'],'approved')


if __name__=='__main__':unittest.main()
