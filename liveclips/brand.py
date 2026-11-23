"""Kit de marca por streamer: logo, cartões de abertura/encerramento, fonte e cores dos títulos.

Tudo é aplicado na exportação com o kit ATUAL do streamer (mudar o kit muda o que sai da próxima exportação).
Limites: os cartões de abertura e encerramento são IMAGENS colocadas por cima do vídeo nos primeiros/últimos
segundos (não acrescentam tempo nem vídeo); a imagem deve ter a proporção do quadro (1080x1920) para cobrir tudo.
Fontes: coloque arquivos .ttf/.otf na pasta `fontes` dentro da pasta de dados. O nome usado é o da família da fonte.
"""
from pathlib import Path
import re
import shutil

CORNERS = ('tl', 'tr', 'bl', 'br')
TITLE_POSITIONS = ('top', 'center', 'bottom')
HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')
ID_RE = re.compile(r'^[a-f0-9]{16}$')
# Margens em pixels num quadro 1080x1920 que mantêm o logo fora do que o TikTok costuma cobrir (valores aproximados).
SAFE = dict(top=170, bottom=500, left=60, right=150)

LOGO_STYLES = ('none', 'sombra', 'contorno')
CARD_FITS = ('original', 'contain', 'cover')
DEFAULT = dict(logo=dict(image='', corner='tl', scale=.16, opacity=.9, style='none', cover=False), intro=dict(image='', seconds=1.0),
               outro=dict(image='', seconds=1.5), frame=dict(image='', opacity=1.0), card_fit='original',
               caption_font='', title_color='', title_position='')


def _image(value, label):
    value = str(value or '').strip()
    if value and not ID_RE.match(value):
        raise ValueError(f'Imagem inválida em {label}.')
    return value


def _num(value, low, high, label, default):
    try:
        number = float(default if value in (None, '') else value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} precisa ser um número.') from None
    if not low <= number <= high:
        raise ValueError(f'{label} deve ficar entre {low:g} e {high:g}.')
    return round(number, 3)


def clean(raw):
    raw = raw if isinstance(raw, dict) else {}
    logo, intro, outro, frame = (raw.get(k) if isinstance(raw.get(k), dict) else {} for k in ('logo', 'intro', 'outro', 'frame'))
    style = logo.get('style') or 'none'
    if style not in LOGO_STYLES:
        raise ValueError('Estilo do logo inválido.')
    card_fit = raw.get('card_fit') or 'original'
    if card_fit not in CARD_FITS:
        raise ValueError('Ajuste dos cartões inválido.')
    corner = logo.get('corner') or 'tl'
    if corner not in CORNERS:
        raise ValueError('Canto do logo inválido.')
    font = ' '.join(str(raw.get('caption_font') or '').replace('\x00', ' ').split())[:60]
    if font and not re.fullmatch(r"[\w .'\-&]+", font):
        raise ValueError('Nome de fonte inválido.')
    color = str(raw.get('title_color') or '')
    if color and not HEX.match(color):
        raise ValueError('Cor do título inválida (use #RRGGBB).')
    position = raw.get('title_position') or ''
    if position and position not in TITLE_POSITIONS:
        raise ValueError('Posição do título inválida.')
    return dict(logo=dict(image=_image(logo.get('image'), 'logo'), corner=corner, scale=_num(logo.get('scale'), .05, .4, 'Tamanho do logo', .16),
                          opacity=_num(logo.get('opacity'), .2, 1, 'Opacidade do logo', .9),
                          style=style, cover=bool(logo.get('cover'))),
                frame=dict(image=_image(frame.get('image'), 'moldura'), opacity=_num(frame.get('opacity'), .2, 1, 'Opacidade da moldura', 1.0)),
                card_fit=card_fit,
                intro=dict(image=_image(intro.get('image'), 'abertura'), seconds=_num(intro.get('seconds'), .3, 4, 'Tempo da abertura', 1.0)),
                outro=dict(image=_image(outro.get('image'), 'encerramento'), seconds=_num(outro.get('seconds'), .3, 4, 'Tempo do encerramento', 1.5)),
                caption_font=font, title_color=('#' + HEX.match(color).group(1).upper()) if color else '', title_position=position)


def active(brand):
    brand = brand or {}
    return bool((brand.get('logo') or {}).get('image') or (brand.get('intro') or {}).get('image') or (brand.get('outro') or {}).get('image')
                or (brand.get('frame') or {}).get('image'))


def logo_center(corner, scale, aspect, canvas=(1080, 1920)):
    """Centro (x, y em 0–1) do logo ancorado no canto, respeitando as margens seguras. `aspect` = altura/largura da imagem."""
    W, H = canvas
    k = W / 1080
    width = W * scale
    height = width * aspect
    left = SAFE['left'] * k
    right = W - SAFE['right'] * k - width
    top = SAFE['top'] * k
    bottom = H - SAFE['bottom'] * k - height
    x = left if corner in ('tl', 'bl') else right
    y = top if corner in ('tl', 'tr') else bottom
    x = max(0, min(W - width, x))
    y = max(0, min(H - height, y))
    return round((x + width / 2) / W, 4), round((y + height / 2) / H, 4)


def assets(brand, root, duration, canvas=(1080, 1920)):
    """Sobreposições no tempo FINAL do vídeo. → (lista, avisos). Imagem que saiu da biblioteca vira aviso, não erro."""
    from . import assets as library
    out, warnings = [], []
    if not active(brand):
        return out, warnings

    def find(image_id, label):
        if not image_id:
            return None
        try:
            item = library.get(root, image_id)
            return item, str(library.path_of(root, image_id))
        except Exception:
            warnings.append(f'A imagem do kit de marca ({label}) não está mais na biblioteca e foi ignorada.')
            return None
    def variant(image_id, destination, label, **kw):
        """Variante preparada (P21). Qualquer falha cai na imagem original, com aviso."""
        try:
            from . import imagerecipe
            return imagerecipe.variant(root, image_id, destination, canvas, **kw)
        except Exception as exc:
            warnings.append(f'Não consegui preparar a variante de {label} ({str(exc)[:80]}); usei a imagem original.')
            return None
    frame = brand.get('frame') or {}
    found = find(frame.get('image'), 'moldura')
    if found:
        made = variant(frame['image'], 'moldura', 'moldura')
        out.append(dict(kind='overlay', id='brand:frame', path=made['path'] if made else found[1], start=0.0, end=round(duration, 3),
                        x=.5, y=.5, scale=1.0, opacity=float(frame.get('opacity', 1.0))))
    logo = brand.get('logo') or {}
    found = find(logo.get('image'), 'logo')
    if found:
        item, path = found
        scale = float(logo['scale'])
        aspect = item['height'] / max(1, item['width'])
        style = logo.get('style') or 'none'
        if style != 'none':
            made = variant(logo['image'], 'logo', 'logo', scale=scale, style=style)
            if made:
                path, aspect, scale = made['path'], made['height'] / max(1, made['width']), made['width'] / canvas[0]
        x, y = logo_center(logo.get('corner', 'tl'), scale, aspect, canvas)
        out.append(dict(kind='overlay', id='brand:logo', path=path, start=0.0, end=round(duration, 3), x=x, y=y,
                        scale=scale, opacity=float(logo['opacity'])))
    fit = brand.get('card_fit') or 'original'
    for key, label in (('intro', 'abertura'), ('outro', 'encerramento')):
        card = brand.get(key) or {}
        found = find(card.get('image'), label)
        if not found:
            continue
        path = found[1]
        if fit != 'original':
            made = variant(card['image'], 'cartao', label, fit=fit)
            if made:
                path = made['path']
        seconds = min(float(card['seconds']), duration / 3)
        start, end = (0.0, seconds) if key == 'intro' else (max(0.0, duration - seconds), duration)
        out.append(dict(kind='overlay', id=f'brand:{key}', path=path, start=round(start, 3), end=round(end, 3), x=.5, y=.5, scale=1.0, opacity=1.0))
    return out, warnings


def apply_titles(titles, brand):
    color, position = (brand or {}).get('title_color'), (brand or {}).get('title_position')
    if not (color or position):
        return titles
    # Só mexe no que o editor deixou no padrão (branco, topo): uma escolha feita clipe a clipe continua valendo.
    return [dict(t, **({'color': color} if color and str(t.get('color', '#FFFFFF')).upper() == '#FFFFFF' else {}),
                 **({'position': position} if position and t.get('position', 'top') == 'top' else {})) for t in titles]


def fonts(root):
    """[{file, family}] das fontes na pasta `fontes`."""
    folder = Path(root) / 'fontes'
    result = []
    if not folder.is_dir():
        return result
    for file in sorted(folder.iterdir()):
        if file.suffix.lower() not in ('.ttf', '.otf') or file.stat().st_size > 30 * 1024 ** 2:
            continue
        family = file.stem
        try:
            from PIL import ImageFont
            family = ImageFont.truetype(str(file), 20).getname()[0]
        except Exception:
            pass
        result.append(dict(file=file.name, family=family))
    return result


def prepare_fonts(root, scratch):
    """Copia as fontes para a pasta de trabalho (o filtro lê por nome relativo). → True se há fontes."""
    target = Path(scratch) / 'fontes'
    target.mkdir(exist_ok=True)
    items = fonts(root)
    for item in items:
        shutil.copyfile(Path(root) / 'fontes' / item['file'], target / item['file'])
    return bool(items)
