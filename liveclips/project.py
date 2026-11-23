"""Projeto de edição do clipe: o que o usuário muda à mão por cima do plano automático.

Tudo aqui usa segundos do corte, contados a partir do início do clipe e ANTES de remover
pausas ou trechos cortados (a mesma convenção de `edit_plan`). O projeto é salvo junto do
candidato (`data['project']`), entra na assinatura do render e nunca altera os originais.
"""
import math
import re

from . import motion

LIMITS = dict(cuts=40, zooms=30, titles=12, lines=240, text=140, sfx=16, speeds=40, freezes=8, overlays=10, replays=4)
RAMP_STEPS = 8
REPLAY_RATE = (.25, 2.0)
REPLAY_LENGTH = (.4, 8.0)
LAYOUTS = ('cam_top', 'split', 'game_pip', 'cam_full', 'fit', 'fill')
PIP_CORNERS = ('tr', 'tl', 'br', 'bl')
FORMATS = ('1x1', '4x5', '16x9')
SPEED_RANGE = (.25, 4.0)
FREEZE_RANGE = (.3, 3.0)
ZOOM_CURVES = tuple(motion.PUNCH_CURVES)
TITLE_STYLES = ('big', 'bar', 'top')
TITLE_POSITIONS = ('top', 'center', 'bottom')
HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')


def empty():
    return dict(version=1, style=None, cuts=[], zooms=[], titles=[], music=None, grade=None, teaser=None,
                voice=dict(clean=False, mode='light'), sfx=[], layout=None, speeds=[], freezes=[], overlays=[], replays=[], formats=[],
                captions=dict(enabled=True, style=None, size=None, margin=None, color=None, lines=None))


def _number(value, low, high, name, default=None):
    if value is None or value == '':
        if default is None:
            raise ValueError(f'{name} é obrigatório.')
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} precisa ser um número.') from None
    if not math.isfinite(number):
        raise ValueError(f'{name} precisa ser um número válido.')
    return max(low, min(high, number))


def _text(value, limit=LIMITS['text']):
    return ' '.join(str(value or '').split())[:limit]


def _span(item, duration, minimum, name):
    start = _number(item.get('start'), 0, duration, name + ' (início)')
    end = _number(item.get('end'), 0, duration, name + ' (fim)')
    if end - start < minimum:
        raise ValueError(f'{name}: a duração mínima é {minimum:g} s.')
    return round(start, 3), round(end, 3)


def merge_cuts(cuts):
    merged = []
    for cut in sorted(cuts, key=lambda c: (c['start'], c['end'])):
        if merged and cut['start'] <= merged[-1]['end'] + .02:
            merged[-1]['end'] = max(merged[-1]['end'], cut['end'])
        else:
            merged.append(dict(cut))
    return merged


def retext_line(line):
    """Reparte os tempos das palavras quando o texto mudou; mantém os originais quando não mudou."""
    tokens = line['text'].split()
    words = line.get('words') or []
    if words and [str(w['word']).strip() for w in words] == tokens:
        return words
    if not tokens:
        return []
    start, end = float(line['start']), float(line['end'])
    weights = [max(1, len(re.sub(r'\W', '', t))) + 1 for t in tokens]
    total, cursor, result = float(sum(weights)), start, []
    for token, weight in zip(tokens, weights):
        step = (end - start) * weight / total
        result.append(dict(start=round(cursor, 3), end=round(cursor + step, 3), word=token))
        cursor += step
    return result


def clean(raw, duration, music_exists=None, image_exists=None):
    """Valida o projeto vindo do navegador. Levanta ValueError com mensagem em português."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError('Projeto de edição inválido.')
    duration = float(duration)
    result = empty()
    style = raw.get('style')
    if style:
        from .editing import EDITOR_PRESETS
        if style not in EDITOR_PRESETS:
            raise ValueError('Estilo de edição desconhecido.')
        result['style'] = style
    cuts = raw.get('cuts') or []
    if not isinstance(cuts, list) or len(cuts) > LIMITS['cuts']:
        raise ValueError(f'Use no máximo {LIMITS["cuts"]} cortes.')
    parsed = []
    for item in cuts:
        a, b = _span(item, duration, .1, 'Corte')
        parsed.append(dict(start=a, end=b))
    result['cuts'] = merge_cuts(parsed)
    if sum(c['end'] - c['start'] for c in result['cuts']) > duration - 1:
        raise ValueError('Os cortes removeriam quase todo o clipe. Sobre pelo menos 1 segundo.')
    zooms = raw.get('zooms') or []
    if not isinstance(zooms, list) or len(zooms) > LIMITS['zooms']:
        raise ValueError(f'Use no máximo {LIMITS["zooms"]} zooms.')
    for index, item in enumerate(zooms):
        a, b = _span(item, duration, .4, 'Zoom')
        curve = item.get('curve') or 'smooth'
        if curve not in ZOOM_CURVES:
            raise ValueError('Curva de zoom desconhecida.')
        result['zooms'].append(dict(id=_text(item.get('id'), 40) or f'z{index}', start=a, end=b,
                                    zoom=round(_number(item.get('zoom'), 1.02, motion.MAX_ZOOM, 'Zoom', 1.08), 3), curve=curve))
    result['zooms'].sort(key=lambda z: z['start'])
    titles = raw.get('titles') or []
    if not isinstance(titles, list) or len(titles) > LIMITS['titles']:
        raise ValueError(f'Use no máximo {LIMITS["titles"]} títulos.')
    for index, item in enumerate(titles):
        text = _text(item.get('text'), 90)
        if not text:
            continue
        a, b = _span(item, duration, .5, 'Título')
        style_name = item.get('style') or 'big'
        position = item.get('position') or ('top' if style_name != 'bar' else 'top')
        color = str(item.get('color') or '#FFFFFF')
        if style_name not in TITLE_STYLES or position not in TITLE_POSITIONS or not HEX.match(color):
            raise ValueError('Título com estilo, posição ou cor inválidos.')
        result['titles'].append(dict(id=_text(item.get('id'), 40) or f't{index}', text=text, start=a, end=b,
                                     style=style_name, position=position, color='#' + HEX.match(color).group(1).upper()))
    result['titles'].sort(key=lambda t: t['start'])
    captions = raw.get('captions') or {}
    if not isinstance(captions, dict):
        raise ValueError('Legendas inválidas.')
    out = result['captions']
    out['enabled'] = bool(captions.get('enabled', True))
    if captions.get('style'):
        from .captions import STYLE_NAMES
        if captions['style'] not in STYLE_NAMES:
            raise ValueError('Estilo de legenda desconhecido.')
        out['style'] = captions['style']
    if captions.get('size') not in (None, ''):
        out['size'] = int(_number(captions['size'], 24, 68, 'Tamanho da legenda'))
    if captions.get('margin') not in (None, ''):
        out['margin'] = int(_number(captions['margin'], 130, 500, 'Distância da legenda'))
    if captions.get('color'):
        if not HEX.match(str(captions['color'])):
            raise ValueError('Cor de legenda inválida.')
        out['color'] = '#' + HEX.match(captions['color']).group(1).upper()
    lines = captions.get('lines')
    if lines is not None:
        if not isinstance(lines, list) or len(lines) > LIMITS['lines']:
            raise ValueError('Linhas de legenda inválidas.')
        out['lines'] = []
        for item in lines:
            text = _text(item.get('text'), 160)
            if not text:
                continue
            a, b = _span(item, duration, .15, 'Legenda')
            line = dict(start=a, end=b, text=text, words=item.get('words') if isinstance(item.get('words'), list) else [])
            line['words'] = [dict(start=round(float(w['start']), 3), end=round(float(w['end']), 3), word=str(w['word'])[:40])
                             for w in retext_line(line)]
            out['lines'].append(line)
        out['lines'].sort(key=lambda l: l['start'])
    music = raw.get('music')
    if music:
        if not isinstance(music, dict) or not music.get('id'):
            raise ValueError('Música inválida.')
        if music_exists is not None and not music_exists(music['id']):
            raise ValueError('Essa música não está na biblioteca.')
        result['music'] = dict(id=str(music['id']), start=round(_number(music.get('start'), 0, 3600, 'Início da música', 0.0) or 0.0, 2),
                               volume=round(_number(music.get('volume'), .02, .6, 'Volume da música', .14), 3),
                               fade_in=round(_number(music.get('fade_in'), 0, 8, 'Entrada gradual', .6), 2),
                               fade_out=round(_number(music.get('fade_out'), 0, 8, 'Saída gradual', 1.2), 2),
                               duck=bool(music.get('duck', True)), authorized=bool(music.get('authorized', False)))
    teaser = raw.get('teaser')
    if teaser:
        a, b = _span(teaser, duration, .8, 'Abertura')
        if b - a > 4.5:
            raise ValueError('A abertura (teaser) pode ter no máximo 4,5 segundos.')
        result['teaser'] = dict(start=a, end=b)
    voice = raw.get('voice') or {}
    voice = voice if isinstance(voice, dict) else {}
    result['voice'] = dict(clean=bool(voice.get('clean')), mode='neural' if voice.get('mode') == 'neural' else 'light')
    effects = raw.get('sfx') or []
    if not isinstance(effects, list) or len(effects) > LIMITS['sfx']:
        raise ValueError(f'Use no máximo {LIMITS["sfx"]} efeitos sonoros.')
    from .sfx import EFFECTS
    for index, item in enumerate(effects):
        if item.get('kind') not in EFFECTS:
            raise ValueError('Efeito sonoro desconhecido.')
        result['sfx'].append(dict(id=_text(item.get('id'), 40) or f's{index}', kind=item['kind'],
                                  at=round(_number(item.get('at'), 0, duration, 'Posição do efeito'), 3),
                                  volume=round(_number(item.get('volume'), .05, 1.0, 'Volume do efeito', .6), 3)))
    result['sfx'].sort(key=lambda e: e['at'])
    layout = raw.get('layout')
    if layout:
        if not isinstance(layout, dict) or layout.get('mode') not in LAYOUTS:
            raise ValueError('Layout desconhecido.')
        corner = layout.get('pip') or 'tr'
        if corner not in PIP_CORNERS:
            raise ValueError('Canto da câmera pequena inválido.')
        result['layout'] = dict(mode=layout['mode'], pip=corner,
                                focus=round(_number(layout.get('focus'), 0, 1, 'Foco do quadro', .5), 3),
                                pip_size=round(_number(layout.get('pip_size'), .2, .5, 'Tamanho da câmera pequena', .36), 3))
    speeds = raw.get('speeds') or []
    if not isinstance(speeds, list) or len(speeds) > LIMITS['speeds']:
        raise ValueError(f'Use no máximo {LIMITS["speeds"]} trechos com velocidade alterada.')
    for index, item in enumerate(speeds):
        a, b = _span(item, duration, .4, 'Velocidade')
        rate = round(_number(item.get('rate'), SPEED_RANGE[0], SPEED_RANGE[1], 'Velocidade', 1.0), 3)
        end_rate = item.get('rate_to')
        if end_rate in (None, '') or abs(float(end_rate) - rate) < .01:
            result['speeds'].append(dict(id=_text(item.get('id'), 40) or f'v{index}', start=a, end=b, rate=rate))
            continue
        # Rampa de velocidade: vira degraus curtos de velocidade constante (o render aceita só trechos constantes).
        final = round(_number(end_rate, SPEED_RANGE[0], SPEED_RANGE[1], 'Velocidade final', rate), 3)
        result['speeds'].extend(ramp_steps(item.get('id') or f'v{index}', a, b, rate, final))
    result['speeds'].sort(key=lambda v: v['start'])
    for before, after in zip(result['speeds'], result['speeds'][1:]):
        if after['start'] < before['end'] - .001:
            raise ValueError('Dois trechos de velocidade não podem se sobrepor.')
    if len(result['speeds']) > LIMITS['speeds']:
        raise ValueError(f'Use no máximo {LIMITS["speeds"]} trechos com velocidade alterada (rampas contam por degrau).')
    replays = raw.get('replays') or []
    if not isinstance(replays, list) or len(replays) > LIMITS['replays']:
        raise ValueError(f'Use no máximo {LIMITS["replays"]} replays.')
    for index, item in enumerate(replays):
        a, b = _span(item, duration, REPLAY_LENGTH[0], 'Replay')
        if b - a > REPLAY_LENGTH[1]:
            raise ValueError(f'O replay pode ter no máximo {REPLAY_LENGTH[1]:g} segundos de fonte.')
        rate = round(_number(item.get('rate'), REPLAY_RATE[0], REPLAY_RATE[1], 'Velocidade do replay', 1.0), 3)
        after = round(_number(item.get('after'), b, duration, 'Posição do replay', b), 3)
        result['replays'].append(dict(id=_text(item.get('id'), 40) or f'r{index}', start=a, end=b, rate=rate, after=after,
                                      mute=bool(item.get('mute', rate != 1.0))))
    result['replays'].sort(key=lambda r: r['after'])
    freezes = raw.get('freezes') or []
    if not isinstance(freezes, list) or len(freezes) > LIMITS['freezes']:
        raise ValueError(f'Use no máximo {LIMITS["freezes"]} congelamentos de imagem.')
    for index, item in enumerate(freezes):
        result['freezes'].append(dict(id=_text(item.get('id'), 40) or f'f{index}',
                                      at=round(_number(item.get('at'), 0, duration, 'Posição do congelamento'), 3),
                                      duration=round(_number(item.get('duration'), FREEZE_RANGE[0], FREEZE_RANGE[1],
                                                             'Duração do congelamento', 1.0), 2)))
    result['freezes'].sort(key=lambda f: f['at'])
    overlays = raw.get('overlays') or []
    if not isinstance(overlays, list) or len(overlays) > LIMITS['overlays']:
        raise ValueError(f'Use no máximo {LIMITS["overlays"]} imagens por clipe.')
    for index, item in enumerate(overlays):
        image = str(item.get('image') or '')
        if not re.match(r'^[a-f0-9]{16}$', image):
            raise ValueError('Imagem inválida.')
        if image_exists is not None and not image_exists(image):
            raise ValueError('Essa imagem não está mais na biblioteca.')
        a, b = _span(item, duration, .3, 'Imagem')
        result['overlays'].append(dict(id=_text(item.get('id'), 40) or f'i{index}', image=image, start=a, end=b,
                                       x=round(_number(item.get('x'), 0, 1, 'Posição horizontal da imagem', .5), 3),
                                       y=round(_number(item.get('y'), 0, 1, 'Posição vertical da imagem', .4), 3),
                                       scale=round(_number(item.get('scale'), .08, 1.0, 'Tamanho da imagem', .45), 3),
                                       opacity=round(_number(item.get('opacity'), .1, 1.0, 'Opacidade da imagem', 1.0), 3)))
        from . import keying
        for field, check in (('key', keying.check_key), ('mask', keying.check_mask)):
            value = check(item.get(field))
            if value:
                result['overlays'][-1][field] = value
        blend = keying.check_blend(item.get('blend'))
        if blend != 'normal':
            result['overlays'][-1]['blend'] = blend
    result['overlays'].sort(key=lambda o: o['start'])
    motion_raw = raw.get('motion') or []
    if not isinstance(motion_raw, list) or len(motion_raw) > 4:
        raise ValueError('Use no máximo 4 gráficos animados por corte.')
    from . import graphics2d as motionlib
    for entry in motion_raw:      # a chave só existe quando há gráficos (projetos antigos ficam idênticos)
        try:
            result.setdefault('motion', []).append(motionlib.clean(entry, duration))
        except motionlib.MotionError as exc:
            raise ValueError(str(exc)) from None
    formats = raw.get('formats') or []
    if not isinstance(formats, list) or any(f not in FORMATS for f in formats):
        raise ValueError('Formato extra desconhecido. Use 1x1, 4x5 ou 16x9.')
    result['formats'] = [f for f in FORMATS if f in formats]
    grade = raw.get('grade')
    if grade:
        if not isinstance(grade, dict):
            raise ValueError('Cor inválida.')
        result['grade'] = dict(contrast=round(_number(grade.get('contrast'), .8, 1.4, 'Contraste', 1.0), 3),
                               saturation=round(_number(grade.get('saturation'), .5, 1.6, 'Saturação', 1.0), 3),
                               brightness=round(_number(grade.get('brightness'), -.2, .2, 'Brilho', 0.0), 3))
    return result


def ramp_steps(base_id, start, end, rate_from, rate_to, steps=RAMP_STEPS):
    """Divide uma rampa linear de velocidade em `steps` degraus constantes (taxa no meio de cada degrau)."""
    width = (end - start) / steps
    result = []
    for k in range(steps):
        mid = (k + .5) / steps
        rate = rate_from + (rate_to - rate_from) * mid
        result.append(dict(id=f'{_text(base_id, 30)}~{k}', start=round(start + k * width, 3), end=round(start + (k + 1) * width, 3),
                           rate=round(max(SPEED_RANGE[0], min(SPEED_RANGE[1], rate)), 3), ramp=_text(base_id, 30)))
    return result


def ramp_duration(start, end, rate_from, rate_to):
    """Duração de saída exata de uma rampa linear: integral de 1/v(s) em [start, end]."""
    span = end - start
    if abs(rate_to - rate_from) < 1e-9:
        return span / rate_from
    return span * math.log(rate_to / rate_from) / (rate_to - rate_from)


def cuts_of(project):
    return [dict(start=c['start'], end=c['end'], kind='manual', id=f'manual:{c["start"]:.3f}:{c["end"]:.3f}')
            for c in (project or {}).get('cuts', [])]


def zooms_of(project, duration):
    result = []
    for item in (project or {}).get('zooms', []):
        a, b = max(0.0, float(item['start'])), min(float(duration), float(item['end']))
        if b - a >= .3:
            result.append(dict(start=round(a, 3), end=round(b, 3), zoom=float(item['zoom']), curve=item.get('curve', 'smooth'),
                               reason='Zoom manual', decision_id='project:' + str(item['id'])))
    return result


def title_color_bgr(color):
    value = HEX.match(color or '#FFFFFF').group(1)
    return value[4:6] + value[2:4] + value[0:2]


def project_of(candidate):
    value = (candidate.get('data') or {}).get('project')
    return value if isinstance(value, dict) else None


def rebase(project, delta, duration):
    """Reposiciona o projeto quando o início do clipe muda. `delta` = início antigo − início novo (segundos).

    Itens que ficam fora do novo intervalo são descartados; os que ficam parcialmente dentro são aparados.
    A música não depende do início do clipe e não muda."""
    if not isinstance(project, dict):
        return project
    duration = float(duration)

    def move(item, minimum):
        a = round(max(0.0, float(item['start']) + delta), 3)
        b = round(min(duration, float(item['end']) + delta), 3)
        if b - a < minimum:
            return None
        return dict(item, start=a, end=b)

    result = dict(project)
    for key, minimum in (('cuts', .1), ('zooms', .4), ('titles', .5)):
        moved = [move(item, minimum) for item in project.get(key) or []]
        result[key] = [item for item in moved if item]
    for key, minimum in (('speeds', .4), ('overlays', .3)):
        moved = [move(item, minimum) for item in project.get(key) or []]
        result[key] = [item for item in moved if item]
    replays = []
    for item in project.get('replays') or []:
        moved = move(item, .4)
        if moved:
            replays.append(dict(moved, after=round(min(duration, max(moved['end'], float(item.get('after', item['end'])) + delta)), 3)))
    result['replays'] = replays
    result['freezes'] = [dict(f, at=round(float(f['at']) + delta, 3)) for f in project.get('freezes') or []
                         if 0 <= float(f['at']) + delta <= duration]
    teaser = project.get('teaser')
    result['teaser'] = move(teaser, .8) if teaser else None
    result['sfx'] = [dict(e, at=round(float(e['at']) + delta, 3)) for e in project.get('sfx') or []
                     if 0 <= float(e['at']) + delta <= duration]
    captions = dict(project.get('captions') or {})
    if captions.get('lines') is not None:
        lines = []
        for line in captions['lines']:
            item = move(line, .15)
            if not item:
                continue
            item['words'] = [dict(w, start=round(float(w['start']) + delta, 3), end=round(float(w['end']) + delta, 3))
                             for w in line.get('words') or []]
            lines.append(item)
        captions['lines'] = lines
    result['captions'] = captions
    return result
