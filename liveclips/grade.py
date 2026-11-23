"""Cor (P17): correção automática por histograma e LUT .cube, tudo clássico e conservador.

A correção só age quando a medida sai da faixa aceitável e nunca passa dos limites abaixo; cada decisão vem com o motivo.
Cena muito colorida (jogo, por exemplo) não recebe correção de dominante: a média das cores não prova que há cast."""
import math
from pathlib import Path
import tempfile

LIMITS = dict(gamma=(0.88, 1.22), contrast=(1.0, 1.12), saturation=(0.92, 1.10), cast=0.04)
TARGET_MEDIAN = 125
MEDIAN_TOLERANCE = 15
SPREAD_MIN = 170
CAST_MAX_SATURATION = 70           # acima disso a cena é colorida demais para inferir dominante
MAX_LUT_SIZE = 65
MAX_LUT_BYTES = 30 * 1024 ** 2
SAMPLES = 6


def measure_frames(images):
    """Estatísticas médias de uma lista de quadros BGR (numpy)."""
    import cv2
    import numpy as np
    if not images:
        return None
    p2, p50, p98, sat, means = [], [], [], [], []
    for image in images:
        small = cv2.resize(image, (320, max(2, int(image.shape[0] * 320 / max(1, image.shape[1])))))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        low, mid, high = np.percentile(gray, [2, 50, 98])
        p2.append(low); p50.append(mid); p98.append(high)
        sat.append(float(cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[:, :, 1].mean()))
        means.append(small.reshape(-1, 3).mean(axis=0))      # B, G, R
    mean = np.mean(means, axis=0)
    return dict(p2=float(np.mean(p2)), p50=float(np.mean(p50)), p98=float(np.mean(p98)), saturation=float(np.mean(sat)),
                mean_b=float(mean[0]), mean_g=float(mean[1]), mean_r=float(mean[2]), frames=len(images))


def sample_pieces(pieces, count=SAMPLES):
    """pieces: [(caminho, início, fim)] em segundos do arquivo -> até `count` quadros BGR, espalhados pelo corte."""
    import cv2
    from . import cover
    total = sum(max(0.0, b - a) for _, a, b in pieces)
    if total <= 0:
        return []
    images = []
    with tempfile.TemporaryDirectory(prefix='cor_') as temp:
        for i in range(count):
            position = total * (i + .5) / count
            for path, a, b in pieces:
                span = max(0.0, b - a)
                if position <= span:
                    target = Path(temp) / f'q{i}.jpg'
                    try:
                        if cover._grab(path, a + position, target):
                            image = cv2.imread(str(target))
                            if image is not None:
                                images.append(image)
                    except Exception:
                        pass
                    break
                position -= span
    return images


def decide(stats, content_mode='live'):
    """Medidas -> (grade, motivos). `grade` é vazio quando a imagem já está dentro da faixa."""
    if not stats:
        return {}, ['Sem quadros para medir; mantive a cor do estilo.']
    grade, reasons = {}, []
    median = stats['p50']
    if abs(median - TARGET_MEDIAN) > MEDIAN_TOLERANCE and 20 < median < 235:
        gamma = math.log(median / 255.0) / math.log(TARGET_MEDIAN / 255.0)
        low, high = LIMITS['gamma']
        gamma = round(max(low, min(high, gamma)), 3)
        if abs(gamma - 1) >= .02:
            grade['gamma'] = gamma
            reasons.append(('Imagem escura' if median < TARGET_MEDIAN else 'Imagem clara') + f' (mediana {median:.0f}/255): gama {gamma:g}.')
    spread = stats['p98'] - stats['p2']
    if spread < SPREAD_MIN:
        contrast = round(max(LIMITS['contrast'][0], min(LIMITS['contrast'][1], 1 + (SPREAD_MIN - spread) / 400.0)), 3)
        if contrast > 1.01:
            grade['contrast'] = contrast
            reasons.append(f'Pouco contraste (faixa {spread:.0f}/255): contraste {contrast:g}.')
    saturation = stats['saturation']
    if saturation < 55:
        grade['saturation'] = LIMITS['saturation'][1] if saturation < 40 else 1.05
        reasons.append(f'Cores apagadas (saturação {saturation:.0f}/255): saturação {grade["saturation"]:g}.')
    elif saturation > 150:
        grade['saturation'] = LIMITS['saturation'][0]
        reasons.append(f'Cores muito fortes (saturação {saturation:.0f}/255): saturação {grade["saturation"]:g}.')
    if saturation < CAST_MAX_SATURATION and content_mode == 'video':
        avg = (stats['mean_r'] + stats['mean_g'] + stats['mean_b']) / 3.0
        if avg > 30:
            limit = LIMITS['cast']
            cast = [round(max(-limit, min(limit, (avg - stats[k]) / 255.0 * .5)), 3) for k in ('mean_r', 'mean_g', 'mean_b')]
            if max(abs(x) for x in cast) >= .015:
                grade['cast'] = cast
                reasons.append('Dominante de cor leve na imagem neutra: correção parcial de equilíbrio.')
    if not grade:
        reasons.append('Imagem dentro da faixa: nenhuma correção automática.')
    return grade, reasons


def merge(base, extra):
    """Soma a correção automática à cor do estilo: contraste e saturação multiplicam; gama e cast só entram aqui."""
    result = dict(base or {})
    for key in ('contrast', 'saturation'):
        if key in extra:
            result[key] = round(float(result.get(key, 1.0)) * float(extra[key]), 4)
    for key in ('gamma', 'cast', 'lut'):
        if key in extra:
            result[key] = extra[key]
    return result


def filters(grade):
    """Trecho extra (gama, equilíbrio de cor e LUT) para o final da cadeia `grade_filters`."""
    parts = []
    if not grade:
        return ''
    gamma = grade.get('gamma')
    if gamma and abs(float(gamma) - 1) > 1e-6:
        parts.append(f'eq=gamma={float(gamma):g}')
    cast = grade.get('cast')
    if cast and len(cast) == 3:
        r, g, b = (max(-.1, min(.1, float(x))) for x in cast)
        parts.append(f'colorbalance=rm={r:g}:gm={g:g}:bm={b:g}')
    if grade.get('lut'):
        parts.append(f"lut3d=file={grade['lut']}:interp=tetrahedral")
    return ','.join(parts)


# ---- LUT .cube ----
class LutError(ValueError):
    pass


def read_cube(path):
    """-> (tamanho, [(r,g,b), ...]). Só LUT 3D, tamanho até 65, valores finitos; o resto é recusado com motivo."""
    path = Path(path)
    if path.stat().st_size > MAX_LUT_BYTES:
        raise LutError('O arquivo de LUT é grande demais.')
    size, rows, domain = None, [], ([0., 0., 0.], [1., 1., 1.])
    for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        text = line.split('#', 1)[0].strip()
        if not text or text.startswith('TITLE'):
            continue
        head = text.split()
        if head[0] == 'LUT_1D_SIZE':
            raise LutError('LUT 1D não é aceita; use um .cube 3D.')
        if head[0] == 'LUT_3D_SIZE':
            try:
                size = int(head[1])
            except (IndexError, ValueError):
                raise LutError('Tamanho da LUT ilegível.')
            if not 2 <= size <= MAX_LUT_SIZE:
                raise LutError('Tamanho de LUT fora do aceito (2 a 65).')
            continue
        if head[0] in ('DOMAIN_MIN', 'DOMAIN_MAX'):
            try:
                value = [float(x) for x in head[1:4]]
            except ValueError:
                raise LutError('Domínio da LUT ilegível.')
            domain = (value, domain[1]) if head[0] == 'DOMAIN_MIN' else (domain[0], value)
            continue
        if head[0][0].isalpha():
            continue        # outras palavras-chave do formato (ex.: LUT_IN_VIDEO_RANGE)
        try:
            values = tuple(float(x) for x in head[:3])
        except ValueError:
            raise LutError('Linha de LUT inválida.')
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise LutError('Linha de LUT inválida.')
        rows.append(values)
    if size is None:
        raise LutError('Não encontrei LUT_3D_SIZE: este não parece um .cube 3D.')
    if len(rows) != size ** 3:
        raise LutError(f'A LUT deveria ter {size ** 3} linhas e tem {len(rows)}.')
    if domain != ([0., 0., 0.], [1., 1., 1.]):
        raise LutError('LUT com domínio diferente de 0–1 não é aceita.')
    return size, rows


def prepare_lut(source, destination, strength=1.0):
    """Valida e grava a LUT na pasta de trabalho, misturada com a identidade conforme a intensidade (0,1–1)."""
    size, rows = read_cube(source)
    strength = max(0.0, min(1.0, float(strength)))
    out = [f'LUT_3D_SIZE {size}']
    for index, (r, g, b) in enumerate(rows):
        ir, ig, ib = (index % size) / (size - 1), ((index // size) % size) / (size - 1), (index // (size * size)) / (size - 1)
        mix = (ir + (r - ir) * strength, ig + (g - ig) * strength, ib + (b - ib) * strength)
        out.append('%.6f %.6f %.6f' % tuple(max(0.0, min(1.0, v)) for v in mix))
    Path(destination).write_text('\n'.join(out) + '\n', encoding='utf-8')
    return Path(destination)


def luts(root):
    """[{file}] das LUTs válidas em `<dados>/luts`."""
    folder = Path(root) / 'luts'
    found = []
    if folder.is_dir():
        for file in sorted(folder.glob('*.cube')):
            try:
                size, _ = read_cube(file)
                found.append(dict(file=file.name, size=size))
            except (LutError, OSError):
                continue
    return found
