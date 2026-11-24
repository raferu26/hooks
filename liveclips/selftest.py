"""Autoteste de instalação (`python -m liveclips selfcheck`) e medição de desempenho (`python -m liveclips medir`) para os testes físicos.

Nada daqui envia dados para fora, abre rede ou lê arquivos pessoais: usa mídia sintética gerada em pasta temporária. Os relatórios saem em JSON
no diretório atual com caminhos/usuário ocultados (`support.clean_text`)."""
import importlib
import json
import os
import pkgutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import __version__, buildinfo, media, support

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
CRITICAL = ('modulos', 'ffmpeg', 'codificacao_cpu', 'servidor')


def _ff(args, timeout=120):
    return subprocess.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *args], capture_output=True, timeout=timeout, creationflags=FLAGS)


def _step(name, fn, results):
    t = time.time()
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f'{type(exc).__name__}: {exc}'
    results.append(dict(passo=name, ok=bool(ok), detalhe=support.clean_text(str(detail))[:600], segundos=round(time.time() - t, 2)))
    print(('[OK]    ' if ok else '[FALHA] ') + name + ' - ' + str(detail)[:140], flush=True)


def _modules():
    import liveclips
    bad = []
    for m in pkgutil.iter_modules(liveclips.__path__):
        try:
            importlib.import_module('liveclips.' + m.name)
        except Exception as exc:
            bad.append(f'{m.name}: {type(exc).__name__}: {exc}')
    return not bad, 'todos os módulos importam' if not bad else '; '.join(bad)[:500]


def _tools():
    status = media.tool_status()
    missing = [k for k, v in status.items() if not v and k in ('ffmpeg', 'ffprobe')]
    return not missing, ', '.join(f'{k}={"ok" if v else "FALTA"}' for k, v in sorted(status.items()))


def _filters():
    out = subprocess.run([media.tool('ffmpeg'), '-hide_banner', '-filters'], capture_output=True, text=True, creationflags=FLAGS).stdout
    need = ('ass', 'loudnorm', 'alimiter', 'sidechaincompress', 'afftdn', 'scale', 'overlay', 'gblur')
    miss = [n for n in need if (' ' + n + ' ') not in out]
    extra = [n for n in ('afwtdn', 'anlmdn') if (' ' + n + ' ') not in out]
    return not miss, ('faltam: ' + ', '.join(miss)) if miss else 'filtros obrigatórios presentes' + (f' (sem {", ".join(extra)}: usa o plano B)' if extra else '')


def _cpu_encode(tmp):
    t = time.time()
    cp = _ff(['-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=30:d=2', '-f', 'lavfi', '-i', 'sine=d=2', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(tmp / 'cpu.mp4')])
    return cp.returncode == 0 and (tmp / 'cpu.mp4').stat().st_size > 1000, f'2 s 1080x1920 em {time.time() - t:.1f} s' if cp.returncode == 0 else cp.stderr.decode('utf-8', 'replace')[-300:]


def _gpu_encoders():
    from . import hardware
    found = hardware.detect()
    return True, ('codificadores de GPU que FUNCIONAM (teste real): ' + ', '.join(found)) if found else 'nenhum codificador de GPU funcionando (usa a CPU)'


def _captions_render(tmp):
    """O libass acha a fonte Arial e desenha a legenda? (no Windows depende do FFmpeg/fontes instalados)"""
    from . import captions
    ass = captions.make_ass([dict(start=0, end=2, text='HOOK AGORA', words=[])], 0, 2, font_size=46, margin=340, style='dynamic', font='Arial', keep_lines=True)
    (tmp / 'c.ass').write_text(ass, encoding='utf-8')
    cp = _ff(['-f', 'lavfi', '-i', 'color=black:s=1080x1920:d=1:r=10', '-vf', f"ass='{(tmp / 'c.ass').as_posix().replace(':', chr(92) + ':')}'", '-frames:v', '1', str(tmp / 'c.png')])
    if cp.returncode:
        return False, cp.stderr.decode('utf-8', 'replace')[-300:]
    from PIL import Image
    import numpy as np
    a = np.array(Image.open(tmp / 'c.png').convert('RGB')).max(axis=2)
    ink = int((a > 150).sum())
    return ink > 2000, f'{ink} pixels de texto desenhados'


def _server(tmp):
    import urllib.request
    from .app import App, server
    app = App(str(tmp / 'dados'), worker=False)
    try:
        srv = server(app, 0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=10) as r:
            html = r.read(200000)
        ok = r.status == 200 and b'Hook' in html
        srv.shutdown()
        return ok, f'servidor local respondeu em 127.0.0.1:{port} ({len(html)} bytes)'
    finally:
        app.close()


def selfcheck(out_dir='.'):
    print(f'Hook’s - autoteste de instalação · {buildinfo.read()["label"]}', flush=True)
    results = []
    tmp = Path(tempfile.mkdtemp(prefix='hooks_selfcheck_'))
    _step('modulos', _modules, results)
    _step('ferramentas', _tools, results)
    _step('ffmpeg', _filters, results)
    _step('codificacao_cpu', lambda: _cpu_encode(tmp), results)
    _step('gpu', _gpu_encoders, results)
    _step('legenda_libass', lambda: _captions_render(tmp), results)
    _step('servidor', lambda: _server(tmp), results)
    report = dict(versao=__version__, build=buildinfo.read(), python=sys.version.split()[0], sistema=support.clean_text(' '.join(support.environment_report(media.tool('ffmpeg')))), resultados=results)
    report['sistema'] = support.clean_text('\n'.join(support.environment_report(media.tool('ffmpeg'))))
    path = Path(out_dir) / 'relatorio_autoteste.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    failed = [r['passo'] for r in results if not r['ok']]
    crit = [p for p in failed if p in CRITICAL]
    print(f'\nResultado: {len(results) - len(failed)}/{len(results)} passos OK. Relatório: {path}', flush=True)
    if crit:
        print('FALHAS CRÍTICAS: ' + ', '.join(crit) + ' - envie o relatório.', flush=True)
    return 1 if crit else 0


# ── medição de desempenho (CPU, memória, GPU) ──
class Sampler(threading.Thread):
    """Amostra, a cada `step` s, o uso de CPU do sistema, a memória (pico) do processo filho e a GPU NVIDIA, se existir. Só leitura."""

    def __init__(self, pid, step=.5):
        super().__init__(daemon=True)
        self.pid, self.step, self.stop_flag = pid, step, threading.Event()
        self.cpu, self.rss, self.gpu, self.vram = [], 0.0, [], 0.0

    def _cpu_times(self):
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            f = lambda t: (t.dwHighDateTime << 32) | t.dwLowDateTime
            return f(idle), f(kern) + f(user)
        try:
            v = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
            return v[3] + v[4], sum(v)
        except (OSError, ValueError):
            return 0, 1

    def _rss_mb(self):
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                            ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
            h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, self.pid)
            if not h:
                return 0.0
            pmc = PMC(); pmc.cb = ctypes.sizeof(pmc)
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
            ctypes.windll.kernel32.CloseHandle(h)
            return pmc.PeakWorkingSetSize / 1048576 if ok else 0.0
        try:
            for line in Path(f'/proc/{self.pid}/status').read_text().splitlines():
                if line.startswith('VmHWM'):
                    return int(line.split()[1]) / 1024
        except (OSError, ValueError):
            pass
        return 0.0

    def _gpu(self):
        try:
            out = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3, creationflags=FLAGS).stdout
            u, m = [float(x) for x in out.splitlines()[0].split(',')]
            return u, m
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return None

    def run(self):
        idle0, tot0 = self._cpu_times()
        while not self.stop_flag.wait(self.step):
            idle, tot = self._cpu_times()
            if tot > tot0:
                self.cpu.append(100.0 * (1 - (idle - idle0) / (tot - tot0)))
            idle0, tot0 = idle, tot
            self.rss = max(self.rss, self._rss_mb())
            g = self._gpu()
            if g:
                self.gpu.append(g[0]); self.vram = max(self.vram, g[1])

    def summary(self):
        avg = lambda v: round(sum(v) / len(v), 1) if v else None
        return dict(cpu_sistema_media_pct=avg(self.cpu), cpu_sistema_pico_pct=round(max(self.cpu), 1) if self.cpu else None, memoria_pico_mb=round(self.rss),
                    gpu_media_pct=avg(self.gpu), gpu_pico_pct=max(self.gpu) if self.gpu else None, vram_pico_mb=round(self.vram) if self.gpu else None)


def _timed_encode(args, seconds):
    p = subprocess.Popen([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *args], stderr=subprocess.PIPE, creationflags=FLAGS)
    s = Sampler(p.pid); s.start(); t = time.time()
    err = p.communicate()[1]
    wall = time.time() - t; s.stop_flag.set(); s.join(2)
    return dict(ok=p.returncode == 0, segundos=round(wall, 2), vezes_tempo_real=round(wall / seconds, 2), **s.summary(), erro=(err or b'').decode('utf-8', 'replace')[-200:])


def medir(out_dir='.', seconds=20):
    """Exporta um clipe SINTÉTICO 1080x1920 de `seconds` s em cada modo de qualidade e codificador disponível e registra tempo, CPU, memória e GPU."""
    from . import hardware, telemetry
    tmp = Path(tempfile.mkdtemp(prefix='hooks_medir_'))
    src = tmp / 'origem.mp4'
    print('Gerando clipe sintético…', flush=True)
    _ff(['-f', 'lavfi', '-i', f'testsrc2=s=1920x1080:r=60:d={seconds}', '-f', 'lavfi', '-i', f'sine=f=300:d={seconds}', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(src)], 300)
    found = hardware.detect()
    rows = []
    for mode in ('rapido', 'equilibrado', 'qualidade', 'entrega'):
        kinds = ['cpu'] + ([k for k in found] if not telemetry.MODES[mode]['cpu_only'] else [])
        for kind in kinds:
            args = hardware.mode_arguments(kind, mode)
            row = dict(modo=mode, codificador=kind, parametros=' '.join(args))
            print(f'  {mode} / {kind}…', flush=True)
            row.update(_timed_encode(['-i', str(src), '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,format=yuv420p', *args, '-c:a', 'aac', '-b:a', '160k', str(tmp / f'{mode}_{kind}.mp4')], seconds))
            out = tmp / f'{mode}_{kind}.mp4'
            row['tamanho_mb'] = round(out.stat().st_size / 1048576, 2) if out.exists() else None
            rows.append(row)
    report = dict(versao=__version__, build=buildinfo.read(), clipe=f'sintético {seconds} s 1920x1080@60 → 1080x1920', sistema=support.clean_text('\n'.join(support.environment_report(media.tool('ffmpeg')))), exportacoes=rows)
    path = Path(out_dir) / 'relatorio_desempenho.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\nRelatório: {path}', flush=True)
    return 0


def relatorio(out_root=None, extra_files=()):
    """Junta, num ZIP para enviar, só o que ajuda a diagnosticar: pacote de diagnóstico (log, eventos, hardware; sem vídeos/banco/perfis),
    relatórios de autoteste e desempenho, log da instalação e o checklist preenchido — tudo passado por `support.clean_text` (nome de usuário e
    tokens ocultados). Devolve o caminho do ZIP e a lista do que foi incluído."""
    import datetime as dt
    import zipfile
    from .store import Store
    root = Path(out_root or os.environ.get('LIVECLIPS_ROOT', r'C:\LiveClips' if os.name == 'nt' else str(Path.home() / 'LiveClips'))).resolve()
    folder = Path('RELATORIOS'); folder.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    target = folder / f'Hooks-relatorio-{stamp}.zip'
    included = []
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        try:
            diag = support.bundle(root, Store(root), __version__, media.tool_status())
            with zipfile.ZipFile(diag) as d:
                for n in d.namelist():
                    z.writestr('diagnostico/' + n, d.read(n)); included.append('diagnostico/' + n)
        except Exception as exc:
            z.writestr('diagnostico/ERRO.txt', support.clean_text(f'{type(exc).__name__}: {exc}')); included.append('diagnostico/ERRO.txt')
        for name in ('relatorio_autoteste.json', 'relatorio_desempenho.json', 'instalacao_teste.log', 'CHECKLIST_W01_W10.md', 'REGISTRO_DE_PROBLEMAS.md', *extra_files):
            p = Path(name)
            if p.is_file() and p.stat().st_size < 2_000_000:
                z.writestr(p.name, support.clean_text(p.read_text(encoding='utf-8', errors='replace'))); included.append(p.name)
    print('Relatório criado:', target, flush=True)
    print('Dentro dele: ' + ', '.join(included), flush=True)
    print('NÃO vai: vídeos, banco de dados, perfis, chat. Nome de usuário do Windows e tokens são ocultados. Nada é enviado por este programa:', flush=True)
    print('você envia o ZIP manualmente para quem está ajudando.', flush=True)
    return target, included
