"""Pacote de entrega (P13/F24): manifesto com hashes, linha do tempo OTIO e estados de entrega.

Estados (nenhum publica nada sozinho):
  em_revisao           render existe, mas a checagem falhou/bloqueou ou ainda não rodou;
  pronto_para_revisao  render e checagens sem bloqueio; falta o olhar humano;
  aprovado             uma pessoa aprovou ESTA versão (hash do vídeo registrado);
  pronto_para_publicar aprovado + sem bloqueio + pacote com hashes conferidos. A publicação continua sendo um ato manual.
"""
import hashlib
import json
import time
from fractions import Fraction
from pathlib import Path

from . import plan as planlib

STATES = ('em_revisao', 'pronto_para_revisao', 'aprovado', 'pronto_para_publicar')
FILES = ('plano.json', 'revisao.json', 'qualidade.txt', 'legendas.ass', 'manifesto.json', 'linha_do_tempo_limites.txt')


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            block = f.read(chunk)
            if not block:
                return h.hexdigest()
            h.update(block)


def delivery_state(qc_report=None, approval=None, package_ok=False, video_sha=None):
    """`approval`: {'by': ..., 'video_sha': ...} ou None. A aprovação só vale para o vídeo com aquele hash."""
    review = (qc_report or {}).get('review') or {}
    if not qc_report or review.get('bloqueia_pronto') or (qc_report or {}).get('level') == 'erro':
        return 'em_revisao'
    if review.get('veredito') in (None, 'indisponivel', 'bloqueado'):
        return 'em_revisao'
    if not approval or not approval.get('video_sha') or approval['video_sha'] != video_sha:
        return 'pronto_para_revisao'
    return 'pronto_para_publicar' if package_ok else 'aprovado'


# ───────────── OpenTimelineIO (JSON escrito à mão; sem dependência) ─────────────

def _rt(value, rate):
    return {'OTIO_SCHEMA': 'RationalTime.1', 'rate': rate, 'value': float(value)}


MARKER_COLORS = dict(punch_in='ORANGE', titulo_contexto='YELLOW', sfx_funcao='PINK', congelar='CYAN', replay='GREEN', velocidade='BLUE',
                     velocidade_rampa='BLUE', musica_ducking='PURPLE', imagem_apoio='MAGENTA', grafico_motion='RED')


def markers_from_plan(plan):
    """Efeitos do plano que o formato de intercâmbio só consegue representar como marcadores (nome, cor, intervalo em segundos)."""
    found = []
    for effect in plan.get('effects') or []:
        start = float(effect.get('start_s') or 0)
        end = max(start, float(effect.get('end_s') or start))
        found.append(dict(name=f"{effect.get('recipe')}: {effect.get('id')}", color=MARKER_COLORS.get(effect.get('recipe'), 'WHITE'),
                          start=start, duration=end - start, params=effect.get('params') or {}))
    return sorted(found, key=lambda m: (m['start'], m['name']))


def marker(item, rate):
    return {'OTIO_SCHEMA': 'Marker.2', 'name': item['name'], 'color': item['color'],
            'marked_range': {'OTIO_SCHEMA': 'TimeRange.1', 'start_time': _rt(item['start'] * rate, rate), 'duration': _rt(item['duration'] * rate, rate)},
            'metadata': {'liveclips': item['params']}, 'comment': ''}


def limits(plan, manifest=None):
    """O que o arquivo de intercâmbio NÃO leva (ou leva só como marcador), para ninguém esperar o visual final no editor."""
    manifest = manifest or {}
    profile = manifest.get('profile') or {}
    effects = plan.get('effects') or []
    count = lambda recipe: sum(1 for e in effects if e.get('recipe') == recipe)
    rows = []
    if count('punch_in'):
        rows.append(f"{count('punch_in')} zoom(s) de destaque: só como marcador; o zoom em si não é aplicado no editor.")
    if count('titulo_contexto'):
        rows.append(f"{count('titulo_contexto')} título(s): só como marcador; o texto estilizado não vai no arquivo.")
    if count('sfx_funcao'):
        rows.append(f"{count('sfx_funcao')} efeito(s) sonoro(s): só como marcador; o áudio do efeito não vai.")
    if count('imagem_apoio'):
        rows.append(f"{count('imagem_apoio')} imagem(ns) de apoio: só como marcador.")
    if count('grafico_motion'):
        rows.append(f"{count('grafico_motion')} gráfico(s) animado(s): só como marcador; a animação não vai.")
    if count('musica_ducking'):
        rows.append('Música e abaixamento automático (ducking): só como marcador; a trilha não vai.')
    rows.append('Legendas e títulos queimados no vídeo: o `legendas.ass` acompanha o pacote, mas não vai como faixa de legenda estilizada.')
    rows.append('Enquadramento vertical (corte/zoom/rastreio), fundo desfocado, layout de webcam e áreas borradas: não são transportados.')
    rows.append('Cor, LUT, voz (EQ/compressão), normalização de volume, estabilização e interpolação de câmera lenta: não são transportados.')
    rows.append('Transições: o Hook’s só usa fade curto de áudio nas emendas; nenhuma transição de vídeo vai no arquivo.')
    rows.append('Rampas de velocidade: vão como velocidade constante por trecho (LinearTimeWarp); a curva não é preservada.')
    active = [k for k in ('voice_preset', 'auto_color', 'lut', 'cut_fade', 'slow_interp', 'stabilize') if profile.get(k) not in (None, '', 'off')]
    if active:
        rows.append('Módulos ligados neste corte e não transportados: ' + ', '.join(active) + '.')
    rows.append('Saída achatada com tudo aplicado: o arquivo de vídeo exportado (clipe.mp4); use-o como referência visual.')
    return rows


def validate_otio(text):
    """Confere o arquivo com a biblioteca oficial quando ela está instalada. → dict(ok, versao, erro) ou None."""
    try:
        import opentimelineio as lib
    except ImportError:
        return None
    try:
        timeline = lib.adapters.read_from_string(text, 'otio_json')
        return dict(ok=True, versao=lib.__version__, clipes=len(list(timeline.find_clips())))
    except Exception as exc:
        return dict(ok=False, versao=getattr(lib, '__version__', ''), erro=str(exc)[:200])


def otio(plan, media_name='saida.mp4', source_names=None):
    """Linha do tempo de vídeo e de áudio com um clipe por ocorrência do plano.

    Velocidade ≠ 1 vira efeito LinearTimeWarp; congelamento vira FreezeFrame; as durações dos clipes são as da SAÍDA (em quadros),
    de modo que a soma bate com a duração do vídeo exportado; `start_time` é o ponto da fonte e a velocidade decide quanta fonte é lida.
    Interoperável com o OpenTimelineIO, mas validada contra a biblioteca apenas nos testes (ver ESTUDIO_0_13)."""
    fps = plan['output']['fps']
    rate = fps['num'] / fps['den']
    source_names = source_names or {}

    def frames(ticks):
        return float(Fraction(ticks, planlib.TPS) * rate)

    def clip(segment):
        speed = Fraction(segment.get('speed', '1'))
        effects = []
        if segment['kind'] == 'freeze':
            effects.append({'OTIO_SCHEMA': 'FreezeFrame.1', 'name': 'congelar', 'effect_name': 'FreezeFrame', 'time_scalar': 0.0, 'metadata': {}})
        elif speed != 1:
            effects.append({'OTIO_SCHEMA': 'LinearTimeWarp.1', 'name': 'velocidade', 'effect_name': 'LinearTimeWarp',
                            'time_scalar': float(speed), 'metadata': {}})
        name = source_names.get(segment['asset_id'], segment['asset_id'])
        return {
            'OTIO_SCHEMA': 'Clip.1', 'name': f"{segment['occurrence_id']} {segment['kind']}", 'metadata': {'liveclips': dict(kind=segment['kind'], mute=segment.get('mute', False))},
            'source_range': {'OTIO_SCHEMA': 'TimeRange.1', 'start_time': _rt(frames(segment['source_in']), rate),
                             'duration': _rt(frames(segment['out_end'] - segment['out_start']), rate)},     # duração NA SAÍDA; o efeito de velocidade consome mais/menos fonte
            'media_reference': {'OTIO_SCHEMA': 'ExternalReference.1', 'name': name, 'target_url': name, 'available_range': None, 'metadata': {}},
            'effects': effects, 'markers': [], 'enabled': True}

    clips = [clip(s) for s in sorted(plan['segments'], key=lambda s: s['out_start'])]
    marks = [marker(m, rate) for m in markers_from_plan(plan)]
    track = lambda kind: {'OTIO_SCHEMA': 'Track.1', 'name': kind, 'kind': kind, 'children': [dict(c) for c in clips], 'metadata': {}, 'enabled': True,
                          'source_range': None, 'effects': [], 'markers': [dict(m) for m in marks] if kind == 'Video' else []}
    stack = {'OTIO_SCHEMA': 'Stack.1', 'name': 'tracks', 'children': [track('Video'), track('Audio')], 'metadata': {}, 'enabled': True,
             'source_range': None, 'effects': [], 'markers': []}
    return {'OTIO_SCHEMA': 'Timeline.1', 'name': f"Hook’s {plan.get('job_id', '')}", 'global_start_time': _rt(0, rate), 'tracks': stack,
            'metadata': {'liveclips': {'plan_digest': planlib.digest(plan), 'nota': 'Os trechos apontam para a mídia-fonte; reaponte para os arquivos originais no editor.'}}}


# ───────────── manifesto e pacote ─────────────

def manifest(folder, video, state_extra=None, versions=None):
    folder = Path(folder)
    video = Path(video)
    entries = {}
    for name in (video.name,) + FILES + ('linha_do_tempo.otio',):
        path = folder / name
        if path.is_file():
            entries[name] = dict(sha256=sha256(path), bytes=path.stat().st_size)
    return dict(schema='liveclips.pacote', version=1, created=time.strftime('%Y-%m-%dT%H:%M:%S'), video=video.name,
                video_sha256=entries.get(video.name, {}).get('sha256'), arquivos=entries, versoes=versions or {}, **(state_extra or {}))


def build(folder, video, plan=None, versions=None):
    """Escreve linha_do_tempo.otio, linha_do_tempo_limites.txt e pacote.json (hashes) ao lado do vídeo. Devolve o manifesto."""
    folder = Path(folder)
    video = Path(video)
    if plan is None and (folder / 'plano.json').is_file():
        plan = json.loads((folder / 'plano.json').read_text(encoding='utf-8'))
    extra = {}
    if plan:
        text = json.dumps(otio(plan, media_name=video.name), ensure_ascii=False, indent=1)
        (folder / 'linha_do_tempo.otio').write_text(text, encoding='utf-8')
        try:
            made = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8')) if (folder / 'manifesto.json').is_file() else {}
        except (OSError, ValueError):
            made = {}
        rows = limits(plan, made)
        (folder / 'linha_do_tempo_limites.txt').write_text(
            'O QUE O ARQUIVO DE INTERCÂMBIO (linha_do_tempo.otio) NÃO LEVA\n\n' + '\n'.join('- ' + r for r in rows) +
            '\n\nCompatibilidade: o arquivo foi conferido com a biblioteca OpenTimelineIO' +
            ('' if validate_otio(text) else ' (biblioteca não instalada nesta máquina: não conferido)') +
            '. Não foi testado em Premiere, Resolve, Final Cut ou CapCut; teste no seu editor antes de depender dele.\n', encoding='utf-8')
        extra = dict(nao_transportado=rows, otio_biblioteca=validate_otio(text))
    result = manifest(folder, video, versions=versions)
    result.update(extra)
    (folder / 'pacote.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    return result


def verify(folder):
    """Reconfere os hashes do pacote. Devolve (ok, lista de divergências)."""
    folder = Path(folder)
    try:
        data = json.loads((folder / 'pacote.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False, ['pacote.json ausente ou ilegível']
    problems = []
    for name, info in (data.get('arquivos') or {}).items():
        path = folder / name
        if not path.is_file():
            problems.append(f'{name}: arquivo ausente')
        elif sha256(path) != info.get('sha256'):
            problems.append(f'{name}: o conteúdo mudou depois do pacote')
    return not problems, problems


# ───────────── projeto portátil (P26): guardar a edição e reabri-la ─────────────

PROJECT_DIR = 'projeto_hooks'
PRIVATE_PROFILE_KEYS = ('delivery_folder',)


def _source_rows(parts):
    rows, seen = [], set()
    for part in parts or []:
        path = Path(str(part.get('path') or ''))
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        size = path.stat().st_size if path.is_file() else None
        rows.append(dict(name=path.name, original_path=key, sha256=part.get('sha'), bytes=size, exists=path.is_file()))
    return rows


def portable_project(folder, candidate, include_sources=False, dry_run=False, versions=None, free_check=True):
    """Pasta `projeto_hooks/` com plano, perfil, referências de mídia (hash e tamanho) e versões, para reproduzir ou reabrir o corte.

    `include_sources=False` guarda só as referências (leve); `True` copia os arquivos-fonte inteiros (pode ser GRANDE).
    `dry_run=True` só informa tamanhos e arquivos, sem escrever nada. Fontes originais nunca são alteradas."""
    folder = Path(folder)
    plan_file = folder / 'plano.json'
    if not plan_file.is_file():
        raise ValueError('Exporte o clipe antes de salvar o projeto (o plano ainda não existe).')
    plan = json.loads(plan_file.read_text(encoding='utf-8'))
    sources = _source_rows(candidate.get('parts'))
    missing = [s['name'] for s in sources if not s['exists']]
    source_bytes = sum(s['bytes'] or 0 for s in sources)
    report = dict(pasta=str(folder / PROJECT_DIR), com_fontes=bool(include_sources), fontes=[dict(nome=s['name'], bytes=s['bytes']) for s in sources],
                  bytes_fontes=source_bytes if include_sources else 0, bytes_referencias_somente=source_bytes, ausentes=missing)
    if dry_run:
        return dict(report, gravado=False)
    if include_sources:
        if missing:
            raise ValueError('Não encontrei estes arquivos-fonte para copiar: ' + ', '.join(missing[:3]))
        if free_check:
            import shutil
            if shutil.disk_usage(folder).free < source_bytes * 1.1 + 50 * 1024 ** 2:
                raise ValueError('Espaço livre insuficiente para copiar as fontes (%.1f GB necessários).' % (source_bytes / 1024 ** 3))
    target = folder / PROJECT_DIR
    target.mkdir(exist_ok=True)
    if include_sources:
        import shutil
        (target / 'fontes').mkdir(exist_ok=True)
        for row in sources:
            copy = target / 'fontes' / row['name']
            if not copy.exists():
                shutil.copyfile(row['original_path'], copy.with_name(copy.name + '.part'))
                copy.with_name(copy.name + '.part').replace(copy)
            row['copy'] = f"fontes/{row['name']}"
    profile = {k: v for k, v in (candidate.get('profile') or {}).items() if k not in PRIVATE_PROFILE_KEYS}
    data = candidate.get('data') or {}
    exports = {}
    for name in sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.mp4', '.json', '.ass', '.srt', '.otio', '.txt', '.jpg')):
        exports[name] = dict(sha256=sha256(folder / name), bytes=(folder / name).stat().st_size)
    project = dict(schema='hooks.projeto', version=1, created=time.strftime('%Y-%m-%dT%H:%M:%S'), candidate=candidate.get('id'),
                   start=candidate.get('start'), end=candidate.get('end'), plan=plan, plan_digest=planlib.digest(plan), parts=candidate.get('parts'),
                   profile=profile, edit_plan=data.get('edit_plan'), edit_overrides=data.get('edit_overrides'), project=data.get('project'),
                   midias=sources, exportados=exports, versoes=versions or {},
                   nota='Plano original do Hook’s preservado integralmente; o .otio é só intercâmbio e não substitui este arquivo.')
    out = target / 'projeto.json'
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(out)
    return dict(report, gravado=True, arquivo=str(out))


def reopen(project_folder, search=None):
    """Reabre `projeto_hooks/`: confere o plano (resumo) e localiza cada mídia (cópia incluída → caminho original → pastas em `search`),
    conferindo o hash. Nada é alterado. → dict(ok, plano, midias=[{nome, estado, caminho}])."""
    base = Path(project_folder)
    base = base / PROJECT_DIR if (base / PROJECT_DIR / 'projeto.json').is_file() else base
    try:
        data = json.loads((base / 'projeto.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('projeto.json ausente ou ilegível.') from None
    if not isinstance(data, dict) or data.get('schema') != 'hooks.projeto':
        raise ValueError('Este arquivo não é um projeto do Hook’s.')
    if not isinstance(data.get('plan'), dict) or not isinstance((data['plan'].get('output') or {}).get('duration_frames'), int) \
            or not isinstance(data['plan'].get('segments'), list):
        raise ValueError('projeto.json incompleto: falta o plano de edição.')
    plan_ok = planlib.digest(data['plan']) == data.get('plan_digest')
    from . import media
    result = []
    inside = (base / 'fontes').resolve()
    for row in data.get('midias') or []:
        # O arquivo do projeto é dado de fora: o nome é só um nome e a cópia só vale dentro de `fontes/`.
        name = str(row.get('name') or '')
        if not name or Path(name).name != name or name in ('.', '..') or '\\' in name:
            result.append(dict(nome=name[:80], estado='ignorada (nome inseguro)', caminho=None))
            continue
        options = []
        if row.get('copy'):
            copy = (base / str(row['copy'])).resolve()
            if inside == copy or inside in copy.parents:
                options.append(copy)
        options.append(Path(row.get('original_path') or ''))
        for folder in search or []:
            options.append(Path(folder) / name)
        state, found = 'ausente', None
        for candidate_path in options:
            if candidate_path.is_file():
                same = (not row.get('sha256')) or media.sha_file(candidate_path) == row['sha256']
                state, found = ('ok' if same else 'alterada'), str(candidate_path)
                if same:
                    break
        result.append(dict(nome=name, estado=state, caminho=found))
    plan = data['plan']
    return dict(ok=plan_ok and all(r['estado'] == 'ok' for r in result), plano_integro=plan_ok, midias=result,
                duracao_frames=plan['output']['duration_frames'], segmentos=len(plan['segments']), efeitos=len(plan.get('effects') or []),
                perfil=data.get('profile'), versoes=data.get('versoes'))
