"""Recuperação de contexto distante com fonte (N10): busca estruturada primeiro, depois textual.

Nada de embeddings: similaridade não prova identidade nem causa. Filtra por sessão/criador/validade ANTES de buscar,
devolve o trecho original (intervalo + citação) e declara ambiguidade quando há mais de um referente plausível.
Se não achar, devolve vazio: o sistema nunca inventa uma lembrança para completar a história.
"""
import math

from .episodes import STOP, references_in, sentences
from .intelligence import normalize

AMBIGUITY_RATIO = .8       # o segundo colocado a menos de 20% do primeiro = ambíguo


def tokens(text):
    return [t for t in normalize(text).split() if t not in STOP and len(t) > 2]


def text_search(transcript, query, *, before=None, limit=5, min_overlap=1):
    """Trechos do passado (antes de `before`, em s de mídia) que compartilham termos com a consulta, com a citação."""
    q = set(tokens(query))
    if not q:
        return []
    rows = sentences(transcript)
    doc_freq = {}
    for r in rows:
        for t in set(tokens(r['text'])):
            doc_freq[t] = doc_freq.get(t, 0) + 1
    n = max(1, len(rows))
    out = []
    for r in rows:
        if before is not None and float(r['end']) > float(before):
            continue
        toks = set(tokens(r['text']))
        common = q & toks
        if len(common) < min_overlap:
            continue
        score = sum(math.log(1 + n / doc_freq.get(t, 1)) for t in common) / math.sqrt(len(toks) or 1)
        out.append(dict(start=round(float(r['start']), 3), end=round(float(r['end']), 3), quote=r['text'][:160],
                        score=round(score, 3), termos=sorted(common), seq=r.get('seq')))
    out.sort(key=lambda x: (-x['score'], -x['start']))
    return out[:limit]


def structured(ctx, session, *, creator='', before=None, kinds=None, at=None):
    """Fatos válidos e episódios da sessão antes de `before`; do criador só o escopo 'creator' dele."""
    facts = [f for f in ctx.facts(session, creator=creator, kinds=kinds, at=at)
             if before is None or not f['evidence'] or min(e['start'] for e in f['evidence']) <= before]
    episodes = [e for e in ctx.episodes(session) if before is None or e['opened'] <= before]
    return dict(fatos=facts, episodios=episodes)


def resolve_reference(ctx, session, transcript, utterance, at, *, creator=''):
    """Resolve 'de novo', 'como eu falei', 'aquilo'. Devolve dict(referencias, ambiguo, resolvido, motivo).

    Cada referente traz a fonte. Com mais de um referente plausível, `ambiguo=True` e todos são listados."""
    kinds = references_in(utterance)
    if not kinds:
        return dict(referencias=[], ambiguo=False, resolvido=False, motivo='A fala não usa referência dependente de contexto.')
    cands = []
    eps = [e for e in ctx.episodes(session) if e['opened'] < at]
    if 'de_novo' in kinds:
        for e in eps:
            if e['kind'] in ('promessa', 'tentativa'):
                age = at - e['opened']
                cands.append(dict(origem='episodio', id=e['id'], tipo=e['kind'], quote=e['text'][:160], start=e['opened'],
                                  end=e['opened'], status=e['status'], score=round(1 / (1 + age / 120), 3)))
    if 'como_eu_falei' in kinds:
        body = utterance
        for ph in ('como eu falei', 'como eu disse', 'como eu avisei'):
            body = normalize(body).replace(ph, ' ')
        for hit in text_search(transcript, body, before=at - .01, limit=3, min_overlap=1):
            cands.append(dict(origem='fala', tipo='fala_anterior', quote=hit['quote'], start=hit['start'], end=hit['end'],
                              score=hit['score'] / (1 + hit['score'])))
    if 'aquilo' in kinds:
        for e in eps[-3:]:
            cands.append(dict(origem='episodio', id=e['id'], tipo=e['kind'], quote=e['text'][:160], start=e['opened'],
                              end=e['opened'], status=e['status'], score=round(.4 + .1 * (e['opened'] / max(at, 1)), 3)))
    for f in ctx.facts(session, creator=creator, kinds=('fato',)):
        if 'aquilo' in kinds and f['evidence'] and f['evidence'][0]['start'] < at:
            cands.append(dict(origem='fato', id=f['id'], tipo='fato', quote=f['text'][:160], start=f['evidence'][0]['start'],
                              end=f['evidence'][0]['end'], score=.3))
    cands.sort(key=lambda c: (-c['score'], -c['start']))
    cands = cands[:4]
    if not cands:
        return dict(referencias=[], ambiguo=False, resolvido=False,
                    motivo='Nenhuma fonte anterior encontrada; não foi inventado um referente.')
    ambiguous = len(cands) > 1 and cands[1]['score'] >= cands[0]['score'] * AMBIGUITY_RATIO
    return dict(referencias=cands, ambiguo=ambiguous, resolvido=not ambiguous,
                motivo='Mais de um referente plausível: o editor/operador decide.' if ambiguous else 'Referente único com fonte.')


def required_context(ctx, session, transcript, start, end, *, creator='', max_back=900.0):
    """Intervalos anteriores a `start` que o trecho [start,end] pressupõe (promessas abertas, referências).

    É o que o editor recebe como `required_intervals`: se uma montagem curta cortar isso, a relação se perde."""
    spoken = [r for r in sentences(transcript) if float(r['end']) > start and float(r['start']) < end]
    needed, notes = [], []
    for r in spoken:
        res = resolve_reference(ctx, session, transcript, r['text'], float(r['start']), creator=creator)
        for ref in res['referencias'][:1 if res['resolvido'] else 3]:
            if start - ref['end'] <= max_back and ref['end'] < start:
                needed.append(dict(start=ref['start'], end=max(ref['end'], ref['start'] + 1), quote=ref['quote'],
                                   motivo=f"referência «{', '.join(references_in(r['text']))}»" + (' (ambígua)' if res['ambiguo'] else '')))
        if res['referencias'] and res['ambiguo']:
            notes.append('Referência ambígua em «' + r['text'][:60] + '».')
    # Episódios abertos cuja resolução cai dentro do trecho.
    for e in ctx.episodes(session):
        resolved = e['resolved']
        if e['kind'] == 'promessa' and resolved is not None and start <= resolved <= end and e['opened'] < start \
                and start - e['opened'] <= max_back:
            needed.append(dict(start=e['opened'], end=e['opened'] + 3, quote=e['text'][:160],
                               motivo='promessa cujo desfecho está no corte'))
    merged = {}
    for n in sorted(needed, key=lambda x: x['start']):
        k = round(n['start'], 1)
        if k in merged:
            if n['motivo'] not in merged[k]['motivo']:
                merged[k]['motivo'] += '; ' + n['motivo']
        else:
            merged[k] = dict(n)
    uniq = list(merged.values())
    return dict(intervalos=uniq, notas=notes)
