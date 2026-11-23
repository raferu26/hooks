"""Análise técnica clássica da fonte (P03): silêncio com histerese, tela preta, imagem parada e envelope de energia.

Só medidas: nenhuma delas diz o que aconteceu na live. Cada evento leva tempo, método, valor e limitação. Silêncio e tela
escura podem ser conteúdo válido, por isso aqui eles são CANDIDATOS e nunca viram corte sozinhos (P05, P25).
Sem modelos, sem rede.
"""
VERSION = 1          # sobe quando o algoritmo muda: invalida o cache por conteúdo

import subprocess
import os

import numpy as np

from . import media
from .qc import parse_blackdetect
from .qc_visual import parse_freeze, parse_silence

RATE = 16000
WINDOW = .05                 # s por amostra do envelope
LIMITS = dict(silence_enter_db=6.0, silence_exit_db=10.0, silence_min_s=.8, silence_pad_s=.15,
              black_min_s=.5, black_pix_th=.10, freeze_min_s=2.0, freeze_noise='-60dB')


def _decode_pcm(path, start=0.0, duration=None):
    args = [media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-ss', f'{float(start):.3f}']
    if duration:
        args += ['-t', f'{float(duration):.3f}']
    args += ['-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 's16le', 'pipe:1']
    done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if done.returncode:
        raise RuntimeError(done.stderr.decode('utf-8', 'replace')[-300:] or 'Não foi possível ler o áudio.')
    return np.frombuffer(done.stdout, dtype='<i2').astype(np.float32) / 32768.0


def envelope(path, start=0.0, duration=None):
    """Envelope RMS em dBFS, uma amostra a cada WINDOW s. Devolve (valores_db, passo_s)."""
    samples = _decode_pcm(path, start, duration)
    return envelope_of(samples)


def envelope_of(samples, rate=RATE, window=WINDOW):
    size = max(1, int(rate * window))
    count = len(samples) // size
    if count == 0:
        return np.zeros(0, dtype=np.float32), window
    frames = samples[:count * size].reshape(count, size)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    return (20 * np.log10(np.maximum(rms, 1e-6))).astype(np.float32), window


def noise_floor(db):
    """Piso de ruído = percentil 10 do envelope (robusto a falas e jogo alto)."""
    return float(np.percentile(db, 10)) if len(db) else -90.0


def silences(db, step=WINDOW, enter_db=None, exit_db=None, min_s=None, pad_s=None, floor=None):
    """Intervalos silenciosos com histerese: entra abaixo de piso+enter_db, só sai acima de piso+exit_db.

    `pad_s` encolhe cada intervalo dos dois lados (margem de segurança contra cortar sílaba). Intervalos mais curtos que
    `min_s` depois da margem são descartados. Devolve também a confiança: sem contraste entre fala e piso (mixagem
    barulhenta) a medida não é confiável e vem marcada `confiavel=False`.
    """
    L = LIMITS
    enter_db = L['silence_enter_db'] if enter_db is None else enter_db
    exit_db = L['silence_exit_db'] if exit_db is None else exit_db
    min_s = L['silence_min_s'] if min_s is None else min_s
    pad_s = L['silence_pad_s'] if pad_s is None else pad_s
    if len(db) == 0:
        return []
    floor = noise_floor(db) if floor is None else floor
    loud = float(np.percentile(db, 90))
    contrast = loud - floor
    spans, inside, begin = [], False, 0
    for i, value in enumerate(db):
        if not inside and value < floor + enter_db:
            inside, begin = True, i
        elif inside and value > floor + exit_db:
            spans.append((begin, i)); inside = False
    if inside:
        spans.append((begin, len(db)))
    out = []
    for a, b in spans:
        start, end = a * step + pad_s, b * step - pad_s
        if end - start >= min_s:
            out.append(dict(start=round(start, 3), end=round(end, 3), method='envelope_rms_histerese',
                            value_db=round(float(np.mean(db[a:b])), 1), floor_db=round(floor, 1),
                            confiavel=bool(contrast >= 12.0),
                            limits='Silêncio do áudio medido não prova ausência de conteúdo; jogo ou música alta o escondem.'))
    return out


def detect_filters():
    L = LIMITS
    return (f"blackdetect=d={L['black_min_s']}:pix_th={L['black_pix_th']},"
            f"freezedetect=n={L['freeze_noise']}:d={L['freeze_min_s']}")


def scan_video(path, duration):
    """Tela preta e imagem parada na FONTE (baixa resolução, um passe). Devolve listas de eventos."""
    text = media.run_stderr([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(path), '-an',
                             '-vf', 'scale=160:-2,' + detect_filters(), '-f', 'null', '-'], timeout=900)
    black = [dict(start=a, end=b, method='blackdetect', limits='Cena escura ou transição pode ser intencional.')
             for a, b in parse_blackdetect(text)]
    frozen = [dict(start=a, end=b, method='freezedetect', limits='Tela estática (menu, pausa) pode ser conteúdo válido.')
              for a, b in parse_freeze(text, duration)]
    return black, frozen


def scan_silence_filter(path, duration):
    """Silêncio pelo filtro `silencedetect` do FFmpeg (referência para conferir o envelope)."""
    text = media.run_stderr([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(path), '-vn',
                             '-af', 'silencedetect=n=-35dB:d=0.8', '-f', 'null', '-'], timeout=900)
    return [dict(start=a, end=b, method='silencedetect') for a, b in parse_silence(text, duration)]


def inspect(path):
    """Propriedades da fonte que decidem o que dá para medir (resolução, rotação, fps, áudio, cor)."""
    try:
        info = media.probe(path)
    except (RuntimeError, ValueError, OSError):
        return {}
    keep = ('width', 'height', 'duration', 'fps', 'signature', 'has_audio', 'rotation', 'codec', 'pix_fmt')
    return {k: info.get(k) for k in keep if k in info}


def analyze(path, duration, regions=None, scan_visual=True):
    """Pacote técnico de um arquivo: eventos candidatos e o que NÃO foi analisado, cada um com método e limitação."""
    result = dict(version=1, silence=[], black=[], freeze=[], energy=[], unanalyzed=[], warnings=[], source=inspect(path))
    try:
        db, step = envelope(path)
        result['silence'] = silences(db, step)
        result['energy'] = energy_peaks(db, step)
        result['noise_floor_db'] = round(noise_floor(db), 1)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        result['unanalyzed'].append(dict(kind='audio', reason=str(exc)[:160]))
    if scan_visual:
        try:
            result['black'], result['freeze'] = scan_video(path, duration)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            result['unanalyzed'].append(dict(kind='video', reason=str(exc)[:160]))
    return result


def energy_peaks(db, step=WINDOW, rise_db=9.0, min_gap_s=1.5):
    """Picos de energia acima do piso+rise_db (gatilho técnico; não é riso, grito nem jogada)."""
    if len(db) == 0:
        return []
    base = float(np.median(db))
    peaks, last = [], -1e9
    for i in range(1, len(db) - 1):
        t = i * step
        if db[i] >= base + rise_db and db[i] >= db[i - 1] and db[i] >= db[i + 1] and t - last >= min_gap_s:
            peaks.append(dict(time=round(t, 2), strength=round(min(3.0, (float(db[i]) - base) / rise_db), 3)))
            last = t
    return peaks
