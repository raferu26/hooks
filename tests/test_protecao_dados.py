"""Proteção de dados e recuperação. Tudo em pastas temporárias, com cópias; nada de dados reais.

Cenários: escrita interrompida, original intocado, colisão de nomes, nomes de arquivo hostis (aspas, $(), &, ;),
pacote/projeto de fora com caminhos perigosos, log sem credenciais, e processo morto à força em cada etapa."""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from liveclips import atomic, delivery, export_pack, media, support
from liveclips.store import Store
from tests import corpus
from tests.test_corpus_cortes import approve, build_case
from tests.corpus import G_MARKER

ROOT = Path(__file__).resolve().parent.parent
HOSTILE = "jogo 'quebrado' $(touch PWNED) & `id` ; \"aspas\" ção ñ.mp4"


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def snapshot(folder):
    """Nome, tamanho, mtime e hash de tudo numa pasta."""
    out = {}
    for p in sorted(Path(folder).rglob('*')):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(folder))] = (st.st_size, st.st_mtime_ns, digest(p))
    return out


class Atomico(unittest.TestCase):
    def test_falha_na_troca_preserva_o_arquivo_anterior(self):
        with tempfile.TemporaryDirectory() as d:
            alvo = Path(d) / 'fonte.json'
            atomic.write_json(alvo, dict(mode='video'))
            with mock.patch('liveclips.atomic.os.replace', side_effect=OSError('disco cheio')):
                with self.assertRaises(OSError):
                    atomic.write_json(alvo, dict(mode='live', lixo='x' * 10000))
            self.assertEqual(json.loads(alvo.read_text()), dict(mode='video'))
            self.assertEqual([p.name for p in Path(d).iterdir()], ['fonte.json'], 'sobrou arquivo temporário')

    def test_sem_arquivo_anterior_nao_cria_nada_pela_metade(self):
        with tempfile.TemporaryDirectory() as d:
            alvo = Path(d) / 'novo.json'
            with mock.patch('liveclips.atomic.os.replace', side_effect=OSError('x')):
                with self.assertRaises(OSError):
                    atomic.write_text(alvo, 'abc')
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_texto_com_acentos_e_privado(self):
        with tempfile.TemporaryDirectory() as d:
            alvo = Path(d) / 'servidor.json'
            atomic.write_json(alvo, dict(titulo='ação'), private=True)
            self.assertIn('ação', alvo.read_text(encoding='utf-8'))
            if os.name == 'posix':
                self.assertEqual(alvo.stat().st_mode & 0o777, 0o600)

    def test_gravacoes_concorrentes_nao_corrompem(self):
        import threading
        with tempfile.TemporaryDirectory() as d:
            alvo = Path(d) / 'estado.json'
            def gravar(n):
                for i in range(30):
                    atomic.write_json(alvo, dict(n=n, i=i, relleno='y' * 5000))
            threads = [threading.Thread(target=gravar, args=(n,)) for n in range(4)]
            [t.start() for t in threads]
            for _ in range(200):
                if alvo.exists():
                    json.loads(alvo.read_text())       # nunca pode ler JSON cortado
            [t.join() for t in threads]
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ['estado.json'])


class Colisao(unittest.TestCase):
    def test_entrega_nunca_sobrescreve_outro_conteudo(self):
        with tempfile.TemporaryDirectory() as d:
            origem = Path(d) / 'a.mp4'; origem.write_bytes(b'novo' * 1000)
            destino = Path(d) / 'entrega' / 'x.mp4'; destino.parent.mkdir()
            destino.write_bytes(b'do usuario')
            final, _ = delivery._copy_checked(origem, destino)
            self.assertEqual(destino.read_bytes(), b'do usuario')
            self.assertEqual(final.name, 'x_2.mp4')
            again, _ = delivery._copy_checked(origem, destino)          # mesma entrega duas vezes: sem duplicar
            self.assertEqual(again, final)
            self.assertEqual(sorted(p.name for p in destino.parent.iterdir()), ['x.mp4', 'x_2.mp4'])

    def test_nome_da_entrega_sem_separadores_nem_curingas(self):
        nome = delivery.safe_name('..\\..//Canal: <ao vivo>|?*"\x00', 40)
        for ruim in '/\\:<>|?*"\x00':
            self.assertNotIn(ruim, nome)
        self.assertNotIn('..', nome)


class Importacao(unittest.TestCase):
    def _projeto(self, d, midias, plano=True):
        base = Path(d) / 'pacote'; base.mkdir()
        p = dict(schema='hooks.projeto', version=1, midias=midias)
        if plano:
            from liveclips import plan as planlib
            pl = dict(output=dict(duration_frames=30), segments=[], effects=[])
            p.update(plan=pl, plan_digest=planlib.digest(pl))
        (base / 'projeto.json').write_text(json.dumps(p), encoding='utf-8')
        return base

    def test_copia_fora_de_fontes_e_ignorada(self):
        with tempfile.TemporaryDirectory() as d:
            segredo = Path(d) / 'segredo.txt'; segredo.write_text('nao tocar')
            base = self._projeto(d, [dict(name='v.mp4', copy='../segredo.txt'), dict(name='../segredo.txt'), dict(name='a\\b.mp4'), dict(name='/etc/passwd')])
            r = export_pack.reopen(base)
            self.assertTrue(all(m['caminho'] is None for m in r['midias']), r['midias'])
            self.assertFalse(r['ok'])
            self.assertEqual(segredo.read_text(), 'nao tocar')

    def test_copia_valida_dentro_de_fontes_e_aceita(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._projeto(d, [dict(name='v.mp4', copy='fontes/v.mp4', sha256=hashlib.sha256(b'abc').hexdigest())])
            (base / 'fontes').mkdir(); (base / 'fontes' / 'v.mp4').write_bytes(b'abc')
            r = export_pack.reopen(base)
            self.assertEqual(r['midias'][0]['estado'], 'ok')

    def test_projeto_incompleto_ou_corrompido_da_erro_claro(self):
        with tempfile.TemporaryDirectory() as d:
            for conteudo in ('{', '[]', json.dumps(dict(schema='hooks.projeto', plan=dict())), json.dumps(dict(schema='outro'))):
                base = Path(d) / 'p'; shutil.rmtree(base, ignore_errors=True); base.mkdir()
                (base / 'projeto.json').write_text(conteudo)
                with self.assertRaises(ValueError):
                    export_pack.reopen(base)

    def test_restauracao_de_backup_recusa_caminho_inseguro(self):
        from liveclips import recovery
        with tempfile.TemporaryDirectory() as d:
            ruim = Path(d) / 'ruim.zip'
            with zipfile.ZipFile(ruim, 'w') as z:
                z.writestr('manifesto.json', json.dumps(dict(schema=recovery.SCHEMA, database='liveclips_v8.sqlite3')))
                z.writestr('liveclips_v8.sqlite3', b'x')
                z.writestr('perfis/../../fora/perfil_v8.json', b'{}')
            raiz = Path(d) / 'dados'; raiz.mkdir()
            with self.assertRaises(Exception):
                recovery.restore_backup(raiz, ruim)
            self.assertFalse((Path(d) / 'fora').exists())
            self.assertFalse(list(raiz.glob('**/fora*')))


class Registro(unittest.TestCase):
    def test_log_e_diagnostico_sem_credenciais(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d) / 'Dados'; raiz.mkdir()
            store = Store(str(raiz))
            support.setup_logging(raiz)
            import logging
            logging.getLogger('liveclips').error('falhou GET /api?token=SEGREDO123&x=1 Authorization: Bearer ABCDEFGH12345 em C:\\Users\\Rafael\\Videos\\a.mp4')
            for h in logging.getLogger('liveclips').handlers:
                h.flush()
            store.event('teste', 'oauth:SEGREDO456 e /home/rafael/meus/videos')
            destino = support.bundle(raiz, store, 'x', tools=dict(ffmpeg='/usr/bin/ffmpeg'))
            texto = ''
            with zipfile.ZipFile(destino) as z:
                nomes = z.namelist()
                for n in nomes:
                    texto += z.read(n).decode('utf-8', 'replace')
            for proibido in ('SEGREDO123', 'SEGREDO456', 'ABCDEFGH12345', 'Rafael\\Videos', '/home/rafael'):
                self.assertNotIn(proibido, texto)
            self.assertFalse([n for n in nomes if n.endswith(('.sqlite3', '.mp4', '.json')) and 'fim' not in n])


@unittest.skipUnless(shutil.which('ffmpeg'), 'precisa do ffmpeg')
class Fluxo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='prot_')
        cls.g = Path(cls.tmp) / 'g.ts'
        corpus.make_g(cls.g)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _caso(self, nome, **kw):
        raiz = Path(self.tmp) / nome; raiz.mkdir()
        kw.setdefault('camera_rect', [0, .3, .25, .3])
        return raiz, *build_case(raiz, self.g, marker=G_MARKER, **kw)

    def test_original_hostil_nao_executa_nada_e_nao_muda(self):
        raiz = Path(self.tmp) / 'hostil'; raiz.mkdir()
        usuario = raiz / 'Meus vídeos'; usuario.mkdir()
        original = usuario / HOSTILE
        shutil.copyfile(self.g, original)
        antes = snapshot(usuario)
        cwd = Path.cwd()
        store = Store(str(raiz / 'dados'))
        streamer = store.create_streamer('Canal')
        from liveclips.store import DEFAULT_PROFILE
        store.save_profile(streamer, dict(DEFAULT_PROFILE, ai_mode='sem_ia', editorial_style='gameplay', min_free_gb=.5, second_pass='off',
                                          delivery_folder=str(raiz / 'entrega')))
        (raiz / 'entrega').mkdir()
        sid = store.new_session(streamer, "sessão 'x' $(id)", original, closed=True)
        session = store.session(sid)
        info = media.probe(original); st = original.stat()
        with store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (sid, 0, str(original.resolve()), media.sha_file(original), info['duration'], info['signature'], st.st_size, st.st_mtime_ns, 'new', '{}'))
        Path(session['path'], 'marcadores.json').write_text(json.dumps([G_MARKER]), encoding='utf-8')
        atomic.write_json(Path(session['path']) / 'fonte.json', dict(mode='video', reframe_mode='conservative'))
        from liveclips.engine import Engine
        engine = Engine(store)
        profile = store.streamer(streamer)['profile']
        engine.analyze_one(store.session(sid), profile)
        engine.suggest_one(store.session(sid), profile)
        itens = [r['id'] for r in store.rows('SELECT id FROM candidates WHERE streamer=?', (streamer,))
                 if store.candidate(r['id'])['data'].get('origin') == 'marcador']
        self.assertTrue(itens, 'o marcador não gerou corte')
        approve(store, itens[0])
        engine.do_render(itens[0], False)
        feito = store.candidate(itens[0])
        self.assertEqual(feito['status'], 'done', feito.get('error'))
        self.assertTrue(Path(feito['export_path']).is_file())
        self.assertEqual(snapshot(usuario), antes, 'o vídeo original foi alterado ou ganhou arquivos ao lado')
        for onde in (cwd, raiz, usuario, Path(tempfile.gettempdir())):
            self.assertFalse((onde / 'PWNED').exists(), f'comando executado a partir do nome de arquivo: {onde}')
        entregues = [p.name for p in (raiz / 'entrega').rglob('*') if p.is_file()]
        self.assertTrue(any(n.endswith('.mp4') for n in entregues), entregues)

    def test_processo_morto_em_cada_etapa_recupera_sem_duplicar(self):
        raiz, store, engine, item = self._caso('morte')
        approve(store, item)
        fonte = Path(store.rows('SELECT path FROM segments')[0]['path'])
        fonte_antes = digest(fonte)
        sessao = Path(store.rows('SELECT path FROM sessions')[0]['path'])
        entrega = raiz / 'entrega'
        worker = ("import sys;from liveclips.store import Store;from liveclips.engine import Engine;"
                  "s=Store(sys.argv[1]);Engine(s).do_render(sys.argv[2],False)")
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        etapas = [('pasta de trabalho criada', lambda: list((sessao / 'cortes').glob('render_*'))),
                  ('vídeo parcial gravado', lambda: [p for p in (sessao / 'cortes').glob('render_*/entrega/clipe.mp4') if p.stat().st_size > 50_000])]
        for nome, pronto in etapas:
            proc = subprocess.Popen([sys.executable, '-W', 'ignore', '-c', worker, str(raiz / 'dados'), item], env=env, cwd=ROOT,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            limite = time.time() + 120
            while time.time() < limite and proc.poll() is None and not pronto():
                time.sleep(.02)
            morreu_antes = proc.poll() is not None
            if not morreu_antes:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            if morreu_antes:
                self.skipTest(f'a exportação terminou antes de chegar à etapa "{nome}" nesta máquina')
            # Reabre como o usuário: novo processo, mesmo diretório de dados.
            import sqlite3
            bruto = sqlite3.connect(str(raiz / 'dados' / 'liveclips_v8.sqlite3'))
            self.assertEqual(bruto.execute('SELECT status FROM candidates WHERE id=?', (item,)).fetchone()[0], 'exporting', nome)
            bruto.close()
            reaberto = Store(str(raiz / 'dados'))                         # abrir o programa já recupera
            self.assertEqual(reaberto.candidate(item)['status'], 'approved', nome)
            self.assertEqual(list((sessao / 'cortes').glob('render_*')), [], f'sobrou pasta de trabalho ({nome})')
            self.assertEqual([p for p in (sessao / 'cortes').iterdir()], [], f'exportação meio pronta visível ({nome})')
            self.assertEqual(digest(fonte), fonte_antes, f'a fonte mudou ({nome})')
            reaberto.recover()                                           # repetir é inofensivo
            self.assertEqual(reaberto.candidate(item)['status'], 'approved')
        # Depois de duas quedas, a exportação completa uma única vez.
        final = Store(str(raiz / 'dados'))
        from liveclips.engine import Engine
        Engine(final).do_render(item, False)
        pronto = final.candidate(item)
        self.assertEqual(pronto['status'], 'done', pronto.get('error'))
        self.assertEqual(len([p for p in (sessao / 'cortes').iterdir() if p.is_dir()]), 1)
        self.assertEqual(final.rows('SELECT COUNT(*) n FROM candidates')[0]['n'], 1 + final.rows('SELECT COUNT(*) n FROM candidates WHERE id!=?', (item,))[0]['n'])
        self.assertEqual(len([p for p in entrega.rglob('*.mp4')]), 1, 'entrega duplicada')
        self.assertEqual(digest(fonte), fonte_antes)

    def test_queda_durante_a_analise_reanalisa_sem_duplicar(self):
        import sqlite3
        raiz = Path(self.tmp) / 'analise'; raiz.mkdir()
        store = Store(str(raiz / 'dados'))
        streamer = store.create_streamer('Corpus')
        from liveclips.store import DEFAULT_PROFILE
        store.save_profile(streamer, dict(DEFAULT_PROFILE, ai_mode='sem_ia', editorial_style='gameplay', min_free_gb=.5, second_pass='off',
                                          camera_rect=[0, .3, .25, .3]))
        sid = store.new_session(streamer, 'a')
        session = store.session(sid)
        arquivo = Path(session['source']) / 'segmento_00000.ts'
        shutil.copyfile(self.g, arquivo)
        info = media.probe(arquivo); st = arquivo.stat()
        with store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (sid, 0, str(arquivo.resolve()), media.sha_file(arquivo), info['duration'], info['signature'], st.st_size, st.st_mtime_ns, 'new', '{}'))
        Path(session['path'], 'marcadores.json').write_text(json.dumps([G_MARKER]), encoding='utf-8')
        antes = digest(arquivo)
        worker = ("import sys;from liveclips.store import Store;from liveclips.engine import Engine;"
                  "s=Store(sys.argv[1]);e=Engine(s);sess=s.session(sys.argv[2]);p=s.streamer(sess['streamer'])['profile'];"
                  "e.analyze_one(sess,p);e.suggest_one(s.session(sys.argv[2]),p)")
        proc = subprocess.Popen([sys.executable, '-W', 'ignore', '-c', worker, str(raiz / 'dados'), sid], cwd=ROOT,
                                env=dict(os.environ, PYTHONPATH=str(ROOT)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        banco = str(raiz / 'dados' / 'liveclips_v8.sqlite3')
        vistos = None
        limite = time.time() + 120
        while time.time() < limite and proc.poll() is None:
            con = sqlite3.connect(banco, timeout=1)
            try:
                vistos = con.execute('SELECT status FROM segments').fetchone()[0]
            except sqlite3.Error:
                pass
            finally:
                con.close()
            if vistos == 'processing':
                break
            time.sleep(.01)
        if proc.poll() is not None:
            self.skipTest('a análise terminou antes de ser interrompida nesta máquina')
        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        reaberto = Store(str(raiz / 'dados'))
        self.assertEqual(reaberto.rows('SELECT status FROM segments')[0]['status'], 'new')
        from liveclips.engine import Engine
        engine = Engine(reaberto)
        perfil = reaberto.streamer(streamer)['profile']
        engine.analyze_one(reaberto.session(sid), perfil)
        engine.suggest_one(reaberto.session(sid), perfil)
        engine.analyze_one(reaberto.session(sid), perfil)           # repetir não cria cópia
        engine.suggest_one(reaberto.session(sid), perfil)
        marcados = [r for r in reaberto.rows('SELECT id FROM candidates WHERE streamer=?', (streamer,))
                    if reaberto.candidate(r['id'])['data'].get('origin') == 'marcador']
        self.assertEqual(len(marcados), 1, 'o corte do marcador foi duplicado depois da queda')
        self.assertEqual(digest(arquivo), antes)

    def test_limpeza_so_apaga_restos_de_exportacao(self):
        raiz, store, engine, item = self._caso('limpeza')
        sessao = Path(store.rows('SELECT path FROM sessions')[0]['path'])
        cortes = sessao / 'cortes'; cortes.mkdir(exist_ok=True)
        resto = cortes / 'render_abc'; resto.mkdir(); (resto / 'x.mp4').write_bytes(b'x')
        feito = cortes / 'abc123_def456'; feito.mkdir(); (feito / 'clipe.mp4').write_bytes(b'ok')
        usuario = raiz / 'meu_render_pessoal'; usuario.mkdir(); (usuario / 'a.mp4').write_bytes(b'u')
        fora = sessao / 'render_do_usuario'; fora.mkdir()
        avulso = cortes / 'render.txt'; avulso.write_text('arquivo, não pasta')
        removidas = store.clean_partial_renders()
        self.assertEqual(removidas, 1)
        self.assertFalse(resto.exists())
        self.assertTrue((feito / 'clipe.mp4').is_file() and (usuario / 'a.mp4').is_file() and fora.is_dir() and avulso.is_file())

    def test_exportacao_existente_nao_e_sobrescrita(self):
        raiz, store, engine, item = self._caso('colisao')
        approve(store, item)
        engine.do_render(item, False)
        feito = store.candidate(item)
        clipe = Path(feito['export_path'])
        antes = digest(clipe)
        # Simula o banco perdendo o status (restauração de backup antigo) e o usuário aprovando de novo.
        with store.connect(True) as c:
            c.execute("UPDATE candidates SET status='approved' WHERE id=?", (item,))
        engine.do_render(item, False)
        depois = store.candidate(item)
        self.assertEqual(digest(Path(depois['export_path'])), antes, 'a exportação anterior foi alterada')
        self.assertEqual(len([p for p in (clipe.parent.parent).iterdir() if p.is_dir()]), 1)


if __name__ == '__main__':
    unittest.main()
