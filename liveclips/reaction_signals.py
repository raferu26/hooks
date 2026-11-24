"""Sugestões determinísticas de troca de layout (sem IA): onde o CONTEÚDO fica visualmente parado enquanto a WEBCAM se mexe.

Sinal: diferença média entre quadros consecutivos (amostrados a poucos quadros por segundo, em baixa resolução, em tons de
cinza) dentro de cada região marcada. É uma medida de movimento de pixels, nada mais: NÃO sabe se o streamer pausou o vídeo,
não identifica pessoas, voz nem emoção. Os limiares são configuráveis e a regra usada é devolvida junto de cada sugestão."""
import subprocess
import tempfile
from pathlib import Path

import numpy as np

SAMPLE_FPS = 5
SIDE = 72                       # largura da amostra em pixels (altura proporcional)
DEFAULTS = dict(still_below=.9, move_above=2.2, min_seconds=2.0, merge_gap=.6, apart=3.0, limit=8)
LIMITS = dict(still_below=(.05, 5), move_above=(.2, 20), min_seconds=(.8, 30), merge_gap=(0, 3), apart=(0, 30), limit=(1, 20))


def clean_options(raw):
    out = dict(DEFAULTS)
    for key, (low, high) in LIMITS.items():
        value = (raw or {}).get(key)
        if value in (None, ''):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'Limiar “{key}” inválido.') from None
        if number != number:
            raise ValueError(f'Limiar “{key}” inválido.')
        out[key] = max(low, min(high, number))
    out['limit'] = int(out['limit'])
    return out


def _even(v):
    return max(2, int(v) // 2 * 2)


def region_motion(ffmpeg, path, local_start, length, regions, source_size, sar=1.0, timeout=300):
    """{papel: ndarray de movimento por amostra} para o trecho [local_start, local_start+length] de `path`.

    `regions`: {papel: {x,y,w,h}} em frações do quadro de exibição; `source_size`: (largura, altura) reais do quadro decodificado
    (rotação e proporção de pixel já aplicadas; `sar`≠1 é normalizado antes do recorte). Um único FFmpeg decodifica uma vez e produz uma saída por região."""
    roles = list(regions)
    with tempfile.TemporaryDirectory() as temp:
        fix = f'scale=trunc(iw*{sar:.6f}/2)*2:ih,' if abs(sar - 1) > 1e-3 else ''
        graph = [f'[0:v]{fix}fps={SAMPLE_FPS},split={len(roles)}' + ''.join(f'[s{i}]' for i in range(len(roles)))]
        sizes = {}
        W, H = source_size
        for i, role in enumerate(roles):
            r = regions[role]
            cw, ch = _even(r['w'] * W), _even(r['h'] * H)
            cx, cy = min(_even(r['x'] * W), W - cw), min(_even(r['y'] * H), H - ch)
            sw = SIDE
            sh = max(2, int(round(ch * sw / cw)) // 2 * 2)
            sizes[role] = (sw, sh)
            graph.append(f'[s{i}]crop={cw}:{ch}:{cx}:{cy},scale={sw}:{sh}:flags=area,format=gray[o{i}]')
        args = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{local_start:.3f}', '-t', f'{length:.3f}', '-i', str(path),
                '-filter_complex', ';'.join(graph)]
        for i, role in enumerate(roles):
            args += ['-map', f'[o{i}]', '-f', 'rawvideo', str(Path(temp) / f'{role}.raw')]
        subprocess.run(args, check=True, timeout=timeout, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        out = {}
        for role in roles:
            sw, sh = sizes[role]
            raw = np.fromfile(Path(temp) / f'{role}.raw', dtype=np.uint8)
            frames = raw[:raw.size // (sw * sh) * sw * sh].reshape(-1, sh, sw).astype(np.float32)
            out[role] = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2)) if len(frames) > 1 else np.zeros(0, np.float32)
    return out


def find_runs(content, webcam, options, offset=0.0):
    """Trechos onde o conteúdo está parado (movimento < still_below) por pelo menos min_seconds. Cada um leva a
    média de movimento do conteúdo e da webcam, e só vale como sugestão se a webcam se mexe (> move_above, em média)."""
    n = min(len(content), len(webcam))
    still = content[:n] < options['still_below']
    dt = 1.0 / SAMPLE_FPS
    runs, start = [], None
    for i in range(n + 1):
        on = i < n and still[i]
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append([start, i])
            start = None
    merged = []
    for a, b in runs:                                           # junta pausas curtas entre dois trechos parados
        if merged and (a - merged[-1][1]) * dt <= options['merge_gap']:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        if (b - a) * dt < options['min_seconds']:
            continue
        cm, wm = float(content[a:b].mean()), float(webcam[a:b].mean())
        if wm < options['move_above']:
            continue
        out.append(dict(start=round(offset + a * dt, 2), end=round(offset + b * dt, 2), content_motion=round(cm, 2), webcam_motion=round(wm, 2)))
    return out


def rank(items, options):
    """Mais movimento na webcam e conteúdo mais parado primeiro; sem sugestões coladas (apart) e até `limit`."""
    ordered = sorted(items, key=lambda r: (r['webcam_motion'] / (r['content_motion'] + .3)) * (r['end'] - r['start']), reverse=True)
    chosen = []
    for item in ordered:
        if all(item['start'] >= c['end'] + options['apart'] or item['end'] <= c['start'] - options['apart'] for c in chosen):
            chosen.append(item)
        if len(chosen) >= options['limit']:
            break
    chosen.sort(key=lambda r: r['start'])
    for item in chosen:
        ratio = item['webcam_motion'] / (item['content_motion'] + .3)
        item['strength'] = 'forte' if ratio >= 6 else 'média' if ratio >= 3 else 'fraca'
        item['reason'] = (f'O conteúdo quase não mudou por {item["end"] - item["start"]:.1f} s (movimento {item["content_motion"]:.1f}) enquanto a '
                          f'webcam se mexeu (movimento {item["webcam_motion"]:.1f}).')
    return chosen


def rule_text(options):
    return (f'Regra: movimento do conteúdo abaixo de {options["still_below"]:g} por pelo menos {options["min_seconds"]:g} s, com movimento médio da webcam '
            f'acima de {options["move_above"]:g} (escala 0–255, diferença média entre quadros). Heurística de pixels: não sabe se o vídeo foi pausado '
            f'nem o que o streamer está fazendo.')
