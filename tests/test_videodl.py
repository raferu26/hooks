"""Download de vídeo por link (YouTube) sem depender da internet: um servidor local entrega um MP4 e o yt-dlp o baixa
pelo mesmo caminho do produto. Não prova que o YouTube em si responde (isso só se vê na máquina do usuário)."""
import functools
import http.server
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from liveclips import media, videodl
from liveclips.app import App
from tests.helpers import setup_session

SLOW = {'on': False}


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def copyfile(self, source, outputfile):
        if not SLOW['on']:
            return super().copyfile(source, outputfile)
        try:
            while True:
                block = source.read(16 * 1024)
                if not block:
                    break
                outputfile.write(block)
                outputfile.flush()
                time.sleep(.15)
        except (BrokenPipeError, ConnectionResetError):
            pass


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'precisa do ffmpeg')
class Download(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('yt-dlp não instalado')
        cls.web = tempfile.mkdtemp(prefix='ytweb_')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=30', '-f', 'lavfi', '-i', 'sine=frequency=440',
                        '-t', '6', '-c:v', 'libx264', '-b:v', '3M', '-c:a', 'aac', '-pix_fmt', 'yuv420p', str(Path(cls.web) / 'video.mp4')], check=True)
        handler = functools.partial(Handler, directory=cls.web)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/video.mp4'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.web, ignore_errors=True)

    def setUp(self):
        SLOW['on'] = False
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)

    def test_baixa_confere_e_informa_progresso(self):
        passos = []
        path = videodl.download(self.url, Path(self.temp.name) / 'dl', on_progress=lambda f, e: passos.append((f, e)))
        self.assertTrue(path.is_file())
        self.assertAlmostEqual(media.probe(path)['duration'], 6.0, delta=.5)
        self.assertTrue(passos and all(0 <= f <= 1 for f, _ in passos))
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name], 'sobrou arquivo temporário')

    def test_cancelar_apaga_o_parcial(self):
        SLOW['on'] = True
        pasta = Path(self.temp.name) / 'dl'
        marca = {'cancel': False}
        def progresso(fracao, etapa):
            if fracao > .1:
                marca['cancel'] = True
        with self.assertRaises(videodl.DownloadCancelled):
            videodl.download(self.url, pasta, on_progress=progresso, cancelled=lambda: marca['cancel'])
        self.assertEqual([p.name for p in pasta.iterdir()] if pasta.exists() else [], [])

    def test_mensagens_em_portugues(self):
        self.assertIn('privado', videodl.explain(Exception('Private video. Sign in if you ...')))
        self.assertIn('ainda não começou', videodl.explain(Exception('Premieres in 5 hours / This live event will begin in 2 hours')))
        self.assertIn('Sem conexão', videodl.explain(Exception('Unable to connect to proxy')))
        self.assertTrue(videodl.is_youtube('https://youtu.be/ZXg07E_XaSA?si=6I2QMueZ-bkIB6E2'))
        self.assertTrue(videodl.is_youtube('https://www.youtube.com/watch?v=x'))
        self.assertFalse(videodl.is_youtube('https://www.twitch.tv/videos/123'))
        self.assertFalse(videodl.is_youtube('https://youtube.com.exemplo.net/x'))

    # --- o fluxo do produto -------------------------------------------------------------------------------------------
    def app(self):
        app = App(self.temp.name, worker=False); self.addCleanup(app.close)
        streamer, _, _ = setup_session(app.store)
        return app, streamer

    def espera(self, app, key, estado):
        limite = time.time() + 60
        while time.time() < limite:
            tarefa = next((t for t in app.engine.renders() if t['candidate'] == key), None)
            if tarefa and tarefa['state'] == estado:
                return tarefa
            time.sleep(.1)
        self.fail(f'a tarefa não chegou a {estado}: {app.engine.renders()}')

    def test_link_de_youtube_baixa_e_cria_sessao_de_video(self):
        app, streamer = self.app()
        antes = {s['id'] for s in app.store.rows('SELECT id FROM sessions')}
        with mock.patch.object(videodl, 'YOUTUBE_HOSTS', videodl.YOUTUBE_HOSTS + ('127.0.0.1',)):
            r = app.action('/api/video/url', dict(streamer=streamer, url=self.url, reframe_mode='conservative'))
        self.assertTrue(r['download'].startswith('download:'))
        tarefa = self.espera(app, r['download'], 'concluido')
        self.assertEqual(tarefa['kind'], 'download')
        self.assertEqual(tarefa['percent'], 100.0)
        novas = [s for s in app.store.rows('SELECT id FROM sessions') if s['id'] not in antes]
        self.assertEqual(len(novas), 1)
        sessao = app.store.session(novas[0]['id'])
        info = __import__('json').loads((Path(sessao['path']) / 'fonte.json').read_text(encoding='utf-8'))
        self.assertEqual((info['mode'], info['url']), ('video', self.url))
        self.assertTrue(Path(sessao['source']).is_file() and str(Path(app.store.root, 'downloads')) in sessao['source'])

    def test_cancelar_na_bandeja_nao_cria_sessao(self):
        SLOW['on'] = True
        app, streamer = self.app()
        antes = len(app.store.rows('SELECT id FROM sessions'))
        with mock.patch.object(videodl, 'YOUTUBE_HOSTS', videodl.YOUTUBE_HOSTS + ('127.0.0.1',)):
            r = app.action('/api/video/url', dict(streamer=streamer, url=self.url))
        time.sleep(.8)
        self.assertEqual(app.engine.cancel_render(r['download']), 'cancelando')
        tarefa = self.espera(app, r['download'], 'cancelado')
        self.assertIn('Nada foi adicionado', tarefa['error'])
        self.assertEqual(len(app.store.rows('SELECT id FROM sessions')), antes)

    def test_live_do_youtube_continua_pelo_caminho_de_gravacao(self):
        app, streamer = self.app()
        meta = dict(title='Live', author='x', plugin='youtube', category='', qualities=['720p'], selected='720p', warnings=[])
        with mock.patch.object(videodl, 'inspect', return_value=dict(title='Live', author='x', duration=0, live=True, id='abc', url='u')), \
                mock.patch.object(app.capture, 'inspect', return_value=meta) as ver, \
                mock.patch.object(app.capture, 'start', return_value='sess1') as gravar:
            r = app.action('/api/video/url', dict(streamer=streamer, url='https://www.youtube.com/watch?v=abc'))
        ver.assert_called_once()
        gravar.assert_called_once()
        self.assertEqual(r['id'], 'sess1')

    def test_link_que_nao_e_do_youtube_nao_passa_pelo_ytdlp(self):
        app, streamer = self.app()
        meta = dict(title='V', author='x', plugin='twitch', category='', qualities=['720p'], selected='720p', warnings=[])
        with mock.patch.object(videodl, 'inspect') as ytdlp, mock.patch.object(app.capture, 'inspect', return_value=meta), \
                mock.patch.object(app.capture, 'start', return_value='s2'):
            app.action('/api/video/url', dict(streamer=streamer, url='https://www.twitch.tv/videos/123'))
        ytdlp.assert_not_called()


if __name__ == '__main__':
    unittest.main()
