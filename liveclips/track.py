"""Enquadramento por rastreio clássico (P08) — sem rede neural.

Segue uma região marcada pelo usuário (`track_roi` no perfil, em frações da imagem) com fluxo óptico
Lucas-Kanade (OpenCV) e verificação direta-inversa. Não reconhece pessoa, rosto ou objeto: acompanha
textura. Por isso é conservador: perdeu a região, passou um corte de cena ou a textura é pobre →
devolve pontos `face=False` e o quadro volta ao padrão do perfil. A saída tem o mesmo formato do
`dynamic_reframe_plan` (dicts com start, end, face, x), então o render não muda.
"""
import math

MAX_SAMPLES = 480
SCENE_CUT = 24.0          # diferença média (0-255) entre quadros reduzidos que indica corte de cena
MIN_FEATURES = 8
FB_TOLERANCE = 1.5        # px de erro direto-inverso aceito


def valid_roi(roi):
    """Valida e normaliza [x,y,w,h] em frações; levanta ValueError se fora da imagem."""
    if roi is None:
        return None
    if not isinstance(roi, (list, tuple)) or len(roi) != 4:
        raise ValueError('Marque a região a acompanhar novamente.')
    x, y, w, h = [float(v) for v in roi]
    if not all(math.isfinite(v) for v in (x, y, w, h)) or not (
            x >= 0 and y >= 0 and w >= .03 and h >= .03 and x + w <= 1.00001 and y + h <= 1.00001):
        raise ValueError('A região a acompanhar precisa estar dentro da imagem (mínimo 3% de largura e altura).')
    return [round(v, 6) for v in (x, y, w, h)]


def _seed(cv2, np, gray, box):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(gray.shape[1], x1), min(gray.shape[0], y1)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    mask = np.zeros(gray.shape, dtype=np.uint8)
    mask[y0:y1, x0:x1] = 255
    pts = cv2.goodFeaturesToTrack(gray, maxCorners=60, qualityLevel=.01, minDistance=4, mask=mask, blockSize=5)
    if pts is None or len(pts) < MIN_FEATURES:
        return None
    return pts.astype('float32')


def track_plan(source, offset, duration, info, roi, step=.75, probe=.25):
    """Pontos de enquadramento horizontal seguindo `roi`. Lista vazia = manter o quadro do perfil."""
    roi = valid_roi(roi)
    if roi is None:
        return []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if info['width'] / max(1, info['height']) <= 9 / 16 + .02:
        return []
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        return []
    points = []
    try:
        if offset > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, offset * 1000)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        if not math.isfinite(fps) or fps < 1:
            fps = float(info.get('fps') or 30)
        stride = max(1, int(round(probe * fps)))
        step_t = stride / fps
        counter = [0]

        def read(_t):
            """Leitura sequencial (sem buscar de novo a cada amostra: a busca em .ts pode cair em outro quadro)."""
            first = counter[0] == 0
            if not first:
                for _ in range(stride - 1):
                    if not cap.grab():
                        return None
            ok, frame = cap.read()
            counter[0] += 1
            if not ok:
                return None
            scale = min(1.0, 640 / max(1, frame.shape[1]))
            small = cv2.resize(frame, (max(2, int(frame.shape[1] * scale)), max(2, int(frame.shape[0] * scale))))
            return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        gray = read(0.0)
        if gray is None:
            return []
        H, W = gray.shape
        box = [roi[0] * W, roi[1] * H, (roi[0] + roi[2]) * W, (roi[1] + roi[3]) * H]
        pts = _seed(cv2, np, gray, box)
        # Textura insuficiente: não há o que rastrear; o plano fica vazio (quadro do perfil).
        if pts is None:
            return []
        cx = (box[0] + box[2]) / 2
        smooth = cx / W
        lost = False
        last_x = smooth
        t = 0.0
        prev_small = cv2.resize(gray, (32, 18))
        samples = 0
        conf = 1.0
        # amostras: (t, x normalizado, ok)
        track = [(0.0, smooth, True, 1.0)]
        initial_count = len(pts)
        while t + step_t <= duration and samples < MAX_SAMPLES:
            t = round(t + step_t, 3)
            samples += 1
            nxt = read(t)
            if nxt is None:
                break
            small = cv2.resize(nxt, (32, 18))
            cut = float(cv2.absdiff(prev_small, small).mean()) > SCENE_CUT
            prev_small = small
            if lost or cut:
                lost = True
                track.append((t, last_x, False, 0.0))
                gray = nxt
                continue
            new, st, _ = cv2.calcOpticalFlowPyrLK(gray, nxt, pts, None, winSize=(31, 31), maxLevel=3)
            back, st2, _ = cv2.calcOpticalFlowPyrLK(nxt, gray, new, None, winSize=(31, 31), maxLevel=3)
            if new is None or back is None:
                lost = True
                track.append((t, last_x, False, 0.0))
                gray = nxt
                continue
            fb = np.linalg.norm((pts - back).reshape(-1, 2), axis=1)
            good = (st.reshape(-1) == 1) & (st2.reshape(-1) == 1) & (fb < FB_TOLERANCE)
            n_good = int(good.sum())
            conf = n_good / max(1, len(pts))
            if n_good < MIN_FEATURES or conf < .35:
                lost = True
                track.append((t, last_x, False, round(conf, 3)))
                gray = nxt
                continue
            delta = np.median((new[good] - pts[good]).reshape(-1, 2), axis=0)
            cx += float(delta[0])
            bw = box[2] - box[0]
            box = [cx - bw / 2, box[1] + float(delta[1]), cx + bw / 2, box[3] + float(delta[1])]
            if not (0 <= cx <= W):
                lost = True
                track.append((t, last_x, False, round(conf, 3)))
                gray = nxt
                continue
            pts = new[good].reshape(-1, 1, 2)
            # reabastece pontos quando restam poucos, sempre dentro da caixa seguida
            if len(pts) < initial_count * .5:
                fresh = _seed(cv2, np, nxt, box)
                if fresh is not None:
                    pts = fresh
                    initial_count = len(pts)
            smooth = smooth * .5 + (cx / W) * .5
            last_x = smooth
            track.append((t, smooth, True, round(conf, 3)))
            gray = nxt
    finally:
        cap.release()
    if not track:
        return []
    # reduz às janelas de saída (`step`), usando a primeira amostra de cada janela
    cursor = 0.0
    previous = None
    while cursor < duration and len(points) < 180:
        window = [s for s in track if cursor - 1e-6 <= s[0] < cursor + step]
        if not window:
            break
        ok = all(s[2] for s in window)
        x = window[0][1]
        if ok and previous is not None and abs(x - previous) < .008:
            x = previous                     # zona morta: não treme por ruído
        if ok:
            previous = x
        points.append(dict(start=round(cursor, 3), end=round(min(duration, cursor + step), 3), face=bool(ok),
                           x=round(x if ok else .5, 5), scene=False, conf=round(min(s[3] for s in window), 3)))
        cursor = round(cursor + step, 3)
    # sem nenhum ponto confiável não há o que aplicar
    if not any(p['face'] for p in points):
        return []
    return points
