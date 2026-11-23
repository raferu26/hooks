"""Enquadramento que segue quem fala (podcast, entrevista, conversa com 2–3 pessoas na mesma imagem).

Como funciona (tudo local, só OpenCV): acha os rostos, agrupa em "lugares" (cada pessoa que fica no mesmo canto)
e mede o movimento da região da boca de cada lugar ao longo do tempo. Quem mexe mais a boca naquele momento é
quem fala. A troca só acontece com vantagem clara, mantida por alguns instantes, e cada fala dura pelo menos
2,5 s (evita ficar pulando). A transição entre pessoas é um deslize rápido, quase um corte.

LIMITES (não verificados em podcast real): não usa o áudio para saber quem fala; risada, mastigação, gesto com a
mão na boca ou quem ouve mexendo a boca podem enganar; rosto de lado ou muito pequeno não é detectado; com mais
de 3 pessoas ou câmera em movimento o plano é descartado (volta ao enquadramento comum).
"""
import statistics

STEP = .25
MIN_TURN = 2.5
SWITCH_RATIO = 1.4
SWITCH_HOLD = 2      # amostras seguidas (≈ .5 s) com vantagem antes de trocar (a troca é antecipada para o começo da fala)
MIN_ACTIVITY = .6    # abaixo disso ninguém está claramente falando: mantém quem estava
TRANSITION = .35
MAX_SEATS = 3
MIN_SHARE = .25      # um "lugar" precisa aparecer em pelo menos 25% das amostras


def seats_from(observations, tolerance=.12, min_share=MIN_SHARE, limit=MAX_SEATS):
    """observations: [[(cx, cy, w, h), ...] por amostra, tudo normalizado 0–1]. → lugares ordenados da esquerda p/ direita."""
    points = sorted((face[0], face) for frame in observations for face in frame)
    clusters = []
    for x, face in points:
        if clusters and x - clusters[-1][-1][0] <= tolerance:
            clusters[-1].append((x, face))
        else:
            clusters.append([(x, face)])
    total = max(1, len(observations))
    seats = []
    for cluster in clusters:
        if len(cluster) / total < min_share:
            continue
        faces = [f for _, f in cluster]
        seats.append(dict(x=statistics.median(f[0] for f in faces), y=statistics.median(f[1] for f in faces),
                          w=statistics.median(f[2] for f in faces), h=statistics.median(f[3] for f in faces), n=len(cluster)))
    seats.sort(key=lambda s: -s['n'])
    return sorted(seats[:limit], key=lambda s: s['x'])


def smooth(values, width=3):
    out = []
    for i in range(len(values)):
        window = values[max(0, i - width + 1):i + 1]
        out.append(sum(window) / len(window))
    return out


def choose(activity, step=STEP, min_turn=MIN_TURN, ratio=SWITCH_RATIO, hold=SWITCH_HOLD, min_activity=MIN_ACTIVITY):
    """activity: {lugar: [atividade da boca por amostra]}. → [(início, fim, lugar)] cobrindo toda a duração."""
    seats = list(activity)
    count = min(len(v) for v in activity.values())
    if not seats or not count:
        return []
    base = {s: sorted(activity[s][:count])[int(.15 * (count - 1))] for s in seats}  # nível de "boca parada" de cada pessoa (percentil 15)
    level = {s: smooth([max(0.0, a - base[s]) for a in activity[s][:count]]) for s in seats}
    first = max(seats, key=lambda s: sum(level[s][:max(1, int(2 / step))]))
    current, last_switch, pending, streak = first, 0, None, 0
    owners = []
    for i in range(count):
        best = max(seats, key=lambda s: level[s][i])
        wins = (best != current and level[best][i] >= min_activity and level[best][i] >= ratio * level[current][i] + .05)
        if wins and (i - last_switch) * step >= min_turn:
            streak = streak + 1 if pending == best else 1
            pending = best
            if streak >= hold:
                # a troca vale desde o começo da vantagem (menos uma amostra do atraso da suavização)
                for j in range(max(last_switch + 1, i - streak), i):
                    owners[j] = best
                current, last_switch, pending, streak = best, i, None, 0
        else:
            pending, streak = None, 0
        owners.append(current)
    turns = []
    for i, seat in enumerate(owners):
        if turns and turns[-1][2] == seat:
            turns[-1][1] = (i + 1) * step
        else:
            turns.append([i * step, (i + 1) * step, seat])
    return [tuple(t) for t in turns]


def plan_from_turns(turns, seats, duration):
    """Pontos do plano de enquadramento: segura em cada pessoa e desliza rápido na troca."""
    points = []
    for index, (a, b, seat) in enumerate(turns):
        a, b = round(a, 3), round(min(duration, b), 3)
        if index == len(turns) - 1:
            b = round(duration, 3)
        x = round(seats[seat]['x'], 5)
        if index < len(turns) - 1 and b - a > TRANSITION + .3:
            points.append(dict(start=a, end=round(b - TRANSITION, 3), face=True, x=x, scene=False))
            points.append(dict(start=round(b - TRANSITION, 3), end=b, face=True, x=x, scene=False))
        else:
            points.append(dict(start=a, end=b, face=True, x=x, scene=False))
    return points


def speaker_plan(source, offset, duration, info, cascade_path=None, step=STEP):
    """Plano de enquadramento seguindo quem fala, ou [] quando não é uma cena de 2–3 pessoas confiável."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if info['width'] / info['height'] <= 9 / 16 + .02 or duration < 2 * MIN_TURN:
        return []
    cascade = cv2.CascadeClassifier(cascade_path or (cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'))
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened() or cascade.empty():
        return []
    grays, observations = [], []
    try:
        t = 0.0
        while t < duration and len(grays) < 600:
            cap.set(cv2.CAP_PROP_POS_MSEC, (offset + t) * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            scale = min(1.0, 640 / max(1, width))
            small = cv2.resize(frame, (max(2, int(width * scale)), max(2, int(height * scale))))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(max(24, int(45 * scale)),) * 2)
            H, W = gray.shape
            observations.append([((x + w / 2) / W, (y + h / 2) / H, w / W, h / H) for x, y, w, h in faces])
            grays.append(gray)
            t += step
    finally:
        cap.release()
    if len(grays) < 2 * MIN_TURN / step:
        return []
    seats = seats_from(observations)
    # Precisa de 2 ou 3 pessoas fixas; câmera em movimento ou grupo grande descarta o plano.
    if not 2 <= len(seats) <= MAX_SEATS:
        return []
    H, W = grays[0].shape
    activity = {}
    for index, seat in enumerate(seats):
        x0 = int(max(0, (seat['x'] - seat['w'] * .35) * W))
        x1 = int(min(W, (seat['x'] + seat['w'] * .35) * W))
        y0 = int(max(0, (seat['y'] + seat['h'] * .10) * H))
        y1 = int(min(H, (seat['y'] + seat['h'] * .55) * H))
        if x1 - x0 < 6 or y1 - y0 < 4:
            return []
        crops = [cv2.resize(g[y0:y1, x0:x1], (32, 16)).astype('float32') for g in grays]
        activity[index] = [0.0] + [float(np.abs(crops[i] - crops[i - 1]).mean()) for i in range(1, len(crops))]
    turns = choose(activity, step)
    if not turns:
        return []
    return plan_from_turns(turns, {i: s for i, s in enumerate(seats)}, len(grays) * step if duration > len(grays) * step else duration)
