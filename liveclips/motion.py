"""Curvas de movimento do editor: easing e keyframes convertidos em expressões do FFmpeg.

A ideia de descrever animações como keyframes com easing e compilar cada trecho
em uma expressão `if(lt(t,...))` vem do editor open source ReaCut (licença MIT,
https://github.com/Xiangyu-CAS/rea-capcut). Aqui o código foi reescrito em Python,
com as curvas e os limites próprios do LiveClips. Veja THIRD_PARTY_NOTICES.md.
"""
import math

EASINGS = ('linear', 'ease_in', 'ease_out', 'ease_in_out', 'back_out')
MAX_ZOOM = 1.15


def _num(value):
    return format(round(float(value), 6), 'g')


def ease(name, x):
    """Versão em Python (testes e pré-visualização); espelha ease_expression."""
    x = max(0.0, min(1.0, float(x)))
    if name == 'ease_in':
        return x * x
    if name == 'ease_out':
        return 1 - (1 - x) * (1 - x)
    if name == 'ease_in_out':
        return x * x * (3 - 2 * x)
    if name == 'back_out':
        u = x - 1
        return 1 + 2.2 * u * u * u + 1.2 * u * u
    return x


def ease_expression(name, x):
    """Expressão do FFmpeg equivalente a `ease`, sem `pow` com base negativa."""
    if name == 'ease_in':
        return f'({x}*{x})'
    if name == 'ease_out':
        return f'(1-(1-{x})*(1-{x}))'
    if name == 'ease_in_out':
        return f'({x}*{x}*(3-2*{x}))'
    if name == 'back_out':
        return f'(1+2.2*({x}-1)*({x}-1)*({x}-1)+1.2*({x}-1)*({x}-1))'
    return f'({x})'


def keyframe_expression(points, clock='t'):
    """Interpola [(tempo, valor, easing)] em uma expressão de FFmpeg.

    O easing de cada ponto descreve o trecho que CHEGA até ele. Antes do primeiro
    ponto vale o primeiro valor e depois do último vale o último.
    """
    clean = []
    for point in points:
        time, value = float(point[0]), float(point[1])
        easing = point[2] if len(point) > 2 else 'linear'
        if not (math.isfinite(time) and math.isfinite(value)) or easing not in EASINGS:
            raise ValueError('Keyframe inválido.')
        clean.append((time, value, easing))
    clean.sort(key=lambda item: item[0])
    unique = [p for i, p in enumerate(clean) if i == len(clean) - 1 or clean[i + 1][0] != p[0]]
    if not unique:
        raise ValueError('Nenhum keyframe.')
    expression = _num(unique[-1][1])
    for index in range(len(unique) - 2, -1, -1):
        left, right = unique[index], unique[index + 1]
        span = max(1e-6, right[0] - left[0])
        progress = ease_expression(right[2], f'(({clock}-{_num(left[0])})/{_num(span)})')
        value = f'({_num(left[1])}+({_num(right[1] - left[1])})*{progress})'
        expression = f'if(lt({clock},{_num(right[0])}),{value},{expression})'
    return f'if(lt({clock},{_num(unique[0][0])}),{_num(unique[0][1])},{expression})'


def keyframe_value(points, t):
    """Mesma interpolação de keyframe_expression, calculada em Python."""
    ordered = sorted(((float(p[0]), float(p[1]), p[2] if len(p) > 2 else 'linear') for p in points),
                     key=lambda item: item[0])
    if t < ordered[0][0]:
        return ordered[0][1]
    for left, right in zip(ordered, ordered[1:]):
        if t < right[0]:
            span = max(1e-6, right[0] - left[0])
            return left[1] + (right[1] - left[1]) * ease(right[2], (t - left[0]) / span)
    return ordered[-1][1]


# Cada curva define: tempo de subida, easing da subida, tempo de descida, easing da descida.
PUNCH_CURVES = {
    'smooth': dict(attack=.28, rise='ease_in_out', release=.32, fall='ease_in_out'),
    'snap': dict(attack=.12, rise='ease_out', release=.38, fall='ease_in_out'),
    'pop': dict(attack=.2, rise='back_out', release=.3, fall='ease_in_out'),
    'beat': dict(attack=.08, rise='ease_out', release=.75, fall='ease_in_out'),
}


def punch_keyframes(point, curve='smooth', duration=None):
    """Keyframes de um punch: sai de 1.0, chega ao alvo, segura e volta."""
    spec = PUNCH_CURVES.get(point.get('curve') or curve, PUNCH_CURVES['smooth'])
    start, end, peak = float(point['start']), float(point['end']), float(point.get('zoom', 1.06))
    if not (math.isfinite(start + end + peak) and 0 <= start < end <= 90 and 1 < peak <= MAX_ZOOM):
        raise ValueError('Punch inválido.')
    length = end - start
    attack = min(spec['attack'], length * .45)
    release = min(spec['release'], length * .55)
    peak_at = start + attack
    fall_at = max(peak_at + .01, end - release)
    return [(start, 1.0, 'linear'), (peak_at, peak, spec['rise']),
            (fall_at, peak, 'linear'), (end, 1.0, spec['fall'])]


def valid_punches(punches, limit=24):
    result = []
    for point in (punches or [])[:limit]:
        try:
            punch_keyframes(point)
        except (KeyError, TypeError, ValueError):
            continue
        result.append(point)
    return sorted(result, key=lambda item: float(item['start']))


def zoom_expression(punches, fps, curve='smooth', push=None, duration=None, clock=None):
    """Expressão de zoom por quadro. Cada punch tem alvo e curva próprios.

    `push` = (zoom_final, duração) aplica um avanço lento e contínuo (estilo
    documental) somado aos punches. Retorna '' quando não há movimento algum.
    """
    punches = valid_punches(punches)
    if not punches and not push:
        return ''
    clock = clock or f'(on/{_num(fps)})'
    expression = '1'
    for point in reversed(punches):
        points = punch_keyframes(point, curve)
        window = f'between({clock},{_num(points[0][0])},{_num(points[-1][0])})'
        expression = f'if({window},{keyframe_expression(points, clock)},{expression})'
    if push:
        target, length = float(push[0]), max(1.0, float(push[1]))
        if not 1 < target <= MAX_ZOOM:
            raise ValueError('Avanço lento inválido.')
        slow = keyframe_expression([(0, 1.0, 'linear'), (length, target, 'ease_in_out')], clock)
        expression = f'min({MAX_ZOOM},({slow})+({expression})-1)'
    return expression


def zoom_at(punches, t, curve='smooth', push=None):
    """Valor de zoom esperado em t (Python); usado para conferir a expressão."""
    value = 1.0
    for point in valid_punches(punches):
        points = punch_keyframes(point, curve)
        if points[0][0] <= t <= points[-1][0]:
            value = keyframe_value(points, t)
            break
    if push:
        slow = keyframe_value([(0, 1.0, 'linear'), (max(1.0, float(push[1])), float(push[0]), 'ease_in_out')], t)
        value = min(MAX_ZOOM, slow + value - 1)
    return value


def zoompan_filter(punches, fps, width, height, curve='smooth', push=None, supersample=2):
    """Filtro zoompan centralizado. O supersample reduz o tremor de subpixel."""
    expression = zoom_expression(punches, fps, curve, push)
    if not expression:
        return ''
    if supersample == int(supersample):
        factor = f'iw*{int(supersample)}:ih*{int(supersample)}'
    else:
        factor = f'trunc(iw*{supersample}/2)*2:trunc(ih*{supersample}/2)*2'
    pre = f'scale={factor}:flags=bicubic,' if supersample > 1 else ''
    return (f",{pre}zoompan=z='{expression}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
            f":d=1:s={width}x{height}:fps={fps}")
