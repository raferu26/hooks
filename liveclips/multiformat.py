"""Exportação automática em vários formatos (P23).

As variantes (1:1, 4:5, 16:9) saem do MESMO plano de edição do vertical: o render recalcula quadro, margens das
legendas, títulos e área útil para cada proporção (`media._render_single(variant=...)`). Este módulo decide quais
formatos entram (perfil + projeto), valida cada arquivo depois de codificado e deriva a legenda `.srt` opcional.
Publicação em redes não faz parte do módulo.
"""
import re

FORMATS = ('1x1', '4x5', '16x9')

# Preset local de cada saída. O codificador (CPU ou placa de vídeo já testada) é escolhido em `hardware.choose`; a
# placa só entra depois de um teste real de 1 s, com retorno automático para a CPU.
PRESETS = {
    '9x16': dict(size=(1080, 1920), codec='h264', pix_fmt='yuv420p', audio='aac', container='mp4'),
    '1x1': dict(size=(1080, 1080), codec='h264', pix_fmt='yuv420p', audio='aac', container='mp4'),
    '4x5': dict(size=(1080, 1350), codec='h264', pix_fmt='yuv420p', audio='aac', container='mp4'),
    '16x9': dict(size=(1920, 1080), codec='h264', pix_fmt='yuv420p', audio='aac', container='mp4'),
}
DURATION_TOLERANCE = .35      # segundos de diferença aceitos entre a variante e o vertical principal


def clean_formats(value):
    """Lista de formatos extras válidos, sem repetição e em ordem fixa. Valor inválido → ValueError."""
    if value in (None, ''):
        return []
    if not isinstance(value, (list, tuple)) or any(v not in FORMATS for v in value):
        raise ValueError('Formato extra inválido (use 1x1, 4x5 ou 16x9).')
    return [f for f in FORMATS if f in value]


def selected(profile, project=None):
    """Formatos extras de um corte = os do perfil + os escolhidos no Estúdio (união, ordem fixa)."""
    wanted = set((profile or {}).get('export_formats') or []) | set((project or {}).get('formats') or [])
    return [f for f in FORMATS if f in wanted]


def check_variant(path, fmt, main_info, probe):
    """Confere a variante já codificada. → (erros, avisos). `probe` é media.probe (injetável para teste).

    Erro = arquivo inutilizável (medidas, codec, pixel format, sem vídeo, sem áudio quando o principal tem).
    Aviso = diferença de duração acima da tolerância."""
    errors, warnings = [], []
    try:
        info = probe(path)
    except Exception as exc:
        return [f'não consegui ler o arquivo ({str(exc)[:80]})'], warnings
    preset = PRESETS[fmt]
    if (info.get('width'), info.get('height')) != preset['size']:
        errors.append(f"medidas {info.get('width')}x{info.get('height')} (esperado {preset['size'][0]}x{preset['size'][1]})")
    codec = info.get('video_codec') or info.get('codec')
    if codec and codec != preset['codec']:
        errors.append(f'codec de vídeo {codec} (esperado {preset["codec"]})')
    pix = info.get('pix_fmt')
    if pix and pix != preset['pix_fmt']:
        errors.append(f'pixel format {pix} (esperado {preset["pix_fmt"]})')
    if main_info.get('has_audio') and not info.get('has_audio'):
        errors.append('sem áudio, mas o vertical principal tem')
    main_duration = float(main_info.get('duration') or 0)
    if main_duration and abs(float(info.get('duration') or 0) - main_duration) > DURATION_TOLERANCE:
        warnings.append(f"duração {float(info.get('duration') or 0):.2f}s difere do principal ({main_duration:.2f}s)")
    return errors, warnings


def _srt_time(seconds):
    ms = int(round(max(0.0, seconds) * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def srt_from_ass(ass_text):
    """Legenda .srt derivada do ASS final (mesmos tempos e textos do vídeo). Eventos consecutivos iguais viram um só."""
    from . import subtitles
    rows = [(a, b, re.sub(r'\s+', ' ', t).strip()) for a, b, t in subtitles.parse_ass(ass_text)]
    rows = sorted([r for r in rows if r[2] and r[1] > r[0]])
    merged = []
    for a, b, text in rows:
        if merged and merged[-1][2] == text and a - merged[-1][1] < .12:
            merged[-1] = (merged[-1][0], b, text)
        else:
            merged.append((a, b, text))
    return ''.join(f'{i}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n\n' for i, (a, b, text) in enumerate(merged, 1))
