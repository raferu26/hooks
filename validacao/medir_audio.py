"""Comparativo de cadeias de áudio CLÁSSICAS (sem modelo) em sinal sintético com referência limpa.
Uso: python3 validacao/medir_audio.py [saida.json]
Sinal: 'voz' sintética (harmônicos com formantes e modulação silábica, rajadas de 1,2 s com pausas de 0,6 s, níveis variando 12 dB),
ruído rosa + zumbido 60 Hz, música (acordes). Métricas, com a voz limpa como referência:
  SDR  = 10log(||limpa||² / ||saída−limpa||²) após alinhar o ganho (qualidade da fala: maior é melhor)
  piso = nível do ruído nas pausas (dBFS RMS)  ·  SNR = nível da fala − piso  ·  LUFS integrado, pico verdadeiro (ebur128)
  VOL σ = desvio do volume de curto prazo (3 s) entre rajadas (consistência: menor é melhor)
Sintético ≠ fala real: serve para comparar cadeias entre si, não para provar qualidade percebida."""
import json, math, re, subprocess, sys, tempfile, os
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveclips import media

SR = 48000
rng = np.random.default_rng(7)


def voice_signal(seconds=24):
    n = SR * seconds; t = np.arange(n) / SR; out = np.zeros(n); mask = np.zeros(n, bool)
    levels = [-18, -30, -22, -28]; pos = 0.3; k = 0
    while pos + 1.2 < seconds:
        a, b = int(pos * SR), int((pos + 1.2) * SR); seg = np.arange(b - a) / SR
        f0 = 120 + 40 * np.sin(2 * np.pi * .7 * seg + k)
        ph = 2 * np.pi * np.cumsum(f0) / SR; s = np.zeros(b - a)
        for h in range(1, 30):
            fh = f0 * h; w = np.exp(-((fh - 600) / 450) ** 2) + .6 * np.exp(-((fh - 1700) / 700) ** 2) + .15 * np.exp(-((fh - 3200) / 900) ** 2)
            s += w * np.sin(h * ph) / h ** .3
        s *= (.55 + .45 * np.sin(2 * np.pi * 4 * seg) ** 2) * np.hanning(b - a) ** .3
        s += .02 * rng.standard_normal(b - a) * (np.abs(np.sin(2 * np.pi * 4 * seg)) > .9)   # consoantes ruidosas
        s *= 10 ** (levels[k % 4] / 20) / (np.sqrt(np.mean(s ** 2)) + 1e-9)
        out[a:b] = s; mask[a:b] = True; pos += 1.8; k += 1
    return out, mask


def noise_signal(seconds=24, level_db=-42):
    n = SR * seconds; w = rng.standard_normal(n); f = np.fft.rfft(w); fr = np.fft.rfftfreq(n, 1 / SR); fr[0] = 1
    pink = np.fft.irfft(f / np.sqrt(fr), n); pink /= np.sqrt(np.mean(pink ** 2))
    hum = np.sin(2 * np.pi * 60 * np.arange(n) / SR) * .5 + np.sin(2 * np.pi * 120 * np.arange(n) / SR) * .25
    z = pink + hum; return z / np.sqrt(np.mean(z ** 2)) * 10 ** (level_db / 20)


def music_signal(seconds=24, level_db=-24):
    t = np.arange(SR * seconds) / SR; m = np.zeros_like(t)
    for f in (220, 277.2, 329.6, 440): m += np.sin(2 * np.pi * f * t) * (.7 + .3 * np.sin(2 * np.pi * .25 * t))
    return m / np.sqrt(np.mean(m ** 2)) * 10 ** (level_db / 20)


def wav(path, x):
    import wave
    x = np.clip(x, -1, 1); with_ = (x * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(with_.tobytes())


def read(path):
    import wave
    with wave.open(str(path), 'rb') as w:
        d = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float) / 32768
        if w.getnchannels() > 1: d = d.reshape(-1, w.getnchannels()).mean(1)
    return d


def ff(args):
    cp = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-y', *args], capture_output=True, text=True)
    if cp.returncode: raise RuntimeError(cp.stderr[-600:])
    return cp.stderr


def db(x): return 20 * math.log10(max(float(x), 1e-9))
def rms(x): return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def ebur(path):
    err = ff(['-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'])
    i = re.findall(r'I:\s+(-?[\d.]+) LUFS', err)[-1]; tp = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', err)[-1]
    return float(i), float(tp)


def short_term_sigma(x, mask):
    """σ (dB) do nível RMS de cada rajada de fala: consistência de volume entre falas."""
    edges = np.flatnonzero(np.diff(mask.astype(int)));
    starts, ends = edges[::2] + 1, edges[1::2] + 1
    lv = [db(rms(x[a:b])) for a, b in zip(starts, ends)]
    return float(np.std(lv)) if len(lv) > 1 else 0.0


def align(out, clean, maxlag=16384):
    """Alinha a saída à referência (filtros como afftdn/anlmdn atrasam o sinal): usa a correlação cruzada por FFT."""
    n = min(len(out), len(clean)); a, b = out[:n], clean[:n]
    N = 1 << (2 * n - 1).bit_length(); cc = np.fft.irfft(np.fft.rfft(a, N) * np.conj(np.fft.rfft(b, N)), N)
    cc = np.concatenate([cc[-maxlag:], cc[:maxlag + 1]]); lag = int(np.argmax(np.abs(cc))) - maxlag
    return (np.concatenate([a[lag:], np.zeros(lag)]) if lag > 0 else np.concatenate([np.zeros(-lag), a[:n + lag]])) if lag else a


def evaluate(out, clean, mask):
    n = min(len(out), len(clean)); o, c, m = align(out, clean), clean[:n], mask[:n]
    g = float(np.dot(o[m], c[m]) / (np.dot(c[m], c[m]) + 1e-12))     # ganho que melhor casa a saída com a voz limpa
    sdr = 10 * math.log10(np.sum(c[m] ** 2) / (np.sum((o[m] / (g if abs(g) > 1e-6 else 1) - c[m]) ** 2) + 1e-12))
    speech, floor = db(rms(o[m])), db(rms(o[~m]))
    return dict(SDR_dB=round(sdr, 2), piso_ruido_dBFS=round(floor, 1), SNR_dB=round(speech - floor, 1), VOL_sigma_dB=round(short_term_sigma(o, m), 2))


CHAINS = {
    'sem_tratamento': 'aresample=48000',
    'atual: highpass70+afftdn(nr12,nf-45)': 'aresample=48000,highpass=f=70,afftdn=nr=12:nf=-45:tn=1',
    'afftdn mais forte (nr20)': 'aresample=48000,highpass=f=70,afftdn=nr=20:nf=-45:tn=1',
    'anlmdn (non-local means)': 'aresample=48000,highpass=f=70,anlmdn=s=7:p=0.002:r=0.006',
    'afwtdn (wavelet)': 'aresample=48000,highpass=f=70,afwtdn=adaptive=1:percent=85',
    'afftdn+gate suave': 'aresample=48000,highpass=f=70,afftdn=nr=12:nf=-45:tn=1,agate=threshold=0.012:ratio=2:attack=10:release=250',
    'afwtdn 60%': 'aresample=48000,highpass=f=70,afwtdn=adaptive=1:percent=60',
    'afwtdn 70%': 'aresample=48000,highpass=f=70,afwtdn=adaptive=1:percent=70',
    'afwtdn 100%': 'aresample=48000,highpass=f=70,afwtdn=adaptive=1:percent=100',
    'afftdn leve (nr6)': 'aresample=48000,highpass=f=70,afftdn=nr=6:nf=-45:tn=1',
    'afftdn + afwtdn 60%': 'aresample=48000,highpass=f=70,afftdn=nr=8:nf=-45:tn=1,afwtdn=adaptive=1:percent=60',
    'so highpass 70': 'aresample=48000,highpass=f=70',
    'notch 60/120 Hz + afftdn': 'aresample=48000,highpass=f=70,equalizer=f=60:t=q:w=20:g=-18,equalizer=f=120:t=q:w=20:g=-14,afftdn=nr=12:nf=-45:tn=1',
}


def main():
    out_json = sys.argv[1] if len(sys.argv) > 1 else None
    tmp = Path(tempfile.mkdtemp(prefix='hooks_audio_'))
    voice, mask = voice_signal(); noise = noise_signal(); mus = music_signal()
    wav(tmp / 'voz.wav', voice); wav(tmp / 'mix.wav', voice + noise); wav(tmp / 'musica.wav', mus)
    res = dict(ruido=[], nivelamento=[], musica=[], final=[])
    g1 = media.audio_chain('0:a', [], {}, 24, 'anull', True, {})
    app_dn = re.search(r'\[0:a\](aresample=48000,highpass=f=70,[^\[;]+)\[voice\]', g1).group(1)   # limpeza real do app
    chains = {'APP (lido do código): ' + app_dn.split('highpass=f=70,')[1]: app_dn, **CHAINS}
    for name, chain in chains.items():
        import time; t0 = time.time()
        ff(['-i', str(tmp / 'mix.wav'), '-af', chain, '-ar', str(SR), str(tmp / 'o.wav')])
        res['ruido'].append(dict(cadeia=name, tempo_s_para_24s=round(time.time() - t0, 2), **evaluate(read(tmp / 'o.wav'), voice, mask)))
    # nivelamento de volume (consistência): compressor/limitador/leveler clássicos, depois loudnorm comum
    LEV = {
        'sem nivelar': 'aresample=48000',
        'compressor natural (preset atual)': 'aresample=48000,acompressor=threshold=-20dB:ratio=2.5:attack=20:release=250:makeup=2',
        'compressor forte (preset atual)': 'aresample=48000,acompressor=threshold=-24dB:ratio=3.5:attack=15:release=200:makeup=4',
        'dynaudnorm (nivelador)': 'aresample=48000,dynaudnorm=f=300:g=11:p=0.9:m=8:s=8',
        'speechnorm': 'aresample=48000,speechnorm=e=6:r=0.0005:l=1',
    }
    for name, chain in LEV.items():
        ff(['-i', str(tmp / 'voz.wav'), '-af', chain, '-ar', str(SR), str(tmp / 'l.wav')])
        o = read(tmp / 'l.wav'); I, TP = ebur(tmp / 'l.wav')
        res['nivelamento'].append(dict(cadeia=name, VOL_sigma_dB=round(short_term_sigma(o, mask[:len(o)]), 2), LUFS=I, pico_dBTP=TP))
    # ducking da música sob a voz: queda da música quando há fala (medida só na música, antes da mistura)
    g0 = media.audio_chain('0:a', [(1, dict(kind='music', volume=.12, duck=True))], {}, 24, 'anull', False, {})
    app_sc = re.search(r'sidechaincompress=([^\[;]+)', g0).group(1)      # parâmetros reais do app, lidos do filtergraph gerado
    for name, sc in {'APP (lido do código): ' + app_sc: app_sc,
                     'versão 0.19: threshold=.06:ratio=8:attack=20:release=350': 'threshold=.06:ratio=8:attack=20:release=350',
                     'mais suave (thr .1, ratio 4)': 'threshold=.1:ratio=4:attack=30:release=300'}.items():
        ff(['-i', str(tmp / 'musica.wav'), '-i', str(tmp / 'voz.wav'), '-filter_complex', f'[0:a][1:a]sidechaincompress={sc}[d]', '-map', '[d]', str(tmp / 'd.wav')])
        d = read(tmp / 'd.wav'); n = min(len(d), len(mask))
        res['musica'].append(dict(cadeia=name, musica_na_fala_dBFS=round(db(rms(d[:n][mask[:n]])), 1), musica_nas_pausas_dBFS=round(db(rms(d[:n][~mask[:n]])), 1),
                                  queda_dB=round(db(rms(d[:n][~mask[:n]])) - db(rms(d[:n][mask[:n]])), 1)))
    # cadeia final real do app (media.audio_chain) com música: LUFS e pico
    for label, vc, prof in (('app: limpeza leve', True, {}), ('app: limpeza leve + preset natural', True, {'voice_preset': 'natural'}), ('app: sem limpeza', False, {})):
        meta = {}
        g = media.audio_chain('0:a', [(1, dict(kind='music', volume=.12, duck=True))], dict(prof), 24, media.loudnorm_filter(), vc, meta)
        ff(['-i', str(tmp / 'mix.wav'), '-i', str(tmp / 'musica.wav'), '-filter_complex', g, '-map', '[aout]', '-ar', str(SR), str(tmp / 'f.wav')])
        o = read(tmp / 'f.wav'); I, TP = ebur(tmp / 'f.wav'); m = mask[:len(o)]
        res['final'].append(dict(cadeia=label, LUFS=I, pico_dBTP=TP, VOL_sigma_dB=round(short_term_sigma(o, m), 2)))
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    if out_json: Path(out_json).write_text(txt, encoding='utf-8')
    print(txt)


if __name__ == '__main__':
    main()
