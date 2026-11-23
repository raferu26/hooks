"""Sinais de energia e movimento. Nao classifica emocoes, risadas ou gritos."""
from array import array
import math
import os
import statistics
import subprocess
import sys
import time

from .media import tool
from .behavior import analyze_rgb_frames


def picos(values, step=.5, floor=.02):
    if not values:
        return []
    baseline = statistics.median(values)
    mad = statistics.median(abs(v-baseline) for v in values)
    scale = max(floor, mad * 3)
    selected = []
    for i, value in enumerate(values):
        strength = min(3.0, max(0.0, (value-baseline)/scale))
        if strength < .8:
            continue
        point = {'time': round(i*step, 2), 'strength': round(strength, 3)}
        if selected and point['time'] - selected[-1]['time'] <= 1.5:
            if point['strength'] > selected[-1]['strength']:
                selected[-1] = point
        else:
            selected.append(point)
    return selected


def extrair(source, length, profile=None, speech=None, ai=True):
    result = {'audio': [], 'motion': [], 'facial': [], 'behavior': [], 'warnings': [],
              'audio_ok': False, 'motion_ok': False, 'facial_ok': False,
              'behavior_ok': False, 'behavior_meta': {}}
    seconds = min(float(length), 180)
    common = [tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-threads', '2',
              '-i', str(source), '-t', str(seconds)]
    try:
        cp = subprocess.run(common + ['-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1'],
                            capture_output=True, timeout=90,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if cp.returncode:
            raise RuntimeError('audio indisponivel')
        samples = array('h')
        samples.frombytes(cp.stdout[:len(cp.stdout)//2*2])
        if sys.byteorder != 'little':
            samples.byteswap()
        values = [math.sqrt(sum(x*x for x in samples[i:i+4000])/len(samples[i:i+4000]))/32768
                  for i in range(0, len(samples), 4000)]
        result['audio'] = picos(values, floor=.025)
        result['audio_ok'] = bool(values)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        result['warnings'].append('Sem sinal de audio: ' + str(exc))
    if profile:
        try:
            x, y, w, h = [float(v) for v in profile['camera_rect']]
            if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x+w <= 1.001 and y+h <= 1.001):
                raise ValueError('retangulo de webcam invalido')
            # Quatro amostras/s equilibram movimentos faciais breves com o uso
            # local de CPU. O resultado descreve movimentos, não estados mentais.
            fps = 4;side = 192;channels = 3
            vf = f'fps={fps},crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale={side}:{side},format=rgb24'
            cp = subprocess.run(common + ['-an', '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                                capture_output=True, timeout=120,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if cp.returncode:
                raise RuntimeError('movimento da webcam indisponivel')
            size = side*side*channels
            frames = [cp.stdout[i:i+size] for i in range(0, len(cp.stdout)-size+1, size)]
            def change(prev,cur,x0,y0,x1,y1):
                indexes=((yy*side+xx)*channels for yy in range(y0,y1,4) for xx in range(x0,x1,4))
                values=[(abs(prev[i]-cur[i])+abs(prev[i+1]-cur[i+1])+abs(prev[i+2]-cur[i+2]))/3
                        for i in indexes]
                return sum(values)/(max(1,len(values))*255)
            changes=[0.0]; upper=[0.0]; lower=[0.0]; asymmetry=[0.0]
            for prev,cur in zip(frames,frames[1:]):
                changes.append(change(prev,cur,0,0,side,side))
                upper.append(change(prev,cur,24,24,168,104))
                lower.append(change(prev,cur,30,96,162,182))
                left=change(prev,cur,8,16,96,184);right=change(prev,cur,96,16,184,184)
                asymmetry.append(abs(left-right))
            step=1/fps
            result['motion'] = picos(changes,step=step,floor=.018)
            facial=[]
            for region,values,floor in (('olhos_sobrancelhas',upper,.018),('boca',lower,.018),
                                        ('assimetria',asymmetry,.012)):
                facial.extend(dict(point,region=region) for point in picos(values,step=step,floor=floor))
            result['facial']=sorted(facial,key=lambda point:point['time'])
            result['motion_ok'] = len(frames) > 1
            result['facial_ok'] = len(frames) > 1
            if not ai:
                result['warnings'].append('Modo sem IA: leitura de rosto e comportamento não foi iniciada.')
                raise StopIteration
            try:
                behavior,meta=analyze_rgb_frames(frames,side,side,fps,
                    sensitivity=profile.get('behavior_sensitivity','balanced'),speech=speech)
                result['behavior']=behavior;result['behavior_meta']=meta
                result['behavior_ok']=meta.get('faces',0)>=5
                if meta.get('face_ratio',0)<.35:
                    result['warnings'].append('Rosto pouco visível na webcam; pistas comportamentais têm baixa cobertura.')
            except RuntimeError as exc:
                # O detector geométrico anterior continua disponível como
                # fallback; a sessão nunca é perdida por falta do aprimoramento.
                result['warnings'].append('Análise facial avançada indisponível: '+str(exc))
        except StopIteration:
            pass
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired, RuntimeError) as exc:
            result['warnings'].append('Sem sinal visual: ' + str(exc))
    else:
        result['warnings'].append('Sem perfil de webcam; movimento nao analisado.')
    try:
        from . import visual
        screen = visual.analyze(source, length, (profile or {}).get('camera_rect'))
        result['visual'] = screen['events'];result['visual_ok'] = screen['ok']
        result['warnings'] += screen['warnings']
    except Exception as exc:
        result['visual'] = [];result['visual_ok'] = False;result['warnings'].append('Sem sinal visual da tela: '+str(exc)[:100])
    if float(length) > seconds:
        result['warnings'].append('Sinais de audio e movimento limitados aos primeiros 180s.')
    return result


def refine_dense(source, start, end, profile, fps=12, speech=None, max_seconds=30, sensitivity=None):
    """Análise facial DENSA de uma janela curta (N18), preservando a proporção do recorte da webcam.

    Serve para reações que a camada barata (4 quadros/s) não consegue localizar bem: ela relê [start, end] no fps
    pedido, com timestamps reais, e devolve eventos com início/ápice/retorno mais um custo medido. Isso NÃO é cobertura
    contínua da live: só as janelas pedidas são relidas. Interpolar ou ampliar não cria observações novas.
    `speech` = intervalos de fala em segundos da MESMA origem do vídeo (para baseline por atividade)."""
    from .media import probe
    began = time.perf_counter()
    start = max(0.0, float(start))
    seconds = min(float(max_seconds), max(0.0, float(end) - start))
    fps = max(4, min(30, int(fps)))
    if seconds < 1 or not profile or not profile.get('camera_rect'):
        raise ValueError('Janela ou retângulo da webcam inválido para a análise densa.')
    x, y, w, h = [float(v) for v in profile['camera_rect']]
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x+w <= 1.001 and y+h <= 1.001):
        raise ValueError('retângulo de webcam inválido')
    info = probe(source)
    crop_w, crop_h = info['width']*w, info['height']*h
    out_w = 288
    out_h = max(32, int(round(out_w*crop_h/crop_w/2))*2)
    vf = f'fps={fps},crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale={out_w}:{out_h},format=rgb24'
    cp = subprocess.run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-threads', '2', '-ss', f'{start:.3f}', '-t', f'{seconds:.3f}',
                         '-i', str(source), '-an', '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                        capture_output=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if cp.returncode:
        raise RuntimeError('leitura densa da webcam indisponível')
    size = out_w*out_h*3
    frames = [cp.stdout[i:i+size] for i in range(0, len(cp.stdout)-size+1, size)]
    local_speech = [(max(0.0, a-start), b-start) for a, b in (speech or []) if b > start and a < start+seconds]
    events, meta = analyze_rgb_frames(frames, out_w, out_h, fps, sensitivity=sensitivity or profile.get('behavior_sensitivity', 'balanced'),
                                      speech=local_speech, crop_px=crop_w)
    for e in events:
        for key in ('time', 'onset', 'apex', 'offset'):
            if key in e:
                e[key] = round(e[key]+start, 3)
    meta.update(window=[round(start, 3), round(start+seconds, 3)], sampling_fps=fps, frame_size=[out_w, out_h],
                elapsed_s=round(time.perf_counter()-began, 3), frames_read=len(frames),
                aspect_preserved=True, mode='denso_seletivo')
    return events, meta
