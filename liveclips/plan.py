"""Plano de edição versionado (F02, F03): o que o render faz, descrito em dados verificáveis.

Três domínios de tempo ficam separados: relógio de captura da live, tempo da fonte (cada arquivo) e tempo da saída.
Tudo aqui é inteiro (ticks de 1/90000 s), com intervalos semiabertos [início, fim). O plano nunca contém comandos:
só dados que um validador confere e um compilador conhece. Ele é montado a partir dos MESMOS trechos que o render usa
(`media.plan_pieces`), então descreve o vídeo que sai, não uma intenção.
"""
import hashlib
import json
import math
from fractions import Fraction

SCHEMA = 'liveclips.edit_plan'
VERSION = 1
TPS = 90000                       # ticks por segundo (múltiplo de 24, 25, 30, 50, 60 e dos frames de 30000/1001)
SPEED = (Fraction(1, 4), Fraction(4))
KINDS = ('main', 'teaser', 'replay', 'freeze')
TOP_KEYS = {'schema', 'version', 'job_id', 'source_assets', 'output', 'story', 'segments', 'layout_events', 'captions',
            'audio', 'effects', 'memory_refs', 'qa_policy_ref', 'decisions', 'created_by'}
SEGMENT_KEYS = {'occurrence_id', 'asset_id', 'kind', 'source_in', 'source_out', 'out_start', 'out_end', 'speed', 'mute',
                'ramp_group'}


def ticks(seconds):
    """Segundos -> ticks, arredondando metade para cima (política única de arredondamento)."""
    return int(math.floor(float(seconds) * TPS + .5))


def seconds(value):
    return value / TPS


def frame_index(tick, fps=(30, 1)):
    """Frame que contém o instante `tick` (frame f cobre [f/fps, (f+1)/fps))."""
    return int(Fraction(tick) * fps[0] / (TPS * fps[1]))


def frame_round(tick, fps=(30, 1)):
    """Frame mais próximo de um instante (usado para pôr legendas e eventos em frames)."""
    value = Fraction(tick) * fps[0] / (TPS * fps[1])
    return int(math.floor(value + Fraction(1, 2)))


def _fps_of(value):
    fps = float(value or 30)
    for num, den in ((24000, 1001), (30000, 1001), (60000, 1001)):
        if abs(fps - num / den) < .01:
            return (num, den)
    return (int(round(fps)), 1)


# ───────────────────────── mapa de tempo ─────────────────────────

def _rate(segment):
    return float(Fraction(segment.get('speed', '1')))


class TimeMap:
    """Ocorrências (trechos da saída) -> tempo da fonte e vice-versa. Uma origem pode aparecer várias vezes (replay)."""

    def __init__(self, segments):
        self.segments = sorted((dict(s) for s in segments), key=lambda s: s['out_start'])

    @property
    def duration(self):
        return max((s['out_end'] for s in self.segments), default=0)

    def to_output(self, asset_id, source_tick):
        """Todos os (occurrence_id, tick de saída) em que o instante da fonte aparece. Vazio = foi cortado."""
        found = []
        for s in self.segments:
            if s['asset_id'] != asset_id or s['kind'] == 'freeze' or not s['source_in'] <= source_tick < s['source_out']:
                continue
            found.append((s['occurrence_id'], s['out_start'] + int(round((source_tick - s['source_in']) / _rate(s)))))
        return found

    def to_source(self, out_tick):
        for s in self.segments:
            if s['out_start'] <= out_tick < s['out_end']:
                if s['kind'] == 'freeze':
                    return s['occurrence_id'], s['asset_id'], s['source_in']
                return s['occurrence_id'], s['asset_id'], s['source_in'] + int(round((out_tick - s['out_start']) * _rate(s)))
        return None

    def words(self, asset_id, words, keep_cut_overlap=.5):
        """Palavras da fonte (em segundos) -> uma entrada por ocorrência, com tempos de saída em ticks.

        Palavra que atravessa um corte: fica se pelo menos `keep_cut_overlap` dela está dentro do trecho mantido
        (marcada `partial`); senão é descartada naquela ocorrência. Nunca se subtrai um deslocamento global."""
        result = []
        for word in words:
            a, b = ticks(word['start']), ticks(word['end'])
            if b <= a:
                continue
            for s in self.segments:
                if s['asset_id'] != asset_id or s['kind'] == 'freeze':
                    continue
                x, y = max(a, s['source_in']), min(b, s['source_out'])
                if y <= x or (y - x) / (b - a) < keep_cut_overlap:
                    continue
                rate = _rate(s)
                result.append(dict(word=word.get('word', ''), occurrence_id=s['occurrence_id'],
                                   out_start=s['out_start'] + int(round((x - s['source_in']) / rate)),
                                   out_end=s['out_start'] + int(round((y - s['source_in']) / rate)),
                                   partial=(x, y) != (a, b), source_start=a, source_end=b))
        result.sort(key=lambda r: (r['out_start'], r['out_end']))
        return result


# ───────────────────────── montagem do plano ─────────────────────────

def assets_of(parts):
    """IDs de ativo estáveis por arquivo (hash do conteúdo quando existe), sem caminhos absolutos."""
    result = {}
    for index, part in enumerate(parts):
        sha = str(part.get('sha') or '')
        result[index] = dict(asset_id=f'src{index}:{sha[:12]}' if sha else f'src{index}', sha256=sha or None,
                             clip_in=ticks(part['in']), clip_out=ticks(part['out']))
    return result


def build(candidate_id, parts, pieces, duration, fps=30, canvas=(1080, 1920), project=None, story=None, decisions=None,
          memory_refs=None, qa_policy='essencial_v1', layout_events=None, profile_ref=None, created_by='liveclips', teaser_count=0):
    """Plano a partir dos trechos que o render realmente usa (`pieces` de `media.plan_pieces`)."""
    assets = assets_of(parts)
    segments = []
    cursor = 0
    ramp_of = {}
    for v in (project or {}).get('speeds', []):
        if v.get('ramp'):
            ramp_of[(round(float(v['start']), 3), round(float(v['end']), 3))] = v['ramp']
    for n, piece in enumerate(pieces):
        index, a, b, rate, hold = piece[:5]
        mute = bool(piece[5]) if len(piece) > 5 else False
        replay = len(piece) > 5
        asset = assets[index]
        if hold:
            length = ticks(hold)
            kind = 'freeze'
            seg = dict(occurrence_id=f'o{n}', asset_id=asset['asset_id'], kind=kind, source_in=ticks(a), source_out=ticks(a) + 1,
                       out_start=cursor, out_end=cursor + length, speed='0', mute=True)
        else:
            src_in, src_out = ticks(a), ticks(b)
            speed = Fraction(float(rate)).limit_denominator(1000)
            length = int(round((src_out - src_in) / float(speed)))
            seg = dict(occurrence_id=f'o{n}', asset_id=asset['asset_id'], kind='replay' if replay else 'teaser' if n < teaser_count else 'main', source_in=src_in, source_out=src_out,
                       out_start=cursor, out_end=cursor + length, speed=f'{speed.numerator}/{speed.denominator}', mute=mute)
        segments.append(seg)
        cursor += length
    tags = list((project or {}).get('replays', []))
    plan = dict(
        schema=SCHEMA, version=VERSION, job_id=str(candidate_id), created_by=created_by,
        source_assets=[dict(asset_id=v['asset_id'], sha256=v['sha256'], clip_in=v['clip_in'], clip_out=v['clip_out'])
                       for v in assets.values()],
        output=dict(width=canvas[0], height=canvas[1], fps=dict(zip(('num', 'den'), _fps_of(fps))),
                    duration_ticks=cursor, duration_frames=frame_round(cursor, _fps_of(fps)), color_policy='sdr_bt709',
                    tps=TPS),
        story=story or dict(intent=None, preserve_chronology=True, evidence_ids=[]),
        segments=segments,
        layout_events=layout_events or [dict(start=0, end=cursor, recipe_id=(project or {}).get('layout', {}).get('mode', 'padrao')
                                             if (project or {}).get('layout') else 'padrao', profile_ref=profile_ref)],
        captions=dict(word_track_ref='palavras_remapeadas_v1', enabled=bool(((project or {}).get('captions') or {}).get('enabled', True))),
        audio=dict(mix_profile_ref='voz_primeiro_v1', loudness_target=-16.0, true_peak_max=-1.5),
        effects=effects_of(project, cursor),
        decisions=decisions or [],
        memory_refs=list(memory_refs or []),
        qa_policy_ref=qa_policy)
    if tags:
        plan['story']['replays'] = [r.get('id') for r in tags]
    return plan


def effects_of(project, total):
    """Efeitos do projeto como registros tipados (sem texto livre que vire comando)."""
    project = project or {}
    items = []
    for z in project.get('zooms', []):
        items.append(dict(id=z['id'], recipe='punch_in', start_s=z['start'], end_s=z['end'], params=dict(zoom=z['zoom'], curve=z.get('curve', 'smooth'))))
    for t in project.get('titles', []):
        items.append(dict(id=t['id'], recipe='titulo_contexto', start_s=t['start'], end_s=t['end'], params=dict(style=t['style'], position=t['position'])))
    for e in project.get('sfx', []):
        items.append(dict(id=e['id'], recipe='sfx_funcao', start_s=e['at'], end_s=e['at'] + .5, params=dict(kind=e['kind'], volume=e['volume'])))
    for f in project.get('freezes', []):
        items.append(dict(id=f['id'], recipe='congelar', start_s=f['at'], end_s=f['at'] + f['duration'], params={}))
    for r in project.get('replays', []):
        items.append(dict(id=r['id'], recipe='replay', start_s=r['start'], end_s=r['end'], params=dict(rate=r.get('rate', 1.0), mute=bool(r.get('mute', r.get('rate', 1.0) != 1.0)))))
    for v in project.get('speeds', []):
        items.append(dict(id=v['id'], recipe='velocidade_rampa' if v.get('ramp') else 'velocidade', start_s=v['start'], end_s=v['end'],
                          params=dict(rate=v['rate'])))
    for number, g in enumerate(project.get('motion', [])):
        items.append(dict(id=f'g{number}', recipe='grafico_motion', start_s=g['start'], end_s=g['start'] + g['duration'], params=dict(template=g['template'])))
    if project.get('music'):
        items.append(dict(id='musica', recipe='musica_ducking', start_s=0, end_s=seconds(total), params=dict(asset=project['music']['id'], duck=project['music'].get('duck', True))))
    for o in project.get('overlays', []):
        items.append(dict(id=o['id'], recipe='imagem_apoio', start_s=o['start'], end_s=o['end'], params=dict(asset=o['image'])))
    return items


# ───────────────────────── contrato: validar, gravar, ler ─────────────────────────

def timemap(plan):
    return TimeMap(plan['segments'])


def validate(plan, media=None, registry=None, tolerance_frames=1):
    """Lista de problemas (código, onde, mensagem). Vazia = plano aceito.

    `media`: {asset_id: duração da fonte em segundos} para conferir os limites. `registry`: módulo `capabilities`."""
    problems = []

    def bad(code, where, message):
        problems.append(dict(code=code, where=where, message=message))

    if not isinstance(plan, dict):
        return [dict(code='formato', where='/', message='O plano precisa ser um objeto.')]
    if plan.get('schema') != SCHEMA:
        bad('schema', 'schema', 'Esquema desconhecido.')
    if plan.get('version') != VERSION:
        bad('versao', 'version', f'Versão {plan.get("version")!r} não suportada (esperado {VERSION}).')
    for key in plan:
        if key not in TOP_KEYS:
            bad('campo_desconhecido', key, 'Campo não previsto no contrato.')
    assets = {a.get('asset_id') for a in plan.get('source_assets') or []}
    segments = plan.get('segments') or []
    if not segments:
        bad('sem_segmentos', 'segments', 'O plano não tem trechos.')
    seen = set()
    cursor = 0
    fps = (plan.get('output', {}).get('fps', {}).get('num', 30), plan.get('output', {}).get('fps', {}).get('den', 1))
    for i, s in enumerate(segments):
        where = f'segments[{i}]'
        for key in s:
            if key not in SEGMENT_KEYS:
                bad('campo_desconhecido', f'{where}.{key}', 'Campo não previsto.')
        if s.get('occurrence_id') in seen:
            bad('id_repetido', where, 'Dois trechos com o mesmo occurrence_id.')
        seen.add(s.get('occurrence_id'))
        if s.get('kind') not in KINDS:
            bad('tipo', where, 'Tipo de trecho desconhecido.')
        if s.get('asset_id') not in assets:
            bad('ativo_ausente', where, 'O trecho aponta para um ativo que não está em source_assets.')
        if not all(isinstance(s.get(k), int) for k in ('source_in', 'source_out', 'out_start', 'out_end')):
            bad('tipo_tempo', where, 'Os tempos precisam ser inteiros (ticks).')
            continue
        if s['out_end'] <= s['out_start'] or (s.get('kind') != 'freeze' and s['source_out'] <= s['source_in']):
            bad('intervalo', where, 'Intervalo vazio ou invertido (os intervalos são [início, fim)).')
        if s['out_start'] != cursor:
            bad('lacuna_ou_sobreposicao', where, f'O trecho começa em {s["out_start"]} e o anterior terminou em {cursor}.')
        cursor = s['out_end']
        try:
            speed = Fraction(s.get('speed', '1'))
        except (ValueError, ZeroDivisionError):
            bad('velocidade', where, 'Velocidade ilegível.')
            continue
        if s.get('kind') != 'freeze' and not SPEED[0] <= speed <= SPEED[1]:
            bad('velocidade', where, 'Velocidade fora de 0,25× a 4×.')
        if s.get('kind') != 'freeze':
            expected = (s['source_out'] - s['source_in']) / float(speed)
            if abs(expected - (s['out_end'] - s['out_start'])) > 1:
                bad('duracao_incoerente', where, 'A duração de saída não bate com a fonte e a velocidade.')
        if media and s.get('asset_id') in media:
            limit = ticks(media[s['asset_id']])
            if s.get('source_out', 0) > limit + ticks(.05):
                bad('fora_da_midia', where, 'O trecho passa do fim da mídia.')
    out = plan.get('output') or {}
    if segments and out.get('duration_ticks') != cursor:
        bad('duracao_total', 'output.duration_ticks', 'A duração declarada não bate com a soma dos trechos.')
    if out.get('duration_frames') is not None and abs(out['duration_frames'] - frame_round(cursor, fps)) > tolerance_frames:
        bad('duracao_frames', 'output.duration_frames', 'A duração em frames não bate com os ticks.')
    for i, ev in enumerate(plan.get('layout_events') or []):
        if not (isinstance(ev.get('start'), int) and isinstance(ev.get('end'), int) and 0 <= ev['start'] < ev['end'] <= cursor):
            bad('layout', f'layout_events[{i}]', 'Evento de layout fora da linha do tempo.')
    total_s = seconds(cursor)
    for i, fx in enumerate(plan.get('effects') or []):
        where = f'effects[{i}]'
        if not (0 <= fx.get('start_s', -1) <= fx.get('end_s', -1)) or fx.get('start_s', 0) > total_s + 1e-6 and fx.get('recipe') not in ('replay', 'velocidade', 'velocidade_rampa', 'congelar'):
            bad('efeito_intervalo', where, 'Efeito fora do clipe.')
        if registry is not None:
            for message in registry.check_use(fx.get('recipe'), fx.get('params') or {}):
                bad('efeito_invalido', where, message)
    for i, ref in enumerate(plan.get('memory_refs') or []):
        if not isinstance(ref, str) or not ref:
            bad('memoria', f'memory_refs[{i}]', 'Referência de memória inválida.')
    return problems


def dump(plan):
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(plan):
    """Hash do plano (sem campos de decisão/explicação): mesmo plano + mesmos ativos = mesmo hash."""
    core = {k: v for k, v in plan.items() if k not in ('decisions', 'created_by', 'story')}
    return hashlib.sha256(dump(core).encode()).hexdigest()


def load(text):
    plan = json.loads(text)
    problems = validate(plan)
    if problems:
        raise ValueError('Plano inválido: ' + '; '.join(p['message'] for p in problems[:3]))
    return plan


def compare_duration(plan, actual_seconds, fps=None):
    """Diferença entre o plano e o arquivo renderizado, em frames. Aceite do dossiê: até 1 frame quando o encoder permitir."""
    rate = _fps_of(fps) if fps else (plan['output']['fps']['num'], plan['output']['fps']['den'])
    planned = Fraction(plan['output']['duration_ticks'], TPS)
    delta = (Fraction(actual_seconds).limit_denominator(100000) - planned) * rate[0] / rate[1]
    return float(delta)
