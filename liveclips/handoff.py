"""Contrato de entrega ao editor (`liveclips.editor_handoff` v1).

O corte só vira "pronto" quando o contexto exigido está dentro dele (ou foi marcado como dispensado por um humano).
Placeholders ("título aqui", "lorem", "xxx") são rejeitados: um campo vazio é honesto, um falso preenchido não é.
Nada aqui decide o que é bom: só impede entregas incompletas e registra por que cada estado foi atingido."""
import re

CONTRACT = 'liveclips.editor_handoff'
VERSION = 1
REVISION_LIMIT = 2

STATES = ('aguardando_contexto', 'pronto_para_revisar', 'aprovado_para_edicao', 'renderizado', 'pronto_para_distribuicao',
          'revisao_humana')
TRANSITIONS = {
    'aguardando_contexto': {'pronto_para_revisar', 'revisao_humana'},
    'pronto_para_revisar': {'aprovado_para_edicao', 'aguardando_contexto', 'revisao_humana'},
    'aprovado_para_edicao': {'renderizado', 'aguardando_contexto', 'revisao_humana'},
    'renderizado': {'pronto_para_distribuicao', 'aguardando_contexto', 'revisao_humana'},
    'pronto_para_distribuicao': {'aguardando_contexto'},
    'revisao_humana': {'aguardando_contexto', 'pronto_para_revisar'},
}
FEEDBACK = ('falta_contexto', 'borda_ruim')
PLACEHOLDER = re.compile(r'(?i)\b(lorem|ipsum|todo|tbd|xxx+|t[ií]tulo aqui|texto aqui|legenda aqui|placeholder|a definir)\b|^\s*[-–—_.]*\s*$')


class HandoffError(ValueError):
    pass


def is_placeholder(text):
    return bool(PLACEHOLDER.search(str(text or '')))


def clean_text(text):
    """Devolve o texto ou None quando for placeholder (None = campo ausente, nunca um falso preenchido)."""
    text = str(text or '').strip()
    return None if is_placeholder(text) else text


def _protected(candidate):
    out = []
    for item in (candidate.get('function_map') or {}).get('protected') or []:
        try:
            if isinstance(item, dict):
                a, b = item['start'], item['end']
            else:
                a, b = item[0], item[1]
            out.append(dict(start=float(a), end=float(b), funcao=item.get('function') if isinstance(item, dict) else None))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def build(candidate, *, required=None, assessment=None, dimensions=None, relations=None, revisions=0):
    """`required`: saída de `context_search.required_context`. O estado inicial sai das dimensões."""
    req = list((required or {}).get('intervalos') or [])
    start, end = float(candidate['start']), float(candidate['end'])
    missing = [r for r in req if not (start <= float(r['start']) and float(r['end']) <= end + .001)]
    notes = list((required or {}).get('notas') or [])
    state = (dimensions or {}).get('estado') or 'pronto_para_revisar'
    if missing:
        state = 'aguardando_contexto'
        notes.append(f'{len(missing)} trecho(s) anterior(es) que o corte pressupõe ainda não estão dentro dele.')
    elif state == 'aguardando_contexto' and not (dimensions or {}).get('aguardando'):
        state = 'pronto_para_revisar'
    if state not in STATES:
        state = 'pronto_para_revisar' if state in ('exploratorio', 'revisao_necessaria') else 'aguardando_contexto'
    titles = candidate.get('llm_titles')
    title = clean_text(candidate.get('title') or (titles[0] if isinstance(titles, list) and titles else None))
    return dict(contract=CONTRACT, version=VERSION, state=state, required_intervals=req, missing_context=missing,
                protected_intervals=_protected(candidate),
                title=title, caption_ok=not is_placeholder(candidate.get('transcript') or '.'),
                exploratory=bool(candidate.get('exploratory')), label=(dimensions or {}).get('estado'),
                reaction=candidate.get('facial_timing'), revisions=int(revisions), revision_limit=REVISION_LIMIT,
                relations=list(relations or []), notes=notes, history=[dict(to=state, why='criado')])


def transition(handoff, to, why=''):
    cur = handoff['state']
    if to not in STATES:
        raise HandoffError('Estado desconhecido.')
    if to not in TRANSITIONS.get(cur, ()):
        raise HandoffError(f'Não dá para ir de {cur} para {to}.')
    if to in ('aprovado_para_edicao', 'pronto_para_revisar') and handoff.get('missing_context'):
        raise HandoffError('O contexto exigido ainda não está dentro do corte.')
    out = dict(handoff, state=to, history=list(handoff.get('history') or []) + [dict(to=to, why=why)])
    return out


def editor_feedback(handoff, kind, interval=None, note=''):
    """Retorno do editor. `falta_contexto` pede mais trecho; depois de REVISION_LIMIT rodadas vai para um humano."""
    if kind not in FEEDBACK:
        raise HandoffError('Retorno inválido: use falta_contexto ou borda_ruim.')
    revisions = int(handoff.get('revisions', 0)) + 1
    out = dict(handoff, revisions=revisions)
    if kind == 'falta_contexto' and interval:
        out['required_intervals'] = list(handoff.get('required_intervals') or []) + [dict(interval, motivo='pedido do editor' + (f': {note}' if note else ''))]
        out['missing_context'] = list(handoff.get('missing_context') or []) + [out['required_intervals'][-1]]
    target = 'revisao_humana' if revisions > REVISION_LIMIT else 'aguardando_contexto'
    out['state'] = target
    out['history'] = list(handoff.get('history') or []) + [dict(to=target, why=f'editor: {kind}' + (f' · {note}' if note else ''))]
    return out
