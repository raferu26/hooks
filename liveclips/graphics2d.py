"""Gráficos animados 2D por templates locais (P27; não confundir com `motion.py`, que cuida do zoom de destaque).

Cenas pré-construídas e parametrizadas (barra de nome, título animado, contador, pulso por áudio), desenhadas com
Pillow quadro a quadro e codificadas em vídeo COM transparência (.mov, codec png). Nenhum script ou expressão vindos
de metadados é executado: as entradas são pequenas e validadas (texto, cores, número, duração, instante).
Sem serviço externo e sem IA. O resultado é cacheado por parâmetros + versão do template + formato do quadro.

Níveis (perfil `motion_level`): off · leve (quadro final estático, barato; não existe para `pulso_audio`) · completo (animado).
O pulso por áudio usa envelope e bandas de frequência do sinal; isso mede energia do som, não "entende" música ou emoção.
"""
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path

VERSION = 1
LEVELS = ('off', 'leve', 'completo')
TEMPLATES = ('barra_nome', 'titulo_animado', 'contador', 'pulso_audio')
HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')
FPS = 30
MIN_CUT = 8.0               # cortes mais curtos não recebem gráfico (poluiria)
MAX_ITEMS = 2               # orçamento por corte
MAX_SHARE = .25             # no máximo 25% da duração do corte com gráfico em tela
MIN_GAP = 1.0               # intervalo mínimo entre dois gráficos


class MotionError(ValueError):
    pass


def _text(value, limit, label, required=False):
    text = ' '.join(str(value or '').replace('\x00', ' ').split())
    text = re.sub(r'[\u0000-\u001f\u007f]', '', text)
    if required and not text:
        raise MotionError(f'{label} é obrigatório.')
    return text[:limit]


def _color(value, default):
    if value in (None, ''):
        return default
    match = HEX.match(str(value))
    if not match:
        raise MotionError('Cor inválida (use #RRGGBB).')
    return '#' + match.group(1).upper()


def _num(value, low, high, label, default):
    try:
        number = float(default if value in (None, '') else value)
    except (TypeError, ValueError):
        raise MotionError(f'{label} precisa ser um número.') from None
    if not math.isfinite(number) or not low <= number <= high:
        raise MotionError(f'{label} deve ficar entre {low:g} e {high:g}.')
    return number


def clean(raw, cut_duration):
    """Item validado: só campos conhecidos; tempos limitados à duração do corte. Levanta MotionError se inválido."""
    if not isinstance(raw, dict):
        raise MotionError('Gráfico inválido.')
    template = raw.get('template')
    if template not in TEMPLATES:
        raise MotionError('Modelo de gráfico desconhecido.')
    start = _num(raw.get('start'), 0, max(0.0, cut_duration - .6), 'Início', 0.5)
    duration = _num(raw.get('duration'), .6, 6, 'Duração', 3.0)
    duration = min(duration, max(.6, cut_duration - start))
    item = dict(template=template, start=round(start, 3), duration=round(duration, 3),
                accent=_color(raw.get('accent'), '#FFD600'), ink=_color(raw.get('ink'), '#FFFFFF'),
                text=_text(raw.get('text'), 60, 'Texto', required=template in ('barra_nome', 'titulo_animado')),
                subtitle=_text(raw.get('subtitle'), 60, 'Subtítulo'))
    if template == 'contador':
        item['value'] = round(_num(raw.get('value'), 0, 1e9, 'Valor', 0), 2)
        item['prefix'] = _text(raw.get('prefix'), 6, 'Prefixo')
        item['suffix'] = _text(raw.get('suffix'), 6, 'Sufixo')
        item['decimals'] = int(_num(raw.get('decimals'), 0, 2, 'Casas decimais', 0))
    return item


# ---------- orçamento e conflitos ----------

def apply_budget(items, cut_duration, level):
    """Escolhe quais gráficos entram. Mantém a ordem recebida (explícitos antes dos automáticos). → (aceitos, decisões)."""
    accepted, decisions = [], []
    if level == 'off':
        return [], [dict(template=i['template'], aceito=False, motivo='configuração: gráficos desligados') for i in items]
    for item in items:
        why = None
        end = item['start'] + item['duration']
        if cut_duration < MIN_CUT:
            why = f'orçamento: corte de {cut_duration:.1f}s é curto demais (mínimo {MIN_CUT:g}s)'
        elif len(accepted) >= MAX_ITEMS:
            why = f'orçamento: no máximo {MAX_ITEMS} gráficos por corte'
        elif sum(a['duration'] for a in accepted) + item['duration'] > cut_duration * MAX_SHARE:
            why = f'orçamento: gráficos ocupariam mais de {int(MAX_SHARE * 100)}% do corte'
        elif any(item['start'] < a['start'] + a['duration'] + MIN_GAP and a['start'] < end + MIN_GAP for a in accepted):
            why = f'conflito: precisa de {MIN_GAP:g}s de intervalo do gráfico anterior'
        elif level == 'leve' and item['template'] == 'pulso_audio':
            why = 'custo: o pulso por áudio só existe animado (nível "completo")'
        if why:
            decisions.append(dict(template=item['template'], start=item['start'], aceito=False, motivo=why))
        else:
            accepted.append(item)
            decisions.append(dict(template=item['template'], start=item['start'], aceito=True, motivo='dentro do orçamento'))
    return accepted, decisions


def automatic_items(context, cut_duration, has_title_at_start=False):
    """Gráfico automático: barra com o nome do canal (e rótulo do marcador, se houver) perto do início.
    Não entra quando o corte já tem título feito à mão no começo (evita dois textos disputando a atenção)."""
    name = _text((context or {}).get('streamer'), 40, 'Nome')
    if not name or has_title_at_start or cut_duration < MIN_CUT:
        return []
    return [dict(template='barra_nome', start=1.2, duration=3.0, accent='#FFD600', ink='#FFFFFF', text=name,
                 subtitle=_text((context or {}).get('label'), 50, 'Rótulo'))]


# ---------- desenho ----------

def fmt_number(value, decimals=0):
    """Número no padrão brasileiro (ponto nos milhares, vírgula nos decimais)."""
    text = f'{value:,.{decimals}f}'
    return text.replace(',', '_').replace('.', ',').replace('_', '.')


def _ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t ** 3


def _rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def box_of(template, canvas):
    """Retângulo (x, y, w, h) em pixels que o gráfico ocupa; só essa área é codificada."""
    W, H = canvas
    if template == 'barra_nome':
        return int(W * .05) // 2 * 2, int(H * .60) // 2 * 2, int(W * .78) // 2 * 2, int(H * .115) // 2 * 2
    if template == 'titulo_animado':
        return 0, int(H * .24) // 2 * 2, W // 2 * 2, int(H * .16) // 2 * 2
    if template == 'contador':
        return 0, int(H * .38) // 2 * 2, W // 2 * 2, int(H * .20) // 2 * 2
    return int(W * .08) // 2 * 2, int(H * .72) // 2 * 2, int(W * .84) // 2 * 2, int(H * .10) // 2 * 2     # pulso_audio


def _fonts(font_file):
    from . import cover
    return lambda size: cover._font(font_file, size)


def draw_frame(item, t, canvas, font_file=None, bands=None):
    """Um quadro RGBA da caixa do template no instante `t` (segundos desde o início do gráfico)."""
    from PIL import Image, ImageDraw
    W, H = canvas
    x, y, w, h = box_of(item['template'], canvas)
    image = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _fonts(font_file)
    accent, ink = _rgb(item['accent']), _rgb(item['ink'])
    D = item['duration']
    k = W / 1080
    enter = _ease_out(t / .4)
    leave = 1 - _ease_in_out((t - (D - .35)) / .35)
    shown = min(enter, leave)
    if item['template'] == 'barra_nome':
        pad = int(14 * k)
        bar_w = max(6, int(10 * k))
        panel_w = max(0, int(w * min(_ease_out(t / .45), leave)))
        if panel_w > bar_w:
            draw.rounded_rectangle((0, 0, panel_w, h - 1), radius=int(14 * k), fill=(12, 14, 20, 205))
            draw.rectangle((0, 0, bar_w, h - 1), fill=accent + (255,))
            alpha = int(255 * max(0.0, min(1.0, (t - .25) / .25)) * leave)
            big = font(max(18, int(h * .42)))
            small = font(max(14, int(h * .26)))
            tx = bar_w + pad * 2
            draw.text((tx, int(h * .10)), item['text'], font=big, fill=ink + (alpha,))
            if item['subtitle']:
                draw.text((tx, int(h * .58)), item['subtitle'], font=small, fill=accent + (alpha,))
    elif item['template'] == 'titulo_animado':
        scale = .86 + .14 * enter
        size = max(20, int(h * .52 * scale))
        f = font(size)
        text_w = draw.textlength(item['text'], font=f)
        while text_w > w * .9 and size > 18:
            size -= 4
            f = font(size)
            text_w = draw.textlength(item['text'], font=f)
        alpha = int(255 * shown)
        tx, ty = (w - text_w) / 2, int(h * .12)
        draw.text((tx + 3 * k, ty + 3 * k), item['text'], font=f, fill=(0, 0, 0, int(alpha * .6)))
        draw.text((tx, ty), item['text'], font=f, fill=ink + (alpha,))
        line = int(text_w * _ease_out((t - .1) / .5) * leave)
        if line > 0:
            draw.rounded_rectangle(((w - line) / 2, int(h * .80), (w + line) / 2, int(h * .80) + max(4, int(8 * k))), radius=4, fill=accent + (alpha,))
        if item['subtitle']:
            small = font(max(14, int(h * .2)))
            sw = draw.textlength(item['subtitle'], font=small)
            draw.text(((w - sw) / 2, int(h * .62)), item['subtitle'], font=small, fill=ink + (int(alpha * .85),))
    elif item['template'] == 'contador':
        progress = _ease_out(t / max(.4, D * .7))
        value = item.get('value', 0) * progress
        digits = item.get('decimals', 0)
        number = item.get('prefix', '') + fmt_number(value, digits) + item.get('suffix', '')
        size = max(30, int(h * .62))
        f = font(size)
        text_w = draw.textlength(number, font=f)
        while text_w > w * .92 and size > 24:
            size -= 6
            f = font(size)
            text_w = draw.textlength(number, font=f)
        alpha = int(255 * shown)
        tx = (w - text_w) / 2
        draw.text((tx + 3 * k, int(h * .02) + 3 * k), number, font=f, fill=(0, 0, 0, int(alpha * .55)))
        draw.text((tx, int(h * .02)), number, font=f, fill=accent + (alpha,))
        if item['text']:
            small = font(max(16, int(h * .17)))
            sw = draw.textlength(item['text'], font=small)
            draw.text(((w - sw) / 2, int(h * .78)), item['text'], font=small, fill=ink + (int(alpha * .9),))
    else:   # pulso_audio
        levels = bands or [0.0] * 9
        count = len(levels)
        gap = int(w * .02)
        bar = (w - gap * (count - 1)) // count
        for i, level in enumerate(levels):
            level = max(.06, min(1.0, level))
            bh = int(h * level * shown)
            left = i * (bar + gap)
            draw.rounded_rectangle((left, h - bh, left + bar, h), radius=max(3, bar // 4), fill=accent + (int(235 * shown),))
    return image


def final_frame(item, canvas, font_file=None):
    """Quadro estático do nível "leve": o estado de repouso do template (depois da entrada, antes da saída)."""
    return draw_frame(item, min(item['duration'] * .6, item['duration'] - .4), canvas, font_file, bands=None)


# ---------- áudio: envelope e bandas ----------

def read_audio(path, rate=16000):
    """Áudio mono 16 kHz em numpy (via FFmpeg). Levanta MotionError se não houver áudio legível."""
    import numpy as np
    from . import media
    flags = subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0
    cp = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(rate), '-f', 's16le', '-'],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, creationflags=flags)
    if cp.returncode or not cp.stdout:
        raise MotionError('Não consegui ler o áudio para animar o gráfico.')
    return np.frombuffer(cp.stdout, dtype='<i2').astype('float32') / 32768.0


def band_levels(samples, start, duration, fps=FPS, rate=16000, bands=9):
    """Níveis 0–1 de `bands` faixas de frequência (escala logarítmica, 80 Hz–6 kHz) para cada quadro de [start, start+duration)."""
    import numpy as np
    frames = int(math.ceil(duration * fps))
    window = 1024
    edges = np.geomspace(80, 6000, bands + 1)
    freqs = np.fft.rfftfreq(window, 1 / rate)
    out = np.zeros((frames, bands), dtype='float32')
    for i in range(frames):
        center = int((start + i / fps) * rate)
        chunk = samples[max(0, center - window // 2):center + window // 2]
        if len(chunk) < window:
            chunk = np.pad(chunk, (0, window - len(chunk)))
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(window)))
        for b in range(bands):
            mask = (freqs >= edges[b]) & (freqs < edges[b + 1])
            out[i, b] = spectrum[mask].mean() if mask.any() else 0.0
    ref = np.percentile(out, 95, axis=0) + 1e-6
    out = np.clip(out / ref, 0, 1.0) ** .8
    # suaviza no tempo (ataque rápido, queda mais lenta) para não piscar
    for i in range(1, frames):
        out[i] = np.maximum(out[i], out[i - 1] * .72)
    return out


# ---------- codificação e cache ----------

def cache_key(item, canvas, level):
    payload = json.dumps([VERSION, item, list(canvas), level, FPS], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def _folder(root):
    path = Path(root) / 'cache' / 'motion'
    path.mkdir(parents=True, exist_ok=True)
    return path


def render_item(item, canvas, root, level='completo', font_file=None, audio=None):
    """Gera (ou reaproveita do cache) o arquivo do gráfico. `audio` = (amostras, instante inicial no áudio do corte) para o pulso.
    → dict(path, kind='video'|'image', box=(x,y,w,h), cached)."""
    if level not in ('leve', 'completo'):
        raise MotionError('Nível de gráfico inválido.')
    box = box_of(item['template'], canvas)
    animated = level == 'completo'
    if item['template'] == 'pulso_audio' and not animated:
        raise MotionError('O pulso por áudio só existe animado.')
    audio_key = None
    if item['template'] == 'pulso_audio':
        if audio is None:
            raise MotionError('O pulso por áudio precisa do áudio do corte.')
        import numpy as np
        samples, origin = audio
        segment = samples[int(origin * 16000):int((origin + item['duration']) * 16000)]
        audio_key = hashlib.sha256(np.round(segment[::97] * 1000).astype('int16').tobytes()).hexdigest()[:12]
    key = cache_key(dict(item, audio=audio_key), canvas, level)
    folder = _folder(root)
    target = folder / (key + ('.mov' if animated else '.png'))
    if target.is_file():
        return dict(path=str(target), kind='video' if animated else 'image', box=box, cached=True)
    tmp = target.with_name(target.stem + '.tmp' + target.suffix)
    if not animated:
        final_frame(item, canvas, font_file).save(tmp, 'PNG')
        tmp.replace(target)
        return dict(path=str(target), kind='image', box=box, cached=False)
    from . import media
    frames = int(math.ceil(item['duration'] * FPS))
    levels = band_levels(audio[0], audio[1], item['duration']) if item['template'] == 'pulso_audio' else None
    x, y, w, h = box
    flags = subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0
    proc = subprocess.Popen([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{w}x{h}', '-r', str(FPS),
                             '-i', '-', '-c:v', 'png', '-pix_fmt', 'rgba', '-f', 'mov', str(tmp)],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    try:
        for i in range(frames):
            frame = draw_frame(item, i / FPS, canvas, font_file, bands=list(levels[min(i, len(levels) - 1)]) if levels is not None else None)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        error = proc.stderr.read().decode('utf-8', errors='replace')
        if proc.wait():
            raise MotionError('A codificação do gráfico falhou: ' + error[-200:])
    except Exception:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(target)
    return dict(path=str(target), kind='video', box=box, cached=False)


def prune(root, keep_days=30):
    """Apaga do cache gráficos não usados há muito tempo (o cache é só otimização; sempre pode ser refeito)."""
    removed = 0
    limit = time.time() - keep_days * 86400
    for file in _folder(root).iterdir():
        try:
            if file.stat().st_mtime < limit:
                file.unlink()
                removed += 1
        except OSError:
            pass
    return removed
