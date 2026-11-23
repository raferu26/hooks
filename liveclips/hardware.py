"""Codificação por placa de vídeo (NVENC, QSV, AMF) com teste real e retorno automático para a CPU.

Nada aqui presume que a placa existe: o FFmpeg só lista o codificador se foi compilado com ele, e só um
teste de codificação de 1 segundo mostra se o driver/placa realmente o aceita. O resultado do teste
fica em memória durante o processo. Qualquer falha cai para libx264, que sempre funciona.
"""
import subprocess

from . import media

ENCODERS = {
    'nvenc': dict(name='h264_nvenc', label='NVIDIA (NVENC)'),
    'qsv': dict(name='h264_qsv', label='Intel (Quick Sync)'),
    'amf': dict(name='h264_amf', label='AMD (AMF)'),
}
CHOICES = ('auto', 'cpu') + tuple(ENCODERS)
CPU_FINAL = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18']
CPU_DRAFT = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '30']

_CACHE = {}


def arguments(kind):
    """Parâmetros do modo Equilibrado para cada fabricante (também usados no teste de 1 segundo)."""
    return mode_arguments(kind, 'equilibrado')


# Ajustes por placa e modo. Não são equivalentes ao x264: cada fabricante tem escala própria de qualidade.
# Valores conservadores (opções aceitas por drivers antigos); se a placa recusar, o render refaz na CPU.
GPU_MODES = {
    'nvenc': {
        'rapido': ['-preset', 'p3', '-rc', 'vbr', '-cq', '23', '-b:v', '0', '-spatial-aq', '1'],
        'equilibrado': ['-preset', 'p5', '-rc', 'vbr', '-cq', '20', '-b:v', '0', '-spatial-aq', '1'],
        'qualidade': ['-preset', 'p7', '-tune', 'hq', '-rc', 'vbr', '-cq', '18', '-b:v', '0', '-spatial-aq', '1', '-bf', '3'],
    },
    'qsv': {
        'rapido': ['-global_quality', '24', '-preset', 'faster'],
        'equilibrado': ['-global_quality', '20', '-preset', 'slow'],
        'qualidade': ['-global_quality', '18', '-preset', 'veryslow'],
    },
    'amf': {
        'rapido': ['-quality', 'speed', '-rc', 'cqp', '-qp_i', '23', '-qp_p', '25'],
        'equilibrado': ['-quality', 'quality', '-rc', 'cqp', '-qp_i', '19', '-qp_p', '21'],
        'qualidade': ['-quality', 'quality', '-rc', 'cqp', '-qp_i', '17', '-qp_p', '19'],
    },
}


def mode_arguments(kind, mode):
    """Argumentos do codificador `kind` ('cpu', 'nvenc', 'qsv', 'amf') no modo de qualidade."""
    from . import telemetry
    mode = telemetry.mode_name(mode)
    if kind not in ENCODERS or telemetry.MODES[mode]['cpu_only']:
        return telemetry.cpu_args(mode)
    return ['-c:v', ENCODERS[kind]['name'], *GPU_MODES[kind][mode]]


def listed(output):
    """Quais codificadores a lista do FFmpeg menciona (não prova que funcionam)."""
    text = str(output or '')
    return [kind for kind, item in ENCODERS.items() if item['name'] in text]


def works(kind, runner=None):
    """Teste real: codifica 1 segundo de vídeo de teste com o codificador."""
    key = (kind,)
    if runner is None and key in _CACHE:
        return _CACHE[key]
    runner = runner or media.run
    try:
        runner([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                'testsrc2=size=1280x720:rate=30:duration=1', *arguments(kind), '-pix_fmt', 'yuv420p', '-f', 'null', '-'], 60)
        ok = True
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
        ok = False
    if runner is media.run:
        _CACHE[key] = ok
    return ok


def detect(runner=None):
    """Lista os codificadores de placa de vídeo que passaram no teste, na ordem de preferência."""
    runner = runner or media.run
    try:
        text = runner([media.tool('ffmpeg'), '-hide_banner', '-encoders'], 30)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
        return []
    return [kind for kind in listed(text) if works(kind, runner if runner is not media.run else None)]


def status():
    """Resumo para a tela de ajustes."""
    found = detect()
    return dict(available=[dict(id=k, label=ENCODERS[k]['label']) for k in found], cpu=True)


def choose(preference='auto', draft=False, force_cpu=False, mode='equilibrado'):
    """Retorna (tipo, argumentos). Rascunhos e `force_cpu` usam sempre a CPU; o modo Entrega também
    (x264 lento), porque prioriza a imagem sobre o tempo."""
    from . import telemetry
    if draft:
        return 'cpu', list(CPU_DRAFT)
    mode = telemetry.mode_name(mode)
    if force_cpu or preference == 'cpu' or telemetry.MODES[mode]['cpu_only']:
        return 'cpu', mode_arguments('cpu', mode)
    found = detect()
    kind = preference if preference in ENCODERS else (found[0] if found else 'cpu')
    if kind != 'cpu' and kind not in found:
        return 'cpu', mode_arguments('cpu', mode)
    return kind, mode_arguments(kind, mode)
