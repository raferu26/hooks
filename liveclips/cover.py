"""Capas (P20): escolha do quadro por medidas técnicas e montagem do título em modelos fixos, tudo local e sem IA.

O que é medido: nitidez (variância do Laplaciano), exposição (média e fração de pixels escuros/estourados), contraste,
saturação e densidade de bordas. Nenhuma medida diz que o quadro “tem emoção” ou “é o melhor momento”: o quadro escolhido é o
mais nítido e bem exposto entre os amostrados, e as alternativas ficam salvas para a pessoa trocar.
Falha aqui nunca derruba a exportação."""
import json
from pathlib import Path
import tempfile
import time

CANVAS = {'9x16': (1080, 1920), '1x1': (1080, 1080), '4x5': (1080, 1350), '16x9': (1920, 1080)}
TEMPLATES = ('limpo', 'faixa', 'destaque')
SAFE = dict(top=160, bottom=480, side=60)       # px em 1080×1920 (igual ao QC)
SAMPLES = 12
MIN_SCORE = 25.0                               # abaixo disso o quadro é tecnicamente fraco; ainda assim a melhor opção é usada
WINDOWS_FONTS = ('segoeuib.ttf', 'arialbd.ttf', 'arial.ttf')
LINUX_FONTS = ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf')


def metrics(image):
    """Medidas de um quadro BGR (numpy). Valores simples e explicáveis."""
    import cv2
    import numpy as np
    height, width = image.shape[:2]
    scale = min(1.0, 480 / max(1, width))
    small = cv2.resize(image, (max(8, int(width * scale)), max(8, int(height * scale)))) if scale < 1 else image
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    edges = cv2.Canny(gray, 80, 160)
    return dict(sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
                brightness=float(gray.mean()),
                dark=float((gray < 20).mean()), bright=float((gray > 240).mean()),
                contrast=float(gray.std()),
                saturation=float(hsv[:, :, 1].mean()),
                edges=float((edges > 0).mean()),
                uniform=bool(np.ptp(gray) < 12))


def score(m):
    """-> (nota 0–100, motivos). A nota é um ranking técnico entre quadros do mesmo corte, não uma promessa de resultado."""
    reasons = []
    sharp = min(1.0, m['sharpness'] / 400.0)
    expo = max(0.0, 1.0 - abs(m['brightness'] - 125) / 125.0)
    clip = max(0.0, 1.0 - (m['dark'] + m['bright']) * 3.0)
    contrast = min(1.0, m['contrast'] / 55.0)
    color = min(1.0, m['saturation'] / 90.0)
    detail = min(1.0, m['edges'] / 0.08)
    value = 100 * (.34 * sharp + .22 * expo + .14 * clip + .12 * contrast + .08 * color + .10 * detail)
    if m['uniform'] or m['dark'] > .85:
        value = min(value, 5.0); reasons.append('quadro quase uniforme ou preto')
    if m['bright'] > .5:
        value = min(value, 15.0); reasons.append('estourado')
    if m['sharpness'] < 40:
        reasons.append('pouco nítido')
    elif m['sharpness'] > 250:
        reasons.append('nítido')
    if abs(m['brightness'] - 125) <= 45:
        reasons.append('exposição equilibrada')
    elif m['brightness'] < 60:
        reasons.append('escuro')
    return round(value, 1), reasons


def _grab(video, at, target):
    from . import media
    media.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{at:.3f}', '-i', str(video),
               '-frames:v', '1', '-q:v', '2', str(target)], 60)
    return Path(target).is_file()


def pick(video, duration, count=SAMPLES, keep=3, folder=None):
    """Amostra quadros do vídeo (sem o primeiro e o último décimo, onde há fades) e devolve os `keep` melhores:
    [{time, score, reasons, metrics, file}]. As alternativas diferem entre si por pelo menos 1 s."""
    import cv2
    duration = float(duration or 0)
    if duration <= 1:
        return []
    own = None
    if folder is None:
        own = tempfile.TemporaryDirectory(prefix='capa_')
        folder = own.name
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    found = []
    try:
        for i in range(count):
            at = duration * (.1 + .8 * i / max(1, count - 1))
            target = folder / f'q{i:02d}.jpg'
            try:
                if not _grab(video, at, target):
                    continue
            except Exception:
                continue
            image = cv2.imread(str(target))
            if image is None:
                continue
            m = metrics(image)
            value, reasons = score(m)
            found.append(dict(time=round(at, 2), score=value, reasons=reasons, metrics={k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()},
                              file=str(target)))
        found.sort(key=lambda x: -x['score'])
        chosen = []
        for item in found:
            if all(abs(item['time'] - other['time']) >= 1.0 for other in chosen):
                chosen.append(item)
            if len(chosen) >= keep:
                break
        if own is not None:   # arquivos temporários somem: guarda só os bytes dos escolhidos
            for item in chosen:
                item['bytes'] = Path(item['file']).read_bytes()
                item['file'] = ''
        return chosen
    finally:
        if own is not None:
            own.cleanup()


def font_path(root=None, brand=None):
    """Fonte da marca (se houver), depois fontes do sistema. None usa a fonte embutida do Pillow."""
    candidates = []
    name = (brand or {}).get('font')
    if root and name:
        candidates.append(Path(root) / 'fontes' / name)
    for file in WINDOWS_FONTS:
        candidates.append(Path('C:/Windows/Fonts') / file)
    candidates += [Path(p) for p in LINUX_FONTS]
    for path in candidates:
        try:
            if path.is_file():
                return str(path)
        except OSError:
            continue
    return None


def _font(path, size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def wrap(text, font, width, draw, max_lines=3):
    words = str(text or '').split()
    lines, line = [], ''
    for word in words:
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines if len(lines) <= max_lines else None


def fit_text(text, path, width, draw, start=120, floor=40, max_lines=3):
    """Maior corpo de letra que cabe em `width` com até `max_lines` linhas. -> (fonte, linhas)."""
    size = start
    while size >= floor:
        font = _font(path, size)
        lines = wrap(text, font, width, draw, max_lines)
        if lines:
            return font, lines
        size -= 6
    font = _font(path, floor)
    words = str(text or '').split()
    keep = ' '.join(words[:max(1, len(words) // 2)]) + '…'     # texto grande demais: encurta em vez de estourar a margem
    return font, (wrap(keep, font, width, draw, max_lines) or [keep[:30]])


def _canvas_from(image, size):
    """Quadro ajustado ao formato: preenche e corta quando a proporção é parecida; senão, quadro inteiro sobre fundo desfocado."""
    from PIL import Image, ImageFilter
    width, height = size
    ratio_in, ratio_out = image.width / image.height, width / height
    if abs(ratio_in - ratio_out) / ratio_out < .25 or ratio_out < ratio_in:
        scale = max(width / image.width, height / image.height)
        resized = image.resize((max(width, round(image.width * scale)), max(height, round(image.height * scale))), Image.LANCZOS)
        left, top = (resized.width - width) // 2, (resized.height - height) // 2
        return resized.crop((left, top, left + width, top + height))
    background = image.resize((width, height), Image.BILINEAR).filter(ImageFilter.GaussianBlur(28))
    scale = min(width / image.width, height / image.height)
    fitted = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    background.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return background


def compose(frame, title, template='destaque', aspect='9x16', font_file=None, color=(255, 255, 255), accent=(255, 214, 0)):
    """Monta a capa. `frame` é caminho ou bytes. Texto sempre dentro das margens seguras (proporcionais ao formato)."""
    import io
    from PIL import Image, ImageDraw
    if aspect not in CANVAS:
        raise ValueError('Formato de capa desconhecido.')
    if template not in TEMPLATES:
        raise ValueError('Modelo de capa desconhecido.')
    image = Image.open(io.BytesIO(frame) if isinstance(frame, (bytes, bytearray)) else str(frame)).convert('RGB')
    size = CANVAS[aspect]
    base = _canvas_from(image, size)
    text = str(title or '').strip()
    if not text or template == 'limpo':
        return base
    width, height = size
    k = height / 1920.0 if aspect != '16x9' else height / 1080.0
    top = int(SAFE['top'] * k) if aspect != '16x9' else int(60 * k)
    bottom = int(SAFE['bottom'] * k) if aspect != '16x9' else int(60 * k)
    side = int(SAFE['side'] * (width / 1080.0)) if aspect != '16x9' else 120
    box_width = width - 2 * side
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font, lines = fit_text(text.upper() if template == 'destaque' else text, font_file, box_width, draw, start=int(130 * k), floor=int(44 * k))
    line_height = int(font.size * 1.12)
    text_height = line_height * len(lines)
    y0 = height - bottom - text_height if aspect != '16x9' else (height - text_height) // 2
    y0 = max(top, y0)
    if template == 'faixa':
        pad = int(28 * k)
        draw.rectangle((0, y0 - pad, width, y0 + text_height + pad), fill=(0, 0, 0, 175))
    else:   # destaque: degradê escuro sob o texto, letra com contorno
        steps = 40
        start = max(0, y0 - int(260 * k))
        for i in range(steps):
            y = start + (height - start) * i // steps
            draw.rectangle((0, y, width, height), fill=(0, 0, 0, int(150 * (i + 1) / steps / 3)))
    for index, line in enumerate(lines):
        length = draw.textlength(line, font=font)
        x = (width - length) / 2
        y = y0 + index * line_height
        fill = accent if (template == 'destaque' and index == 0) else color
        if template == 'destaque':
            draw.text((x, y), line, font=font, fill=fill + (255,), stroke_width=max(2, int(font.size * .06)), stroke_fill=(0, 0, 0, 255))
        else:
            draw.text((x, y), line, font=font, fill=fill + (255,))
    return Image.alpha_composite(base.convert('RGBA'), layer).convert('RGB')


def title_of(candidate):
    from . import delivery
    return delivery.title_of(candidate)


def _brand_logo(image, brand, root, aspect, notes):
    """Logo do kit de marca na capa (opcional: `brand.logo.cover`), usando a variante já preparada (P21)."""
    logo = (brand or {}).get('logo') or {}
    if not (logo.get('cover') and logo.get('image') and root):
        return image
    try:
        from PIL import Image
        from . import imagerecipe
        made = imagerecipe.variant(root, logo['image'], 'capa_logo', CANVAS[aspect], scale=.16, style=logo.get('style') or 'none')
        mark = Image.open(made['path']).convert('RGBA')
        opacity = float(logo.get('opacity', .9))
        if opacity < 1:
            mark.putalpha(mark.getchannel('A').point(lambda v: int(v * opacity)))
        W, H = image.size
        margin = int(W * .05)
        corner = logo.get('corner', 'tl')
        x = margin if corner in ('tl', 'bl') else W - mark.width - margin
        y = margin if corner in ('tl', 'tr') else H - mark.height - margin
        base = image.convert('RGBA')
        base.alpha_composite(mark, (max(0, x), max(0, y)))
        return base.convert('RGB')
    except Exception as exc:
        notes.append('Logo não aplicado na capa: ' + str(exc)[:100])
        return image


def make_for_export(video, candidate, root=None, aspects=('9x16', '1x1', '4x5'), template=None):
    """Gera `capa_<formato>.jpg` ao lado do vídeo e `capa.json` (escolhas e medidas). -> dict ou None se não houve quadro."""
    video = Path(video)
    from . import media
    profile = candidate.get('profile') or {}
    brand = profile.get('brand') or {}
    template = template or profile.get('cover_template') or 'destaque'
    if template not in TEMPLATES:
        template = 'destaque'
    info = media.probe(video)
    options = pick(video, info['duration'])
    if not options:
        return None
    best = options[0]
    font_file = font_path(root, brand)
    title = title_of(candidate)
    written = []
    notes = []
    for aspect in aspects:
        target = video.parent / f'capa_{aspect}.jpg'
        composed = compose(best['bytes'], title, template, aspect, font_file)
        composed = _brand_logo(composed, brand, root, aspect, notes)
        tmp = target.with_suffix('.tmp.jpg')
        composed.save(tmp, quality=92)
        tmp.replace(target)
        written.append(target.name)
    alternatives = []
    for index, item in enumerate(options[1:], 1):
        target = video.parent / f'capa_alt{index}.jpg'
        target.write_bytes(item['bytes'])
        alternatives.append(dict(file=target.name, time=item['time'], score=item['score'], reasons=item['reasons']))
    report = dict(version=1, at=int(time.time()), template=template, title=title, files=written,
                  chosen=dict(time=best['time'], score=best['score'], reasons=best['reasons'], metrics=best['metrics']),
                  alternatives=alternatives, weak=best['score'] < MIN_SCORE,
                  logo_notes=notes,
                  note='Quadro escolhido por nitidez e exposição; não indica qual é o melhor momento. Confira antes de publicar.')
    (video.parent / 'capa.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
