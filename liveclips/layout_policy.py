"""Política de composição adaptativa (F09, F10, R09, R11, R12).

Perfil da webcam em coordenadas normalizadas COM a resolução de origem; decisão de layout com permanência mínima e
histerese (nunca oscila a cada frame); suavização de rastreamento com limite de velocidade e aceleração; volta ao
perfil manual quando a confiança cai. Este módulo decide e valida; o render ainda aplica UM layout por clipe
(ver capabilities R12) — a lista de trechos é gravada no plano para revisão e para o próximo marco do render."""
import math

PROFILE_VERSION = 2
BASE = 'cam_top'
ACTION_LAYOUT = 'game_pip'      # jogo dominante com a câmera pequena
REACTION_LAYOUT = 'cam_full'    # close na reação
MIN_DWELL = 2.0                 # s de permanência mínima antes de outra troca
COOLDOWN = 1.2                  # s no layout base entre duas trocas
MIN_CONFIDENCE = .55
MAX_SWITCHES_PER_10S = 2


# ───────────── perfil e regiões ─────────────

def normalize_rect(rect_px, width, height):
    x, y, w, h = (float(v) for v in rect_px)
    if width <= 0 or height <= 0 or w <= 0 or h <= 0:
        raise ValueError('Retângulo ou resolução inválidos.')
    rect = [x / width, y / height, w / width, h / height]
    if rect[0] < 0 or rect[1] < 0 or rect[0] + rect[2] > 1.0001 or rect[1] + rect[3] > 1.0001:
        raise ValueError('O retângulo passa dos limites da imagem.')
    return [round(v, 5) for v in rect]


def profile_region(camera_rect, source_size, face_rect=None, confirmed=True, version=PROFILE_VERSION):
    """Registro persistente da webcam: normalizado + resolução em que foi marcado + confirmação do usuário."""
    for v in camera_rect:
        if not 0 <= float(v) <= 1:
            raise ValueError('As coordenadas da câmera precisam estar normalizadas (0 a 1).')
    record = dict(version=version, camera=[float(v) for v in camera_rect], source=dict(width=int(source_size[0]), height=int(source_size[1])),
                  confirmed_by_user=bool(confirmed))
    if face_rect:
        record['face_in_camera'] = [float(v) for v in face_rect]       # relativo à webcam, não à tela
    return record


def to_pixels(record, width, height):
    """Região da webcam na resolução ATUAL da live. Proporcional: mudar de 720p para 1080p não desloca o recorte."""
    cx, cy, cw, ch = record['camera']
    box = dict(x=round(cx * width), y=round(cy * height), w=round(cw * width), h=round(ch * height))
    box['x'], box['y'] = min(box['x'], width - 2), min(box['y'], height - 2)
    box['w'], box['h'] = max(2, min(box['w'], width - box['x'])), max(2, min(box['h'], height - box['y']))
    face = None
    if record.get('face_in_camera'):
        fx, fy, fw, fh = record['face_in_camera']
        face = dict(x=box['x'] + round(fx * box['w']), y=box['y'] + round(fy * box['h']), w=round(fw * box['w']), h=round(fh * box['h']))
    return dict(camera=box, face=face, aspect=round(box['w'] / box['h'], 4))


def overlap(a, b):
    """Fração de `a` coberta por `b` (retângulos x,y,w,h)."""
    ax, ay, aw, ah = a['x'], a['y'], a['w'], a['h']
    bx, by, bw, bh = b['x'], b['y'], b['w'], b['h']
    w = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    h = max(0, min(ay + ah, by + bh) - max(ay, by))
    return (w * h) / (aw * ah) if aw * ah else 0.0


def protected_hits(box, protected, limit=.02):
    """Quais regiões protegidas (rosto, mira, alvo, placar, texto do jogo) um elemento cobriria (mais de `limit`)."""
    return [p['name'] for p in protected if overlap(p, box) > limit]


# ───────────── decisão de layout ─────────────

def choose_layouts(events, duration, base=BASE, min_dwell=MIN_DWELL, cooldown=COOLDOWN):
    """`events`: dicts(time, kind 'acao'|'reacao', confidence, dur). Devolve trechos [{start,end,layout,why}] cobrindo o clipe.

    Regras: abaixo de MIN_CONFIDENCE o layout base permanece; nenhuma troca dura menos que `min_dwell`; entre duas trocas há
    `cooldown` no layout base; no máximo 2 trocas por janela de 10 s; ação e reação que se sobrepõem ficam com a mais confiável."""
    duration = float(duration)
    wanted = []
    parsed = []
    for ev in events or []:
        try:
            parsed.append((float(ev['time']), float(ev.get('confidence', 0)), ev))
        except (KeyError, TypeError, ValueError):
            continue
    for t, conf, ev in sorted(parsed, key=lambda x: x[0]):
        if conf < MIN_CONFIDENCE or not 0 <= t < duration:
            continue
        layout = ACTION_LAYOUT if ev.get('kind') == 'acao' else REACTION_LAYOUT if ev.get('kind') == 'reacao' else None
        if not layout:
            continue
        length = max(min_dwell, float(ev.get('dur', min_dwell)))
        wanted.append(dict(start=max(0.0, t - .15), end=min(duration, t + length), layout=layout, confidence=conf, kind=ev['kind']))
    chosen = []
    for item in wanted:
        if chosen and item['start'] < chosen[-1]['end'] + cooldown:
            last = chosen[-1]
            if item['layout'] == last['layout']:
                last['end'] = max(last['end'], item['end'])       # mesma troca: estende
            elif item['confidence'] > last['confidence'] + .1 and item['start'] >= last['start'] + min_dwell:
                last['end'] = item['start']
                chosen.append(item)
            continue
        chosen.append(item)
    chosen = [c for c in chosen if c['end'] - c['start'] >= min_dwell - .01]
    # limite de trocas por janela de 10 s
    limited = []
    for item in chosen:
        recent = [x for x in limited if item['start'] - x['start'] < 10]
        if len(recent) >= MAX_SWITCHES_PER_10S:
            continue
        limited.append(item)
    out, cursor = [], 0.0
    for item in limited:
        if item['start'] > cursor:
            out.append(dict(start=round(cursor, 3), end=round(item['start'], 3), layout=base, why='layout estável do perfil'))
        why = ('ação decisiva do jogo: jogo dominante' if item['kind'] == 'acao' else 'reação observável: close na webcam')
        out.append(dict(start=round(item['start'], 3), end=round(item['end'], 3), layout=item['layout'],
                        why=f'{why} (confiança {item["confidence"]:.2f})'))
        cursor = item['end']
    if cursor < duration:
        out.append(dict(start=round(cursor, 3), end=round(duration, 3), layout=base, why='layout estável do perfil'))
    return out or [dict(start=0.0, end=round(duration, 3), layout=base, why='layout estável do perfil')]


def switches(segments):
    return sum(1 for a, b in zip(segments, segments[1:]) if a['layout'] != b['layout'])


# ───────────── rastreamento suave ─────────────

def smooth_track(points, max_speed=.35, max_accel=1.2, scene_cuts=(), min_conf=.5, fallback=(.5, .5), tolerance=.02):
    """Suaviza (x, y) normalizados por quadro. `points`: dicts(time, x, y, confidence).

    - zona de tolerância: movimento menor que `tolerance` não move o recorte;
    - velocidade máxima (largura/s) e aceleração máxima (largura/s²);
    - em mudança de cena reinicia na posição nova;
    - confiança baixa: congela e, se durar mais de 1 s, volta ao enquadramento do perfil manual (`fallback`)."""
    out, pos, vel, last_t, low_since = [], None, (0.0, 0.0), None, None
    cuts = sorted(scene_cuts)
    for p in sorted(points, key=lambda q: q['time']):
        t, conf = float(p['time']), float(p.get('confidence', 1))
        reset = last_t is None or any(last_t < c <= t for c in cuts)
        dt = 0.0 if reset else max(1e-3, t - last_t)
        if conf < min_conf:
            low_since = t if low_since is None else low_since
            if t - low_since > 1.0:
                pos, vel = tuple(fallback), (0.0, 0.0)
            out.append(dict(time=t, x=(pos or fallback)[0], y=(pos or fallback)[1], state='fallback' if t - low_since > 1.0 else 'congelado'))
            last_t = t
            continue
        low_since = None
        target = (float(p['x']), float(p['y']))
        if pos is None or reset:
            pos, vel = target, (0.0, 0.0)
        else:
            new_pos, new_vel = [], []
            for axis in (0, 1):
                error = target[axis] - pos[axis]
                if abs(error) < tolerance:
                    wanted_v = 0.0
                else:
                    wanted_v = max(-max_speed, min(max_speed, error / max(dt, .05)))
                dv = max(-max_accel * dt, min(max_accel * dt, wanted_v - vel[axis]))
                v = vel[axis] + dv
                nx = pos[axis] + v * dt
                if (error > 0 and nx > target[axis]) or (error < 0 and nx < target[axis]):
                    nx, v = target[axis], 0.0
                new_pos.append(nx)
                new_vel.append(v)
            pos, vel = tuple(new_pos), tuple(new_vel)
        out.append(dict(time=t, x=round(pos[0], 5), y=round(pos[1], 5), state='ok'))
        last_t = t
    return out


def max_step(track):
    """Maior deslocamento entre amostras consecutivas (para conferir estabilidade)."""
    return max((math.hypot(b['x'] - a['x'], b['y'] - a['y']) for a, b in zip(track, track[1:])), default=0.0)


def to_plan_events(segments, ticks_fn):
    return [dict(start=ticks_fn(s['start']), end=ticks_fn(s['end']), recipe_id=s['layout'], profile_ref=s['why']) for s in segments]
