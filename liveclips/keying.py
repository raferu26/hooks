"""Chaves de cor, máscaras e mistura (P16) para imagens sobrepostas — tudo calculado uma vez, em CPU, sem modelo.

`key`: {mode:'chroma', color:'#00FF00', tolerance:0–1, softness:0–1, despill:bool} ou {mode:'luma', threshold:0–1, softness:0–1, keep:'light'|'dark'}.
`mask`: {shape:'circle'|'rounded', feather:0–0.4, radius:0–0.5}.  `blend`: 'normal' | 'screen' | 'multiply'.
Valores fora da faixa são recusados na validação (não ajustados em silêncio)."""
import re

BLENDS = ('normal', 'screen', 'multiply')
HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')


def _num(value, low, high, label, default):
    if value in (None, ''):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + ' inválido.')
    if not (low <= number <= high) or number != number:
        raise ValueError(f'{label} deve ficar entre {low:g} e {high:g}.')
    return round(number, 3)


def check_key(raw):
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError('Chave de cor inválida.')
    mode = raw.get('mode')
    if mode == 'chroma':
        match = HEX.match(str(raw.get('color') or '#00FF00'))
        if not match:
            raise ValueError('Cor da chave inválida (use #RRGGBB).')
        return dict(mode='chroma', color='#' + match.group(1).upper(), tolerance=_num(raw.get('tolerance'), 0, 1, 'Tolerância', .25),
                    softness=_num(raw.get('softness'), 0, 1, 'Suavidade', .1), despill=bool(raw.get('despill', True)))
    if mode == 'luma':
        keep = raw.get('keep') or 'light'
        if keep not in ('light', 'dark'):
            raise ValueError('A chave de luminância mantém "light" ou "dark".')
        return dict(mode='luma', threshold=_num(raw.get('threshold'), 0, 1, 'Limiar', .5), softness=_num(raw.get('softness'), 0, 1, 'Suavidade', .1), keep=keep)
    raise ValueError('Modo de chave inválido (chroma ou luma).')


def check_mask(raw):
    if not raw:
        return None
    if not isinstance(raw, dict) or raw.get('shape') not in ('circle', 'rounded'):
        raise ValueError('Máscara inválida (circle ou rounded).')
    return dict(shape=raw['shape'], feather=_num(raw.get('feather'), 0, .4, 'Suavização da borda', .02),
                radius=_num(raw.get('radius'), 0, .5, 'Raio', .12))


def check_blend(value):
    value = value or 'normal'
    if value not in BLENDS:
        raise ValueError('Modo de mistura inválido.')
    return value


def _smooth(x):
    import numpy as np
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def key_alpha(rgb, key):
    """Alfa 0–1 (float32, HxW) segundo a chave."""
    import numpy as np
    data = rgb.astype('float32') / 255.0
    soft = max(.001, key['softness'])
    if key['mode'] == 'chroma':
        color = np.array([int(key['color'][i:i + 2], 16) for i in (1, 3, 5)], 'float32') / 255.0
        # distância na crominância (YCbCr) para ignorar variação de brilho do pano
        def cbcr(a):
            return np.stack([-.1687 * a[..., 0] - .3313 * a[..., 1] + .5 * a[..., 2], .5 * a[..., 0] - .4187 * a[..., 1] - .0813 * a[..., 2]], -1)
        distance = np.sqrt(((cbcr(data) - cbcr(color)) ** 2).sum(-1)) / .7
        return _smooth((distance - key['tolerance']) / soft).astype('float32')
    luma = .2126 * data[..., 0] + .7152 * data[..., 1] + .0722 * data[..., 2]
    value = (luma - key['threshold']) / soft if key['keep'] == 'light' else (key['threshold'] - luma) / soft
    return _smooth(value + .5).astype('float32')


def despill(rgb, key, alpha):
    """Tira o verde (ou azul) que sobra na borda do objeto: limita o canal da chave à média dos outros dois."""
    import numpy as np
    out = rgb.astype('float32')
    channel = int(np.argmax([int(key['color'][i:i + 2], 16) for i in (1, 3, 5)]))
    others = [i for i in range(3) if i != channel]
    limit = out[..., others].mean(-1)
    out[..., channel] = np.minimum(out[..., channel], limit)
    return np.clip(out, 0, 255).astype('uint8')


def mask_alpha(width, height, mask):
    import numpy as np
    ys, xs = np.mgrid[0:height, 0:width].astype('float32')
    nx, ny = (xs + .5) / width, (ys + .5) / height
    feather = max(.001, mask['feather'])
    if mask['shape'] == 'circle':
        distance = np.sqrt(((nx - .5) * width) ** 2 + ((ny - .5) * height) ** 2) / (min(width, height) / 2.0)
        return _smooth((1.0 - distance) / feather + .5).astype('float32')
    radius = mask['radius'] * min(width, height)
    qx = np.abs((nx - .5) * width) - (width / 2.0 - radius)
    qy = np.abs((ny - .5) * height) - (height / 2.0 - radius)
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - radius
    return _smooth((-outside / (feather * min(width, height))) + .5).astype('float32')


def apply(source, destination, width, key=None, mask=None):
    """Imagem -> PNG RGBA no tamanho final, com chave e máscara aplicadas. Levanta ValueError se a imagem não abrir."""
    import numpy as np
    from PIL import Image
    try:
        image = Image.open(str(source)).convert('RGBA')
    except Exception as exc:
        raise ValueError('Não consegui abrir a imagem: ' + str(exc)[:80])
    if image.width > width:
        image = image.resize((width, max(2, round(image.height * width / image.width))), Image.LANCZOS)
    pixels = np.array(image)
    rgb, alpha = pixels[..., :3], pixels[..., 3].astype('float32') / 255.0
    if key:
        keyed = key_alpha(rgb, key)
        if key['mode'] == 'chroma' and key.get('despill', True):
            rgb = despill(rgb, key, keyed)
        alpha = alpha * keyed
    if mask:
        alpha = alpha * mask_alpha(image.width, image.height, mask)
    out = np.dstack([rgb, np.clip(alpha * 255, 0, 255).astype('uint8')]).astype('uint8')
    Image.fromarray(out, 'RGBA').save(str(destination))
    return destination


def layer(source, destination, canvas, x, y, scale, opacity, blend, key=None, mask=None):
    """Camada do tamanho do quadro para os modos de mistura (screen/multiply): a imagem posicionada sobre o fundo neutro do modo."""
    import numpy as np
    from PIL import Image
    W, H = canvas
    width = max(16, int(W * scale) // 2 * 2)
    tmp = str(destination) + '.tmp.png'
    apply(source, tmp, width, key, mask)
    image = Image.open(tmp).convert('RGBA')
    background = (255, 255, 255, 255) if blend == 'multiply' else (0, 0, 0, 255)
    page = Image.new('RGBA', (W, H), background)
    left, top = round(W * x - image.width / 2), round(H * y - image.height / 2)
    alpha = np.array(image)[..., 3].astype('float32') / 255.0 * float(opacity)
    patch = np.array(image)[..., :3].astype('float32')
    base = np.array(page.crop((0, 0, W, H)))[..., :3].astype('float32')
    x0, y0, x1, y1 = max(0, left), max(0, top), min(W, left + image.width), min(H, top + image.height)
    if x1 > x0 and y1 > y0:
        sub = patch[y0 - top:y1 - top, x0 - left:x1 - left]
        a = alpha[y0 - top:y1 - top, x0 - left:x1 - left][..., None]
        base[y0:y1, x0:x1] = base[y0:y1, x0:x1] * (1 - a) + sub * a
    Image.fromarray(base.astype('uint8'), 'RGB').save(str(destination))
    import os
    os.remove(tmp)
    return destination
