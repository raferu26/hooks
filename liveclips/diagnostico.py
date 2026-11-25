"""DIAGNOSTICO_WINDOWS: relatório legível, local, sem vídeos, projetos, senhas nem tokens. Nada é enviado: o arquivo fica na pasta para
você revisar e compartilhar se quiser. Responde, com fatos, "estou abrindo a versão certa e ela tem os recursos?"."""
import hashlib
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import buildinfo, desktop, funcionalidades, media, support

ROOT = buildinfo.ROOT
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def _lines(title, rows):
    return ['', '== ' + title + ' =='] + [('  [OK]    ' if ok else '  [FALHA] ' if ok is False else '  [info]  ') + text for ok, text in rows]


def integrity():
    """Arquivos do pacote conferem com o MANIFESTO.sha256?"""
    manifest = ROOT / 'MANIFESTO.sha256'
    if not manifest.exists():
        return None, 'sem MANIFESTO.sha256 (instalação a partir do repositório de desenvolvimento)'
    bad, total = [], 0
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if '  ' not in line:
            continue
        digest, name = line.split('  ', 1)
        if name.startswith('wheels/'):
            continue
        total += 1
        path = ROOT / name
        if not path.exists():
            bad.append(name + ' (ausente)')
        elif name.endswith(('.bat', '.ps1')):
            continue                                  # o manifesto guarda o hash com CRLF; o Windows pode regravar o arquivo
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            bad.append(name + ' (diferente)')
    return not bad, f'{total} arquivos conferidos' if not bad else 'divergentes: ' + ', '.join(bad[:8])


def other_processes():
    if os.name != 'nt':
        return None, 'verificação de processos só no Windows'
    try:
        out = subprocess.run(['tasklist', '/fo', 'csv', '/nh', '/fi', 'imagename eq pythonw.exe'], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout
        out += subprocess.run(['tasklist', '/fo', 'csv', '/nh', '/fi', 'imagename eq python.exe'], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout
        n = sum(1 for l in out.splitlines() if 'python' in l.lower())
        return None, f'{n} processo(s) Python em execução (inclui o Hook’s atual, se aberto). Se a janela abrir a versão errada, feche o Hook’s antigo pelo botão Encerrar.'
    except (OSError, subprocess.SubprocessError) as exc:
        return None, 'não consegui listar processos: ' + str(exc)[:80]


def port_state(port=8765):
    s = socket.socket()
    s.settimeout(1)
    try:
        used = s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()
    return None, f'porta {port}: ' + ('EM USO (pode ser o Hook’s ou outro programa)' if used else 'livre')


def running_server(root):
    info = desktop.read_discovery(root)
    if not info:
        return None, 'nenhum servidor do Hook’s registrado em servidor.json (normal se o app está fechado)'
    live = desktop.alive(info)
    same = desktop.same_build(info)
    text = f'servidor registrado na porta {info.get("port")}: ' + ('respondendo' if live else 'NÃO responde (arquivo sobrou de uma queda)') + \
        f' · {desktop.describe(info)}'
    if live and not same:
        return False, text + ' · É OUTRA INSTALAÇÃO: o atalho desta versão não deve abrir esse servidor (feche-o pelo botão Encerrar).'
    return (True if live else None), text + (' · é desta instalação' if live else '')


def recent_errors(root, n=12):
    log = Path(root) / 'hooks_servidor.log'
    try:
        lines = [l for l in log.read_text(encoding='utf-8', errors='replace').splitlines() if any(w in l.lower() for w in ('error', 'erro', 'traceback', 'falha'))]
    except OSError:
        return None, 'sem log do servidor ainda'
    return (False if lines else True), ('\n      '.join(support.clean_text(l)[:200] for l in lines[-n:]) if lines else 'nenhum erro registrado no log do servidor')


def build(root=None):
    root = Path(root or desktop.default_root())
    info = buildinfo.read()
    out = [f'Hook’s — DIAGNÓSTICO — {time.strftime("%Y-%m-%d %H:%M:%S")}', 'Não contém vídeos, projetos, senhas nem tokens. Nada foi enviado. Revise antes de compartilhar.']
    out += _lines('Identidade desta instalação', [
        (None, f'Windows/sistema: {platform.platform()}'), (None, f'Pasta do aplicativo: {support.clean_text(str(ROOT))}'),
        (None, f'Pasta de dados: {support.clean_text(str(root))}'), (None, f'Versão: {info["version"]} · commit {info["commit"]} · variante {info["variant"]}'),
        (None, f'Build em: {info.get("built") or "desenvolvimento"} · ramo: {info.get("branch", "?")}'), (None, f'Python: {sys.version.split()[0]} ({platform.architecture()[0]})')])
    ui = buildinfo.ui_build()
    ok, detail = integrity()
    out += _lines('Arquivos', [(ok, 'Integridade (MANIFESTO.sha256): ' + detail), (ui['confere'], f'Interface (frontend) id {ui["id"]}: ' + ('confere com o conteúdo' if ui['confere'] else 'NÃO confere (arquivo alterado ou desatualizado)')),
                               ((ROOT / 'liveclips' / 'static' / 'index.html').exists(), 'liveclips/static/index.html presente')])
    tools = media.tool_status()
    try:
        ff = media.run([media.tool('ffmpeg'), '-version'], 20)
        ff = (ff.decode('utf-8', 'replace') if isinstance(ff, bytes) else ff).splitlines()[0]
    except Exception as exc:
        ff = 'indisponível: ' + str(exc)[:100]
    out += _lines('Ferramentas', [(bool(tools.get('ffmpeg')), 'FFmpeg: ' + ff), (bool(tools.get('ffprobe')), 'FFprobe')])
    flags = subprocess.run([media.tool('ffmpeg'), '-hide_banner', '-filters'], capture_output=True, text=True, creationflags=NO_WINDOW).stdout if tools.get('ffmpeg') else ''
    need = ('ass', 'scale', 'overlay', 'crop', 'blend', 'concat', 'lutyuv', 'gblur', 'boxblur', 'drawbox', 'trim', 'fps', 'split', 'loudnorm')
    miss = [n for n in need if (' ' + n + ' ') not in flags]
    out += _lines('Filtros de renderização (composição)', [(not miss, 'todos presentes: ' + ', '.join(need) if not miss else 'FALTAM: ' + ', '.join(miss))])
    try:
        from . import hardware
        gpu = hardware.detect()
        out += _lines('Codificação', [(None, 'CPU (x264): sempre disponível; Entrega usa CPU'), (None, 'GPU que funciona de verdade: ' + (', '.join(gpu) if gpu else 'nenhuma (usa a CPU)'))])
    except Exception as exc:
        out += _lines('Codificação', [(None, 'não consegui detectar GPU: ' + str(exc)[:100])])
    rows = funcionalidades.run_all(root=Path(root) / 'diagnostico_tmp', render=bool(tools.get('ffmpeg')))
    out += _lines('Recursos declarados nesta versão (devem estar no produto)', [(ok, f'{name}: {detail}') for name, ok, detail in rows])
    out += _lines('Recursos esperados', [(None, ', '.join(funcionalidades.declared(info)))])
    out += _lines('Servidor, portas e processos', [running_server(root), port_state(), other_processes()])
    out += _lines('Erros recentes do servidor', [recent_errors(root)])
    try:
        import shutil
        shutil.rmtree(Path(root) / 'diagnostico_tmp', ignore_errors=True)
    except OSError:
        pass
    return '\n'.join(out) + '\n'


def main(argv=()):
    root = Path(argv[0]) if argv else desktop.default_root()
    text = build(root)
    target = Path.cwd() / 'diagnostico_windows.txt'
    target.write_text(text, encoding='utf-8')
    print(text)
    print('Relatório salvo em:', target, '\nRevise e, se quiser, envie esse arquivo. Nada foi enviado pela internet.')
    return 1 if 'FALHA' in text else 0
