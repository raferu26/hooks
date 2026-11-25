"""TESTES DO PRODUTO DISTRIBUÍDO. Extrai o ZIP de release numa pasta LIMPA e testa o aplicativo a partir dele (não da árvore de desenvolvimento):
identidade (versão/commit/interface), catálogo de 8 layouts, seleção de regiões pela interface (Playwright), prévia que muda, exportação que reflete
o layout, persistência após reiniciar o servidor, cenas na exportação, projeto antigo, webcam viva com conteúdo parado, áudio único.
Uso: python tools/testar_pacote.py ZIP [--porta 8880] [--sem-ui]   → sai com código 1 se QUALQUER verificação falhar."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
results, fails = {}, []


def check(name, cond, info=''):
    results[name] = bool(cond)
    print(('OK    ' if cond else 'FALHA ') + name + (f'  {info}' if (info and not cond) else ''), flush=True)
    if not cond:
        fails.append(f'{name} {info}')


class Server:
    def __init__(self, pkg, root, port, python):
        self.pkg, self.root, self.port, self.python = pkg, root, port, python
        self.proc = None

    def start(self):
        code = f"import sys; sys.path.insert(0, {str(self.pkg)!r}); from liveclips.__main__ import main; sys.argv=['liveclips','--root',{str(self.root)!r},'--port',{str(self.port)!r},'--no-browser']; main()"
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
        self.log = open(self.root.parent / 'servidor_pacote.log', 'ab')
        self.proc = subprocess.Popen([self.python, '-I', '-c', code], cwd=str(self.pkg), stdout=self.log, stderr=self.log, env=env)
        end = time.time() + 90
        while time.time() < end:
            f = self.root / 'servidor.json'
            if f.exists():
                try:
                    self.info = json.loads(f.read_text(encoding='utf-8'))
                    self.get('/')
                    return
                except (OSError, ValueError):
                    pass
            if self.proc.poll() is not None:
                raise SystemExit('servidor do pacote encerrou: ' + (self.root.parent / 'servidor_pacote.log').read_text(errors='replace')[-600:])
            time.sleep(.3)
        raise SystemExit('servidor do pacote não subiu')

    def get(self, path):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', headers={'X-LiveClips-Token': self.info['token']})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    def post(self, path, data):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=json.dumps(data).encode(),
                                     headers={'X-LiveClips-Token': self.info['token'], 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(exc.read().decode('utf-8', 'replace')[:300]) from None

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()
        for _ in range(20):
            if not (self.root / 'servidor.json').exists():
                break
            time.sleep(.2)
        (self.root / 'servidor.json').unlink(missing_ok=True)


def frames(video, at, vf='scale=108:192,format=gray'):
    import numpy as np
    out = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-ss', str(at), '-i', str(video), '-frames:v', '1', '-vf', vf, '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(192, 108).astype(int)


def wait_for(fn, timeout=240, step=1.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('zip')
    ap.add_argument('--porta', type=int, default=8880)
    ap.add_argument('--sem-ui', action='store_true')
    ap.add_argument('--python', default=sys.executable)
    a = ap.parse_args()
    import numpy as np
    work = Path(tempfile.mkdtemp(prefix='hooks_pacote_'))
    with zipfile.ZipFile(a.zip) as z:
        check('zip_integro', z.testzip() is None)
        z.extractall(work / 'extraido')
    pkg = next((work / 'extraido').iterdir())
    manifest = [l.split('  ', 1) for l in (pkg / 'MANIFESTO.sha256').read_text(encoding='utf-8').splitlines() if '  ' in l]
    bad = [n for d, n in manifest if hashlib.sha256((pkg / n).read_bytes()).hexdigest() != d]
    check('manifesto_confere_na_pasta_limpa', not bad, bad[:3])
    build = json.loads((pkg / 'BUILD_INFO.json').read_text(encoding='utf-8'))
    estado = json.loads((pkg / 'ESTADO_DO_RELEASE.json').read_text(encoding='utf-8'))
    check('estado_do_release_nao_afirma_windows', estado['windows_fisico'] is False and estado['aprovada_para_distribuicao'] is False)
    root = work / 'dados'
    root.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    cp = subprocess.run([a.python, '-I', str(HERE / '_semear_pacote.py'), str(pkg), str(root)], capture_output=True, text=True, env=env)
    check('semear_dados_com_codigo_do_pacote', cp.returncode == 0, cp.stderr[-300:])
    ids = cp.stdout.split('SEMEADO')[1].split()[1:]
    srv = Server(pkg, root, a.porta, a.python)
    srv.start()
    try:
        html = srv.get('/').decode('utf-8')
        # T1 inicialização / identidade
        check('t1_frontend_carrega', 'Hook' in html and len(html) > 100000)
        check('t1_id_da_tela_no_manifesto', f'name="ui-build" content="{build["ui"]}"' in html, build['ui'])
        state = json.loads(srv.get('/api/state'))
        check('t1_versao_do_servidor_coincide_com_manifesto', state['build']['version'] == build['version'] and state['build']['commit'] == build['commit'])
        diag = srv.post('/api/diagnostico', {})
        check('t1_servidor_roda_do_pacote_extraido', Path(diag['instalacao'].replace('~', str(Path.home()))).resolve() == pkg.resolve() or str(work) in diag['instalacao'] or pkg.name in diag['instalacao'], diag['instalacao'])
        check('t1_diagnostico_todas_verificacoes_ok', all(v['ok'] for v in diag['verificacoes']), diag['verificacoes'])
        check('t1_recursos_declarados_no_build', set(build['funcionalidades_esperadas']) == set(diag['recursos_declarados']))
        # T2 catálogo
        proj = srv.post('/api/project/get', {'id': ids[0]})
        cat = proj['catalog']['composition']
        check('t2_catalogo_8_layouts', len(cat['layouts']) == 8)
        check('t2_tres_principais', [l['id'] for l in cat['layouts'] if l['group'] == 'main'] == ['cam_compacta', 'cam_ampliada', 'cam_flutuante'])
        # T8 projeto antigo (sem composição) renderiza como antes
        check('t8_projeto_antigo_abre_sem_composicao', not (proj['project'] or {}).get('composition'))
        # T3/T6 pela interface
        if not a.sem_ui:
            ue = subprocess.run([a.python, str(REPO / 'ui' / 'e2e_reacao.py')], capture_output=True, text=True, env=dict(os.environ, PORT=str(a.porta), OUT=str(work / 'telas')))
            tail = ue.stdout.strip().splitlines()
            check('t3_t6_interface_e2e_no_pacote', ue.returncode == 0, '\n'.join(tail[-6:]) + ue.stderr[-300:])
            shots = work / 'telas'
            print('capturas de tela:', shots, flush=True)
            shutil.copytree(shots, REPO / 'validacao' / 'telas_pacote', dirs_exist_ok=True) if shots.exists() else None
        # T4/T5/T7: prévia muda, exportação reflete layout, cenas — pela API real do aplicativo, em vídeo sintético
        cid = ids[1]

        def preview_ready(version_after):
            r = srv.post('/api/project/get', {'id': cid})
            pr = r['preview']
            return r if pr.get('ready') and pr.get('available') and r['version'] >= version_after else None
        base = wait_for(lambda: preview_ready(0), 240)
        check('t4_previa_inicial_pronta', bool(base))
        raw0 = srv.get(f'/media/preview?id={cid}&pv=0') if base else b''
        (work / 'prev0.mp4').write_bytes(raw0)
        comp = dict(layout='cam_ampliada', regions=dict(webcam=dict(x=.70, y=.03, w=.27, h=.42), conteudo=dict(x=0, y=0, w=.58, h=1)),
                    scenes=[dict(id='a', start=2.0, end=4.0, layout='foco_reacao', fade=0)])
        project = dict(base['project'] or {}, composition=comp)
        saved = srv.post('/api/project/save', {'id': cid, 'version': base['version'], 'project': project, 'preview': True, 'learn': False})
        again = wait_for(lambda: preview_ready(saved['version']), 240)
        check('t4_previa_nova_pronta_apos_escolher_layout', bool(again))
        if again:
            (work / 'prev1.mp4').write_bytes(srv.get(f'/media/preview?id={cid}&pv={again["preview"]["version"]}'))
            f0, f1 = frames(work / 'prev0.mp4', .5, 'scale=54:96,format=gray'), frames(work / 'prev1.mp4', .5, 'scale=54:96,format=gray')
            check('t4_previa_muda_com_o_layout', float(np.abs(f0 - f1).mean()) > 8, float(np.abs(f0 - f1).mean()))
        # exportação
        ver = srv.post('/api/project/get', {'id': cid})['version']
        srv.post('/api/review', {'id': cid, 'version': ver, 'action': 'approve', 'quality_mode': 'rapido'})
        done = wait_for(lambda: (lambda r: r if r['status'] == 'done' else None)(srv.post('/api/project/get', {'id': cid})), 300, 2)
        check('t5_exportacao_concluida', bool(done), (srv.post('/api/project/get', {'id': cid}) or {}).get('error'))
        if done:
            out = work / 'export.mp4'
            out.write_bytes(srv.get(f'/media/export?id={cid}'))
            meta = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(out)], capture_output=True, text=True).stdout)
            vid = next(s for s in meta['streams'] if s['codec_type'] == 'video')
            check('t5_exportacao_1080x1920', (vid['width'], vid['height']) == (1080, 1920))
            check('t5_audio_unico', sum(1 for s in meta['streams'] if s['codec_type'] == 'audio') == 1)
            # webcam viva (topo muda no tempo) e conteúdo parado (base igual) fora da cena
            a1, a2 = frames(out, .3), frames(out, 1.3)
            top = slice(0, 76)
            check('t5_webcam_continua_animada_na_exportacao', float(np.abs(a1[top] - a2[top]).mean()) > 6, float(np.abs(a1[top] - a2[top]).mean()))
            check('t5_conteudo_parado_continua_parado', float(np.abs(a1[110:] - a2[110:]).mean()) < 1.0, float(np.abs(a1[110:] - a2[110:]).mean()))
            # T7 cena (2–4 s do clipe, que começa em 0,5 s do arquivo): foco na reação ≠ layout base
            base_f, scene_f = frames(out, 1.0), frames(out, 3.0)
            check('t7_cena_aparece_na_exportacao', float(np.abs(base_f - scene_f).mean()) > 10, float(np.abs(base_f - scene_f).mean()))
    finally:
        srv.stop()
    # T6 persistência: reinicia o servidor e confere a composição salva
    srv2 = Server(pkg, root, a.porta, a.python)
    srv2.start()
    try:
        got = srv2.post('/api/project/get', {'id': ids[1]})['project']['composition']
        check('t6_composicao_persiste_apos_reiniciar', got and got['layout'] == 'cam_ampliada' and got['scenes'][0]['layout'] == 'foco_reacao' and 'webcam' in got['regions'], got)
    finally:
        srv2.stop()
    # T9 instalação limpa: nada do repositório no caminho de importação do servidor
    check('t9_pacote_nao_contem_testes_nem_fontes_de_ui', not (pkg / 'tests').exists() and not (pkg / 'ui').exists())
    print(json.dumps(dict(resultados=results, falhas=fails), ensure_ascii=False, indent=1))
    shutil.rmtree(work, ignore_errors=True)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
