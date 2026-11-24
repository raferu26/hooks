"""Comparativo A/B de áudio para OUVIR: original × preset de voz DESLIGADO × preset NATURAL (cadeia real do app, sem IA).

Uso:
  python3 validacao/ab_audio.py AMOSTRA1.wav [AMOSTRA2.mp4 ...] [--saida PASTA] [--segundos 60] [--limpeza]
  python3 validacao/ab_audio.py --demo --saida PASTA            # gera 3 amostras SINTÉTICAS só para conferir o fluxo
Aceita qualquer arquivo de áudio ou vídeo que o FFmpeg leia (use cópias; os originais não são alterados).
Para cada amostra gera, na mesma pasta: 1_original, 2_preset_desligado, 3_preset_natural (e, com --limpeza, 4/5 = os dois presets
com a limpeza de ruído do app). TODAS as versões saem com o MESMO volume (-16 LUFS) para a comparação não ser enganada por
"mais alto parece melhor". Também gera `ouvir.html` (abre no navegador, modo cego opcional) e `metricas.json`.
Métricas objetivas (não substituem o ouvido): LUFS, pico verdadeiro, LRA, consistência (σ do volume de curto prazo, 3 s),
piso de ruído (percentil 10 do envelope) e % de quadros com pico acima de −1 dBFS."""
import argparse, html, json, random, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveclips import media, technical

TARGET = -16.0
VARIANTS = [('1_original', None, False), ('2_preset_desligado', 'off', False), ('3_preset_natural', 'natural', False)]
VARIANTS_CLEAN = [('4_desligado_com_limpeza', 'off', True), ('5_natural_com_limpeza', 'natural', True)]


def ff(args, capture=False):
    cp = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-y', *args], capture_output=True, text=True)
    if cp.returncode:
        raise RuntimeError(cp.stderr[-800:])
    return cp.stderr


def duration(path):
    cp = subprocess.run([media.tool('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, text=True)
    return float(cp.stdout.strip())


def measure(path):
    """LUFS integrado, LRA, pico verdadeiro e σ do volume de curto prazo (janelas de 3 s acima de −50 LUFS)."""
    err = ff(['-v', 'verbose', '-i', str(path), '-af', 'ebur128=peak=true:framelog=verbose', '-f', 'null', '-'])
    final = err[err.rfind('Summary:'):]
    I = float(re.search(r'I:\s+(-?[\d.]+) LUFS', final).group(1)); LRA = float(re.search(r'LRA:\s+(-?[\d.]+) LU', final).group(1))
    TP = float(re.search(r'Peak:\s+(-?[\d.]+) dBFS', final).group(1))
    S = [float(x) for x in re.findall(r'\bS:\s*(-?[\d.]+)', err[:err.rfind('Summary:')]) if float(x) > -50]
    return I, LRA, TP, (float(np.std(S)) if len(S) > 5 else 0.0)


def envelope_stats(path):
    db, _ = technical.envelope(path)
    return round(float(np.percentile(db, 10)), 1) if len(db) else None


def clipped_pct(path):
    x = technical._decode_pcm(path)
    return round(float(np.mean(np.abs(x) > 10 ** (-1 / 20)) * 100), 3)


def render(src, out, preset, clean, seconds):
    """Passa pela cadeia real do app (media.audio_chain) e iguala o volume ao alvo com ganho linear + limitador."""
    dur = min(seconds, duration(src)) if seconds else duration(src)
    tmp = Path(out).with_suffix('.tmp.wav')
    if preset is None:
        chain = 'aresample=48000'
    else:
        meta = {}
        graph = media.audio_chain('0:a', [], {'voice_preset': preset}, dur, 'anull', clean, meta).replace('[aout]', '[ach]')
        chain = None
    base = ['-i', str(src), '-t', f'{dur:g}', '-vn']
    if chain:
        ff([*base, '-af', chain, '-ac', '2', '-ar', '48000', str(tmp)])
    else:
        ff([*base, '-filter_complex', graph, '-map', '[ach]', '-ac', '2', '-ar', '48000', str(tmp)])
    I, _, TP, _ = measure(tmp)
    gain = TARGET - I
    for _ in range(3):   # o limitador come um pouco de volume: corrige até ficar a ≤0,3 LU do alvo (mesmo volume em todas as versões)
        ff(['-i', str(tmp), '-af', f'volume={gain:.2f}dB,alimiter=limit=.84:attack=3:release=60:level=0', '-ar', '48000', '-c:a', 'pcm_s16le', str(out)])
        got = measure(out)[0]
        if abs(got - TARGET) <= .3: break
        gain += TARGET - got
    tmp.unlink(missing_ok=True)


def demo_samples(folder):
    """Três amostras SINTÉTICAS (voz limpa; voz + ruído; voz + música + efeitos) só para provar o fluxo. Não são fala real."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import medir_audio as MA
    voice, mask = MA.voice_signal(20); noise = MA.noise_signal(20, -38); music = MA.music_signal(20, -22)
    rng = np.random.default_rng(5); sfx = np.zeros_like(voice)
    for t in (3.3, 8.8, 14.1):
        i = int(t * MA.SR); n = int(.25 * MA.SR); sfx[i:i + n] += rng.standard_normal(n) * np.hanning(n) * .25
    out = []
    for name, sig in (('voz_limpa', voice), ('voz_com_ruido', voice + noise), ('gameplay_musica_efeitos', voice + music + sfx)):
        p = Path(folder) / f'{name}.wav'; MA.wav(p, sig); out.append(p)
    return out


def page(rows, folder, blind_seed):
    rnd = random.Random(blind_seed)
    blocks = []
    for sample, items in rows.items():
        order = list(range(len(items))); rnd.shuffle(order)
        players = []
        for k, idx in enumerate(order):
            it = items[idx]
            players.append(f'<div class="p"><b class="lbl" data-real="{html.escape(it["label"])}" data-blind="{chr(65 + k)}">{chr(65 + k)}</b>'
                           f'<audio controls preload="none" src="{html.escape(it["file"])}"></audio>'
                           f'<span class="m">LUFS {it["I"]} · pico {it["TP"]} dBTP · LRA {it["LRA"]} LU · consistência σ {it["sigma"]} dB · piso {it["floor"]} dBFS · clip {it["clip"]}%</span></div>')
        blocks.append(f'<section><h2>{html.escape(sample)}</h2>{"".join(players)}'
                      '<div class="q">Anote (por versão): clareza · artefatos ("embaixo d\'água", chiado, bombeamento) · voz preservada · volume consistente</div>'
                      f'<textarea data-k="{html.escape(sample)}" rows="3" placeholder="Suas notas…"></textarea></section>')
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Comparativo A/B de áudio — Hook's</title>
<style>body{{font:15px system-ui;background:#0e0e11;color:#ededf2;max-width:880px;margin:24px auto;padding:0 16px}}section{{border:1px solid #2a2b35;border-radius:12px;padding:14px;margin:16px 0;background:#17171c}}
.p{{display:flex;gap:12px;align-items:center;margin:8px 0;flex-wrap:wrap}}.lbl{{min-width:150px;display:inline-block;background:#ff4d8d;color:#1a050e;border-radius:8px;padding:2px 10px}}
audio{{flex:1;min-width:260px}}.m{{color:#9a9cab;font-size:12.5px;flex-basis:100%}}.q{{color:#9a9cab;margin:10px 0 6px}}textarea{{width:100%;background:#0e0e11;color:inherit;border:1px solid #3b3d4b;border-radius:8px;padding:8px}}
button{{background:#262731;color:inherit;border:1px solid #3b3d4b;border-radius:8px;padding:6px 12px}}</style>
<h1>Comparativo A/B de áudio</h1><p>Todas as versões estão com o <b>mesmo volume ({TARGET:g} LUFS)</b>. Ouça com fones. No <b>modo cego</b> os nomes ficam A/B/C… e a ordem é sorteada.</p>
<p><button id="b">Modo cego: LIGADO (clique para revelar)</button></p>{"".join(blocks)}
<script>let blind=true;const b=document.getElementById('b');function show(){{document.querySelectorAll('.lbl').forEach(e=>e.textContent=blind?e.dataset.blind:e.dataset.real);b.textContent=blind?'Modo cego: LIGADO (clique para revelar)':'Nomes revelados (clique para voltar ao cego)'}}
b.onclick=()=>{{blind=!blind;show()}};show();document.querySelectorAll('textarea').forEach(t=>{{try{{t.value=localStorage.getItem('ab-'+t.dataset.k)||''}}catch(e){{}}t.oninput=()=>{{try{{localStorage.setItem('ab-'+t.dataset.k,t.value)}}catch(e){{}}}}}});</script></html>'''


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('arquivos', nargs='*'); ap.add_argument('--saida', default='ab_audio_saida')
    ap.add_argument('--segundos', type=float, default=60); ap.add_argument('--limpeza', action='store_true'); ap.add_argument('--demo', action='store_true')
    a = ap.parse_args(); out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
    files = [Path(f) for f in a.arquivos]
    if a.demo:
        files += demo_samples(tempfile.mkdtemp(prefix='hk_ab_demo_'))
    if not files:
        ap.error('informe arquivos ou use --demo')
    variants = VARIANTS + (VARIANTS_CLEAN if a.limpeza else [])
    rows, metrics = {}, {}
    for src in files:
        items = []
        for label, preset, clean in variants:
            name = f'{src.stem}__{label}.wav'; render(src, out / name, preset, clean, a.segundos)
            I, LRA, TP, sigma = measure(out / name)
            items.append(dict(label=label, file=name, I=I, LRA=LRA, TP=TP, sigma=round(sigma, 2), floor=envelope_stats(out / name), clip=clipped_pct(out / name)))
        rows[src.stem] = items; metrics[src.stem] = items
    (out / 'metricas.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'ouvir.html').write_text(page(rows, out, 7), encoding='utf-8')
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
