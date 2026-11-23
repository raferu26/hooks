"""Relógio do chat: quanto o tempo do chat pode estar errado em relação à mídia.

O chat grava `time` (relógio monotônico desde que o chat conectou), não alinhado ao vídeo. Aqui o programa diz a
incerteza em vez de fingir alinhamento: com `wall` e `sent_ts` do provedor, estima a latência; sem isso, assume a
incerteza padrão. Um deslocamento só é aplicado quando existe `chat_clock.json` (feito por quem mediu), nunca por palpite."""
import json
from pathlib import Path
import statistics

DEFAULT_UNCERTAINTY_S = 5.0
FILE = 'chat_clock.json'


def latency_stats(messages):
    """Latência provedor→gravação (wall − sent_ts), com ≥5 mensagens que tenham os dois campos."""
    lat = []
    for m in messages:
        try:
            lat.append(float(m['wall']) - float(m['sent_ts']) / 1000.0)
        except (KeyError, TypeError, ValueError):
            pass
    if len(lat) < 5:
        return None
    lat.sort()
    p10, p90 = lat[int(len(lat) * .1)], lat[min(len(lat) - 1, int(len(lat) * .9))]
    return dict(n=len(lat), median_s=round(statistics.median(lat), 3), spread_s=round(p90 - p10, 3))


def clock_for(messages, saved=None):
    """media_time = chat_time + offset_s ± uncertainty_s."""
    if saved and isinstance(saved.get('offset_s'), (int, float)):
        return dict(offset_s=float(saved['offset_s']), uncertainty_s=float(saved.get('uncertainty_s', DEFAULT_UNCERTAINTY_S)), source='arquivo')
    st = latency_stats(messages)
    if st:
        return dict(offset_s=0.0, uncertainty_s=round(max(1.0, abs(st['median_s']) + st['spread_s']), 2), source='latencia_do_provedor', latencia=st)
    return dict(offset_s=0.0, uncertainty_s=DEFAULT_UNCERTAINTY_S, source='desconhecida')


def load_saved(session_path):
    try:
        return json.loads((Path(session_path) / FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def apply(messages, clock):
    off = float(clock.get('offset_s', 0.0))
    return [dict(m, time=float(m['time']) + off) for m in messages if isinstance(m.get('time'), (int, float))] if off else list(messages)
