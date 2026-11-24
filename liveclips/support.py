"""Apoio ao usuário: tempo restante, log em arquivo e pacote de diagnóstico para enviar quando algo falha."""
import datetime as dt
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import re
import time
import zipfile
from pathlib import Path

LOG_NAME = 'liveclips.log'
SECRET = re.compile(r'(?i)((?:token|oauth|sig|signature|key|auth|authorization|password|senha|secret|cookie|session|sessao)[=:]\s*(?:bearer\s+)?)[^&\s"\';]+')
BEARER = re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}')
USER_DIR = re.compile(r'(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s"\']+|(/(?:home|Users)/)[^/\s"\']+')


class Eta:
    """Tempo restante a partir da velocidade média. Só opina depois de 5 s e 3% de avanço (antes disso o número seria chute)."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()

    def update(self, fraction):
        fraction = max(0.0, min(1.0, float(fraction)))
        elapsed = self.clock() - self.started
        if fraction >= .999:
            return dict(percent=100, eta=0)
        if elapsed < 5 or fraction < .03:
            return dict(percent=round(fraction * 100), eta=None)
        return dict(percent=round(fraction * 100), eta=round(elapsed * (1 - fraction) / fraction))


def human(seconds):
    if seconds is None:
        return ''
    seconds = int(seconds)
    if seconds < 60:
        return 'menos de 1 min'
    minutes = round(seconds / 60)
    if minutes < 60:
        return f'~{minutes} min'
    hours, rest = divmod(minutes, 60)
    return f'~{hours} h' + (f' {rest} min' if rest else '')


def clean_text(text, home=None):
    """Tira do texto o que não deve viajar: tokens/senhas em URLs e a pasta pessoal do usuário."""
    text = BEARER.sub(r'\1[oculto]', SECRET.sub(r'\1[oculto]', str(text)))
    text = USER_DIR.sub(lambda m: (m.group(1) or m.group(2)) + '~', text)
    for folder in {str(home or Path.home()), os.environ.get('USERPROFILE', '')}:
        if folder and len(folder) > 3:
            text = text.replace(folder, '~').replace(folder.replace('\\', '/'), '~')
    return text


def setup_logging(root):
    """Log rotativo em <pasta de dados>/logs. Chamar uma vez; repetir não duplica o arquivo."""
    folder = Path(root) / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('liveclips')
    logger.setLevel(logging.INFO)
    target = str((folder / LOG_NAME).resolve())
    if not any(getattr(h, 'baseFilename', None) == target for h in logger.handlers):
        handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    return logger


def log_error(message, exc=None):
    logging.getLogger('liveclips').error(message, exc_info=exc)


def _tail(path, limit=200_000):
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode('utf-8', 'replace')
    except OSError:
        return ''


def _run(cmd, timeout=15):
    import subprocess
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=flags, errors='replace')
        return cp.stdout if cp.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def environment_report(ffmpeg=None):
    """Linhas de diagnóstico do computador para os testes: CPU, memória, placa(s) de vídeo, codificadores do FFmpeg e versões das bibliotecas.
    Só leitura e só hardware/software: sem nome de usuário, sem arquivos, sem rede. Cada fonte que falhar vira 'indisponível'."""
    import importlib.metadata as md
    lines = ['Computador:']
    cpu = mem = ''
    gpus = []
    if os.name == 'nt':
        out = _run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                    "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name; '---'; "
                    "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' | driver ' + $_.DriverVersion }; '---'; "
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"], 25).split('---')
        if len(out) == 3:
            cpu = out[0].strip(); gpus = [g.strip() for g in out[1].splitlines() if g.strip()]
            try:
                mem = '%.1f GB' % (int(out[2].strip()) / 1024 ** 3)
            except ValueError:
                mem = ''
    else:
        try:
            cpu = next((l.split(':', 1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')), '')
            mem = '%.1f GB' % (int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal'))) / 1024 ** 2)
        except (OSError, StopIteration, ValueError):
            pass
        smi = _run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'], 10)
        gpus = [g.strip() for g in smi.splitlines() if g.strip()]
    lines += [f'  CPU: {cpu or "indisponível"} · {os.cpu_count()} processadores lógicos', f'  Memória: {mem or "indisponível"}',
              '  Placa(s) de vídeo: ' + ('; '.join(gpus) if gpus else 'indisponível')]
    if ffmpeg:
        enc = _run([ffmpeg, '-hide_banner', '-encoders'], 20)
        found = sorted({w for w in ('h264_nvenc', 'hevc_nvenc', 'h264_qsv', 'h264_amf', 'libx264') if w in enc})
        ver = (_run([ffmpeg, '-version'], 10).splitlines() or [''])[0]
        filt = _run([ffmpeg, '-hide_banner', '-filters'], 20)
        lines += [f'  FFmpeg: {ver}', '  Codificadores de vídeo: ' + (', '.join(found) or 'nenhum reconhecido'),
                  '  Filtros de áudio usados pelo Hook’s: ' + ', '.join(f'{n}={"sim" if (" " + n + " ") in filt else "NÃO"}' for n in ('afftdn', 'afwtdn', 'anlmdn', 'sidechaincompress', 'loudnorm', 'alimiter', 'ass'))]
    libs = []
    for name in ('numpy', 'opencv-python-headless', 'opencv-contrib-python', 'pillow', 'streamlink', 'yt-dlp', 'cryptography', 'opentimelineio', 'faster-whisper', 'mediapipe'):
        try:
            libs.append(f'{name} {md.version(name)}')
        except md.PackageNotFoundError:
            libs.append(f'{name} (não instalado)')
    lines += ['', 'Bibliotecas:'] + ['  ' + l for l in libs]
    try:
        from . import buildinfo
        b = buildinfo.read()
        lines += ['', f'Build: {b["label"]}', f'Contém: {", ".join(b.get("includes") or []) or "desenvolvimento"}']
    except Exception:
        pass
    return lines


def bundle(root, store, version, tools=None, extra=None):
    """ZIP com log, eventos recentes e dados do sistema. Sem vídeos, banco, perfis ou chat. → caminho do ZIP."""
    root = Path(root)
    folder = root / 'diagnosticos'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    destination = folder / f'LiveClips-diagnostico-{stamp}.zip'
    counts = {}
    for label, sql in (('streamers', 'SELECT COUNT(*) n FROM streamers'), ('sessões', 'SELECT COUNT(*) n FROM sessions'),
                       ('segmentos', 'SELECT COUNT(*) n FROM segments')):
        try:
            counts[label] = store.rows(sql)[0]['n']
        except Exception:
            counts[label] = '?'
    try:
        for row in store.rows('SELECT status, COUNT(*) n FROM candidates GROUP BY status'):
            counts['cortes ' + str(row['status'])] = row['n']
    except Exception:
        pass
    try:
        import shutil
        free = round(shutil.disk_usage(root).free / 1024 ** 3, 1)
    except OSError:
        free = '?'
    info = [f'Hook’s {version}', f'Gerado em {dt.datetime.now().astimezone().isoformat(timespec="seconds")}',
            f'Python {platform.python_version()} · {platform.platform()}', f'Espaço livre: {free} GB', '']
    info += [f'{k}: {v}' for k, v in counts.items()]
    try:
        info += [''] + environment_report((tools or {}).get('ffmpeg'))
    except Exception:
        info += ['', 'Relatório do computador indisponível.']
    if extra:
        info += [''] + [str(line) for line in extra]
    if tools:
        info += ['', 'Ferramentas:'] + [f'  {name}: {"ok" if path else "FALTA"}' for name, path in sorted(tools.items())]
    events = []
    try:
        for row in store.rows('SELECT * FROM events ORDER BY id DESC LIMIT 300'):
            when = dt.datetime.fromtimestamp(row['created']).strftime('%Y-%m-%d %H:%M:%S')
            events.append(f'{when} [{row["kind"]}] {row["message"]}')
    except Exception:
        pass
    pending = destination.with_suffix('.tmp')
    with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('sistema.txt', clean_text('\n'.join(info)))
        archive.writestr('eventos.txt', clean_text('\n'.join(events)))
        for index, log in enumerate(sorted((root / 'logs').glob('liveclips.log*'), key=lambda p: p.stat().st_mtime, reverse=True)[:2]):
            archive.writestr(f'logs/{log.name}', clean_text(_tail(log)))
        try:
            sessions = store.rows('SELECT path FROM sessions ORDER BY created DESC LIMIT 8')
        except Exception:
            sessions = []
        for number, session in enumerate(sessions):
            capture = Path(session['path']) / 'captura.log'
            if capture.is_file():
                archive.writestr(f'captura_{number + 1}.log', clean_text(_tail(capture, 60_000)))
            ended = Path(session['path']) / 'captura_fim.json'
            if ended.is_file():
                archive.writestr(f'captura_{number + 1}_fim.json', clean_text(_tail(ended, 4_000)))
    pending.replace(destination)
    return destination
