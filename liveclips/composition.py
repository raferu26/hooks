"""Composição de reação: FONTE → REGIÕES → TRANSFORMAÇÕES → LAYOUT → QUADRO FINAL (sem IA, só geometria).

Um único motor para os oito layouts. O usuário marca regiões (webcam, conteúdo, webcam 2) no quadro ORIGINAL; cada layout
é uma tabela de "caixas" no quadro vertical; `resolve()` transforma regiões + caixas em camadas (recorte em pixels da
fonte, tamanho final, posição) e `video_graph()` escreve o filtergraph a partir dessas MESMAS camadas. A interface
desenha a prévia imediata com o resultado de `resolve()` — não existe uma segunda conta de coordenadas.

Coordenadas das regiões: frações 0–1 do quadro de EXIBIÇÃO da fonte (depois de rotação e de proporção de pixel), com
origem no canto superior esquerdo: {x, y, w, h}. São independentes da resolução (a mesma região vale para o arquivo
original, para o proxy e para a prévia). Nada aqui altera o arquivo de origem.
"""
import math
import re

VERSION = 1
CANVAS = (1080, 1920)
ROLES = ('webcam', 'conteudo', 'webcam2')
FITS = ('fit', 'fill', 'custom')
BG_KINDS = ('black', 'color', 'blur')
CORNERS = ('tl', 'tr', 'bl', 'br', 'free')
MIN_REGION = .02            # fração mínima do quadro (2%) para uma região ser considerada marcada
UPSCALE_WARN = 2.0          # ampliar mais que isso deixa a imagem visivelmente suave
HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')

# Cada layout: rótulo, papéis exigidos, descrição curta e parâmetros iniciais (valores de partida, todos ajustáveis).
LAYOUTS = {
    'cam_compacta': dict(label='Webcam compacta', roles=('webcam', 'conteudo'), group='main',
                         hint='Webcam em cima, pequena; o conteúdo ocupa a maior parte.', params=dict(split=.30)),
    'cam_ampliada': dict(label='Webcam ampliada', roles=('webcam', 'conteudo'), group='main',
                         hint='Webcam grande em cima para valorizar a expressão; conteúdo abaixo, quase quadrado.',
                         params=dict(split=.45)),
    'cam_flutuante': dict(label='Webcam flutuante', roles=('webcam', 'conteudo'), group='main',
                          hint='Conteúdo em tela cheia e a webcam sobreposta em uma janela.', params=dict(pip_size=.34)),
    'cam_embaixo': dict(label='Webcam embaixo', roles=('webcam', 'conteudo'), group='more',
                        hint='Conteúdo em cima, streamer embaixo.', params=dict(split=.62)),
    'foco_reacao': dict(label='Foco na reação', roles=('webcam', 'conteudo'), group='more',
                        hint='O streamer ocupa quase tudo; o conteúdo vira uma janela pequena.', params=dict(pip_size=.36)),
    'dueto': dict(label='Dueto lado a lado', roles=('webcam', 'webcam2'), group='more',
                  hint='Duas pessoas dividindo a tela vertical.', params=dict(split=.5)),
    'duas_cams': dict(label='Duas webcams + conteúdo', roles=('webcam', 'webcam2', 'conteudo'), group='more',
                      hint='Dois participantes em cima e o conteúdo embaixo.', params=dict(split=.34, col_split=.5)),
    'cinema': dict(label='Modo cinema', roles=('webcam', 'conteudo'), group='more',
                   hint='Conteúdo horizontal inteiro, sem cortar; sobra vira fundo.', params=dict(split=.28, bg='blur')),
}
ROLE_LABELS = dict(webcam='Webcam', conteudo='Conteúdo', webcam2='Webcam 2')
DEFAULTS = dict(split=.45, col_split=.5, gap=0, content_fit='fill', content_zoom=1.0, content_fx=.5, content_fy=.5,
                cam_fit='fill', cam_zoom=1.0, cam_fx=.5, cam_fy=.4, cam2_fit='fill', cam2_zoom=1.0, cam2_fx=.5, cam2_fy=.4,
                pip='br', pip_size=.34, pip_margin=40, pip_x=.8, pip_y=.8, pip_border=0, pip_border_color='#FFFFFF',
                hide_content=False, bg='black', bg_color='#101010')
# Cinema mostra o conteúdo inteiro por padrão; os demais preenchem a caixa (recortando, sem distorcer).
LAYOUT_OVERRIDES = dict(cinema=dict(content_fit='fit', cam_fy=.4), cam_flutuante=dict(pip='tr', pip_border=4),
                        foco_reacao=dict(pip='br', pip_border=4, content_fit='fit'))
NUMBERS = dict(split=(.15, .85), col_split=(.25, .75), gap=(0, 40), content_zoom=(1, 4), content_fx=(0, 1), content_fy=(0, 1),
               cam_zoom=(1, 4), cam_fx=(0, 1), cam_fy=(0, 1), cam2_zoom=(1, 4), cam2_fx=(0, 1), cam2_fy=(0, 1),
               pip_size=(.15, .7), pip_margin=0, pip_x=(0, 1), pip_y=(0, 1), pip_border=(0, 12))


def catalog():
    """Para a interface: layouts, papéis, valores iniciais e limites."""
    return dict(version=VERSION, layouts=[dict(id=k, **{x: (list(v[x]) if isinstance(v[x], tuple) else v[x]) for x in ('label', 'roles', 'group', 'hint')},
                                               params=params_for(k)) for k, v in LAYOUTS.items()],
                role_labels=ROLE_LABELS, fits=list(FITS), bg_kinds=list(BG_KINDS), corners=list(CORNERS),
                limits={k: list(v) if isinstance(v, tuple) else [v, 200] for k, v in NUMBERS.items()}, canvas=list(CANVAS))


def params_for(layout):
    out = dict(DEFAULTS)
    out.update(LAYOUTS[layout]['params'])
    out.update(LAYOUT_OVERRIDES.get(layout, {}))
    return out


def _num(value, low, high, name, default):
    if value is None or value == '':
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} precisa ser um número.') from None
    if not math.isfinite(number):
        raise ValueError(f'{name} precisa ser um número válido.')
    return max(low, min(high, number))


def _hex(value, default):
    match = HEX.match(str(value or ''))
    return '#' + match.group(1).upper() if match else default


def clean_region(raw, role):
    """Região {x,y,w,h} validada: dentro do quadro (cortada nas bordas) e com pelo menos 2% do quadro em cada lado."""
    if not isinstance(raw, dict):
        raise ValueError(f'Região “{ROLE_LABELS.get(role, role)}” inválida.')
    try:
        x, y, w, h = (float(raw[k]) for k in ('x', 'y', 'w', 'h'))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f'Região “{ROLE_LABELS.get(role, role)}” precisa de x, y, w e h numéricos.') from None
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise ValueError(f'Região “{ROLE_LABELS.get(role, role)}” tem coordenadas inválidas.')
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(1.0, x + w), min(1.0, y + h)
    if x1 - x0 < MIN_REGION or y1 - y0 < MIN_REGION:
        raise ValueError(f'A região “{ROLE_LABELS.get(role, role)}” está vazia, fora do quadro ou pequena demais (mínimo 2% do quadro).')
    return dict(x=round(x0, 5), y=round(y0, 5), w=round(x1 - x0, 5), h=round(y1 - y0, 5))


def clean(raw):
    """Valida/normaliza `project['composition']`. Devolve None (sem composição) ou o dicionário canônico.

    Regiões ausentes são aceitas (o assistente ainda está marcando): a composição fica `incompleta` e o render usa o
    enquadramento de sempre até que todas as regiões do layout existam."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError('Composição inválida.')
    layout = raw.get('layout')
    if layout not in LAYOUTS:
        raise ValueError('Layout de reação desconhecido.')
    regions = {}
    given = raw.get('regions') or {}
    if not isinstance(given, dict):
        raise ValueError('Regiões inválidas.')
    for role in ROLES:
        if given.get(role):
            regions[role] = clean_region(given[role], role)
    base = params_for(layout)
    source = raw.get('params') or {}
    if not isinstance(source, dict):
        raise ValueError('Parâmetros da composição inválidos.')
    params = {}
    for key, default in base.items():
        value = source.get(key, default)
        if key in NUMBERS:
            low, high = NUMBERS[key] if isinstance(NUMBERS[key], tuple) else (NUMBERS[key], 200)
            params[key] = round(_num(value, low, high, key, default), 4)
        elif key in ('content_fit', 'cam_fit', 'cam2_fit'):
            if value not in FITS:
                raise ValueError('Modo de enquadramento inválido (use fit, fill ou custom).')
            params[key] = value
        elif key == 'pip':
            if value not in CORNERS:
                raise ValueError('Posição da janela inválida.')
            params[key] = value
        elif key == 'bg':
            if value not in BG_KINDS:
                raise ValueError('Fundo inválido (use black, color ou blur).')
            params[key] = value
        elif key in ('bg_color', 'pip_border_color'):
            params[key] = _hex(value, default)
        elif key == 'hide_content':
            params[key] = bool(value)
    params['pip_margin'] = int(_num(params['pip_margin'], 0, 200, 'pip_margin', 40))
    params['gap'] = int(params['gap'])
    params['pip_border'] = int(params['pip_border'])
    return dict(version=VERSION, layout=layout, regions=regions, params=params)


def is_ready(comp):
    return bool(comp) and all(role in comp.get('regions', {}) for role in LAYOUTS[comp['layout']]['roles'])


def missing_roles(comp):
    return [r for r in LAYOUTS[comp['layout']]['roles'] if r not in comp.get('regions', {})]


# ───────────── geometria ─────────────

def _even(value, low=2):
    return max(low, int(round(value / 2.0)) * 2)


def _boxes(layout, params, W, H):
    """Caixas no quadro final: papel → (x, y, w, h, z). Tudo em pixels pares e dentro de W×H."""
    gap = params['gap']
    top = _even(H * params['split'])
    if layout in ('cam_compacta', 'cam_ampliada'):
        return dict(webcam=(0, 0, W, top, 1), conteudo=(0, top + gap, W, H - top - gap, 0))
    if layout == 'cinema':
        return dict(webcam=(0, 0, W, top, 1), conteudo=(0, top + gap, W, H - top - gap, 0))
    if layout == 'cam_embaixo':
        return dict(conteudo=(0, 0, W, top, 0), webcam=(0, top + gap, W, H - top - gap, 1))
    if layout == 'dueto':
        left = _even(W * params['split'])
        return dict(webcam=(0, 0, left, H, 0), webcam2=(left + gap, 0, W - left - gap, H, 0))
    if layout == 'duas_cams':
        left = _even(W * params['col_split'])
        return dict(webcam=(0, 0, left, top, 0), webcam2=(left + gap, 0, W - left - gap, top, 0),
                    conteudo=(0, top + gap, W, H - top - gap, 0))
    if layout in ('cam_flutuante', 'foco_reacao'):
        return dict(_full=(0, 0, W, H, 0))
    raise ValueError('Layout de reação desconhecido.')


def _place(region, box, fit, zoom, fx, fy, SW, SH):
    """Recorte (pixels da fonte) + tamanho + posição de uma região dentro de uma caixa. Nunca distorce: o recorte tem a
    proporção da caixa (fill/custom) ou a região inteira é reduzida por um fator único (fit)."""
    rx = int(round(region['x'] * SW) // 2 * 2)
    ry = int(round(region['y'] * SH) // 2 * 2)
    rw = max(2, min(SW - rx, int(round(region['w'] * SW)) // 2 * 2))
    rh = max(2, min(SH - ry, int(round(region['h'] * SH)) // 2 * 2))
    bx, by, bw, bh, z = box
    bw, bh = max(2, bw), max(2, bh)
    if fit == 'fit':
        s = min(bw / rw, bh / rh)
        ow, oh = _even(min(bw, rw * s)), _even(min(bh, rh * s))
        crop = (rx, ry, rw, rh)
        pos = (bx + int((bw - ow) * fx) // 2 * 2, by + int((bh - oh) * fy) // 2 * 2)
        scale = s
    else:
        s = max(bw / rw, bh / rh) * (zoom if fit == 'custom' else 1.0)
        cw = min(rw, max(2, int(round(bw / s)) // 2 * 2))
        ch = min(rh, max(2, int(round(bh / s)) // 2 * 2))
        cx = rx + int((rw - cw) * fx) // 2 * 2
        cy = ry + int((rh - ch) * fy) // 2 * 2
        crop = (cx, cy, cw, ch)
        ow, oh = bw, bh
        pos = (bx, by)
        scale = bw / cw
    shown = crop[2] * crop[3] / float(rw * rh)
    return dict(crop=crop, size=(ow, oh), pos=pos, z=z, scale=round(scale, 4), region_px=(rx, ry, rw, rh),
                aspect_error=abs((ow / oh) / (crop[2] / crop[3]) - 1), hidden=round(1 - shown, 4))


def _pip_geometry(region, params, W, H, SW, SH, size_frac):
    """Janela sobreposta com a proporção da região (sem distorcer), ancorada em um canto ou livre."""
    aspect = (region['w'] * SW) / float(region['h'] * SH)
    w = _even(W * size_frac)
    h = _even(w / aspect)
    if h > H * .7:
        h = _even(H * .7)
        w = _even(h * aspect)
    margin = params['pip_margin']
    corner = params['pip']
    if corner == 'free':
        x = int(params['pip_x'] * W - w / 2)
        y = int(params['pip_y'] * H - h / 2)
    else:
        x = margin if corner[1] == 'l' else W - w - margin
        y = margin + 120 if corner[0] == 't' else H - h - margin - 360   # respeita a faixa das legendas/interface
    x = max(0, min(W - w, x)) // 2 * 2
    y = max(0, min(H - h, y)) // 2 * 2
    return x, y, w, h


def resolve(comp, SW, SH, canvas=CANVAS):
    """Camadas da composição para uma fonte SW×SH (pixels de exibição). `comp` já validado por `clean()`.

    Devolve dict(ready, layers=[{role, crop, size, pos, z, ...}], bg, warnings). Camadas em ordem de empilhamento."""
    W, H = canvas
    if not comp:
        return dict(ready=False, layers=[], warnings=[], missing=[])
    layout, params = comp['layout'], comp['params']
    roles = LAYOUTS[layout]['roles']
    missing = missing_roles(comp)
    out = dict(ready=not missing, layout=layout, canvas=[W, H], missing=missing, layers=[], warnings=[],
               bg=dict(kind=params['bg'], color=params['bg_color']), source=[SW, SH])
    if missing:
        return out
    boxes = _boxes(layout, params, W, H)
    fitkey = dict(webcam='cam', webcam2='cam2', conteudo='content')
    layers = []
    if layout in ('cam_flutuante', 'foco_reacao'):
        main_role, small_role = ('conteudo', 'webcam') if layout == 'cam_flutuante' else ('webcam', 'conteudo')
        k = fitkey[main_role]
        main = _place(comp['regions'][main_role], boxes['_full'], params[k + '_fit'], params[k + '_zoom'], params[k + '_fx'],
                      params[k + '_fy'], SW, SH)
        layers.append(dict(role=main_role, **main))
        if not (layout == 'foco_reacao' and params['hide_content']):
            px, py, pw, ph = _pip_geometry(comp['regions'][small_role], params, W, H, SW, SH, params['pip_size'])
            k = fitkey[small_role]
            small = _place(comp['regions'][small_role], (px, py, pw, ph, 1), 'fill' if params[k + '_fit'] == 'fit' else params[k + '_fit'],
                           params[k + '_zoom'], params[k + '_fx'], params[k + '_fy'], SW, SH)
            layers.append(dict(role=small_role, border=params['pip_border'], border_color=params['pip_border_color'], **small))
    else:
        for role in roles:
            k = fitkey[role]
            placed = _place(comp['regions'][role], boxes[role], params[k + '_fit'], params[k + '_zoom'], params[k + '_fx'],
                            params[k + '_fy'], SW, SH)
            layers.append(dict(role=role, **placed))
    layers.sort(key=lambda layer: layer['z'])
    out['layers'] = layers
    for layer in layers:
        name = ROLE_LABELS[layer['role']]
        if layer['scale'] > UPSCALE_WARN:
            out['warnings'].append(f'{name}: a região original é pequena e será ampliada {layer["scale"]:.1f}×; ficará suave (a imagem não é reconstruída).')
        if layer['hidden'] > .05:
            out['warnings'].append(f'{name}: {round(layer["hidden"] * 100)}% da região marcada fica fora do quadro (recorte). Use “Mostrar inteiro” para ver tudo.')
    for a in range(len(layers)):
        for b in range(a + 1, len(layers)):
            ra, rb = comp['regions'][layers[a]['role']], comp['regions'][layers[b]['role']]
            ox = min(ra['x'] + ra['w'], rb['x'] + rb['w']) - max(ra['x'], rb['x'])
            oy = min(ra['y'] + ra['h'], rb['y'] + rb['h']) - max(ra['y'], rb['y'])
            if ox > 0 and oy > 0 and ox * oy > .25 * min(ra['w'] * ra['h'], rb['w'] * rb['h']):
                out['warnings'].append(f'{ROLE_LABELS[layers[a]["role"]]} e {ROLE_LABELS[layers[b]["role"]]} se sobrepõem na fonte (mostra a mesma imagem duas vezes).')
    return out


# ───────────── filtergraph ─────────────

def _color(value):
    return '0x' + HEX.match(value).group(1).upper()


def video_graph(comp, SW, SH, source='0:v', fps=30, canvas=CANVAS, sar=1.0, out='base', draft=False):
    """Trecho de filtergraph source → [out] (yuv420p, canvas) para a composição. Levanta ValueError se estiver incompleta.

    `SW`,`SH`: dimensões de exibição do quadro que chega em `source` (já com rotação aplicada pelo FFmpeg). `sar`≠1 é
    normalizado no início para que os recortes em pixels batam com as frações das regiões."""
    plan = resolve(comp, SW, SH, canvas)
    if not plan['ready']:
        raise ValueError('A composição de reação está incompleta: marque ' + ' e '.join(ROLE_LABELS[r] for r in plan['missing']) + '.')
    W, H = canvas
    layers = plan['layers']
    bgk = plan['bg']['kind']
    count = len(layers) + 1
    head = f'[{source}]fps={fps},'
    if abs(sar - 1) > 1e-3:
        head += f'scale=trunc(iw*{sar:.6f}/2)*2:ih:flags=lanczos,'
    head += 'setsar=1,' + (f'split={count}' + ''.join(f'[c{i}]' for i in range(count)))
    parts = [head]
    bg_in = f'c{count - 1}'
    if bgk == 'blur':
        if draft:
            parts.append(f'[{bg_in}]scale={W // 8}:{H // 8}:force_original_aspect_ratio=increase:flags=bilinear,crop={W // 8}:{H // 8},'
                         f'gblur=sigma=7,scale={W}:{H}:flags=bilinear[bg]')
        else:
            parts.append(f'[{bg_in}]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},gblur=sigma=28[bg]')
    else:
        color = _color(plan['bg']['color'] if bgk == 'color' else '#000000')
        parts.append(f'[{bg_in}]scale=64:36:flags=neighbor,scale={W}:{H}:flags=neighbor,drawbox=x=0:y=0:w={W}:h={H}:color={color}:t=fill[bg]')
    current = 'bg'
    for i, layer in enumerate(layers):
        cx, cy, cw, ch = layer['crop']
        ow, oh = layer['size']
        chain = f'[c{i}]crop={cw}:{ch}:{cx}:{cy},scale={ow}:{oh}:flags={"bilinear" if draft else "lanczos"},setsar=1'
        if layer.get('border'):
            chain += f',drawbox=x=0:y=0:w=iw:h=ih:color={_color(layer["border_color"])}:t={layer["border"]}'
        parts.append(chain + f'[l{i}]')
        last = i == len(layers) - 1
        label = 'ovr' if last else f'o{i}'
        px, py = layer['pos']
        parts.append(f'[{current}][l{i}]overlay={px}:{py}:format=auto[{label}]')
        current = label
    parts.append(f'[{current}]setsar=1,format=yuv420p[{out}]')
    return ';'.join(parts)


def summary(comp):
    """Texto curto para listas e relatórios."""
    if not comp:
        return 'enquadramento padrão'
    state = 'completa' if is_ready(comp) else 'incompleta (faltam: ' + ', '.join(ROLE_LABELS[r] for r in missing_roles(comp)) + ')'
    return f'{LAYOUTS[comp["layout"]]["label"]} · {state}'


# ───────────── presets reutilizáveis (arquivo local, sem banco nem rede) ─────────────

PRESET_FILE = 'layouts_reacao.json'
PRESET_LIMIT = 40
ASPECT_TOLERANCE = .03          # regiões guardadas só se aplicam a fontes com proporção até 3% diferente
BUILTIN = [
    dict(id='b:reacao_pequena', name='Reação — webcam pequena', layout='cam_compacta'),
    dict(id='b:reacao_grande', name='Reação — webcam grande', layout='cam_ampliada'),
    dict(id='b:foco_streamer', name='Reação — foco no streamer', layout='foco_reacao'),
    dict(id='b:gameplay', name='Gameplay — webcam flutuante', layout='cam_flutuante'),
    dict(id='b:podcast', name='Podcast — duas pessoas', layout='dueto'),
    dict(id='b:dupla', name='Dupla reação', layout='duas_cams'),
    dict(id='b:cinema', name='Cinema YouTube', layout='cinema'),
]


def _load(root):
    import json
    from pathlib import Path
    file = Path(root) / PRESET_FILE
    try:
        data = json.loads(file.read_text(encoding='utf-8'))
        items = data.get('items') if isinstance(data, dict) else None
        return [i for i in items if isinstance(i, dict) and i.get('id') and i.get('layout') in LAYOUTS] if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _store(root, items):
    from pathlib import Path
    from . import atomic
    atomic.write_json(Path(root) / PRESET_FILE, dict(version=1, items=items))


def compatible(item, source):
    """As regiões guardadas fazem sentido para esta fonte? (proporção próxima; senão só layout e ajustes valem)."""
    if not item.get('regions') or not item.get('source_aspect') or not source:
        return False
    return abs(source[0] / float(source[1]) / item['source_aspect'] - 1) <= ASPECT_TOLERANCE


def list_presets(root, source=None):
    out = [dict(item, builtin=True, regions=None, params=params_for(item['layout']), has_regions=False, compatible=False) for item in BUILTIN]
    for item in _load(root):
        out.append(dict(item, builtin=False, has_regions=bool(item.get('regions')), compatible=compatible(item, source)))
    return out


def _name(value):
    name = ' '.join(str(value or '').split())[:60]
    if not name:
        raise ValueError('Dê um nome ao layout.')
    return name


def save_preset(root, name, comp, source=None, with_regions=False):
    import time
    import uuid
    comp = clean(comp)
    if not comp:
        raise ValueError('Não há composição para salvar.')
    items = _load(root)
    name = _name(name)
    if len(items) >= PRESET_LIMIT:
        raise ValueError(f'Limite de {PRESET_LIMIT} layouts salvos. Exclua algum antes.')
    if any(i['name'].lower() == name.lower() for i in items):
        raise ValueError('Já existe um layout salvo com esse nome.')
    item = dict(id=uuid.uuid4().hex[:12], name=name, layout=comp['layout'], params=comp['params'], created=int(time.time()),
                regions=comp['regions'] if with_regions and comp['regions'] else None,
                source_aspect=round(source[0] / float(source[1]), 4) if with_regions and source else None)
    _store(root, items + [item])
    return item


def rename_preset(root, preset_id, name):
    items, name = _load(root), _name(name)
    if any(i['name'].lower() == name.lower() and i['id'] != preset_id for i in items):
        raise ValueError('Já existe um layout salvo com esse nome.')
    for item in items:
        if item['id'] == preset_id:
            item['name'] = name
            _store(root, items)
            return item
    raise ValueError('Layout salvo não encontrado.')


def duplicate_preset(root, preset_id):
    import uuid
    items = _load(root)
    if len(items) >= PRESET_LIMIT:
        raise ValueError(f'Limite de {PRESET_LIMIT} layouts salvos. Exclua algum antes.')
    for item in items:
        if item['id'] == preset_id:
            taken = {i['name'].lower() for i in items}
            name, n = item['name'] + ' (cópia)', 2
            while name.lower() in taken:
                name, n = f'{item["name"]} (cópia {n})', n + 1
            copy = dict(item, id=uuid.uuid4().hex[:12], name=name[:60])
            _store(root, items + [copy])
            return copy
    raise ValueError('Layout salvo não encontrado.')


def delete_preset(root, preset_id):
    items = _load(root)
    if not any(i['id'] == preset_id for i in items):
        raise ValueError('Layout salvo não encontrado.')
    _store(root, [i for i in items if i['id'] != preset_id])
