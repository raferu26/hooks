"""Qualidade da face e cobertura declarada (N16).

Baixa qualidade reduz a cobertura declarada em vez de gerar certeza artificial: o resultado correto pode ser
"não observável". Movimento fino (sobrancelha, canto da boca) exige rosto grande o bastante E amostragem densa o
bastante; a 4 fps um movimento de 100 ms pode cair inteiro entre duas amostras e nenhum recorte maior recupera isso.
"""
MIN_FACE_PX = 64          # abaixo disso, só movimento grosseiro
FINE_FACE_PX = 96         # mínimo para falar em movimento fino
FINE_FPS = 8              # amostragem mínima para não perder movimentos de ~150 ms com folga
LONG_GAP_S = 1.0


def assess(meta, fps=4):
    """`meta` = behavior_meta do segmento (frames, faces, face_ratio, gaps, face_px...). Devolve dict com nível e limites."""
    meta = meta or {}
    frames = int(meta.get('frames') or 0)
    faces = int(meta.get('faces') or 0)
    ratio = float(meta.get('face_ratio') if meta.get('face_ratio') is not None else (faces / frames if frames else 0.0))
    face_px = meta.get('face_px')
    fps = float(meta.get('sampling_fps') or fps)
    limits = []
    if frames == 0:
        return dict(level='insuficiente', coverage=0.0, face_px=None, sampling_fps=fps, fine_motion_ok=False,
                    nao_observavel=True, limits=['Sem quadros analisados da webcam: nada pode ser afirmado sobre o rosto.'])
    if ratio < .35:
        level = 'insuficiente'
        limits.append(f'Rosto visível em só {round(ratio * 100)}% das amostras: movimentos faciais não são observáveis.')
    elif ratio < .6 or (face_px is not None and face_px < MIN_FACE_PX):
        level = 'baixa'
    elif ratio >= .85 and (face_px is None or face_px >= 128):
        level = 'alta'
    else:
        level = 'media'
    if face_px is not None and face_px < MIN_FACE_PX:
        limits.append(f'Rosto pequeno (~{round(face_px)} px): só movimento grosseiro; ampliar o recorte não cria informação.')
    fine = level in ('alta', 'media') and (face_px is None or face_px >= FINE_FACE_PX) and fps >= FINE_FPS
    if fps < FINE_FPS:
        limits.append(f'Amostragem de {fps:g} quadros/s: movimentos mais curtos que ~{round(1000 / fps)} ms podem não ter sido vistos '
                      '(interpolar ou ampliar a imagem não recupera amostras que não existem).')
    gaps = [g for g in meta.get('gaps') or [] if g[1] - g[0] >= LONG_GAP_S]
    if gaps:
        limits.append(f'{len(gaps)} perda(s) de rosto de {LONG_GAP_S:g}s ou mais; o estado de movimento foi reiniciado após cada uma.')
    return dict(level=level, coverage=round(ratio, 3), face_px=None if face_px is None else round(float(face_px), 1),
                sampling_fps=fps, fine_motion_ok=bool(fine), nao_observavel=level == 'insuficiente', gaps=gaps, limits=limits)


def gaps_from_times(times, step, min_gap=LONG_GAP_S):
    """Intervalos sem rosto, a partir dos instantes em que houve rosto detectado."""
    out = []
    ordered = sorted(float(t) for t in times)
    for a, b in zip(ordered, ordered[1:]):
        if b - a - step >= min_gap:
            out.append([round(a + step, 3), round(b, 3)])
    return out
