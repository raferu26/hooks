"""Medidas independentes do render (não usam nada do que o próprio render declara): quadros, cores, áudio."""
import subprocess

import cv2
import numpy as np

from liveclips import media

RATE = 16000
WINDOW = 160          # 10 ms


def audio(path):
    """Áudio mono 16 kHz (float) do arquivo."""
    raw = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def windows(samples):
    n = len(samples) // WINDOW
    return samples[:n * WINDOW].reshape(n, WINDOW)


def rms_db(samples):
    value = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
    return 20 * np.log10(value + 1e-9)


def speech_blocks(samples, floor_db=-55.0, gap=.2, minimum=1.0):
    """Trechos com voz (tom de 300 Hz): [(início, fim, rms em dBFS)]. O bipe de 2 kHz não conta."""
    w = windows(samples)
    spectrum = np.abs(np.fft.rfft(w, axis=1))
    tone = 20 * np.log10(spectrum[:, 3] / WINDOW + 1e-9)          # bin de 300 Hz (100 Hz por bin)
    active = tone > floor_db
    blocks, start, last = [], None, None
    for i, on in enumerate(active):
        if on:
            if start is None:
                start = i
            last = i
        elif start is not None and (i - last) * WINDOW / RATE > gap:
            blocks.append((start, last + 1))
            start = None
    if start is not None:
        blocks.append((start, last + 1))
    out = []
    for a, b in blocks:
        if (b - a) * WINDOW / RATE >= minimum:
            out.append((a * WINDOW / RATE, b * WINDOW / RATE, rms_db(samples[a * WINDOW:b * WINDOW])))
    return out


def beep_onset(samples):
    """Primeiro instante com energia de 2 kHz bem acima do resto (bin 20)."""
    w = windows(samples)
    spectrum = np.abs(np.fft.rfft(w, axis=1))[:, 20]
    peak = spectrum.max()
    if peak <= 0:
        return None
    hit = np.where(spectrum > peak * .3)[0]
    return float(hit[0] * WINDOW / RATE) if len(hit) else None


def scan(video, step=1, scale=.5):
    """Percorre o vídeo e devolve (fps, [(índice, quadro BGR reduzido)]). Reduz na leitura para caber na memória."""
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    i = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                yield fps, i, cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            i += 1
    finally:
        cap.release()


def mask(frame, color):
    b, g, r = (frame[..., 0].astype(int), frame[..., 1].astype(int), frame[..., 2].astype(int))
    if color == 'magenta':
        return (r > 190) & (b > 190) & (g < 90)
    if color == 'red':
        return (r > 190) & (g < 70) & (b < 70)
    if color == 'orange':
        return (r > 200) & (g > 90) & (g < 180) & (b < 70)
    if color == 'white':
        return (r > 235) & (g > 235) & (b > 235)
    if color == 'blue':
        return (b > 190) & (r < 80) & (g < 120)
    if color == 'yellow':
        return (r > 200) & (g > 200) & (b < 90)
    if color == 'green':
        return (g > 150) & (r < 60) & (b < 110)
    raise ValueError(color)


def blob(frame, color, region=None):
    """Maior componente da cor: dict(x, y, w, h, area) em pixels do quadro dado, ou None. `region`=(x0,y0,x1,y1)."""
    m = mask(frame, color)
    ox = oy = 0
    if region:
        x0, y0, x1, y1 = region
        m = m[y0:y1, x0:x1]
        ox, oy = x0, y0
    count, _, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if count <= 1:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = (int(v) for v in stats[best])
    return dict(x=x + ox, y=y + oy, w=w, h=h, area=area)
