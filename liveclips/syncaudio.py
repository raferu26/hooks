"""Sincronismo por áudio (P06): acha o deslocamento entre duas gravações do mesmo evento por correlação cruzada do envelope.

Só devolve um deslocamento quando o pico é claro: pico principal bem acima do segundo e do ruído. Em dúvida, RECUSA
(`ok=False` com o motivo) em vez de chutar. Nada de modelo: energia em janelas de 20 ms + FFT."""
import json
from pathlib import Path
import subprocess
from . import atomic

RATE = 8000
HOP = 160                 # 20 ms
MAX_SECONDS = 600         # só os primeiros 10 min de cada arquivo entram na busca
MIN_PEAK_RATIO = 3.0      # pico principal / segundo pico (fora da vizinhança)
MIN_SNR = 6.0             # pico / desvio da correlação
MIN_OVERLAP = 20.0        # s de áudio em comum exigidos


def envelope(path, seconds=MAX_SECONDS):
    """Envelope de energia (20 ms) do áudio, normalizado. Levanta RuntimeError se não há áudio legível."""
    import numpy as np
    from . import media
    command = [media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-t', str(seconds), '-f', 's16le', '-']
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, creationflags=flags)
    if proc.returncode or len(proc.stdout) < RATE * 2:
        raise RuntimeError('Não consegui ler áudio suficiente de ' + Path(str(path)).name + '.')
    samples = np.frombuffer(proc.stdout, dtype='<i2').astype('float32') / 32768.0
    frames = len(samples) // HOP
    energy = np.sqrt((samples[:frames * HOP].reshape(frames, HOP) ** 2).mean(1) + 1e-10)
    env = np.log1p(energy * 100.0)
    env = env - env.mean()
    spread = env.std()
    if spread < 1e-4:
        raise RuntimeError('O áudio de ' + Path(str(path)).name + ' é constante (silêncio ou tom): não dá para sincronizar.')
    return env / spread


def correlate(ref, other, max_shift=120.0):
    """Correlação cruzada normalizada por FFT. -> dict(ok, offset, confidence, ratio, snr, reason).

    `offset` em segundos: o instante `t` de `ref` corresponde ao instante `t + offset` de `other` (use `-ss a+offset` em `other`)."""
    import numpy as np
    step = HOP / RATE
    n = len(ref) + len(other)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(other, size)), size)
    lags = np.concatenate([np.arange(0, len(ref)), np.arange(-len(other) + 1, 0)])
    values = np.concatenate([corr[:len(ref)], corr[size - len(other) + 1:]])
    limit = int(max_shift / step)
    mask = np.abs(lags) <= limit
    lags, values = lags[mask], values[mask]
    if len(values) < 10:
        return dict(ok=False, reason='Faixa de busca pequena demais.')
    values = values / max(1, min(len(ref), len(other)))
    best = int(np.argmax(values))
    peak = float(values[best])
    near = np.abs(lags - lags[best]) <= int(1.0 / step)
    rest = values[~near]
    second = float(rest.max()) if len(rest) else 0.0
    sigma = float(values.std()) or 1e-9
    snr = peak / sigma
    ratio = peak / second if second > 1e-9 else float('inf')
    offset = -float(lags[best]) * step          # corr[k] = Σ ref[n+k]·other[n]  →  t_other = t_ref − k
    overlap = min(len(ref), len(other)) * step - abs(offset)
    result = dict(offset=round(offset, 3), peak=round(peak, 4), snr=round(snr, 2), ratio=round(min(ratio, 99.0), 2), overlap=round(overlap, 1))
    if overlap < MIN_OVERLAP:
        return dict(result, ok=False, reason='Pouco áudio em comum entre os arquivos.')
    if peak <= 0.02 or snr < MIN_SNR:
        return dict(result, ok=False, reason='Nenhum pico de correlação claro: os áudios parecem não ser do mesmo evento.')
    if ratio < MIN_PEAK_RATIO:
        return dict(result, ok=False, reason='Há mais de um deslocamento plausível (som repetitivo); recusei para não alinhar errado.')
    return dict(result, ok=True, reason='')


def measure(ref_path, other_path, max_shift=120.0):
    try:
        return correlate(envelope(ref_path), envelope(other_path), max_shift)
    except RuntimeError as exc:
        return dict(ok=False, reason=str(exc))


FILE = 'audio_externo.json'


def load(session_path):
    """Áudio externo vinculado à sessão, se estiver confirmado: {path, offset, ...} ou None."""
    try:
        data = json.loads((Path(session_path) / FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not data.get('ok') or not Path(str(data.get('path', ''))).is_file():
        return None
    return data


def link(session_path, ref_path, other_path):
    """Mede e grava o vínculo (também quando recusa, para o painel mostrar o motivo). -> resultado."""
    result = measure(ref_path, other_path)
    record = dict(result, path=str(other_path), ref=str(ref_path))
    atomic.write_json(Path(session_path) / FILE, record, indent=1)
    return record


def unlink(session_path):
    (Path(session_path) / FILE).unlink(missing_ok=True)
