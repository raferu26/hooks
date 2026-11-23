"""Entradas ruins e uso fora do roteiro: arquivo vazio/corrompido/sem áudio/várias faixas, original movido ou alterado,
disco sem espaço, cliques repetidos e exportações simultâneas, configurações inválidas. Pastas temporárias apenas."""
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from liveclips import media
from liveclips.store import Store, DEFAULT_PROFILE
from tests import corpus
from tests.corpus import G_MARKER
from tests.test_corpus_cortes import approve, build_case

CAM = [0, .3, .25, .3]


def ff(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True)


@unittest.skipUnless(shutil.which('ffmpeg'), 'precisa do ffmpeg')
class Extremas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='ext_'))
        cls.g = cls.tmp / 'g.ts'
        corpus.make_g(cls.g)
        cls.semaudio = cls.tmp / 'semaudio.ts'
        ff('-i', cls.g, '-an', '-c:v', 'copy', cls.semaudio)
        cls.soaudio = cls.tmp / 'so_audio.m4a'
        ff('-i', cls.g, '-vn', '-c:a', 'aac', cls.soaudio)
        cls.multi = cls.tmp / 'multitrilha.mkv'
        ff('-i', cls.g, '-i', cls.g, '-map', '0:v', '-map', '0:a', '-map', '1:a', '-c', 'copy', '-t', 25, cls.multi)
        cls.vazio = cls.tmp / 'vazio.ts'; cls.vazio.write_bytes(b'')
        cls.texto = cls.tmp / 'texto.mp4'; cls.texto.write_bytes(b'isto nao e um video' * 100)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def caso(self, source=None, **kw):
        type(self).n += 1
        raiz = self.tmp / f'c{self.n}'; raiz.mkdir()
        kw.setdefault('camera_rect', CAM)
        store, engine, item = build_case(raiz, source or self.g, marker=dict(G_MARKER, time=22, pre=12, post=8), **kw)
        return raiz, store, engine, item

    def saida(self, store, item):
        feito = store.candidate(item)
        self.assertEqual(feito['status'], 'done', feito.get('error'))
        caminho = Path(feito['export_path'])
        return media.probe(caminho / 'clipe.mp4' if caminho.is_dir() else caminho)

    # --- arquivos que não são vídeo
    def test_mensagens_claras_para_arquivos_ruins(self):
        casos = [(self.vazio, 'vazio'), (self.texto, 'não é um vídeo legível'), (self.tmp / 'nao_existe.mp4', 'não existe')]
        for arquivo, trecho in casos:
            with self.assertRaises(RuntimeError) as ctx:
                media.probe(arquivo)
            self.assertIn(trecho, str(ctx.exception), arquivo.name)
            self.assertIn(arquivo.name, str(ctx.exception))
        with self.assertRaisesRegex(ValueError, 'não contém vídeo'):
            media.probe(self.soaudio)

    # --- mídia incomum que deve funcionar
    def test_video_sem_audio_exporta(self):
        _, store, engine, item = self.caso(self.semaudio)
        approve(store, item); engine.do_render(item, False)
        info = self.saida(store, item)
        self.assertEqual((info['width'], info['height']), (1080, 1920))
        self.assertFalse(info['has_audio'])

    def test_varias_faixas_de_audio_exportam_com_audio(self):
        _, store, engine, item = self.caso(self.multi)
        approve(store, item); engine.do_render(item, False)
        info = self.saida(store, item)
        self.assertTrue(info['has_audio'])
        self.assertAlmostEqual(info['duration'], 15.0, delta=1.0)   # janela 10–25 s: a fonte tem 25 s

    # --- original movido, alterado, sem espaço
    def test_original_movido_da_erro_claro_e_recupera_ao_voltar(self):
        raiz, store, engine, item = self.caso()
        approve(store, item)
        arquivo = Path(store.rows('SELECT path FROM segments')[0]['path'])
        guardado = raiz / 'guardado.ts'; shutil.move(arquivo, guardado)
        engine.do_render(item, False)
        linha = store.candidate(item)
        self.assertEqual(linha['status'], 'error')
        self.assertIn('Religar original', linha['error'])
        self.assertFalse(list(Path(store.rows('SELECT path FROM sessions')[0]['path']).glob('cortes/*')), 'criou exportação sem fonte')
        shutil.move(guardado, arquivo)
        parts = linha['parts'] if isinstance(linha['parts'], list) else json.loads(linha['parts'])
        store.review(item, linha['version'], linha['start'], linha['end'], parts, 'retry', editorial_confirmed=True)
        engine.do_render(item, False)
        self.assertEqual(store.candidate(item)['status'], 'done', store.candidate(item).get('error'))

    def test_original_alterado_bloqueia_sem_tocar_no_arquivo(self):
        raiz, store, engine, item = self.caso()
        approve(store, item)
        arquivo = Path(store.rows('SELECT path FROM segments')[0]['path'])
        with open(arquivo, 'ab') as f:
            f.write(b'\0' * 1024)
        tamanho = arquivo.stat().st_size
        engine.do_render(item, False)
        linha = store.candidate(item)
        self.assertEqual(linha['status'], 'error')
        self.assertIn('foi alterado', linha['error'])
        self.assertEqual(arquivo.stat().st_size, tamanho)

    def test_sem_espaco_em_disco_nao_deixa_lixo(self):
        raiz, store, engine, item = self.caso(min_free_gb=.5)
        streamer = store.rows('SELECT id FROM streamers')[0]['id']
        perfil = store.streamer(streamer)['profile']
        store.save_profile(streamer, dict(perfil, min_free_gb=100))
        approve(store, item)
        sessao = Path(store.rows('SELECT path FROM sessions')[0]['path'])
        with self.assertRaises(media.LowSpace) as ctx:
            engine.do_render(item, False)
        self.assertIn('Nenhum vídeo foi apagado', str(ctx.exception))
        linha = store.candidate(item)
        self.assertEqual(linha['status'], 'approved', 'o corte deve voltar à fila, não ficar preso nem virar erro')
        self.assertEqual([p.name for p in (sessao / 'cortes').glob('*')] if (sessao / 'cortes').exists() else [], [])
        store.save_profile(streamer, dict(perfil, min_free_gb=.5))      # liberou espaço/reserva: segue sozinho
        engine.do_render(item, False)
        self.assertEqual(store.candidate(item)['status'], 'done')

    # --- cliques repetidos e simultaneidade
    def test_aprovar_duas_vezes_e_exportar_ao_mesmo_tempo_gera_um_corte(self):
        raiz, store, engine, item = self.caso()
        approve(store, item)
        approve(store, item)                # segundo clique em "aprovar": não cria outro corte nem muda o estado
        self.assertEqual(store.rows("SELECT COUNT(*) n FROM candidates WHERE status='approved'")[0]['n'], 1)
        saidas = []
        def exportar():
            try:
                engine.do_render(item, False)
            except Exception as exc:        # nenhuma exceção deveria escapar
                saidas.append(exc)
        threads = [threading.Thread(target=exportar) for _ in range(3)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(saidas, [])
        linha = store.candidate(item)
        self.assertEqual(linha['status'], 'done', linha.get('error'))
        sessao = Path(store.rows('SELECT path FROM sessions')[0]['path'])
        self.assertEqual(len([p for p in (sessao / 'cortes').iterdir() if p.is_dir()]), 1)
        self.assertEqual(list((sessao / 'cortes').glob('render_*')), [])
        self.assertEqual(len(list((raiz / 'entrega').rglob('*.mp4'))), 1)

    # --- desempenho: o original só é relido por inteiro na primeira conferência
    def test_original_nao_e_relido_a_cada_previa_e_exportacao(self):
        raiz, store, engine, item = self.caso()
        arquivo = Path(store.rows('SELECT path FROM segments')[0]['path']).resolve()
        lidos = []
        original = media.sha_file
        def espiao(path):
            if Path(path).resolve() == arquivo:
                lidos.append(path)
            return original(path)
        media._SHA_CACHE.clear()
        with mock.patch.object(media, 'sha_file', espiao):
            cand = store.candidate(item)
            parts = cand['parts'] if isinstance(cand['parts'], list) else json.loads(cand['parts'])
            store.review(item, cand['version'], cand['start'], cand['end'], parts, 'preview', editorial_confirmed=True)
            engine.do_render(item, True)
            approve(store, item)
            engine.do_render(item, False)
        self.assertEqual(store.candidate(item)['status'], 'done')
        self.assertEqual(len(lidos), 1, f'o original foi lido por inteiro {len(lidos)} vezes')

    # --- configuração inválida
    def test_perfil_invalido_e_recusado_e_o_anterior_continua(self):
        store = Store(str(self.tmp / 'perfis')) if False else Store(tempfile.mkdtemp(dir=self.tmp))
        sid = store.create_streamer('Canal')
        bom = store.streamer(sid)['profile']
        ruins = [dict(caption_margin=9999), dict(caption_margin='abc'), dict(font_size=float('nan')), dict(min_free_gb=float('inf')),
                 dict(threads=0), dict(model='gigante'), dict(language='klingon'), dict(editorial_style='inexistente')]
        for ruim in ruins:
            with self.assertRaises((ValueError, TypeError, OverflowError), msg=str(ruim)):
                store.save_profile(sid, dict(bom, **ruim))
            self.assertEqual(store.streamer(sid)['profile'], bom, f'perfil mudou depois de {ruim}')


if __name__ == '__main__':
    unittest.main()
