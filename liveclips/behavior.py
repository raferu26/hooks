"""Leitura local de movimentos faciais observaveis para apoiar a clipagem.

O modulo nao diagnostica emocoes, personalidade ou intencao. Ele converte
blendshapes e movimento de cabeca em pistas temporais explicaveis e compara
cada pessoa com o proprio padrao observado no trecho.
"""
from hashlib import sha256
import math
import os
from pathlib import Path
import statistics
from urllib.request import Request, urlopen


MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/face_landmarker/'
             'face_landmarker/float16/1/face_landmarker.task')
MODEL_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'

CUE_LABELS = {
    'sorriso': 'elevação dos cantos da boca',
    'boca_aberta': 'abertura rápida da boca',
    'sobrancelhas_elevadas': 'elevação das sobrancelhas',
    'sobrancelhas_contraidas': 'contração das sobrancelhas',
    'olhos_abertos': 'abertura dos olhos',
    'olhos_apertados': 'estreitamento dos olhos',
    'labios_pressos': 'pressão dos lábios',
    'assimetria_boca': 'assimetria no movimento da boca',
    'mudanca_olhar': 'mudança rápida da direção do olhar',
    'virada_cabeca': 'mudança rápida da posição da cabeça',
}


def model_path():
    custom = os.environ.get('LIVECLIPS_MODEL_DIR')
    if custom:
        root = Path(custom).expanduser()
    elif os.environ.get('LOCALAPPDATA'):
        root = Path(os.environ['LOCALAPPDATA'])/'LiveClips'/'modelos'
    else:
        root = Path.home()/'.liveclips'/'modelos'
    return root/'face_landmarker.task'


def prepare_model(path=None, timeout=120):
    """Baixa atomicamente o modelo oficial e verifica o arquivo exato."""
    target = Path(path or model_path())
    if target.is_file() and sha256(target.read_bytes()).hexdigest() == MODEL_SHA256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.download')
    request = Request(MODEL_URL, headers={'User-Agent': 'LiveClips/0.9.0'})
    try:
        with urlopen(request, timeout=timeout) as response, temporary.open('wb') as output:
            digest = sha256()
            size = 0
            while True:
                block = response.read(1024*1024)
                if not block:
                    break
                output.write(block);digest.update(block);size += len(block)
                if size > 50*1024*1024:
                    raise ValueError('O modelo facial excedeu o tamanho esperado.')
        if size < 1024*1024 or digest.hexdigest() != MODEL_SHA256:
            raise ValueError('O modelo facial baixado não passou na verificação de integridade.')
        temporary.replace(target)
        return target
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _mean(scores, *names):
    values = [float(scores.get(name, 0) or 0) for name in names]
    return sum(values)/max(1, len(values))


def observable_cues(scores):
    """Agrupa blendshapes em movimentos; os nomes evitam alegar emoção."""
    left_smile = float(scores.get('mouthSmileLeft', 0) or 0)
    right_smile = float(scores.get('mouthSmileRight', 0) or 0)
    eye_horizontal = max(
        _mean(scores, 'eyeLookInLeft', 'eyeLookOutRight'),
        _mean(scores, 'eyeLookOutLeft', 'eyeLookInRight'))
    return {
        'sorriso': _mean(scores, 'mouthSmileLeft', 'mouthSmileRight',
                         'cheekSquintLeft', 'cheekSquintRight'),
        'boca_aberta': _mean(scores, 'jawOpen', 'mouthFunnel', 'mouthPucker'),
        'sobrancelhas_elevadas': _mean(scores, 'browInnerUp', 'browOuterUpLeft',
                                       'browOuterUpRight'),
        'sobrancelhas_contraidas': _mean(scores, 'browDownLeft', 'browDownRight'),
        'olhos_abertos': _mean(scores, 'eyeWideLeft', 'eyeWideRight'),
        'olhos_apertados': _mean(scores, 'eyeSquintLeft', 'eyeSquintRight'),
        'labios_pressos': _mean(scores, 'mouthPressLeft', 'mouthPressRight'),
        'assimetria_boca': abs(left_smile-right_smile),
        'mudanca_olhar': eye_horizontal,
    }


def head_pose(matrix):
    """Extrai angulos aproximados de uma matriz 4x4 do Face Landmarker."""
    try:
        rows = matrix.tolist() if hasattr(matrix, 'tolist') else matrix
        yaw = math.degrees(math.atan2(float(rows[0][2]), float(rows[2][2])))
        pitch = math.degrees(math.atan2(-float(rows[1][2]),
                                        math.hypot(float(rows[1][0]), float(rows[1][1]))))
        roll = math.degrees(math.atan2(float(rows[1][0]), float(rows[1][1])))
        if all(math.isfinite(v) for v in (yaw, pitch, roll)):
            return yaw, pitch, roll
    except (IndexError, TypeError, ValueError, ZeroDivisionError):
        pass
    return None


def _events(series, cue, sensitivity='balanced', step=.25, reference=None, activity=None):
    """Eventos de `series` contra o padrão de `reference` (por padrão, a própria série).

    `reference` permite um baseline por atividade (falando x ouvindo). Cada evento traz início, ápice e retorno, a
    direção do movimento e a incerteza temporal (o passo de amostragem): o ápice é a amostra mais extrema, não o
    instante físico exato."""
    if len(series) < 1 or len(reference if reference is not None else series) < 5:
        return []
    values = [float(row['value']) for row in (reference if reference is not None else series)]
    baseline = statistics.median(values)
    deviations = [abs(value-baseline) for value in values]
    mad = statistics.median(deviations)
    multiplier = {'precise': 4.0, 'balanced': 3.0, 'sensitive': 2.25}.get(sensitivity, 3.0)
    absolute_floor = .055 if cue not in ('virada_cabeca',) else 4.5
    threshold = max(absolute_floor, mad*multiplier)
    active = []
    for row in series:
        delta = abs(float(row['value'])-baseline)
        if delta >= threshold:
            active.append(dict(row, delta=delta))
    groups = []
    for row in active:
        if groups and row['time']-groups[-1][-1]['time'] <= max(.7, step*2.5):
            groups[-1].append(row)
        else:
            groups.append([row])
    result = []
    for group in groups:
        peak = max(group, key=lambda row: row['delta'])
        duration = max(step, group[-1]['time']-group[0]['time']+step)
        # Um espasmo de um unico quadro pode ser compressao/oclusao. Ele fica
        # disponivel como pista, mas recebe confianca menor.
        persistence = min(1.0, duration/max(.5, step*2))
        strength = min(3.0, peak['delta']/max(threshold, 1e-6))
        confidence = min(.98, .45+.25*persistence+.20*min(1.0, strength/2))
        onset = float(group[0]['time'])
        offset = float(group[-1]['time']) + step
        result.append({
            'onset': round(onset, 3), 'apex': round(float(peak['time']), 3), 'offset': round(offset, 3),
            'direction': 'aumento' if float(peak['value']) >= baseline else 'reducao',
            'samples': len(group), 'time_uncertainty_s': round(step, 3), 'lineage': 'webcam_pixels',
            **({'activity': activity} if activity else {}),
            'time': round(float(peak['time']), 3),
            'strength': round(strength, 3),
            'confidence': round(confidence, 3),
            'duration': round(duration, 3),
            'cue': cue,
            'label': CUE_LABELS[cue],
            'baseline': round(baseline, 4),
            'peak': round(float(peak['value']), 4),
        })
    return result


def behavior_events(frames, sensitivity='balanced', step=.25, speech=None):
    """Cria eventos relativos ao padrao da pessoa no trecho analisado.

    ``frames`` contem ``time``, ``scores`` e, opcionalmente, ``pose``.
    Nenhum frame ou identidade e persistido no resultado.
    """
    valid = [frame for frame in frames if isinstance(frame.get('scores'), dict)]
    if len(valid) < 5:
        return []
    cue_series = {cue: [] for cue in CUE_LABELS if cue != 'virada_cabeca'}
    pose_series = []
    previous_pose = None
    previous_at = None
    for frame in valid:
        at = float(frame.get('time', 0))
        for cue, value in observable_cues(frame['scores']).items():
            cue_series[cue].append({'time': at, 'value': value})
        pose = frame.get('pose')
        # Rosto perdido e recuperado: a pose anterior NÃO atravessa a lacuna (senão a volta vira um salto de cabeça falso).
        if previous_at is not None and at - previous_at > step*2.5:
            previous_pose = None
        if pose and previous_pose:
            delta = math.sqrt(sum((float(a)-float(b))**2 for a,b in zip(pose, previous_pose)))
            pose_series.append({'time': at, 'value': delta})
        elif pose:
            pose_series.append({'time': at, 'value': 0.0})
        previous_pose = pose if pose else previous_pose
        previous_at = at
    result = []
    speaking = lambda t: any(a <= t <= b for a, b in (speech or []))
    for cue, series in list(cue_series.items()) + [('virada_cabeca', pose_series)]:
        if speech:
            talk = [r for r in series if speaking(r['time'])]
            listen = [r for r in series if not speaking(r['time'])]
            # Baseline próprio de cada atividade quando há amostras suficientes; senão, o geral (e sem rótulo de atividade).
            for part, name in ((talk, 'falando'), (listen, 'ouvindo')):
                if len(part) >= 8:
                    result.extend(_events(part, cue, sensitivity, step, activity=name))
                elif part:
                    result.extend(_events(part, cue, sensitivity, step, reference=series))
        else:
            result.extend(_events(series, cue, sensitivity, step))
    return sorted(result, key=lambda row: (row['time'], -row['strength'], row['cue']))


def analyze_rgb_frames(frames, width, height, fps=4, sensitivity='balanced', path=None, speech=None, crop_px=None):
    """Executa Face Landmarker localmente; retorna pistas e metadados seguros."""
    target = Path(path or model_path())
    if not target.is_file():
        raise RuntimeError('modelo facial ainda não foi preparado; execute o instalador da V6.8')
    try:
        import mediapipe as mp
        import numpy as np
    except ImportError as exc:
        raise RuntimeError('MediaPipe não instalado; execute o instalador da V6.8') from exc
    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    RunningMode = mp.tasks.vision.RunningMode
    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(target)),
        running_mode=RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=.45,
        min_face_presence_confidence=.45,
        min_tracking_confidence=.45,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )
    observations = []
    sizes = []
    seen = 0
    frame_size = int(width)*int(height)*3
    with FaceLandmarker.create_from_options(options) as landmarker:
        for index, raw in enumerate(frames):
            if len(raw) != frame_size:
                continue
            image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
            result = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=image),
                round(index*1000/max(.1, fps)))
            if not result.face_blendshapes:
                continue
            seen += 1
            scores = {item.category_name: float(item.score)
                      for item in result.face_blendshapes[0] if item.category_name}
            matrices = result.facial_transformation_matrixes or []
            observations.append({'time': index/max(.1, fps), 'scores': scores,
                                 'pose': head_pose(matrices[0]) if matrices else None})
            if getattr(result, 'face_landmarks', None) and crop_px:
                marks = result.face_landmarks[0]
                xs = [m.x for m in marks]
                if xs:
                    sizes.append((max(xs)-min(xs))*float(crop_px))
    from .face_quality import gaps_from_times
    events = behavior_events(observations, sensitivity=sensitivity, step=1/max(.1, fps), speech=speech)
    sizes.sort()
    return events, {
        'engine': 'mediapipe-face-landmarker',
        'frames': len(frames),
        'faces': seen,
        'face_ratio': round(seen/max(1, len(frames)), 3),
        'sampling_fps': fps,
        'gaps': gaps_from_times([o['time'] for o in observations], 1/max(.1, fps)),
        'face_px': round(sizes[len(sizes)//2], 1) if sizes else None,
        'privacy': 'Somente pistas numéricas foram mantidas; imagens e identidade não foram armazenadas.',
        'scope': 'Movimentos observáveis; não diagnostica emoção, intenção ou personalidade.',
    }


if __name__ == '__main__':
    prepared = prepare_model()
    print('Modelo facial verificado:', prepared)
