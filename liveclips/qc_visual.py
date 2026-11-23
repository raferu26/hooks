"""Controle de qualidade pela imagem e pelo som do arquivo exportado (complementa `qc.py`).

Tudo aqui lê o vídeo pronto, não o plano: quadro congelado, começo parado, áudio estourado, áudio e vídeo fora de
sincronia no contêiner, rosto encostado na borda e a legenda como ela foi desenhada (renderizada, não estimada).
Nada bloqueia nem apaga o arquivo. Cada item tem `status` ok | atencao | erro, como em `qc.py`.

Limites honestos, para a pessoa saber o que o relatório não diz:
- Os limiares abaixo são pontos de partida razoáveis, NÃO calibrados com vídeos reais; ajustar com o uso.
- Quadro congelado também acontece de propósito (tela de menu, imagem parada); por isso só vira "atenção".
- A sincronia medida é a do contêiner (início e duração das faixas). Fala fora do lábio não é medida.
- "Rosto cortado" depende do detector de rosto; sem rosto detectado não afirma nada.
- A zona do TikTok continua sendo uma estimativa conservadora (ver `qc.ZONAS`); aqui só a legenda é medida de verdade.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import media

CONGELADO_MIN = 2.0         # s de imagem parada para avisar
CONGELADO_RUIDO = '0.003'   # tolerância do freezedetect (≈ -50 dB)
COMECO_MUDO_MIN = 1.0       # s de silêncio logo no início
COMECO_PARADO_MIN = 1.5     # s de imagem parada logo no início
SILENCIO_DB = '-45dB'
ESTOURO_ATENCAO = 10        # amostras no 0 dBFS
ESTOURO_ERRO = 500
SINC_INICIO = .12           # s de diferença entre o começo do áudio e do vídeo
SINC_DURACAO = .30          # s de diferença entre a duração do áudio e do vídeo
BORDA_ROSTO = .012          # fração do quadro: rosto a menos disso da borda conta como encostado
AMOSTRAS = 3                # quadros de amostra guardados para o olho humano
MARGEM_RENDER = 6           # px de tolerância na medida da legenda (contorno que o detector não vê)


def item(id_, label, status, detail=''):
    return dict(id=id_, label=label, status=status, detail=detail)


# ---------------------------------------------------------------- leitura das saídas do FFmpeg

def parse_freeze(stderr, duration):
    """-> [(início, fim)] de imagem parada. Se o fim não aparece, a imagem ficou parada até o final."""
    starts = [float(x) for x in re.findall(r'freeze_start:\s*([\d.]+)', stderr)]
    ends = [float(x) for x in re.findall(r'freeze_end:\s*([\d.]+)', stderr)]
    spans = []
    for i, start in enumerate(starts):
        spans.append((start, ends[i] if i < len(ends) else float(duration)))
    return spans


def parse_silence(stderr, duration):
    starts = [float(x) for x in re.findall(r'silence_start:\s*(-?[\d.]+)', stderr)]
    ends = [float(x) for x in re.findall(r'silence_end:\s*([\d.]+)', stderr)]
    return [(max(0.0, s), ends[i] if i < len(ends) else float(duration)) for i, s in enumerate(starts)]


def parse_volume(stderr):
    """-> dict(max_db, zero_db) de um volumedetect, ou None se não houve áudio medido."""
    peak = re.search(r'max_volume:\s*(-?[\d.]+) dB', stderr)
    if not peak:
        return None
    zero = re.search(r'histogram_0db:\s*(\d+)', stderr)
    return dict(max_db=float(peak.group(1)), zero_db=int(zero.group(1)) if zero else 0)


def parse_crop(stderr):
    """União de todas as caixas que o cropdetect achou -> (x0, y0, x1, y1) ou None se não havia nada desenhado."""
    boxes = [tuple(int(v) for v in m) for m in re.findall(r'crop=(\d+):(\d+):(\d+):(\d+)', stderr)]
    boxes = [(x, y, x + w, y + h) for w, h, x, y in boxes if w > 0 and h > 0]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


# ---------------------------------------------------------------- regras (sem FFmpeg, fáceis de testar)

def _overlaps_planned(span, planned):
    return any(span[0] < b + .05 and span[1] > a - .05 for a, b in planned)


def freeze_check(spans, duration, planned=()):
    """Congelamento que o plano não pediu (os `freeze` do editor são propositais e não contam)."""
    real = [s for s in spans if s[1] - s[0] >= CONGELADO_MIN and not _overlaps_planned(s, planned)]
    if not real:
        return item('congelado', 'Imagem parada', 'ok')
    total = sum(b - a for a, b in real)
    status = 'erro' if total > duration * .5 else 'atencao'
    spots = ', '.join(f'{a:.1f}–{b:.1f}s' for a, b in real[:3])
    return item('congelado', 'Imagem parada', status,
                f'{len(real)} trecho(s) sem movimento ({total:.1f}s no total): {spots}. '
                'Se for uma tela parada de propósito, pode ignorar; se não, o vídeo pode ter travado.')


def start_check(freezes, silences, duration):
    """Os primeiros segundos decidem se a pessoa fica. Começo mudo e/ou parado é aviso."""
    mute = next((b - a for a, b in silences if a <= .08 and b - a >= COMECO_MUDO_MIN), 0.0)
    still = next((b - a for a, b in freezes if a <= .08 and b - a >= COMECO_PARADO_MIN), 0.0)
    if not mute and not still:
        return item('comeco', 'Começo do vídeo', 'ok')
    parts = []
    if mute:
        parts.append(f'{mute:.1f}s de silêncio no início')
    if still:
        parts.append(f'{still:.1f}s de imagem parada no início')
    status = 'erro' if mute and still and max(mute, still) >= 2.0 else 'atencao'
    return item('comeco', 'Começo do vídeo', status, '; '.join(parts).capitalize() + '. Corte esse trecho ou comece na primeira fala.')


def clipping_check(volume):
    if not volume:
        return item('estouro', 'Áudio estourado', 'ok')
    n = volume['zero_db']
    if n >= ESTOURO_ERRO:
        return item('estouro', 'Áudio estourado', 'erro', f'{n} amostras no limite digital (0 dB): o som está distorcendo.')
    if n >= ESTOURO_ATENCAO:
        return item('estouro', 'Áudio estourado', 'atencao', f'{n} amostras no limite digital (0 dB): pode haver estalos.')
    return item('estouro', 'Áudio estourado', 'ok')


def sync_check(video, audio):
    """`video`/`audio`: dict(start, duration) das faixas do arquivo (ffprobe). Mede o contêiner, não o lábio."""
    if not video or not audio:
        return item('sincronia', 'Áudio e vídeo juntos', 'ok')
    off = abs(audio['start'] - video['start'])
    gap = abs(audio['duration'] - video['duration'])
    problems = []
    if off > SINC_INICIO:
        problems.append(f'o áudio começa {off:.2f}s {"depois" if audio["start"] > video["start"] else "antes"} do vídeo')
    if gap > SINC_DURACAO:
        problems.append(f'as faixas diferem em {gap:.2f}s de duração')
    if not problems:
        return item('sincronia', 'Áudio e vídeo juntos', 'ok')
    status = 'erro' if off > .5 or gap > 1.0 else 'atencao'
    return item('sincronia', 'Áudio e vídeo juntos', status, '; '.join(problems).capitalize() + '.')


def face_edge_check(boxes_by_frame):
    """`boxes_by_frame`: [[(x, y, w, h) normalizados]] um item por quadro olhado. Rosto fora ou rente à borda = cortado."""
    seen = [b for frame in boxes_by_frame for b in frame]
    if not seen:
        return None   # sem rosto detectado não se afirma nada
    cut = 0
    for frame in boxes_by_frame:
        for x, y, w, h in frame:
            if x < BORDA_ROSTO or y < BORDA_ROSTO or x + w > 1 - BORDA_ROSTO or y + h > 1 - BORDA_ROSTO:
                cut += 1
                break
    if not cut:
        return item('rosto_cortado', 'Rosto no quadro', 'ok')
    frames = len([f for f in boxes_by_frame if f])
    status = 'erro' if frames >= 3 and cut == frames else 'atencao'
    return item('rosto_cortado', 'Rosto no quadro', status,
                f'Em {cut} de {frames} quadros olhados o rosto fica encostado ou passa da borda: pode estar cortado.')


def caption_render_check(bbox, canvas, zones, captions=True):
    """`bbox`: (x0, y0, x1, y1) do que a legenda desenhou. Compara com as zonas do app em pixels reais."""
    if not captions:
        return []
    if bbox is None:
        return [item('legenda_render', 'Legenda desenhada', 'atencao',
                     'O vídeo tem legenda no arquivo, mas nada apareceu ao desenhá-la (fonte ou estilo?).')]
    width, height = canvas
    x0, y0, x1, y1 = bbox
    bottom_gap = height - y1
    problems = []
    if bottom_gap < zones['bottom'] - MARGEM_RENDER:
        problems.append(f'a base da legenda fica a {bottom_gap} px do fim (o app cobre ~{zones["bottom"]} px)')
    if x1 > width - zones['right'] + MARGEM_RENDER and y1 > height * .35:
        problems.append(f'o texto vai até {width - x1} px da borda direita, onde ficam os botões (~{zones["right"]} px)')
    if x0 < zones['left'] - MARGEM_RENDER:
        problems.append(f'o texto encosta a {x0} px da borda esquerda')
    if y0 < zones['top'] - MARGEM_RENDER:
        problems.append(f'o texto sobe até {y0} px do topo (abas do app: ~{zones["top"]} px)')
    if not problems:
        return [item('legenda_render', 'Legenda desenhada', 'ok',
                     f'Medida no vídeo: ocupa de {x0} a {x1} px na largura e de {y0} a {y1} px na altura.')]
    return [item('legenda_render', 'Legenda desenhada', 'atencao',
                 'Medido ao desenhar a legenda: ' + '; '.join(problems) + '. As zonas do TikTok são aproximadas.')]


# ---------------------------------------------------------------- execução (usa FFmpeg e, se houver, o detector de rosto)

def _run(args, timeout=300):
    return media.run_stderr(args, timeout=timeout)


def scan_video(video, duration):
    cmd = [media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(video), '-an',
           '-vf', f'scale=160:-2,freezedetect=n={CONGELADO_RUIDO}:d={CONGELADO_MIN}', '-f', 'null', '-']
    return parse_freeze(_run(cmd), duration)


def scan_audio(video, duration):
    cmd = [media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(video), '-vn',
           '-af', f'volumedetect,silencedetect=n={SILENCIO_DB}:d=0.8', '-f', 'null', '-']
    text = _run(cmd)
    return parse_silence(text, duration), parse_volume(text)


def stream_times(video):
    import json
    out = media.run([media.tool('ffprobe'), '-v', 'error', '-show_entries', 'stream=codec_type,start_time,duration',
                     '-of', 'json', str(video)], 60)
    streams = {}
    for s in json.loads(out).get('streams', []):
        try:
            streams.setdefault(s['codec_type'], dict(start=float(s.get('start_time') or 0), duration=float(s['duration'])))
        except (KeyError, TypeError, ValueError):
            continue
    return streams.get('video'), streams.get('audio')


def caption_only_ass(ass_text):
    """O mesmo arquivo de legenda, mantendo só as falas (estilo 'Principal'); títulos e caixas ficam de fora da medida."""
    keep = []
    for line in ass_text.splitlines():
        if line.startswith('Dialogue:') and line.split(',', 4)[3].strip() != 'Principal':
            continue
        keep.append(line)
    return '\n'.join(keep) + '\n'


def render_caption_bbox(ass_text, canvas, duration, fonts_dir=None, fps=8, shrink=2):
    """Desenha só as falas sobre fundo preto e mede onde caiu texto, em pixels do vídeo final.
    Junta (máximo) todos os quadros e procura o retângulo que contém algo claro. None = nada foi desenhado.
    Levanta ImportError se o numpy não estiver instalado (quem chama então mantém a estimativa antiga)."""
    import numpy as np
    if 'Dialogue:' not in caption_only_ass(ass_text):
        return None
    width, height = int(canvas[0]) // shrink, int(canvas[1]) // shrink
    with tempfile.TemporaryDirectory(prefix='qc_ass_') as folder:
        path = Path(folder) / 'falas.ass'
        path.write_text(caption_only_ass(ass_text), encoding='utf-8-sig')
        fonts = f':fontsdir={Path(fonts_dir).as_posix()}' if fonts_dir and Path(fonts_dir).is_dir() else ''
        cmd = [media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
               f'color=c=black:s={canvas[0]}x{canvas[1]}:r={fps}:d={max(1.0, float(duration)):.2f}',
               '-vf', f'ass=falas.ass{fonts},scale={width}:{height},format=gray', '-f', 'rawvideo', '-']
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        proc = subprocess.Popen(cmd, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        size = width * height
        acc = np.zeros((height, width), dtype=np.uint8)
        try:
            while True:
                raw = proc.stdout.read(size)
                if len(raw) < size:
                    break
                np.maximum(acc, np.frombuffer(raw, dtype=np.uint8).reshape(height, width), out=acc)
        finally:
            proc.stdout.close()
            error = proc.stderr.read().decode('utf-8', errors='replace')
            proc.stderr.close()
            code = proc.wait(timeout=120)
        if code and not acc.any():
            raise RuntimeError(error[-300:] or 'O FFmpeg não conseguiu desenhar a legenda.')
    ys, xs = np.nonzero(acc > 40)
    if not len(xs):
        return None
    return (int(xs.min()) * shrink, int(ys.min()) * shrink, (int(xs.max()) + 1) * shrink, (int(ys.max()) + 1) * shrink)


def extract_frames(video, folder, duration, count=5, width=540):
    """`count` quadros espalhados pelo vídeo (10%…90%). -> lista de caminhos."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        at = max(0.0, min(duration - .1, duration * (.1 + .8 * i / max(1, count - 1))))
        target = folder / f'q{i + 1:02d}.jpg'
        _run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{at:.3f}', '-i', str(video),
              '-frames:v', '1', '-vf', f'scale={width}:-2', '-q:v', '4', str(target)], 60)
        if target.is_file():
            paths.append(target)
    return paths


def face_boxes(paths):
    """Caixas de rosto normalizadas por quadro, ou None se não há detector disponível neste computador."""
    try:
        import cv2
        from . import camera_detect
    except Exception:
        return None
    result = []
    for path in paths:
        image = cv2.imread(str(path))
        if image is None:
            result.append([])
            continue
        try:
            result.append([tuple(b) for b in camera_detect.detect_faces(image)])
        except Exception:
            return None
    return result


def save_samples(frames, destination, count=AMOSTRAS):
    """Guarda `count` dos quadros ao lado do vídeo, para conferir sem abrir o arquivo. -> nomes dos arquivos."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for old in destination.glob('amostra_*.jpg'):
        old.unlink(missing_ok=True)
    if not frames:
        return []
    picks = [frames[round(i * (len(frames) - 1) / max(1, count - 1))] for i in range(min(count, len(frames)))]
    names = []
    for i, source in enumerate(dict.fromkeys(picks)):
        name = f'amostra_{i + 1}.jpg'
        (destination / name).write_bytes(Path(source).read_bytes())
        names.append(name)
    return names


def visual_checks(video, duration, ass_path=None, canvas=(1080, 1920), zones=None, planned_freezes=(), fonts_dir=None,
                  samples_dir=None, has_audio=True, ai=True):
    """Todas as checagens desta camada. -> (itens, nomes das amostras). Nenhuma exceção sai daqui."""
    items, samples = [], []
    freezes = []
    try:
        freezes = scan_video(video, duration)
        items.append(freeze_check(freezes, duration, planned_freezes))
    except Exception as exc:
        items.append(item('congelado', 'Imagem parada', 'atencao', 'Não consegui checar imagem parada: ' + str(exc)[:120]))
    silences = []
    if has_audio:
        try:
            silences, volume = scan_audio(video, duration)
            items.append(clipping_check(volume))
        except Exception as exc:
            items.append(item('estouro', 'Áudio estourado', 'atencao', 'Não consegui checar estouro: ' + str(exc)[:120]))
        try:
            items.append(sync_check(*stream_times(video)))
        except Exception as exc:
            items.append(item('sincronia', 'Áudio e vídeo juntos', 'atencao', 'Não consegui checar a sincronia: ' + str(exc)[:120]))
    items.append(start_check(freezes, silences, duration))
    frames = []
    with tempfile.TemporaryDirectory(prefix='qc_frames_') as temp:
        try:
            frames = extract_frames(video, temp, duration)
            boxes = face_boxes(frames) if ai else None   # sem IA: não procura rostos
            if boxes is not None:
                check = face_edge_check(boxes)
                if check:
                    items.append(check)
            if samples_dir:
                samples = save_samples(frames, samples_dir)
        except Exception as exc:
            items.append(item('amostras', 'Quadros de amostra', 'atencao', 'Não consegui extrair quadros: ' + str(exc)[:120]))
    if ass_path and Path(ass_path).is_file():
        try:
            text = Path(ass_path).read_text(encoding='utf-8-sig')
            if 'Dialogue:' in text and zones:
                bbox = render_caption_bbox(text, canvas, duration, fonts_dir)
                items += caption_render_check(bbox, canvas, zones, captions='Principal' in text)
        except ImportError:
            pass   # sem numpy não há medida; continua valendo a estimativa feita pelo arquivo .ass
        except Exception as exc:
            items.append(item('legenda_render', 'Legenda desenhada', 'atencao', 'Não consegui medir a legenda desenhada: ' + str(exc)[:120]))
    return items, samples
