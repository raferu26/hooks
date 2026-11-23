"""Controle de qualidade automático da exportação.

Roda depois de cada exportação e guarda um relatório curto no corte. Nunca bloqueia nem apaga o arquivo:
o relatório só avisa o que vale olhar antes de postar. Cada item tem `status` ok | atencao | erro.

Limites: a zona segura do TikTok NÃO é um número oficial (as referências públicas divergem: 250–528 px
embaixo, 120–220 px em cima, 100–185 px à direita em 1080×1920). Usamos valores conservadores em ZONAS e
tratamos qualquer invasão como "atenção", nunca como erro. As checagens de legenda leem o arquivo .ass
da exportação (estimativa por tamanho de fonte, não por pixels renderizados).
"""
import math
import re

from . import media

ZONAS = dict(top=160, bottom=480, right=150, left=60)  # px em 1080×1920
LUFS_TOLERANCIA = (1.5, 3.0)  # atenção a partir de 1,5 LU de distância do alvo; erro a partir de 3
PICO_ATENCAO = .3  # dB acima do limite de pico verdadeiro configurado
PRETO_MIN = .4  # s
LEITURA_MAX_CPS = 25  # caracteres por segundo
CHAR_LARGURA = .56  # largura média de um caractere em negrito (fração do tamanho da fonte)
LINHAS_MAX = 3


def item(id_, label, status, detail=''):
    return dict(id=id_, label=label, status=status, detail=detail)


def _tempo(value):
    h, m, s = value.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def _strip_tags(text):
    return re.sub(r'\{[^}]*\}', '', text).replace('\\N', ' ').replace('\\n', ' ')


def parse_ass(text):
    """→ (play_x, play_y, {estilo: dict(size, margin_v, margin_l, margin_r, align)}, [eventos])."""
    play_x, play_y = 720, 1280
    styles, events = {}, []
    style_fields = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('PlayResX:'):
            play_x = int(float(line.split(':')[1]))
        elif line.startswith('PlayResY:'):
            play_y = int(float(line.split(':')[1]))
        elif line.startswith('Format:') and 'Fontname' in line:
            style_fields = [f.strip() for f in line.split(':', 1)[1].split(',')]
        elif line.startswith('Style:') and style_fields:
            values = [v.strip() for v in line.split(':', 1)[1].split(',')]
            row = dict(zip(style_fields, values))
            try:
                styles[row['Name']] = dict(size=float(row['Fontsize']), margin_v=float(row['MarginV']),
                                           margin_l=float(row['MarginL']), margin_r=float(row['MarginR']),
                                           align=int(row['Alignment']))
            except (KeyError, ValueError):
                continue
        elif line.startswith('Dialogue:'):
            parts = line.split(':', 1)[1].split(',', 9)
            if len(parts) < 10:
                continue
            try:
                events.append(dict(start=_tempo(parts[1].strip()), end=_tempo(parts[2].strip()), style=parts[3].strip(),
                                   margin_v=int(parts[7] or 0), text=_strip_tags(parts[9]).strip()))
            except ValueError:
                continue
    return play_x, play_y, styles, events


def _block(event, style, play_x):
    """Estimativa do bloco de texto: (linhas, altura em PlayRes, maior palavra em PlayRes)."""
    size = style['size']
    avail = max(50, play_x - style['margin_l'] - style['margin_r'])
    text = event['text']
    width = len(text) * size * CHAR_LARGURA
    words = text.split() or ['']
    longest = max(len(w) for w in words) * size * CHAR_LARGURA
    lines = max(1, math.ceil(width / avail))
    return lines, lines * size * 1.2, longest, avail


def caption_checks(ass_text, duration, canvas=(1080, 1920)):
    """Legenda cortada no fim, sobrecarga de leitura, linhas demais e invasão da área do app."""
    play_x, play_y, styles, events = parse_ass(ass_text)
    if not events:
        return [item('legendas', 'Legendas', 'ok', 'Sem legendas neste vídeo.')]
    scale = canvas[1] / play_y  # PlayRes → pixels finais
    out = []
    cut = [e for e in events if e['start'] < duration - .05 and e['end'] > duration + .15]
    late = [e for e in events if e['start'] >= duration - .05]
    if cut or late:
        sample = (cut or late)[0]['text'][:50]
        out.append(item('legenda_cortada', 'Legenda cortada no fim', 'erro',
                        f'{len(cut) + len(late)} fala(s) passam do fim do vídeo (ex.: "{sample}"). Estenda o corte ou ajuste o final.'))
    else:
        out.append(item('legenda_cortada', 'Legenda cortada no fim', 'ok'))
    fast = []
    for e in events:
        span = max(.05, e['end'] - e['start'])
        if len(e['text']) / span > LEITURA_MAX_CPS and len(e['text']) > 8:
            fast.append(e)
    out.append(item('leitura', 'Velocidade de leitura', 'atencao' if len(fast) >= 2 else 'ok',
                    f'{len(fast)} legenda(s) acima de {LEITURA_MAX_CPS} caracteres por segundo.' if len(fast) >= 2 else ''))
    tall, wide, zone_bottom, zone_top = [], [], [], []
    for e in events:
        style = styles.get(e['style'])
        if not style:
            continue
        lines, height, longest, avail = _block(e, style, play_x)
        if lines > LINHAS_MAX:
            tall.append(e)
        if longest > avail:
            wide.append(e)
        margin = e['margin_v'] or style['margin_v']
        if style['align'] in (1, 2, 3):  # ancorado embaixo
            bottom_edge_px = margin * scale
            if bottom_edge_px < ZONAS['bottom'] - 20:
                zone_bottom.append((e, ZONAS['bottom'] - bottom_edge_px, margin))
        elif style['align'] in (7, 8, 9):  # ancorado em cima
            if margin * scale < ZONAS['top'] - 20:
                zone_top.append((e, ZONAS['top'] - margin * scale, margin))
    out.append(item('linhas', 'Tamanho das legendas', 'atencao' if tall or wide else 'ok',
                    (f'{len(tall)} legenda(s) com mais de {LINHAS_MAX} linhas. ' if tall else '') +
                    ('Há palavra mais larga que a tela. ' if wide else '')))
    if zone_bottom:
        worst = max(d for _, d, _ in zone_bottom)
        needed = math.ceil((ZONAS['bottom'] + 20) / scale)
        out.append(item('zona_inferior', 'Legenda na área do app (embaixo)', 'atencao',
                        f'A base da legenda fica a {round(ZONAS["bottom"] - worst)} px do fim; o TikTok costuma cobrir cerca de '
                        f'{ZONAS["bottom"]} px (valor aproximado, não oficial). Aumente a distância da legenda para ~{needed} ou mais.'))
    else:
        out.append(item('zona_inferior', 'Legenda na área do app (embaixo)', 'ok'))
    if zone_top:
        out.append(item('zona_superior', 'Texto na área do app (topo)', 'atencao',
                        f'Texto a menos de {ZONAS["top"]} px do topo, onde ficam as abas do TikTok.'))
    else:
        out.append(item('zona_superior', 'Texto na área do app (topo)', 'ok'))
    return out


def audio_checks(measure, target=-16.0, peak_limit=-1.5):
    """`measure`: dict(input_i, input_tp) do loudnorm em modo de medição, ou None quando o áudio é mudo."""
    if not measure:
        return [item('volume', 'Volume (LUFS)', 'erro', 'O áudio está mudo ou abaixo do que dá para medir.'),
                item('pico', 'Pico de áudio', 'ok')]
    loud = float(measure['input_i'])
    off = loud - target
    status = 'erro' if abs(off) >= LUFS_TOLERANCIA[1] else 'atencao' if abs(off) >= LUFS_TOLERANCIA[0] else 'ok'
    detail = '' if status == 'ok' else f'{loud:.1f} LUFS medido, alvo {target:.0f} ({off:+.1f} LU). ' + (
        'Mais baixo que o padrão: pode soar fraco no feed.' if off < 0 else 'Mais alto que o padrão: a plataforma pode comprimir.')
    tp = float(measure['input_tp'])
    peak = 'erro' if tp > -.3 else 'atencao' if tp > peak_limit + PICO_ATENCAO else 'ok'
    return [item('volume', 'Volume (LUFS)', status, detail or f'{loud:.1f} LUFS'),
            item('pico', 'Pico de áudio', peak, '' if peak == 'ok' else f'Pico verdadeiro de {tp:.1f} dBTP: pode distorcer após a compressão da plataforma.')]


def black_checks(intervals, duration):
    """`intervals`: [(início, fim)] de quadros pretos. Ignora só o que tem menos de PRETO_MIN."""
    long = [(a, b) for a, b in intervals if b - a >= PRETO_MIN]
    total = sum(b - a for a, b in long)
    if not long:
        return item('preto', 'Quadros pretos', 'ok')
    status = 'erro' if total > duration * .5 else 'atencao'
    spots = ', '.join(f'{a:.1f}–{b:.1f}s' for a, b in long[:3])
    return item('preto', 'Quadros pretos', status, f'{len(long)} trecho(s) preto(s) ({total:.1f}s no total): {spots}.')


def parse_blackdetect(stderr):
    pairs = []
    for match in re.finditer(r'black_start:([\d.]+)\s+black_end:([\d.]+)', stderr):
        pairs.append((float(match.group(1)), float(match.group(2))))
    return pairs


def format_checks(info, expected, canvas):
    out = []
    size = (info['width'], info['height'])
    out.append(item('formato', 'Formato do vídeo', 'ok' if size == tuple(canvas) else 'atencao',
                    '' if size == tuple(canvas) else f'{size[0]}×{size[1]} em vez de {canvas[0]}×{canvas[1]}.'))
    if expected:
        diff = abs(info['duration'] - expected)
        out.append(item('duracao', 'Duração', 'ok' if diff <= 1.0 else 'atencao',
                        '' if diff <= 1.0 else f'Saiu com {info["duration"]:.1f}s; o editor previa {expected:.1f}s.'))
    out.append(item('audio', 'Faixa de áudio', 'ok' if info.get('has_audio') else 'erro',
                    '' if info.get('has_audio') else 'O arquivo exportado não tem áudio.'))
    return out


def summarize(items):
    errors = sum(i['status'] == 'erro' for i in items)
    warns = sum(i['status'] == 'atencao' for i in items)
    level = 'erro' if errors else 'atencao' if warns else 'ok'
    text = 'Tudo certo nas checagens automáticas.' if level == 'ok' else (
        f'{errors} problema(s) e {warns} aviso(s): ' + '; '.join(i['label'] for i in items if i['status'] != 'ok') + '.')
    return dict(level=level, errors=errors, warnings=warns, summary=text)


def measure_loudness(path, timeout=300):
    stderr = media.run_stderr([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(path), '-vn',
                               '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], timeout=timeout)
    return media.parse_loudness(stderr)


def detect_black(path, timeout=300):
    stderr = media.run_stderr([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(path), '-an',
                               '-vf', f'scale=160:-2,blackdetect=d={PRETO_MIN}:pic_th=.98:pix_th=.10', '-f', 'null', '-'],
                              timeout=timeout)
    return parse_blackdetect(stderr)


def check_export(video, ass_path=None, expected_duration=None, canvas=(1080, 1920), target=None, peak_limit=None,
                 visual=True, planned_freezes=(), fonts_dir=None, samples_dir=None, ai=True):
    """Relatório completo de um arquivo exportado. Nunca levanta: uma checagem que falha vira item 'atencao'."""
    from pathlib import Path
    target = media.LOUDNESS['I'] if target is None else target
    peak_limit = media.LOUDNESS['TP'] if peak_limit is None else peak_limit
    items = []
    try:
        info = media.probe(video)
    except Exception as exc:  # arquivo ilegível
        return dict(level='erro', errors=1, warnings=0, summary='Não foi possível ler o arquivo exportado.',
                    items=[item('arquivo', 'Arquivo exportado', 'erro', str(exc)[:200])])
    items += format_checks(info, expected_duration, canvas)
    if info.get('has_audio'):
        try:
            items += audio_checks(measure_loudness(video), target, peak_limit)
        except Exception as exc:
            items.append(item('volume', 'Volume (LUFS)', 'atencao', 'Não consegui medir o volume: ' + str(exc)[:120]))
    try:
        items.append(black_checks(detect_black(video), info['duration']))
    except Exception as exc:
        items.append(item('preto', 'Quadros pretos', 'atencao', 'Não consegui checar quadros pretos: ' + str(exc)[:120]))
    if ass_path and Path(ass_path).is_file():
        try:
            items += caption_checks(Path(ass_path).read_text(encoding='utf-8-sig'), info['duration'], canvas)
        except Exception as exc:
            items.append(item('legendas', 'Legendas', 'atencao', 'Não consegui checar as legendas: ' + str(exc)[:120]))
    samples = []
    if visual:
        from . import qc_visual
        extra, samples = qc_visual.visual_checks(video, info['duration'], ass_path, canvas, ZONAS, planned_freezes, fonts_dir,
                                                 samples_dir, bool(info.get('has_audio')), ai)
        measured = any(i['id'] == 'legenda_render' and not i['detail'].startswith(('Não consegui', 'O vídeo tem legenda'))
                       for i in extra)
        if measured:   # a legenda desenhada de verdade vale mais que a estimativa pelo tamanho da fonte
            items = [i for i in items if i['id'] != 'zona_inferior']
        items += extra
    return dict(summarize(items), items=items, zones=dict(ZONAS), approximate_zones=True, samples=samples)


def manifest_checks(folder):
    """Itens do QC vindos do que o render e as capas registraram na pasta do corte (recuos, filtros ausentes, capa fraca)."""
    import json
    from pathlib import Path
    out = []
    folder = Path(folder)
    try:
        manifest = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        manifest = {}
    recuo = manifest.get('recuo')
    if recuo:
        out.append(item('recuo', 'Plano B no render', 'atencao',
                        'O render falhou com ' + ', '.join(recuo.get('modulos', [])) + ' ligado(s); exportei sem eles. Veja manifesto.json.'))
    if manifest.get('fallback') or manifest.get('pipeline') == 'legacy':
        out.append(item('plano_b', 'Método antigo de render', 'atencao', 'O render em uma passada falhou e o método antigo foi usado.'))
    if manifest.get('voice_skipped'):
        out.append(item('voz_filtro', 'Filtro de voz ausente', 'atencao',
                        'Este FFmpeg não tem: ' + ', '.join(manifest['voice_skipped']) + '. A voz saiu sem esses filtros.'))
    if manifest.get('overlay_warnings'):
        out.append(item('imagem_efeito', 'Efeito de imagem não aplicado', 'atencao', '; '.join(manifest['overlay_warnings'])[:200]))
    motion = manifest.get('motion') or {}
    if motion.get('avisos'):
        out.append(item('grafico', 'Gráfico animado não aplicado', 'atencao', '; '.join(motion['avisos'])[:200]))
    if manifest.get('stabilize_skipped'):
        out.append(item('estabilizacao', 'Estabilização não aplicada', 'atencao', manifest['stabilize_skipped']))
    try:
        cover = json.loads((folder / 'capa.json').read_text(encoding='utf-8'))
        if cover.get('weak'):
            out.append(item('capa', 'Capa tecnicamente fraca', 'atencao', 'Nenhum quadro amostrado ficou nítido e bem exposto; confira as alternativas.'))
    except (OSError, ValueError):
        pass
    return out


def as_text(report):
    """Texto simples para o arquivo qualidade.txt ao lado do vídeo."""
    marks = dict(ok='OK', atencao='ATENÇÃO', erro='PROBLEMA')
    lines = ['Controle de qualidade automático — ' + report['summary'], '']
    for it in report['items']:
        lines.append(f"[{marks[it['status']]}] {it['label']}" + (f" — {it['detail']}" if it['detail'] else ''))
    lines += ['', 'As zonas do TikTok são aproximadas (não há medida oficial); trate como guia, não como regra.']
    return '\n'.join(lines) + '\n'
