"""Receitas locais de imagem (P21): redimensionar sem distorcer, margens, contorno, sombra, recorte,
máscara fornecida, fundo uniforme com tolerância, conversão de formato e variantes por destino.

Não é editor de imagem nem remove fundo de fotos quaisquer: `key_bg` só funciona quando as bordas têm uma
cor praticamente uniforme; senão recusa. As fontes nunca são alteradas: as variantes vão para
`<dados>/imagens/variantes/` com catálogo (fonte, medidas, alpha, versão) e a chave de cache inclui o
conteúdo da fonte, a receita e a versão do módulo — mudou o asset, a variante é refeita.
"""
import hashlib
import io
import json
import re
import time
from pathlib import Path

VERSION = 1
FITS = ('contain', 'cover')
FORMATS = ('png', 'jpg', 'webp')
HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')
DESTINATIONS = ('logo', 'marca_dagua', 'moldura', 'cartao', 'capa_logo')
MAX_SIDE = 8000


class RecipeError(ValueError):
    pass


def _hex(value, default):
    if value in (None, ''):
        return default
    match = HEX.match(str(value))
    if not match:
        raise RecipeError('Cor inválida (use #RRGGBB).')
    h = match.group(1)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _num(value, low, high, label, default):
    try:
        number = float(default if value in (None, '') else value)
    except (TypeError, ValueError):
        raise RecipeError(f'{label} precisa ser um número.') from None
    if not low <= number <= high:
        raise RecipeError(f'{label} deve ficar entre {low:g} e {high:g}.')
    return number


def clean(raw):
    """Valida uma receita e devolve a forma normalizada (usada também na chave de cache)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    fit = raw.get('fit') or 'contain'
    if fit not in FITS:
        raise RecipeError('Ajuste inválido (contain ou cover).')
    out['fit'] = fit
    for key in ('width', 'height'):
        if raw.get(key) not in (None, ''):
            out[key] = int(_num(raw[key], 16, MAX_SIDE, key, 0))
    out['margin'] = int(_num(raw.get('margin'), 0, 400, 'Margem', 0))
    outline = raw.get('outline') or {}
    if outline.get('px'):
        out['outline'] = dict(px=int(_num(outline['px'], 1, 40, 'Contorno', 1)), color=_hex(outline.get('color'), (255, 255, 255)))
    shadow = raw.get('shadow') or {}
    if shadow.get('blur') or shadow.get('dx') or shadow.get('dy'):
        out['shadow'] = dict(dx=int(_num(shadow.get('dx'), -80, 80, 'Sombra x', 0)), dy=int(_num(shadow.get('dy'), -80, 80, 'Sombra y', 6)),
                             blur=int(_num(shadow.get('blur'), 0, 60, 'Sombra suavidade', 10)), opacity=_num(shadow.get('opacity'), 0, 1, 'Sombra opacidade', .5))
    crop = raw.get('crop')
    if crop:
        if not isinstance(crop, (list, tuple)) or len(crop) != 4:
            raise RecipeError('Recorte inválido.')
        x, y, w, h = [float(v) for v in crop]
        if not (0 <= x < 1 and 0 <= y < 1 and w >= .02 and h >= .02 and x + w <= 1.00001 and y + h <= 1.00001):
            raise RecipeError('Recorte fora da imagem.')
        out['crop'] = [round(v, 5) for v in (x, y, w, h)]
    if raw.get('key_bg') not in (None, '', 0):
        out['key_bg'] = _num(raw['key_bg'], 1, 80, 'Tolerância do fundo', 12)
    fmt = (raw.get('format') or 'png').lower().replace('jpeg', 'jpg')
    if fmt not in FORMATS:
        raise RecipeError('Formato inválido (png, jpg ou webp).')
    out['format'] = fmt
    out['quality'] = int(_num(raw.get('quality'), 40, 100, 'Qualidade', 92))
    out['bg'] = _hex(raw.get('bg'), (255, 255, 255))
    return out


def load(path):
    """Abre a imagem em RGBA sRGB (aplica a rotação do EXIF; converte perfil ICC para sRGB quando existe)."""
    from PIL import Image, ImageOps
    try:
        image = Image.open(str(path))
        image.load()
    except Exception as exc:
        raise RecipeError('Não consegui abrir a imagem.') from exc
    note = ''
    try:
        image = ImageOps.exif_transpose(image)
    except Exception:
        pass
    icc = image.info.get('icc_profile')
    if icc:
        try:
            from PIL import ImageCms
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            target = ImageCms.createProfile('sRGB')
            mode = 'RGBA' if image.mode in ('RGBA', 'LA', 'PA') or 'transparency' in image.info else 'RGB'
            alpha = image.convert('RGBA').getchannel('A') if mode == 'RGBA' else None
            converted = ImageCms.profileToProfile(image.convert('RGB'), source, target, outputMode='RGB')
            image = converted.convert('RGBA')
            if alpha is not None:
                image.putalpha(alpha)
            note = 'perfil de cor convertido para sRGB'
        except Exception:
            note = 'perfil de cor não convertido (assumido sRGB)'
    image = image.convert('RGBA')
    image.info['note'] = note
    return image


def fit_to(image, width, height, mode='contain', focus=(.5, .5)):
    """Cabe em width×height sem distorcer. contain → imagem inteira sobre transparência; cover → preenche e corta."""
    from PIL import Image
    w, h = image.size
    if mode == 'cover':
        k = max(width / w, height / h)
    else:
        k = min(width / w, height / h)
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    resized = image.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    if mode == 'cover':
        left = int(round((nw - width) * focus[0]))
        top = int(round((nh - height) * focus[1]))
        canvas.paste(resized.crop((left, top, left + width, top + height)), (0, 0))
    else:
        canvas.paste(resized, ((width - nw) // 2, (height - nh) // 2))
    return canvas


def pad(image, px):
    from PIL import Image
    if px <= 0:
        return image
    out = Image.new('RGBA', (image.width + 2 * px, image.height + 2 * px), (0, 0, 0, 0))
    out.paste(image, (px, px))
    return out


def outline(image, px, color):
    """Contorno externo pela dilatação do alfa (precisa de margem transparente: é acrescentada)."""
    from PIL import Image, ImageFilter
    base = pad(image, px + 1)
    alpha = base.getchannel('A')
    grown = alpha.filter(ImageFilter.MaxFilter(2 * px + 1)).filter(ImageFilter.GaussianBlur(.6))
    ring = Image.new('RGBA', base.size, color + (255,))
    ring.putalpha(grown)
    return Image.alpha_composite(ring, base)


def shadow(image, dx, dy, blur, opacity, color=(0, 0, 0)):
    from PIL import Image, ImageFilter
    margin = blur * 2 + max(abs(dx), abs(dy)) + 1
    base = pad(image, margin)
    alpha = base.getchannel('A')
    offset = Image.new('L', base.size, 0)
    offset.paste(alpha, (dx, dy))
    if blur:
        offset = offset.filter(ImageFilter.GaussianBlur(blur))
    offset = offset.point(lambda v: int(v * opacity))
    layer = Image.new('RGBA', base.size, color + (255,))
    layer.putalpha(offset)
    return Image.alpha_composite(layer, base)


def crop_region(image, box):
    x, y, w, h = box
    W, H = image.size
    return image.crop((int(round(x * W)), int(round(y * H)), int(round((x + w) * W)), int(round((y + h) * H))))


def apply_mask(image, mask_path):
    """Máscara fornecida: o brilho da máscara (ou o alfa dela, se houver) vira a transparência da imagem."""
    from PIL import Image
    mask = load(mask_path)
    if mask.getchannel('A').getextrema()[0] < 255:
        channel = mask.getchannel('A')
    else:
        channel = mask.convert('L')
    channel = channel.resize(image.size, Image.LANCZOS)
    out = image.copy()
    existing = out.getchannel('A')
    from PIL import ImageChops
    out.putalpha(ImageChops.multiply(existing, channel))
    return out


def key_uniform_background(image, tolerance):
    """Torna transparente um fundo de cor uniforme. Recusa quando as bordas não são uniformes (foto comum)."""
    import numpy as np
    arr = np.asarray(image.convert('RGB')).astype('float32')
    h, w = arr.shape[:2]
    band = max(2, min(h, w) // 40)
    border = np.concatenate([arr[:band].reshape(-1, 3), arr[-band:].reshape(-1, 3),
                             arr[:, :band].reshape(-1, 3), arr[:, -band:].reshape(-1, 3)])
    color = np.median(border, axis=0)
    close = (np.abs(border - color).max(axis=1) <= tolerance).mean()
    if close < .92:
        raise RecipeError('O fundo não é uniforme; esta receita só remove fundo de uma cor só (use uma máscara para fotos).')
    dist = np.abs(arr - color).max(axis=2)
    # rampa suave logo acima da tolerância evita serrilhado na borda
    alpha = np.clip((dist - tolerance) / max(1.0, tolerance * .6), 0, 1)
    existing = np.asarray(image.getchannel('A')).astype('float32') / 255
    from PIL import Image
    out = image.copy()
    out.putalpha(Image.fromarray((alpha * existing * 255).round().astype('uint8')))
    return out


def run(image, recipe):
    """Aplica a receita (já limpa) na ordem: recorte → fundo → máscara → ajuste → contorno → sombra → margem."""
    steps = []
    if recipe.get('crop'):
        image = crop_region(image, recipe['crop'])
        steps.append('recorte')
    if recipe.get('key_bg'):
        image = key_uniform_background(image, recipe['key_bg'])
        steps.append('fundo uniforme removido')
    if recipe.get('mask'):
        image = apply_mask(image, recipe['mask'])
        steps.append('máscara')
    width, height = recipe.get('width'), recipe.get('height')
    if width or height:
        w0, h0 = image.size
        if width and height:
            image = fit_to(image, width, height, recipe['fit'])
        else:  # só um lado: mantém a proporção
            k = (width / w0) if width else (height / h0)
            from PIL import Image
            image = image.resize((max(1, round(w0 * k)), max(1, round(h0 * k))), Image.LANCZOS)
        steps.append(recipe['fit'] if width and height else 'proporcional')
    if recipe.get('outline'):
        image = outline(image, recipe['outline']['px'], tuple(recipe['outline']['color']))
        steps.append('contorno')
    if recipe.get('shadow'):
        s = recipe['shadow']
        image = shadow(image, s['dx'], s['dy'], s['blur'], s['opacity'])
        steps.append('sombra')
    if recipe.get('margin'):
        image = pad(image, recipe['margin'])
        steps.append('margem')
    return image, steps


def save(image, path, recipe):
    """Grava no formato pedido. JPG não tem transparência: compõe sobre `bg` e avisa."""
    from PIL import Image
    path = Path(path)
    fmt = recipe['format']
    tmp = path.with_name(path.name + '.tmp')
    flattened = False
    if fmt == 'jpg':
        base = Image.new('RGB', image.size, tuple(recipe['bg']))
        base.paste(image, mask=image.getchannel('A'))
        base.save(tmp, 'JPEG', quality=recipe['quality'], subsampling=0, optimize=True)
        flattened = image.getchannel('A').getextrema()[0] < 255
    elif fmt == 'webp':
        image.save(tmp, 'WEBP', quality=recipe['quality'], method=4)
    else:
        image.save(tmp, 'PNG', optimize=True)
    tmp.replace(path)
    return flattened


def alpha_of(image):
    return image.getchannel('A').getextrema()[0] < 255


# ---------- lote (arquivos mistos, erros isolados, sem sobrescrever fontes) ----------

def _unique(path):
    path = Path(path)
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f'{path.stem}_{n}{path.suffix}')
        if not candidate.exists():
            return candidate
    raise RecipeError('Muitos arquivos com o mesmo nome na pasta de saída.')


def batch(paths, recipe, out_dir, suffix='_hooks'):
    """Processa cada arquivo por conta própria: um erro não interrompe os demais. Nunca grava sobre a fonte."""
    recipe = clean(recipe)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for source in paths:
        source = Path(source)
        row = dict(source=str(source), name=source.name)
        try:
            image = load(source)
            result, steps = run(image, recipe)
            ext = {'jpg': '.jpg', 'png': '.png', 'webp': '.webp'}[recipe['format']]
            target = _unique(out_dir / (source.stem + suffix + ext))
            if target.resolve() == source.resolve():
                raise RecipeError('A saída coincide com a fonte; escolha outra pasta.')
            flattened = save(result, target, recipe)
            row.update(ok=True, output=str(target), width=result.width, height=result.height, alpha=alpha_of(result) and recipe['format'] != 'jpg',
                       steps=steps, note=image.info.get('note', ''), flattened=flattened)
        except Exception as exc:
            row.update(ok=False, error=str(exc)[:200])
        report.append(row)
    return report


# ---------- variantes por destino, com catálogo e cache ----------

def _vfolder(root):
    path = Path(root) / 'imagens' / 'variantes'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _catalog_file(root):
    return _vfolder(root) / 'catalogo.json'


def _read_catalog(root):
    try:
        value = json.loads(_catalog_file(root).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_catalog(root, data):
    file = _catalog_file(root)
    tmp = file.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(file)


def recipe_for(destination, canvas, scale=.16, style='none', fit='contain'):
    """Receita padrão de cada destino. `scale` é a fração da largura do quadro ocupada pelo elemento visível."""
    W, H = canvas
    if destination in ('logo', 'marca_dagua', 'capa_logo'):
        inner = max(16, int(round(W * scale / 2)) * 2)
        recipe = dict(width=inner, fit='contain', format='png')
        if style == 'sombra':
            recipe['shadow'] = dict(dx=0, dy=max(2, inner // 40), blur=max(3, inner // 30), opacity=.55)
        elif style == 'contorno':
            recipe['outline'] = dict(px=max(1, inner // 70), color='#000000')
        return clean(recipe)
    if destination == 'moldura':
        return clean(dict(width=W, height=H, fit='cover', format='png'))
    if destination == 'cartao':
        return clean(dict(width=W, height=H, fit=fit, format='png'))
    raise RecipeError('Destino de imagem desconhecido.')


def variant(root, image_id, destination, canvas=(1080, 1920), scale=.16, style='none', fit='contain'):
    """Variante pronta (PNG com alfa) de um asset da biblioteca. Reutiliza do catálogo quando nada mudou.
    → dict(path, width, height, alpha, cached)."""
    from . import assets, media
    if destination not in DESTINATIONS:
        raise RecipeError('Destino de imagem desconhecido.')
    source = assets.path_of(root, image_id)
    recipe = recipe_for(destination, canvas, scale, style, fit)
    sha = media.sha_file(source)
    key = hashlib.sha256(json.dumps([VERSION, sha, destination, list(canvas), recipe], sort_keys=True, default=list).encode()).hexdigest()[:20]
    catalog = _read_catalog(root)
    item = catalog.get(key)
    if item and (_vfolder(root) / item['file']).is_file():
        return dict(item, path=str(_vfolder(root) / item['file']), cached=True)
    image = load(source)
    result, steps = run(image, recipe)
    if result.width % 2 or result.height % 2:      # FFmpeg/yuv trabalham melhor com medidas pares
        from PIL import Image
        wide, high = result.width + result.width % 2, result.height + result.height % 2
        canvas_img = Image.new('RGBA', (wide, high), (0, 0, 0, 0))
        canvas_img.paste(result, (0, 0))
        result = canvas_img
    target = _vfolder(root) / f'{key}.png'
    save(result, target, recipe)
    item = dict(key=key, file=target.name, source=image_id, source_sha=sha, destination=destination, canvas=list(canvas), recipe=recipe,
                steps=steps, width=result.width, height=result.height, alpha=alpha_of(result), version=VERSION, created=int(time.time()),
                note=image.info.get('note', ''))
    # variantes antigas da mesma fonte e destino saem do catálogo (o arquivo vai junto)
    for old_key, old in list(catalog.items()):
        if old.get('source') == image_id and old.get('destination') == destination and old.get('canvas') == list(canvas) and old_key != key:
            (_vfolder(root) / old['file']).unlink(missing_ok=True)
            catalog.pop(old_key, None)
    catalog[key] = item
    _write_catalog(root, catalog)
    return dict(item, path=str(target), cached=False)


def catalog(root):
    return sorted(_read_catalog(root).values(), key=lambda i: -i.get('created', 0))


def prune(root):
    """Remove variantes cuja fonte saiu da biblioteca ou mudou de conteúdo."""
    from . import assets, media
    data = _read_catalog(root)
    removed = 0
    for key, item in list(data.items()):
        try:
            current = media.sha_file(assets.path_of(root, item['source']))
        except Exception:
            current = None
        if current != item.get('source_sha'):
            (_vfolder(root) / item['file']).unlink(missing_ok=True)
            data.pop(key)
            removed += 1
    if removed:
        _write_catalog(root, data)
    return removed
