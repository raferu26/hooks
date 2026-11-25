"""Abre o Hook’s como aplicativo: sobe o servidor em segundo plano (sem janela preta) e abre uma janela própria.

Uso (o atalho do Windows chama isto com pythonw, sem console):  pythonw -m liveclips.desktop
Fluxo: acha o servidor já aberto ou inicia um; abre a janela (Edge ou Chrome em modo aplicativo); quando a janela
fecha, encerra o Hook’s sozinho SE não houver gravação, análise nem exportação em andamento. Se houver, o Hook’s
continua em segundo plano e avisa: abrir o atalho de novo traz a janela de volta.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

DISCOVERY = 'servidor.json'
WATCH_LOCK = 'janela.lock'
LOG = 'hooks_servidor.log'


def default_root():
    return Path(os.environ.get('LIVECLIPS_ROOT', r'C:\LiveClips' if os.name == 'nt' else str(Path.home() / 'LiveClips'))).resolve()


def message(text, title='Hook’s'):
    """Aviso visível mesmo sem console. No Windows usa uma caixa de mensagem; fora dele escreve no terminal."""
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40 | 0x1000)
            return
        except Exception:
            pass
    print(title + ': ' + text, file=sys.stderr, flush=True)


# ───── servidor ─────
def read_discovery(root):
    try:
        info = json.loads((Path(root) / DISCOVERY).read_text(encoding='utf-8'))
        return info if isinstance(info, dict) and info.get('port') else None
    except (OSError, ValueError):
        return None


def _open(info, path='/', data=None, timeout=3):
    url = f"http://127.0.0.1:{int(info['port'])}{path}"
    headers = {'X-LiveClips-Token': str(info.get('token', ''))}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def same_build(info, mine=None):
    """O servidor descrito em servidor.json é desta instalação (mesma versão, mesmo commit, mesma pasta)? Arquivo antigo, sem esses
    campos, conta como "outra instalação": nunca se presume que é a mesma."""
    from . import buildinfo
    mine = mine or buildinfo.identity()
    if not info or not all(info.get(k) for k in ('versao', 'commit', 'install')):
        return False
    norm = lambda p: os.path.normcase(os.path.normpath(str(p)))
    return (info['versao'], info['commit'], norm(info['install'])) == (mine['versao'], mine['commit'], norm(mine['install']))


def describe(info):
    return f"versão {info.get('versao') or 'anterior (sem identificação)'}" + (f" ({str(info['commit'])[:10]})" if info.get('commit') else '') + \
        (f" da pasta {info['install']}" if info.get('install') else '')


def confirm(text, title='Hook’s'):
    """Pergunta Sim/Não. No Windows usa uma caixa de mensagem; fora dele, False (não decide por você)."""
    if os.name == 'nt':
        try:
            import ctypes
            return ctypes.windll.user32.MessageBoxW(None, text, title, 0x24 | 0x1000) == 6
        except Exception:
            return False
    print(title + ': ' + text, file=sys.stderr, flush=True)
    return False


def replace_other_install(info, show, ask, sleep=time.sleep, now=time.time, timeout=25):
    """Outra instalação do Hook’s responde sobre a mesma pasta de dados. Devolve True se ela foi encerrada (com o seu OK, e só se estiver
    ociosa) e dá para subir esta; False se nada foi feito (a janela NÃO deve abrir na versão errada)."""
    act = activity(info)
    if not is_idle(act):
        show('Outra versão do Hook’s (' + describe(info) + ') está aberta e ' + ('ocupada (gravando, analisando ou exportando)' if act else 'não respondeu sobre o que faz') +
             '.\n\nNão vou encerrá-la sozinha. Abra a janela dela, espere terminar e use o botão Encerrar; depois clique neste atalho de novo.\n\nNenhum dado foi alterado.')
        return False
    if not ask('Outra versão do Hook’s está aberta sobre os mesmos dados:\n' + describe(info) + '\n\nPara abrir ESTA versão preciso encerrar a anterior. '
               'Nenhum projeto ou dado é apagado.\n\nEncerrar a anterior e abrir esta?'):
        show('Certo, não alterei nada. A janela só abre quando não houver outra versão rodando.')
        return False
    request_quit(info)
    limit = now() + timeout
    while now() < limit and alive(info):
        sleep(.5)
    if alive(info):
        show('A versão anterior não encerrou. Feche-a pelo botão Encerrar dentro dela e tente de novo.')
        return False
    return True


def alive(info):
    """O servidor descrito em servidor.json responde de verdade (o arquivo pode ter sobrado de uma queda)."""
    try:
        return bool(info) and bool(_open(info, '/'))
    except (OSError, ValueError):
        return False


def activity(info):
    """O que o Hook’s está fazendo; None se não deu para saber."""
    try:
        return json.loads(_open(info, '/api/state', timeout=8)).get('activity')
    except (OSError, ValueError, AttributeError):
        return None


def is_idle(act):
    return bool(act) and not act.get('capturas') and not act.get('analisando') and not act.get('exportando')


def request_quit(info):
    try:
        _open(info, '/api/app/quit', {}, timeout=8)
        return True
    except (OSError, ValueError):
        return False


def server_python(executable=None):
    """Servidor roda com python.exe (console escondido): assim ffmpeg e streamlink não abrem janelas pretas."""
    exe = Path(executable or sys.executable)
    if exe.name.lower() == 'pythonw.exe':
        candidate = exe.with_name('python.exe')
        if candidate.exists():
            return candidate
    return exe


def start_server(root, popen=subprocess.Popen, executable=None):
    root = Path(root)
    exe = server_python(executable)
    env = os.environ.copy()
    env['PATH'] = str(exe.parent) + os.pathsep + env.get('PATH', '')
    env['LIVECLIPS_ROOT'] = str(root)
    logs = root / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    log = open(logs / LOG, 'ab')
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
    try:
        return popen([str(exe), '-m', 'liveclips', '--root', str(root), '--no-browser'], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, env=env, cwd=str(Path(__file__).resolve().parent.parent), creationflags=flags)
    finally:
        log.close()                              # o processo filho tem a própria cópia do arquivo


class StartError(RuntimeError):
    pass


def wait_ready(root, proc=None, timeout=180, sleep=time.sleep, now=time.time):
    """Espera o servidor aparecer. O primeiro start pode levar dezenas de segundos (carrega os modelos)."""
    limit = now() + timeout
    while now() < limit:
        info = read_discovery(root)
        if info and alive(info):
            return info
        if proc is not None and proc.poll() is not None:
            info = read_discovery(root)          # corrida: outro atalho pode ter subido o servidor
            if info and alive(info):
                return info
            raise StartError('O Hook’s fechou logo depois de abrir.')
        sleep(.5)
    raise StartError('O Hook’s demorou demais para ficar pronto.')


# ───── janela ─────
def find_browser(env=None, exists=os.path.exists, which=shutil.which):
    """Edge (já vem no Windows 10/11) e depois Chrome. Fora do Windows tenta o que houver, só para desenvolvimento."""
    env = os.environ if env is None else env
    roots = [env.get(k) for k in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA') if env.get(k)]
    for rel in (r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe'):
        for base in roots:
            path = os.path.join(base, rel)
            if exists(path):
                return path
    for name in ('msedge', 'microsoft-edge', 'google-chrome', 'chromium', 'chromium-browser'):
        found = which(name)
        if found:
            return found
    return None


def window_command(browser, url, profile):
    return [browser, f'--app={url}', f'--user-data-dir={profile}', '--window-size=1440,900', '--no-first-run',
            '--no-default-browser-check']


class Lock:
    """Quem segura o lock é o 'vigia': o único atalho que decide encerrar o Hook’s quando a janela fecha."""
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        try:
            handle.seek(0, 2)
            if not handle.tell():                # no Windows o trecho travado precisa existir no arquivo
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self):
        if self.handle:
            try:
                self.handle.close()
            finally:
                self.handle = None


def watch(window, info, sleep=time.sleep, alive_fn=alive, misses=3, every=3.0, now=time.time):
    """Espera a janela fechar. Se o servidor sumir antes (botão Encerrar), fecha a janela também."""
    gone = 0
    next_check = now()
    while window.poll() is None:
        sleep(.5)
        if now() >= next_check:
            next_check = now() + every
            gone = 0 if alive_fn(info) else gone + 1
            if gone >= misses:
                try:
                    window.terminate()
                except OSError:
                    pass
                return 'servidor_encerrou'
    return 'janela_fechou'


def launch(root, popen=subprocess.Popen, show=message, sleep=time.sleep, browser_finder=find_browser, open_default=webbrowser.open,
           ready_timeout=180, min_window_s=8.0, now=time.time, ask=None):
    ask = ask or confirm
    root = Path(root)
    lock = Lock(root / WATCH_LOCK)
    watcher = lock.acquire()
    try:
        info = read_discovery(root)
        proc = None
        if info and alive(info) and not same_build(info):
            if not replace_other_install(info, show, ask, sleep=sleep, now=now):
                return 1
            info = None
        if not (info and alive(info)):
            if watcher:
                proc = start_server(root, popen)
            info = wait_ready(root, proc, timeout=ready_timeout, sleep=sleep)
        url = f"http://127.0.0.1:{int(info['port'])}"
        browser = browser_finder()
        if not browser:
            open_default(url)
            show('Não encontrei o Microsoft Edge nem o Google Chrome para abrir a janela do Hook’s, então abri no seu navegador padrão.\n\n'
                 'O Hook’s continua rodando em segundo plano. Para encerrar, use o botão Encerrar dentro do app.')
            return 0
        opened = now()
        window = popen(window_command(browser, url, root / 'janela'))
        if not watcher:
            return 0                              # outro atalho já vigia; este só trouxe a janela
        result = watch(window, info, sleep=sleep)
        if result == 'servidor_encerrou':
            return 0
        if now() - opened < min_window_s:
            # Navegador que repassa a janela a outro processo e sai na hora: não dá para saber se a janela ainda está aberta.
            # Na dúvida, o Hook’s continua rodando (encerrar por engano no meio de uma live é pior do que ficar aberto).
            show('A janela do Hook’s fechou rápido demais para eu saber se você terminou, então deixei o Hook’s rodando em segundo plano.\n\n'
                 'Clique no atalho para abrir a janela de novo. Para encerrar de vez, use o botão Encerrar dentro do app.')
            return 0
        if not alive(info):
            return 0
        act = activity(info)
        if is_idle(act):
            request_quit(info)
            return 0
        if act is None:
            return 0                              # sem leitura confiável: não derruba um servidor que talvez esteja gravando
        partes = []
        if act.get('capturas'):
            partes.append(f"gravando {act['capturas']} live(s)")
        if act.get('analisando'):
            partes.append('analisando')
        if act.get('exportando'):
            partes.append(f"exportando {act['exportando']} clipe(s)")
        show('O Hook’s continua ' + ' e '.join(partes) + ' em segundo plano.\n\n'
             'Clique no atalho do Hook’s para abrir a janela de novo. Para encerrar de vez, abra o app e use o botão Encerrar.')
        return 0
    finally:
        lock.release()


def main(argv=None):
    root = default_root()
    try:
        return launch(root)
    except Exception as exc:
        show = f'Não foi possível abrir o Hook’s.\n\n{exc}\n\nDetalhes em: {root / "logs" / LOG}'
        message(show)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
