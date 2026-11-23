"""Download de vídeos do YouTube (não ao vivo) com o yt-dlp, para o Hook’s analisar como arquivo.

Por que existe: o Streamlink só lê transmissões ao vivo. Num vídeo comum do YouTube ele abre um único fluxo de 360p
e termina na hora com 0 bytes ("gravação parou sozinha, 0 pedaços"). O yt-dlp baixa o arquivo de verdade, em boa qualidade.
"""
from pathlib import Path
from urllib.parse import urlsplit

from . import media, music

YOUTUBE_HOSTS = ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be', 'www.youtu.be', 'youtube-nocookie.com',
                 'www.youtube-nocookie.com')
MAX_HEIGHT = 1080
FORMAT = (f'bv*[height<={MAX_HEIGHT}][ext=mp4]+ba[ext=m4a]/b[height<={MAX_HEIGHT}][ext=mp4]/'
          f'bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]/b')


class DownloadError(music.MusicError):
    pass


class DownloadCancelled(Exception):
    pass


def is_youtube(url):
    host = (urlsplit(str(url)).hostname or '').lower()
    return host in YOUTUBE_HOSTS


def is_live(info):
    status = str((info or {}).get('live_status') or '')
    return bool((info or {}).get('is_live')) or status in ('is_live', 'is_upcoming', 'post_live')


def inspect(url, factory=None):
    """Metadados sem baixar. → dict(title, author, duration, live, id)."""
    try:
        with music._ydl({'skip_download': True}, factory) as ydl:
            info = ydl.extract_info(str(url), download=False)
    except Exception as exc:     # yt-dlp levanta tipos próprios; todos viram uma mensagem clara
        raise DownloadError(explain(exc)) from None
    if not isinstance(info, dict):
        raise DownloadError('O YouTube não devolveu informações desse link.')
    if info.get('_type') == 'playlist':
        entries = [e for e in (info.get('entries') or []) if e]
        if not entries:
            raise DownloadError('Essa lista não tem vídeos acessíveis. Cole o link de um vídeo.')
        info = entries[0]
    return dict(title=str(info.get('title') or '')[:500], author=str(info.get('uploader') or info.get('channel') or '')[:500],
                duration=float(info.get('duration') or 0), live=is_live(info), id=str(info.get('id') or ''),
                url=str(info.get('webpage_url') or url))


def explain(error):
    text = str(error)
    low = text.lower()
    if 'live event will begin' in low or 'premiere' in low:
        return 'Esse vídeo ainda não começou (estreia ou live agendada). Tente depois que ele estiver no ar.'
    if 'private' in low or 'members-only' in low or 'members only' in low or 'join this channel' in low:
        return 'O vídeo é privado ou só para membros do canal; o Hook’s não consegue baixá-lo.'
    if 'age' in low and 'restrict' in low:
        return 'O YouTube pediu login por restrição de idade. Baixe o arquivo por outro meio e use "Enviar arquivo".'
    if 'no space' in low or 'espa' in low and 'baixo' in low:
        return text
    return music.explain(error).replace('Não foi possível obter a música:', 'Não foi possível baixar o vídeo:').replace(
        'ou envie o arquivo de áudio', 'ou baixe o arquivo por outro meio e use "Enviar arquivo"')


def download(url, folder, on_progress=None, cancelled=None, factory=None):
    """Baixa até 1080p em MP4 para `folder`. `on_progress(fração 0-1, etapa)`; `cancelled()` → True aborta e apaga o parcial.
    → Path do arquivo final (conferido com o ffprobe)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg = media.find_tool('ffmpeg')

    def hook(data):
        if cancelled and cancelled():
            raise DownloadCancelled()
        if not on_progress:
            return
        if data.get('status') == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            if total:
                on_progress(min(1.0, float(data.get('downloaded_bytes') or 0) / total), 'Baixando do YouTube')
        elif data.get('status') == 'finished':
            on_progress(1.0, 'Juntando imagem e som')

    options = {'skip_download': False, 'format': FORMAT, 'merge_output_format': 'mp4', 'outtmpl': str(folder / '%(id)s.%(ext)s'),
               'progress_hooks': [hook], 'windowsfilenames': True, 'restrictfilenames': True, 'overwrites': False, 'continuedl': True,
               'noprogress': True, 'concurrent_fragment_downloads': 3}
    if ffmpeg:
        options['ffmpeg_location'] = str(Path(ffmpeg).parent)
    try:
        with music._ydl(options, factory) as ydl:
            info = ydl.extract_info(str(url), download=True)
            if isinstance(info, dict) and info.get('_type') == 'playlist':
                info = next((e for e in info.get('entries') or [] if e), None)
            if not isinstance(info, dict):
                raise DownloadError('O YouTube não devolveu o vídeo.')
            path = Path(ydl.prepare_filename(info))
            merged = path.with_suffix('.mp4')
            path = merged if merged.is_file() else path
    except DownloadCancelled:
        _clean_partials(folder)
        raise
    except Exception as exc:
        if exc.__class__.__name__ == 'DownloadCancelled' or isinstance(getattr(exc, 'exc_info', [None, None])[1:2] and exc.exc_info[1], DownloadCancelled):
            _clean_partials(folder)
            raise DownloadCancelled() from None
        raise DownloadError(explain(exc)) from None
    if not path.is_file() or path.stat().st_size == 0:
        raise DownloadError('O download terminou sem gerar o arquivo. Tente de novo; se repetir, atualize o yt-dlp (INSTALAR.bat).')
    try:
        media.probe(path)
    except (RuntimeError, ValueError) as exc:
        raise DownloadError('O arquivo baixado não abriu como vídeo: ' + str(exc)[:200]) from None
    return path


def _clean_partials(folder):
    for pattern in ('*.part', '*.ytdl', '*.temp.*', '*.f[0-9]*.*'):
        for item in Path(folder).glob(pattern):
            try:
                item.unlink()
            except OSError:
                pass
