"""Biblioteca de músicas do editor.

Entradas aceitas: link do YouTube/SoundCloud (baixa só o áudio com yt-dlp) ou arquivo
de áudio do computador. Tudo vira um .m4a dentro de `<dados>/musicas/`, com uma análise
leve (forma de onda, andamento estimado e melhor trecho) usada pelo editor.

O Hook’s não decide sobre direitos autorais: a música só entra no corte depois de o
usuário confirmar a autorização no editor, e título/canal/link vão para `creditos.txt`.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import os
import subprocess
import tempfile
import time
from urllib.parse import parse_qs, urlparse

from . import media

MAX_SECONDS = 25 * 60
MAX_UPLOAD = 120 * 1024 ** 2
AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.aac', '.wav', '.flac', '.ogg', '.opus', '.webm', '.mp4')
HOSTS = ('youtube.com', 'youtu.be', 'music.youtube.com', 'soundcloud.com')
ID_RE = re.compile(r'^[a-f0-9]{16}$')


class MusicError(ValueError):
    pass


def folder(root):
    path = Path(root) / 'musicas'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_file(root):
    return folder(root) / 'index.json'


def load_index(root):
    try:
        value = json.loads(_index_file(root).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(root, index):
    target = _index_file(root)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf-8')
    temp.replace(target)


def clean_url(url):
    """Valida o link e remove playlist/parâmetros de tempo. Só abre YouTube e SoundCloud."""
    raw = str(url or '').strip()
    parsed = urlparse(raw if '://' in raw else 'https://' + raw)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or not any(host == h or host.endswith('.' + h) for h in HOSTS):
        raise MusicError('Use um link do YouTube (youtube.com, youtu.be ou music.youtube.com) ou do SoundCloud.')
    if host == 'youtu.be':
        video = parsed.path.strip('/').split('/')[0]
        if not re.fullmatch(r'[\w-]{6,20}', video):
            raise MusicError('Link do YouTube sem identificador de vídeo.')
        return 'https://www.youtube.com/watch?v=' + video
    if 'youtube.com' in host:
        query = parse_qs(parsed.query)
        video = (query.get('v') or [''])[0]
        if not video and parsed.path.startswith(('/shorts/', '/live/', '/embed/')):
            video = parsed.path.split('/')[2] if len(parsed.path.split('/')) > 2 else ''
        if not re.fullmatch(r'[\w-]{6,20}', video or ''):
            raise MusicError('Cole o link de um vídeo ou música específico, não de playlist ou canal.')
        return 'https://www.youtube.com/watch?v=' + video
    return raw.split('#')[0]


def track_id(*parts):
    return hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:16]


def js_runtime():
    """O yt-dlp precisa de Deno ou Node para resolver o desafio do YouTube (desde 2025.11)."""
    for name in ('deno', 'node'):
        if shutil.which(name):
            return name
    return ''


def status():
    try:
        import yt_dlp
        version = yt_dlp.version.__version__
    except ImportError:
        version = ''
    return dict(yt_dlp=version, js_runtime=js_runtime(), ffmpeg=bool(media.find_tool('ffmpeg')))


def _ydl(options=None, downloader=None):
    try:
        import yt_dlp
    except ImportError as exc:
        raise MusicError('O yt-dlp não está instalado. Execute INSTALAR.bat de novo ou use: pip install -U "yt-dlp[default]"') from exc
    base = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'socket_timeout': 25, 'retries': 3,
            'extractor_retries': 2, 'skip_download': True, 'cachedir': False}
    runtime = js_runtime()
    if runtime:
        base['js_runtimes'] = {runtime: {}}
    base.update(options or {})
    return (downloader or yt_dlp.YoutubeDL)(base)


def explain(error):
    text = str(error)
    low = text.lower()
    if 'javascript runtime' in low or 'js runtime' in low or 'n challenge' in low or 'signature' in low:
        return ('O YouTube exigiu um interpretador JavaScript. Instale o Deno (winget install DenoLand.Deno) ou o Node.js, '
                'atualize com: pip install -U "yt-dlp[default]" e tente novamente.')
    if 'sign in' in low or 'confirm you' in low or 'bot' in low:
        return 'O YouTube pediu confirmação de acesso para este vídeo. Tente outro link ou envie o arquivo de áudio.'
    if 'private' in low or 'unavailable' in low or 'removed' in low:
        return 'O vídeo está privado, indisponível ou foi removido.'
    if 'copyright' in low or 'blocked' in low:
        return 'O vídeo está bloqueado para esta região ou por direitos autorais.'
    if 'timed out' in low or 'unable to connect' in low or 'getaddrinfo' in low or 'proxy' in low:
        return 'Sem conexão com o YouTube. Confira a internet e tente novamente.'
    return 'Não foi possível obter a música: ' + text.splitlines()[0][:240] + '. Atualize o yt-dlp ou envie o arquivo de áudio.'


def inspect(url, factory=None):
    """Metadados sem baixar. `factory` existe para testes."""
    link = clean_url(url)
    try:
        with _ydl(downloader=factory) as ydl:
            info = ydl.extract_info(link, download=False)
    except MusicError:
        raise
    except Exception as exc:  # yt-dlp usa vários tipos de exceção
        raise MusicError(explain(exc)) from exc
    if not isinstance(info, dict):
        raise MusicError('Resposta inesperada do yt-dlp.')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming'):
        raise MusicError('Transmissões ao vivo não podem ser usadas como música.')
    duration = float(info.get('duration') or 0)
    if duration <= 0:
        raise MusicError('Não consegui descobrir a duração desse link.')
    if duration > MAX_SECONDS:
        raise MusicError(f'A faixa tem {duration/60:.0f} minutos; o limite é {MAX_SECONDS//60} minutos.')
    return dict(url=link, title=str(info.get('track') or info.get('title') or 'Sem título')[:200],
                uploader=str(info.get('artist') or info.get('uploader') or info.get('channel') or '')[:120],
                duration=round(duration, 2), thumbnail=str(info.get('thumbnail') or ''), source_id=str(info.get('id') or ''))


def convert(source, target):
    """Normaliza qualquer áudio/vídeo para .m4a estéreo 44,1 kHz (toca no navegador e no FFmpeg)."""
    args = [media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
            '-vn', '-map', '0:a:0', '-ac', '2', '-ar', '44100', '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', str(target)]
    media.run(args, timeout=600)
    return target


def decode_mono(path, rate=11025, limit=MAX_SECONDS):
    import numpy as np
    args = [media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(path), '-t', str(limit),
            '-vn', '-ac', '1', '-ar', str(rate), '-f', 's16le', '-']
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0      # sem janela de console piscando no Windows
    process = subprocess.run(args, capture_output=True, timeout=300, creationflags=flags)
    if process.returncode:
        raise MusicError('Não consegui ler o áudio desta faixa.')
    return np.frombuffer(process.stdout, dtype=np.int16).astype('float32') / 32768.0, rate


def analyze(path, clip_length=30):
    """Forma de onda, andamento (estimado), primeira batida e melhor trecho de `clip_length` s.

    São estimativas: o andamento só é indicado quando a periodicidade é clara.
    """
    import numpy as np
    samples, rate = decode_mono(path)
    if samples.size < rate:
        raise MusicError('A faixa é curta demais.')
    duration = samples.size / rate
    hop = rate // 100  # 10 ms
    # Forma de onda para a interface (240 pontos, 0..1).
    bins = 240
    chunk = max(1, samples.size // bins)
    peaks = [float(np.max(np.abs(samples[i * chunk:(i + 1) * chunk]))) if i * chunk < samples.size else 0.0 for i in range(bins)]
    top = max(peaks) or 1.0
    waveform = [round(p / top, 3) for p in peaks]
    # Energia por segundo (para o melhor trecho).
    seconds = int(duration)
    energy = np.array([float(np.sqrt(np.mean(samples[i * rate:(i + 1) * rate] ** 2))) for i in range(seconds)])
    # Fluxo espectral (início de notas) a cada 10 ms.
    n_fft = 512
    window = np.hanning(n_fft)
    count = max(0, (samples.size - n_fft) // hop)
    flux = np.zeros(count, dtype='float32')
    previous = None
    for index in range(count):
        magnitude = np.log1p(30 * np.abs(np.fft.rfft(samples[index * hop:index * hop + n_fft] * window)))
        if previous is not None:
            flux[index] = float(np.maximum(0, magnitude - previous).sum())
        previous = magnitude
    bpm, confidence, first = 0.0, 0.0, 0.0
    if flux.size > 600 and float(flux.std()) > 0:
        centered = flux - flux.mean()
        lags = np.arange(30, 101)  # 200..60 BPM
        correlation = np.array([float(np.dot(centered[:-lag], centered[lag:])) / (centered.size - lag) for lag in lags])
        zero = float(np.dot(centered, centered)) / centered.size or 1.0
        weighted = correlation * np.array([1.0 if 40 <= lag <= 75 else .88 for lag in lags])
        best = int(np.argmax(weighted))
        lag = int(lags[best])
        confidence = max(0.0, min(1.0, float(correlation[best]) / zero))
        if confidence >= .12:
            bpm = round(6000.0 / lag, 1)
            phases = [float(flux[p::lag].sum()) for p in range(lag)]
            first = round(int(np.argmax(phases)) * .01, 3)
    best_start = 0.0
    if seconds > clip_length + 6:
        sums = np.convolve(energy, np.ones(clip_length), 'valid')
        lower = int(seconds * .08)  # ignora a introdução
        window_sums = sums[lower:] if sums.size > lower + 1 else sums
        best_start = float(lower + int(np.argmax(window_sums))) if sums.size > lower + 1 else float(int(np.argmax(sums)))
        if bpm:  # alinha o começo a uma batida
            period = 60.0 / bpm
            best_start = round(first + round((best_start - first) / period) * period, 2)
            best_start = max(0.0, min(best_start, duration - clip_length))
    return dict(duration=round(duration, 2), waveform=waveform, bpm=bpm, bpm_confidence=round(confidence, 2),
                first_beat=first, best_start=round(best_start, 2))


def beat_times(info, start, end):
    """Batidas estimadas dentro de [start, end) em segundos da faixa. Vazio se não há andamento confiável."""
    bpm = float((info or {}).get('bpm') or 0)
    if bpm <= 0:
        return []
    period = 60.0 / bpm
    first = float(info.get('first_beat') or 0)
    index = math.ceil((float(start) - first) / period)
    result = []
    while True:
        moment = first + index * period
        if moment >= end:
            return result
        result.append(round(moment, 3))
        index += 1


def _register(root, item):
    index = load_index(root)
    index[item['id']] = item
    _save_index(root, index)
    return item


def public(item):
    """O navegador nunca recebe o caminho do arquivo."""
    return {k: v for k, v in item.items() if k != 'file'}


def library(root):
    items = []
    for item in load_index(root).values():
        if (folder(root) / item.get('file', '-')).is_file():
            items.append(public(item))
    return sorted(items, key=lambda x: -float(x.get('added', 0)))


def get(root, music_id):
    if not ID_RE.match(str(music_id or '')):
        raise MusicError('Música inválida.')
    item = load_index(root).get(music_id)
    if not item or not (folder(root) / item['file']).is_file():
        raise MusicError('Essa música não está mais na biblioteca.')
    return item


def path_of(root, music_id):
    return folder(root) / get(root, music_id)['file']


def fetch(root, url, factory=None):
    """Baixa o áudio de um link (reaproveita se já estiver na biblioteca)."""
    link = clean_url(url)
    music_id = track_id('url', link)
    cached = load_index(root).get(music_id)
    if cached and (folder(root) / cached['file']).is_file():
        return public(cached)
    meta = inspect(link, factory)
    media.require_space(Path(root), 1, extra=300 * 1024 ** 2)
    with tempfile.TemporaryDirectory(prefix='musica_', dir=folder(root)) as temp:
        options = {'skip_download': False, 'format': 'bestaudio/best', 'outtmpl': str(Path(temp) / 'faixa.%(ext)s'),
                   'max_filesize': 300 * 1024 ** 2, 'noprogress': True}
        try:
            with _ydl(options, factory) as ydl:
                ydl.download([link])
        except Exception as exc:
            raise MusicError(explain(exc)) from exc
        downloaded = sorted(Path(temp).glob('faixa.*'), key=lambda p: -p.stat().st_size)
        if not downloaded:
            raise MusicError('O download terminou sem arquivo de áudio.')
        target = folder(root) / (music_id + '.m4a')
        convert(downloaded[0], target)
    return _finish(root, music_id, target, meta, origin='youtube' if 'youtube' in link else 'link')


def import_file(root, source, name=''):
    """Registra um arquivo de áudio local (copia convertendo; o original não é alterado)."""
    source = Path(source)
    if source.suffix.lower() not in AUDIO_EXTENSIONS or not source.is_file():
        raise MusicError('Escolha um arquivo de áudio MP3, M4A, WAV, FLAC, OGG ou OPUS.')
    if source.stat().st_size > MAX_UPLOAD:
        raise MusicError('Arquivo grande demais (limite de 120 MB).')
    music_id = track_id('file', media.sha_file(source))
    cached = load_index(root).get(music_id)
    if cached and (folder(root) / cached['file']).is_file():
        return public(cached)
    target = folder(root) / (music_id + '.m4a')
    convert(source, target)
    try:
        seconds = media.audio_duration(target)
    except ValueError as exc:
        target.unlink(missing_ok=True)
        raise MusicError('Não encontrei áudio nesse arquivo.') from exc
    if seconds > MAX_SECONDS:
        target.unlink(missing_ok=True)
        raise MusicError(f'A faixa tem {seconds/60:.0f} minutos; o limite é {MAX_SECONDS//60} minutos.')
    meta = dict(url='', title=(name or source.stem)[:200], uploader='', duration=round(seconds, 2))
    return _finish(root, music_id, target, meta, origin='arquivo')


def _finish(root, music_id, target, meta, origin):
    try:
        analysis = analyze(target)
    except (MusicError, OSError, subprocess.SubprocessError, ValueError):
        analysis = dict(duration=meta.get('duration', 0), waveform=[], bpm=0.0, bpm_confidence=0.0, first_beat=0.0, best_start=0.0)
    item = dict(id=music_id, file=target.name, origin=origin, added=time.time(),
                title=meta['title'], uploader=meta.get('uploader', ''), url=meta.get('url', ''),
                duration=analysis.get('duration') or meta.get('duration', 0),
                waveform=analysis['waveform'], bpm=analysis['bpm'], bpm_confidence=analysis['bpm_confidence'],
                first_beat=analysis['first_beat'], best_start=analysis['best_start'])
    return public(_register(root, item))


def remove(root, music_id):
    item = get(root, music_id)
    (folder(root) / item['file']).unlink(missing_ok=True)
    index = load_index(root)
    index.pop(music_id, None)
    _save_index(root, index)
