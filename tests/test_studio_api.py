import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from liveclips import assets, media, music
from liveclips.app import App, server
from liveclips.timeline import build_timeline, plan
from tests.helpers import candidate, setup_session


def png(path, size='64x48'):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    f'color=c=red:s={size}', '-frames:v', '1', str(path)], check=True)


def tone(path, seconds=3):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    f'sine=frequency=440:duration={seconds}', str(path)], check=True)


class StudioApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name, worker=False)
        self.http = server(self.app, 0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.base = 'http://127.0.0.1:' + str(self.http.server_port)
        self.streamer, self.sid, _ = setup_session(self.app.store)
        self.item, _ = candidate(self.app.store, self.sid)
        words = [dict(start=10.5 + i * .4, end=10.85 + i * .4, word=w) for i, w in enumerate(
            'Gente olha isso aqui agora porque ninguem acredita nisso'.split())]
        data = self.item['data']
        data['transcript_segments'] = [dict(start=10.5, end=14.5, text=' '.join(w['word'] for w in words), words=words)]
        with self.app.store.connect(True) as c:
            c.execute('UPDATE candidates SET data=? WHERE id=?', (json.dumps(data), self.item['id']))

    def close(self):
        self.http.shutdown(); self.http.server_close(); self.app.close(); self.thread.join(2)

    def post(self, path, data, raw=None, headers=None):
        head = {'X-LiveClips-Token': self.app.token}
        head.update(headers or {})
        body = raw if raw is not None else json.dumps(data).encode()
        try:
            with urlopen(Request(self.base + path, body, headers=head), timeout=20) as res:
                return res.status, json.loads(res.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_project_get_returns_editable_lines_and_catalogs(self):
        code, got = self.post('/api/project/get', dict(id=self.item['id']))
        self.assertEqual(code, 200)
        self.assertFalse(got['saved']); self.assertFalse(got['lines_edited'])
        self.assertEqual(got['duration'], 20)
        self.assertTrue(got['lines']); self.assertEqual(got['lines'][0]['words'][0]['word'], 'Gente')
        self.assertIn('hook', got['suggestions']); self.assertTrue(got['catalog']['sfx'])
        self.assertIn('impact', got['catalog']['caption_styles'])

    def test_save_project_bumps_version_queues_draft_and_validates(self):
        project = dict(cuts=[dict(start=5, end=7)], titles=[dict(text='Olha isso', start=0, end=3)])
        code, saved = self.post('/api/project/save', dict(id=self.item['id'], version=self.item['version'], project=project))
        self.assertEqual(code, 200); self.assertEqual(saved['version'], self.item['version'] + 1)
        row = self.app.store.candidate(self.item['id'])
        self.assertEqual(row['preview_status'], 'queued'); self.assertEqual(row['data']['project']['cuts'][0]['end'], 7)
        code, error = self.post('/api/project/save', dict(id=self.item['id'], version=row['version'],
                                                         project=dict(cuts=[dict(start=0, end=19.5)])))
        self.assertEqual(code, 400); self.assertIn('Sobre', error['error'])
        code, error = self.post('/api/project/save', dict(id=self.item['id'], version=1, project={}))
        self.assertEqual(code, 400); self.assertIn('mudou', error['error'])

    def test_music_must_exist_and_must_be_authorized_to_approve(self):
        code, error = self.post('/api/project/save', dict(id=self.item['id'], version=1,
                                                         project=dict(music=dict(id='a' * 16))))
        self.assertEqual(code, 400); self.assertIn('biblioteca', error['error'])
        source = Path(self.temp.name) / 'tom.wav'; tone(source)
        code, up = self.post('/api/upload?kind=music&name=tom.wav', None, raw=source.read_bytes(),
                             headers={'Content-Type': 'application/octet-stream'})
        self.assertEqual(code, 200); track = up['item']['id']
        self.assertNotIn('file', up['item'])
        code, saved = self.post('/api/project/save', dict(id=self.item['id'], version=1, project=dict(music=dict(id=track))))
        self.assertEqual(code, 200)
        code, error = self.post('/api/review', dict(id=self.item['id'], version=saved['version'], start=10, end=30, action='approve'))
        self.assertEqual(code, 400); self.assertIn('música', error['error'])
        code, saved = self.post('/api/project/save', dict(id=self.item['id'], version=saved['version'],
                                                         project=dict(music=dict(id=track, authorized=True))))
        code, ok = self.post('/api/review', dict(id=self.item['id'], version=saved['version'], start=10, end=30, action='approve'))
        self.assertEqual(code, 200)

    def test_changing_bounds_moves_project_times(self):
        project = dict(titles=[dict(text='Início', start=2, end=5)], cuts=[dict(start=12, end=14)])
        code, saved = self.post('/api/project/save', dict(id=self.item['id'], version=1, project=project))
        code, moved = self.post('/api/project/save', dict(id=self.item['id'], version=saved['version'], start=11, end=30,
                                                         project=dict(titles=[dict(text='Início', start=1, end=4)])))
        self.assertEqual(code, 200)
        row = self.app.store.candidate(self.item['id'])
        self.assertEqual(row['start'], 11); self.assertEqual(row['data']['project']['titles'][0]['start'], 1)

    def test_bounds_only_keeps_project_and_queues_preview(self):
        project = dict(titles=[dict(text='Início', start=4, end=7)])
        code, saved = self.post('/api/project/save', dict(id=self.item['id'], version=1, project=project))
        code, moved = self.post('/api/project/save', dict(id=self.item['id'], version=saved['version'], start=11, end=30))
        self.assertEqual(code, 200)
        row = self.app.store.candidate(self.item['id'])
        self.assertEqual(row['start'], 11)
        self.assertEqual(row['data']['project']['titles'][0]['text'], 'Início')
        self.assertEqual(row['data']['project']['titles'][0]['start'], 3)
        self.assertEqual(row['preview_status'], 'queued')
        code, error = self.post('/api/project/save', dict(id=self.item['id'], version=moved['version']))
        self.assertEqual(code, 400)

    def test_rebase_discards_what_leaves_the_clip(self):
        from liveclips.project import rebase, clean
        base = clean(dict(cuts=[dict(start=1, end=3), dict(start=10, end=12)], titles=[dict(text='x', start=0, end=2)]), 20)
        moved = rebase(base, -2, 18)
        self.assertEqual(moved['cuts'], [dict(start=0.0, end=1.0), dict(start=8.0, end=10.0)])  # o primeiro é aparado
        self.assertEqual(moved['titles'], [])

    def test_upload_rejects_non_audio_and_fake_images(self):
        code, error = self.post('/api/upload?kind=music&name=a.mp3', None, raw=b'isto nao e audio')
        self.assertEqual(code, 400)
        code, error = self.post('/api/upload?kind=image&name=a.png', None, raw=b'<html>nao</html>')
        self.assertEqual(code, 400); self.assertIn('PNG', error['error'])
        code, error = self.post('/api/upload?kind=exe&name=a.exe', None, raw=b'x')
        self.assertEqual(code, 400)

    def test_image_upload_is_deduplicated_and_served_with_cookie_only(self):
        source = Path(self.temp.name) / 'meme.png'; png(source)
        code, first = self.post('/api/upload?kind=image&name=meme.png', None, raw=source.read_bytes())
        code2, second = self.post('/api/upload?kind=image&name=meme.png', None, raw=source.read_bytes())
        self.assertEqual((code, code2), (200, 200)); self.assertEqual(first['item']['id'], second['item']['id'])
        self.assertEqual((first['item']['width'], first['item']['height']), (64, 48))
        url = self.base + '/media/image?id=' + first['item']['id']
        with self.assertRaises(HTTPError) as ctx:
            urlopen(Request(url), timeout=5)
        self.assertEqual(ctx.exception.code, 403)
        with urlopen(Request(url, headers={'Cookie': 'lc_session=' + self.app.token}), timeout=5) as res:
            self.assertEqual(res.headers['Content-Type'], 'image/png')

    def test_music_link_routes_use_ytdlp_wrapper_and_report_errors_in_portuguese(self):
        with patch('liveclips.music.inspect', return_value=dict(title='Faixa', duration=100)) as inspect:
            code, got = self.post('/api/music/inspect', dict(url='https://youtu.be/abc'))
        self.assertEqual(code, 200); self.assertEqual(got['title'], 'Faixa')
        with patch('liveclips.music.fetch', side_effect=music.MusicError('Esse vídeo é privado.')):
            code, error = self.post('/api/music/fetch', dict(url='https://youtu.be/abc'))
        self.assertEqual(code, 400); self.assertIn('privado', error['error'])
        code, error = self.post('/api/music/fetch', dict(url='https://exemplo.com/x'))
        self.assertEqual(code, 400)
        code, listing = self.post('/api/music/list', {})
        self.assertEqual(code, 200); self.assertIn('status', listing)

    def test_draft_preview_goes_through_engine_with_root(self):
        with patch('liveclips.media.render', return_value=Path(self.temp.name) / 'r.mp4') as render:
            version = self.app.store.review(self.item['id'], 1, 10, 30, self.item['parts'], 'preview')
            self.app.engine.do_render(self.item['id'], True)
        self.assertEqual(render.call_args.args[3], 'draft')
        self.assertEqual(render.call_args.kwargs['root'], self.app.store.root)


if __name__ == '__main__':
    unittest.main()
