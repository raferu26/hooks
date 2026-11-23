"""Inventário técnico da mídia de entrada (F01): o que o arquivo é, antes de qualquer corte.

Não altera `media.probe` (sua assinatura entra no cache de renders). Serve para avisar riscos reais ao usuário:
taxa de quadros variável, rotação, HDR, várias faixas de áudio, 10 bits, ausência de áudio.
"""
import json
from fractions import Fraction

from . import media

HDR_TRANSFERS = ('smpte2084', 'arib-std-b67')


def _ratio(text):
    try:
        value = Fraction(str(text))
        return value if value > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def parse(data):
    """`data`: saída JSON do ffprobe (-show_streams -show_format). Puro, para testar sem arquivos."""
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    if not video:
        raise ValueError('O arquivo não contém vídeo.')
    avg, real = _ratio(video.get('avg_frame_rate')), _ratio(video.get('r_frame_rate'))
    vfr = bool(avg and real and abs(float(avg) - float(real)) / float(real) > .01)
    rotation = 0
    for side in video.get('side_data_list') or []:
        if 'rotation' in side:
            rotation = int(round(float(side['rotation']))) % 360
    if not rotation and (video.get('tags') or {}).get('rotate'):
        rotation = int(float(video['tags']['rotate'])) % 360
    width, height = int(video.get('width', 0)), int(video.get('height', 0))
    shown = (height, width) if rotation in (90, 270) else (width, height)
    transfer = video.get('color_transfer') or ''
    bits = int(video.get('bits_per_raw_sample') or 0) or (10 if '10' in str(video.get('pix_fmt', '')) else 8)
    info = dict(
        duration=float(data.get('format', {}).get('duration') or video.get('duration') or 0),
        codec=video.get('codec_name'), pix_fmt=video.get('pix_fmt'), bit_depth=bits,
        stored_size=[width, height], display_size=list(shown), rotation=rotation,
        fps=float(avg or real or 0), fps_real=float(real or 0), vfr=vfr,
        color=dict(space=video.get('color_space'), primaries=video.get('color_primaries'), transfer=transfer or None, range=video.get('color_range')),
        hdr=transfer in HDR_TRANSFERS,
        audio=[dict(codec=a.get('codec_name'), channels=a.get('channels'), sample_rate=a.get('sample_rate')) for a in audios],
    )
    risks = []
    if vfr:
        risks.append(dict(id='vfr', level='atencao', message='Taxa de quadros variável: áudio e legendas podem sair do sincronismo. Converta para taxa fixa antes de editar.'))
    if rotation:
        risks.append(dict(id='rotacao', level='atencao', message=f'O arquivo tem rotação de {rotation}°; confira se o enquadramento está do lado certo.'))
    if info['hdr']:
        risks.append(dict(id='hdr', level='atencao', message='Vídeo HDR: o programa entrega SDR (BT.709), então as cores podem mudar. Revise o resultado.'))
    if bits > 8:
        risks.append(dict(id='10bits', level='info', message=f'Vídeo de {bits} bits; a saída é convertida para 8 bits.'))
    if not audios:
        risks.append(dict(id='sem_audio', level='atencao', message='O arquivo não tem áudio: legendas por fala e mixagem não se aplicam.'))
    if len(audios) > 1:
        risks.append(dict(id='varias_faixas', level='atencao', message=f'{len(audios)} faixas de áudio; só a primeira é usada. Se o jogo e a voz estão separados, mixe antes.'))
    info['risks'] = risks
    return info


def describe(path):
    data = json.loads(media.run([media.tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], 60))
    return parse(data)
