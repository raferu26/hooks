"""Ações do estúdio 0.13 expostas pela API local: plano, revisão, entrega, conversa, memória, referências e telemetria.

Cada função recebe o `store` (ou o cache de conversas) e devolve dados simples. Nada aqui renderiza, publica ou apaga mídia.
"""
import json
import time
from pathlib import Path

from . import capabilities, converse, export_pack, project as projectlib, references
from .memory import MemoryError_
from .telemetry import MODES, Telemetry

_CONVERSATIONS = {}          # (id, version) -> Conversation; vive só na sessão do programa


def _folder(item):
    path = item.get('export_path') or item.get('preview_path')
    return Path(path).parent if path else None


def _load(folder, name):
    try:
        return json.loads((folder / name).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def plan_view(store, candidate_id):
    """Plano, revisão, decisões e estado de entrega de um corte. Campos ausentes vêm como None, nunca inventados."""
    item = store.candidate(candidate_id)
    data = item['data']
    folder = _folder(item)
    plan = _load(folder, 'plano.json') if folder else None
    review = _load(folder, 'revisao.json') if folder else None
    video_sha = None
    if item.get('export_path') and Path(item['export_path']).is_file():
        video_sha = export_pack.sha256(item['export_path'])
    ok, problems = export_pack.verify(folder) if folder and (folder / 'pacote.json').is_file() else (False, ['pacote ainda não montado'])
    state = export_pack.delivery_state(data.get('qc'), data.get('approval'), package_ok=ok, video_sha=video_sha) if item.get('export_path') else 'em_revisao'
    fm = data.get('function_map') or {}
    return dict(
        plano=dict(resumo=_plan_summary(plan), efeitos=plan.get('effects', []), segmentos=plan['segments']) if plan else None,
        revisao=review, qualidade=data.get('qc'), estado=state, aprovacao=data.get('approval'), pacote=dict(ok=ok, problemas=problems),
        decisoes=dict(mapa_de_funcoes=fm.get('decision'), motivos=fm.get('why'), montagem=(fm.get('chosen') or {}), protegidos=fm.get('protected', []),
                      memorias=data.get('memory_refs', [])),
        contexto=data.get('intelligence'), entrega=data.get('handoff'),
        capacidades=capabilities.summary(), inteligencia=capabilities.intelligence_summary())


def context_action(store, path, payload):
    """Contexto, casos e correções. Toda correção guarda quem, quando, por quê e o que depende dela."""
    from .context_store import ContextStore, ContextError
    ctx = ContextStore(store.root)
    try:
        if path == '/api/context/missed':
            item = store.candidate(payload['id']) if payload.get('id') else None
            session = payload.get('session') or (item or {}).get('session')
            if not session:
                raise ValueError('Informe a sessão ou um corte.')
            creator = store.session(session)['streamer']
            cid = ctx.add_case('missed', session, creator=creator, human_intervals=[[payload['start'], payload['end']]],
                               reason=str(payload.get('reason') or ''), error_type=payload.get('error_type'))
            return dict(caso=cid)
        if path == '/api/context/cases':
            return dict(casos=ctx.cases(session=payload.get('session'), kind=payload.get('kind')))
        if path == '/api/context/facts':
            return dict(registros=ctx.facts(payload['session'], creator=payload.get('creator', '')))
        if path == '/api/context/fact':
            scope = payload.get('scope', 'session')
            if scope not in ('job', 'session', 'creator'):
                raise ValueError('Escopo inválido: use job, session ou creator.')
            creator = store.session(payload['session'])['streamer']
            evidence = payload.get('evidence')
            if not evidence and payload.get('start') is not None:        # a pessoa apontou o trecho: é confirmação humana
                evidence = [dict(kind='confirmacao_humana', start=payload['start'], end=payload.get('end', payload['start']),
                                 quote=str(payload['text'])[:160])]
            kind = payload.get('kind') or ('fato' if evidence else 'hipotese')    # sem fonte, nunca vira "fato"
            fid = ctx.add_fact(payload['session'], kind, str(payload['text']), evidence,
                               creator=creator, scope=scope, source='usuario')
            return dict(id=fid)
        if path == '/api/context/correct':
            return ctx.correct_fact(str(payload['id']), str(payload['text']), payload.get('evidence'), str(payload.get('why', '')), 'usuario')
        if path == '/api/context/rollback':
            return dict(registro=ctx.rollback_fact(str(payload['id'])))
    except ContextError as exc:
        raise ValueError(str(exc))
    raise ValueError('Ação de contexto não encontrada.')


def _plan_summary(plan):
    if not plan:
        return None
    out = plan['output']
    return dict(duracao_s=round(out['duration_ticks'] / out['tps'], 3), quadros=out['duration_frames'], fps=out['fps'], trechos=len(plan['segments']))


def approve(store, candidate_id, by='usuario'):
    """Aprovação humana DESTA versão do arquivo (hash do vídeo). Não publica nada."""
    item = store.candidate(candidate_id)
    if item['status'] != 'done' or not item.get('export_path') or not Path(item['export_path']).is_file():
        raise ValueError('Exporte o clipe antes de aprovar.')
    review = (item['data'].get('qc') or {}).get('review') or {}
    if review.get('bloqueia_pronto'):
        raise ValueError('A revisão automática encontrou falha crítica. Corrija e exporte de novo antes de aprovar.')
    record = dict(by=str(by)[:40], video_sha=export_pack.sha256(item['export_path']), at=round(time.time()))
    store.set_data(candidate_id, 'approval', record)
    return record


def build_package(store, candidate_id):
    item = store.candidate(candidate_id)
    folder = _folder(item)
    if not item.get('export_path') or not folder:
        raise ValueError('Exporte o clipe para montar o pacote.')
    from . import media
    manifest = export_pack.build(folder, item['export_path'], versions=dict(renderer=media.RENDERER_VERSION))
    return dict(manifest=manifest, estado=plan_view(store, candidate_id)['estado'])


def save_project(store, candidate_id, include_sources=False, dry_run=False):
    """Projeto portátil (P26): plano + perfil + referências de mídia; as fontes só vão junto se pedido (e o tamanho é informado antes)."""
    item = store.candidate(candidate_id)
    folder = _folder(item)
    if not item.get('export_path') or not folder:
        raise ValueError('Exporte o clipe para salvar o projeto.')
    from . import media
    return export_pack.portable_project(folder, item, include_sources=bool(include_sources), dry_run=bool(dry_run),
                                        versions=dict(renderer=media.RENDERER_VERSION))


def conversation(candidate_id, version, project, duration):
    key = (candidate_id, version)
    if key not in _CONVERSATIONS:
        for old in [k for k in _CONVERSATIONS if k[0] == candidate_id]:
            del _CONVERSATIONS[old]
        _CONVERSATIONS[key] = converse.Conversation(project, duration)
    return _CONVERSATIONS[key]


def talk(store, payload):
    """Conversa sobre UM corte. Devolve o projeto proposto; salvar continua sendo um clique do usuário (/api/project/save)."""
    item = store.candidate(payload['id'])
    duration = item['end'] - item['start']
    conv = conversation(item['id'], int(item['version']), projectlib.project_of(item), duration)
    action = payload.get('action', 'say')
    if action == 'say':
        text = str(payload.get('text', '')).strip()
        if not text or len(text) > 400:
            raise ValueError('Escreva o pedido em até 400 caracteres.')
        if isinstance(payload.get('project'), dict):
            # O editor pode ter alterações ainda não salvas: a conversa parte do que está na tela, validado pelas mesmas regras.
            shown = projectlib.clean(payload['project'], duration)
            if shown != conv.project:
                _CONVERSATIONS.pop((item['id'], int(item['version'])), None)
                conv = conversation(item['id'], int(item['version']), shown, duration)
        result = conv.say(text)
    elif action == 'confirm':
        result = conv.confirm()
    elif action == 'undo':
        result = conv.undo()
    elif action == 'redo':
        result = conv.redo()
    else:
        raise ValueError('Ação de conversa desconhecida.')
    return dict(result, projeto=conv.project, pode_desfazer=len(conv.versions) > 1, pode_refazer=bool(conv.undone), pendente=len(conv.pending))


# ───────────── memória, referências e telemetria ─────────────

def memory_list(store, payload):
    memory = store.memory
    rows = memory.list(payload.get('namespace') or None, payload.get('streamer') or None)
    return dict(itens=[dict(id=r['id'], namespace=r['namespace'], escopo=r['scope'], chave=r['key'], corpo=r['body'], origem=r['origin'],
                            status=r['status'], versao=r['version'], validade=r.get('valid_until')) for r in rows[:100]], resumo=memory.stats())


def memory_action(store, path, payload):
    memory = store.memory
    try:
        if path == '/api/memory/vocabulary':
            memory.add_vocabulary(payload['streamer'], str(payload['term']))
            return dict(vocabulario=memory.vocabulary(payload['streamer']))
        if path == '/api/memory/forget':
            memory.forget(str(payload['id']))
            return dict(ok=True)
        if path == '/api/memory/rollback':
            return dict(registro=memory.rollback(str(payload['id']), payload.get('version')))
        if path == '/api/memory/history':
            return dict(historico=memory.history(str(payload['id'])))
    except MemoryError_ as exc:
        raise ValueError(str(exc))
    raise ValueError('Ação de memória não encontrada.')


def references_action(store, path, payload):
    try:
        if path == '/api/references/add':
            return dict(registro=references.add(store.memory, dict(payload['reference']), payload.get('valid_days')))
        if path == '/api/references/query':
            found = references.query(store.memory, payload.get('niche'), payload.get('platform'), payload.get('region'), payload.get('kind'), payload.get('language'))
            return dict(itens=found, sugestoes=references.usable_suggestions(found))
        if path == '/api/references/cycle':
            return references.cycle_plan(payload.get('niches') or [], payload.get('platforms') or [], int(payload.get('size', 40)))
    except (references.ReferenceError_, MemoryError_) as exc:
        raise ValueError(str(exc))
    raise ValueError('Ação de referências não encontrada.')


def telemetry_report(store):
    return dict(relatorio=Telemetry(store.root).report(), modos={k: dict(rotulo=v['label'], nota=v['note']) for k, v in MODES.items()})
