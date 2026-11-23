"""Sinais visuais da tela do jogo/conteúdo (fora da webcam): clarões, rajadas de movimento e cortes de cena.

São heurísticas simples sobre brilho e diferença entre quadros, não "entendem" o jogo: não sabem o que é um abate,
uma vitória ou um menu. Um clarão pode ser explosão ou tela branca de carregamento. Por isso só pontuam quando
coincidem com fala/áudio (ver ranking) e cortes de cena nunca pontuam. Um modelo por jogo (HUD, killfeed) seria
o caminho para entender eventos de verdade e exige exemplos do SEU jogo.
"""
import os
import subprocess

from .media import tool

SIDE = (64, 36)
FPS = 2
CUT_MOTION = .30
FLASH_LUMA = .10


def _mask(camera_rect, size=SIDE):
    """Máscara (True = usar) que exclui a região da webcam."""
    import numpy as np
    w, h = size
    mask = np.ones((h, w), bool)
    if camera_rect:
        x, y, cw, ch = [float(v) for v in camera_rect]
        mask[int(max(0, y) * h):int(min(1, y + ch) * h) + 1, int(max(0, x) * w):int(min(1, x + cw) * w) + 1] = False
    return mask


def events_from(motion, luma, step=1 / FPS):
    """motion[i]: diferença média (0–1) entre o quadro i-1 e i; luma[i]: brilho médio (0–1). → lista de eventos."""
    from .signals import picos
    events = []
    cut_times = set()
    for i in range(1, len(motion)):
        if motion[i] >= CUT_MOTION:
            before = luma[i - 1] if i - 1 < len(luma) else 0
            rises = i < len(luma) and luma[i] - before >= FLASH_LUMA
            # Clarão passageiro (o brilho volta ao normal em até 1,5 s) é evento; mudança que permanece é corte de cena.
            transient = rises and any(abs(luma[j] - before) <= .05 for j in range(i + 1, min(len(luma), i + 4)))
            events.append(dict(time=round(i * step, 2), strength=round(min(3.0, (luma[i] - before) / FLASH_LUMA * 1.2), 2) if transient else 3.0,
                               kind='flash' if transient else 'corte'))
            cut_times.add(i)
    for i in range(1, len(luma)):
        jump = luma[i] - luma[i - 1]
        if jump >= FLASH_LUMA and i not in cut_times:
            events.append(dict(time=round(i * step, 2), strength=round(min(3.0, jump / FLASH_LUMA * 1.2), 2), kind='flash'))
    calm = [0.0 if i in cut_times else m for i, m in enumerate(motion)]
    for point in picos(calm, step=step, floor=.012):
        if point['strength'] >= 1.2:
            events.append(dict(time=point['time'], strength=point['strength'], kind='rajada'))
    return sorted(events, key=lambda e: e['time'])


def analyze(source, length, camera_rect=None, timeout=120):
    """→ dict(events, ok, warnings). Nunca levanta: falha vira aviso."""
    result = dict(events=[], ok=False, warnings=[])
    try:
        import numpy as np
        w, h = SIDE
        cp = subprocess.run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-threads', '2', '-i', str(source), '-t', str(min(float(length), 180)),
                             '-an', '-vf', f'fps={FPS},scale={w}:{h}:flags=area,format=gray', '-f', 'rawvideo', 'pipe:1'],
                            capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if cp.returncode:
            raise RuntimeError('vídeo ilegível para a análise visual')
        size = w * h
        n = len(cp.stdout) // size
        if n < 4:
            raise RuntimeError('vídeo curto demais')
        frames = np.frombuffer(cp.stdout[:n * size], np.uint8).reshape(n, h, w).astype('float32') / 255
        mask = _mask(camera_rect)
        if mask.sum() < size * .2:
            mask = _mask(None)
        used = frames[:, mask]
        luma = used.mean(axis=1)
        motion = np.concatenate([[0.0], np.abs(used[1:] - used[:-1]).mean(axis=1)])
        result['events'] = events_from([float(m) for m in motion], [float(v) for v in luma])
        result['ok'] = True
    except Exception as exc:
        result['warnings'].append('Sem sinal visual da tela: ' + str(exc)[:120])
    return result
