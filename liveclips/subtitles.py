"""Importação de legendas prontas (P14): SRT, VTT e ASS/SSA viram segmentos temporizados, sem reconhecimento de fala.

O texto é de quem forneceu o arquivo; o Hook’s não inventa falas nem tempos de palavra. Um SRT comum não traz o tempo de
cada palavra: o destaque por palavra só existe se o arquivo for ASS com carimbos `\\k`, e qualquer divisão estimada fica
marcada (`words_estimated=True`).
"""
from pathlib import Path
import re

MAX_BYTES = 4 * 1024 * 1024
MAX_SEGMENTS = 20000
EXTENSIONS = ('.srt', '.vtt', '.ass', '.ssa')
_TAGS = re.compile(r'<[^>]+>|\{[^}]*\}')
_TIME = re.compile(r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})')


class SubtitleError(ValueError):
    pass


def decode(raw):
    """Bytes -> texto. Aceita UTF-8 (com ou sem BOM), UTF-16 e, por último, Windows-1252 (arquivos antigos em português)."""
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16')
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1')


def _seconds(text):
    match = _TIME.fullmatch(text.strip())
    if not match:
        raise SubtitleError('Tempo inválido na legenda: ' + text.strip()[:24])
    hours, minutes, secs, fraction = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs) + int(fraction.ljust(3, '0')) / 1000


def clean_text(text):
    """Tira marcações de estilo, junta linhas e normaliza espaços. Não corrige nem reescreve palavras."""
    text = _TAGS.sub('', text.replace('\\N', ' ').replace('\\n', ' '))
    return re.sub(r'\s+', ' ', text).strip()


def _blocks(text):
    return [b for b in re.split(r'\n\s*\n', text.replace('\r\n', '\n').replace('\r', '\n').strip()) if b.strip()]


def parse_srt_vtt(text):
    found = []
    for block in _blocks(text):
        lines = [l for l in block.split('\n') if l.strip()]
        index = next((i for i, l in enumerate(lines) if '-->' in l), None)
        if index is None:
            continue   # cabeçalho WEBVTT, NOTE, STYLE
        left, right = lines[index].split('-->', 1)
        found.append((_seconds(left.split()[0]), _seconds(right.strip().split()[0]), clean_text(' '.join(lines[index + 1:]))))
    return found


def _ass_time(text):
    match = re.fullmatch(r'(\d+):(\d{2}):(\d{2})[.](\d{1,2})', text.strip())
    if not match:
        raise SubtitleError('Tempo inválido na legenda ASS: ' + text.strip()[:24])
    h, m, s, c = match.groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(c.ljust(2, '0')) / 100


def parse_ass(text):
    found = []
    fields = None
    for line in text.replace('\r\n', '\n').split('\n'):
        line = line.strip()
        if line.lower().startswith('format:') and fields is None and 'text' in line.lower() and 'start' in line.lower():
            fields = [f.strip().lower() for f in line.split(':', 1)[1].split(',')]
        elif line.lower().startswith('dialogue:') and fields:
            values = line.split(':', 1)[1].lstrip().split(',', len(fields) - 1)
            if len(values) < len(fields):
                continue
            row = dict(zip(fields, values))
            found.append((_ass_time(row['start']), _ass_time(row['end']), clean_text(row['text'])))
    return found


def parse(raw, name='legenda.srt'):
    """Bytes (ou texto) de uma legenda -> segmentos `{start, end, text, source}` em segundos, ordenados e validados."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise SubtitleError('O arquivo de legenda é grande demais (limite de 4 MB).')
        raw = decode(raw)
    suffix = Path(name).suffix.lower()
    if suffix not in EXTENSIONS:
        raise SubtitleError('Formato de legenda não suportado. Use SRT, VTT ou ASS.')
    rows = parse_ass(raw) if suffix in ('.ass', '.ssa') else parse_srt_vtt(raw)
    segments = []
    for start, end, text in rows:
        if not text or end <= start or start < 0:
            continue
        segments.append(dict(start=round(start, 3), end=round(end, 3), text=text, words=[], source='importada'))
    if not segments:
        raise SubtitleError('Nenhuma fala temporizada foi encontrada neste arquivo.')
    if len(segments) > MAX_SEGMENTS:
        raise SubtitleError('Legenda longa demais.')
    return sorted(segments, key=lambda s: (s['start'], s['end']))


def shift(segments, offset):
    """Soma `offset` segundos (pode ser negativo) aos tempos; descarta o que ficar inteiro antes de zero."""
    out = []
    for seg in segments:
        start, end = seg['start'] + offset, seg['end'] + offset
        if end <= 0:
            continue
        out.append(dict(seg, start=round(max(0.0, start), 3), end=round(end, 3)))
    return out


def window(segments, start, end):
    """Segmentos que tocam [start, end), com tempos relativos ao início do trecho."""
    return [dict(s, start=round(max(s['start'], start) - start, 3), end=round(min(s['end'], end) - start, 3))
            for s in segments if s['start'] < end and s['end'] > start]


def for_session(session_path):
    """Lê `legendas/*.srt|vtt|ass` da pasta da sessão (tempos em segundos da sessão). Devolve (segmentos, avisos)."""
    folder = Path(session_path) / 'legendas'
    if not folder.is_dir():
        return [], []
    segments, warnings = [], []
    for file in sorted(folder.iterdir()):
        if file.suffix.lower() not in EXTENSIONS or not file.is_file():
            continue
        try:
            segments.extend(parse(file.read_bytes(), file.name))
        except (SubtitleError, OSError) as exc:
            warnings.append(f'{file.name}: {exc}')
    return sorted(segments, key=lambda s: s['start']), warnings
