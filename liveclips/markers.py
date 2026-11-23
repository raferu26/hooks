"""Cortes a partir de marcadores e sinais técnicos (P04), sem transcrição e sem modelo.

Um marcador é um instante que ALGUÉM (ou outro programa) apontou: atalho durante a live, arquivo de eventos, lista de
tempos. O Hook’s monta o corte em volta dele (preparação, evento central, desfecho) e nunca inventa o que aconteceu:
o rótulo é o que veio no arquivo. Candidatos só por pico de energia/movimento são heurística e vêm marcados como tal.
"""
import csv
import io
import json
import math
from pathlib import Path
import re

FILES = ('marcadores.json', 'marcadores.csv', 'marcadores.txt')
DEFAULT_PRE = 8.0
DEFAULT_POST = 12.0
PROTECT_PRE = 3.0          # preparação mínima preservada antes do evento central
PROTECT_POST = 3.0         # desfecho mínimo preservado depois
LIMITS = dict(short=(15.0, 58.0), narrative=(25.0, 88.0))
MAX_MARKERS = 2000


class MarkerError(ValueError):
    pass


def clock(value):
    """'83', '83,5', '1:23', '01:23.5', '1:02:03' -> segundos (float). Rejeita negativo e não finito."""
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = str(value).strip().replace(',', '.')
        if not re.fullmatch(r'\d+(\.\d+)?(:\d{1,2}(\.\d+)?){0,2}', text):
            raise MarkerError(f'Tempo inválido: {text[:20]!r}')
        parts = [float(p) for p in text.split(':')]
        seconds = 0.0
        for p in parts:
            seconds = seconds * 60 + p
    if not math.isfinite(seconds) or seconds < 0:
        raise MarkerError('Tempo de marcador inválido.')
    return seconds


def _item(time, label='', pre=None, post=None, source='arquivo'):
    pre = DEFAULT_PRE if pre in (None, '') else float(pre)
    post = DEFAULT_POST if post in (None, '') else float(post)
    if not (0 <= pre <= 60 and 0 <= post <= 60):
        raise MarkerError('Antes/depois do marcador devem ficar entre 0 e 60 s.')
    return dict(time=round(clock(time), 3), label=' '.join(str(label or '').split())[:80], pre=pre, post=post, source=source)


def parse(raw, name='marcadores.json'):
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig', errors='replace')
    suffix = Path(name).suffix.lower()
    items = []
    if suffix == '.json':
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise MarkerError('JSON de marcadores inválido.') from exc
        rows = data.get('marcadores', data.get('markers', [])) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise MarkerError('Esperava uma lista de marcadores.')
        for row in rows:
            if isinstance(row, (int, float, str)):
                row = dict(t=row)
            if not isinstance(row, dict):
                continue
            key = next((k for k in ('t', 'tempo', 'time', 'segundos', 'seconds') if k in row), None)
            if key is None:
                continue
            items.append(_item(row[key], row.get('rotulo', row.get('label', '')), row.get('antes', row.get('pre')),
                               row.get('depois', row.get('post'))))
    elif suffix == '.csv':
        sample = raw[:2000]
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
        for row in csv.reader(io.StringIO(raw), delimiter=delimiter):
            if not row or not row[0].strip() or not re.match(r'^\s*\d', row[0]):
                continue            # cabeçalho ou linha vazia
            items.append(_item(row[0], row[1] if len(row) > 1 else '', row[2] if len(row) > 2 else None,
                               row[3] if len(row) > 3 else None))
    elif suffix == '.txt':
        for line in raw.splitlines():
            match = re.match(r'^\s*(\d+(?:[:.,]\d+)*)\s*(.*)$', line)
            if match:
                items.append(_item(match.group(1), match.group(2)))
    else:
        raise MarkerError('Formato de marcadores não suportado. Use JSON, CSV ou TXT.')
    if len(items) > MAX_MARKERS:
        raise MarkerError('Marcadores demais.')
    return sorted(items, key=lambda m: m['time'])


def for_session(session_path):
    """Lê `marcadores.json|csv|txt` da pasta da sessão (tempos em segundos da sessão). Devolve (marcadores, avisos)."""
    found, warnings = [], []
    for name in FILES:
        file = Path(session_path) / name
        if file.is_file():
            try:
                found.extend(parse(file.read_bytes(), name))
            except (MarkerError, OSError) as exc:
                warnings.append(f'{name}: {exc}')
    return sorted(found, key=lambda m: m['time']), warnings


def epoch_to_session(timeline, epoch):
    """Instante de relógio (epoch) -> segundos da sessão, pelo horário de gravação dos segmentos. None se fora da gravação.

    O fim de cada arquivo é o `mtime`; o início é `mtime - duração`. Aproximação: o relógio do PC precisa estar certo e o
    arquivo precisa ter sido fechado no fim do segmento. Por isso o atalho ao vivo vem com margem generosa."""
    for row in timeline:
        end_epoch = float(row['mtime']) / 1e9
        start_epoch = end_epoch - (row['end'] - row['start'])
        if start_epoch - .5 <= epoch <= end_epoch + .5:
            return round(max(row['start'], min(row['end'], row['start'] + (epoch - start_epoch))), 3)
    return None


def cluster(markers, clip_format='short'):
    """Agrupa marcadores cujas janelas cabem juntas no limite de duração; o resto vira corte separado."""
    low, high = LIMITS.get(clip_format, LIMITS['short'])
    groups = []
    for m in sorted(markers, key=lambda x: x['time']):
        if groups:
            first = groups[-1][0]
            if (m['time'] + m['post']) - (first['time'] - first['pre']) <= high:
                groups[-1].append(m); continue
        groups.append([m])
    return groups


def candidates_from_markers(markers, low_edge, high_edge, group_id, clip_format='short', score=8.0):
    """Marcadores -> candidatos dentro de [low_edge, high_edge] (um único grupo contínuo de mídia).

    Cada candidato guarda `protected` (preparação e desfecho mínimos ao redor de cada evento) para que remoção de pausas
    e velocidade não toquem neles. O rótulo é o do arquivo; nada é deduzido do conteúdo."""
    low, high = LIMITS.get(clip_format, LIMITS['short'])
    out = []
    for group in cluster([m for m in markers if low_edge <= m['time'] <= high_edge], clip_format):
        start = max(low_edge, min(m['time'] - m['pre'] for m in group))
        end = min(high_edge, max(m['time'] + m['post'] for m in group))
        if end - start < low:                       # curto demais: estende pelos dois lados, depois por onde houver mídia
            need = low - (end - start)
            start = max(low_edge, start - need / 2)
            end = min(high_edge, end + need / 2)
            if end - start < low:
                end = min(high_edge, start + low)
                start = max(low_edge, end - low)
        if end - start > high:
            end = start + high
        if end - start < 3:
            continue
        labels = [m['label'] for m in group if m['label']]
        out.append(dict(
            start=round(start, 3), end=round(end, 3), group_id=group_id, score=score,
            reasons=['Momento marcado por você' + (': ' + '; '.join(labels[:3]) if labels else '') + '.'],
            transcript='', origin='marcador', heuristic=False, markers=[dict(time=m['time'], label=m['label']) for m in group],
            protected=[[round(max(start, m['time'] - PROTECT_PRE), 3), round(min(end, m['time'] + PROTECT_POST), 3)] for m in group],
            clip_format=clip_format))
    return out


def candidates_from_signals(signals, low_edge, high_edge, group_id, clip_format='short', rest=25.0, limit=3,
                            weights=None, existing=()):
    """Heurística técnica: picos de energia do áudio e movimento da webcam. NÃO identifica jogada, riso ou emoção.

    Pesos configuráveis; `rest` é a janela de descanso entre candidatos. O resultado fica `exploratory` e com nota baixa:
    é um ponto de partida para revisão, não uma promessa de achar o melhor momento."""
    weights = weights or dict(audio=.6, motion=.4)
    scored = []
    for kind, weight in weights.items():
        for p in signals.get(kind, []):
            if low_edge <= p['time'] <= high_edge:
                scored.append((p['time'], weight * float(p.get('strength', 1.0)), kind))
    scored.sort(key=lambda x: -x[1])
    chosen = []
    for time_, power, kind in scored:
        near = [s for s in scored if abs(s[0] - time_) <= 2.5 and s[2] != kind]
        bonus = .4 * max((s[1] for s in near), default=0.0)           # audio e movimento juntos valem mais
        total = power + bonus
        if any(abs(time_ - c[0]) < rest for c in chosen) or any(e['start'] - 5 <= time_ <= e['end'] + 5 for e in existing):
            continue
        chosen.append((time_, total, kind))
        if len(chosen) >= limit:
            break
    out = []
    for time_, total, kind in sorted(chosen):
        group = candidates_from_markers([dict(time=time_, label='', pre=DEFAULT_PRE, post=DEFAULT_POST)],
                                        low_edge, high_edge, group_id, clip_format, score=min(4.5, 2.0 + total))
        for item in group:
            item.update(origin='sinais', heuristic=True, exploratory=True,
                        reasons=['Pico técnico de ' + ('áudio' if kind == 'audio' else 'movimento') +
                                 '. É uma heurística sem garantia de interesse; confira antes de aprovar.'],
                        markers=[])
            out.append(item)
    return out
