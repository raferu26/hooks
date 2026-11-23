"""Juiz de seleção: refina começo e fim, checa se o corte se sustenta sozinho, escolhe com diversidade
e diz o quanto confia em cada sugestão.

Tudo é determinístico e explicável. O ranking (ranking.py) propõe muitos candidatos; aqui cada um
recebe duas notas separadas — começo (gancho e independência de contexto) e fim (a ideia fecha?) —
e é testado em variações de limites alinhadas às frases. Os tempos são absolutos (linha do tempo da
sessão), como no ranking.
"""
import re

from .agents import _weak_opening, hook_score, sentences
from .captions import plain

# Conectivos no começo mostram que a frase continua um raciocínio anterior.
CONNECTORS = {'mas', 'e', 'ai', 'dai', 'entao', 'porque', 'pq', 'ou', 'porem', 'tambem', 'pois', 'so', 'logo',
              'and', 'but', 'so', 'because', 'then'}
# Pronomes sem antecedente dentro do corte pedem o trecho anterior (peso menor: "isso aqui ó" costuma funcionar).
REFERENCES = {'isso', 'isto', 'aquilo', 'ele', 'ela', 'eles', 'elas', 'la', 'esse', 'essa', 'desse', 'dessa',
              'nisso', 'dele', 'dela', 'disso', 'aquele', 'aquela', 'it', 'they', 'that'}
# Terminar numa destas palavras deixa a frase no ar.
DANGLING = {'e', 'mas', 'que', 'entao', 'porque', 'tipo', 'ou', 'de', 'do', 'da', 'com', 'pra', 'para', 'um', 'uma',
            'o', 'a', 'se', 'quando', 'ai', 'and', 'but', 'the', 'to', 'of'}
TERMINAL = ('.', '!', '?', '…')

EXTEND_MAX = 9.0      # no máximo quanto o começo pode recuar para trazer o contexto
LIMITS = {'short': (12.0, 60.0, 30.0), 'narrative': (25.0, 90.0, 50.0)}
TIERS = ((.66, 'alta'), (.45, 'média'), (0.0, 'baixa'))


def _clamp(value, low=0.0, high=10.0):
    return max(low, min(high, value))


def _first_tokens(text, count=2):
    return [plain(w) for w in str(text).split() if plain(w)][:count]


def dependency(text):
    """0 a 1: o quanto a frase de abertura depende de algo dito antes."""
    tokens = _first_tokens(text, 2)
    if not tokens:
        return 0.0
    if tokens[0] in CONNECTORS:
        return 1.0
    if tokens[0] in REFERENCES or (len(tokens) > 1 and tokens[1] in REFERENCES and tokens[0] in ('por', 'de', 'em')):
        return .5
    return 0.0


def _sentence_list(transcript, start, end):
    return sentences(transcript, start, end)


def edge_scores(transcript, start, end, lookback=EXTEND_MAX):
    """Notas de começo e fim (0 a 10) com os problemas encontrados. Sem palavras temporizadas: neutro."""
    frases = _sentence_list(transcript, start - lookback, end + 6)
    inside = [f for f in frases if f['end'] > start + .05 and f['start'] < end - .05]
    if not inside:
        return dict(open=5.0, close=5.0, issues=[], flags={}, dependency=0.0, first='', last='', known=False)
    issues, flags = [], {}
    first, last = inside[0], inside[-1]
    mid_start = first['start'] < start - .2 and first['end'] > start + .5
    # Começar no meio de uma frase só conta se faltar um pedaço relevante dela.
    if mid_start:
        cut_words = [w for w in first['words'] if w['end'] <= start + .05]
        mid_start = len(cut_words) >= 2
    dep = dependency(first['text'])
    hook = hook_score(first['text'])
    lead = max(0.0, first['start'] - start)
    open_score = 10 * (.45 * hook / 10 + .55 * (1 - dep)) - (3 if mid_start else 0) - min(2.0, lead)
    if _weak_opening(first):
        open_score -= 1.5
        issues.append('O começo é um cumprimento ou enchimento.')
    if dep >= 1:
        issues.append('Começa continuando uma ideia anterior (“' + ' '.join(first['text'].split()[:3]) + '…”).')
    elif dep > 0:
        issues.append('A primeira frase se refere a algo dito antes.')
    if mid_start:
        issues.append('O corte começa no meio de uma frase.')
    if lead > 1.2:
        issues.append(f'{lead:.1f}s de silêncio antes da primeira fala.')
    mid_end = last['start'] < end - .5 and last['end'] > end + .2
    tail = max(0.0, end - last['end'])
    tokens = [plain(w['text']) for w in last['words'] if plain(w['text'])]
    ended = last['text'].rstrip('"”’)»').endswith(TERMINAL)
    dangling = bool(tokens) and tokens[-1] in DANGLING and not ended
    close_score = 10.0
    if mid_end:
        close_score -= 4
        issues.append('O corte termina antes da frase acabar.')
    if dangling:
        close_score -= 3
        issues.append('A última frase termina no ar (“…' + ' '.join(last['text'].split()[-2:]) + '”).')
    if not ended and not mid_end and not dangling:
        close_score -= 1.5
    close_score -= min(2.5, max(0.0, tail - 1.0))
    flags.update(mid_start=mid_start, mid_end=mid_end, dangling=dangling, lead=round(lead, 2), tail=round(tail, 2))
    return dict(open=round(_clamp(open_score), 2), close=round(_clamp(close_score), 2), issues=issues, flags=flags,
                dependency=dep, first=first['text'], last=last['text'], known=True)


def _starts(transcript, start, floor, lookback):
    """Candidatos a começo: o original e inícios de frase próximos (com folga de 0,25 s)."""
    result = {round(start, 2)}
    for f in _sentence_list(transcript, max(floor, start - lookback), start + 6):
        value = round(max(floor, f['start'] - .25), 2)
        if start - lookback <= value <= start + 6:
            result.add(value)
    return sorted(result)


def _ends(transcript, end, ceiling, lookahead=6.0):
    result = {round(end, 2)}
    for f in _sentence_list(transcript, end - lookahead, end + lookahead):
        value = round(min(ceiling, f['end'] + .35), 2)
        if end - lookahead <= value <= end + lookahead:
            result.add(value)
    return sorted(result)


def refine(candidate, transcript, bounds, clip_format='short', habits=None):
    """Escolhe começo e fim melhores para um candidato, sem sair de `bounds` (início, fim da sessão)."""
    low, high = bounds
    min_len, max_len, target = LIMITS.get(clip_format, LIMITS['short'])
    start0, end0 = float(candidate['start']), float(candidate['end'])
    habits = habits or {}
    shift_start = float(habits.get('start_offset', 0) or 0) if habits.get('offset_reliable') else 0.0
    shift_end = float(habits.get('end_offset', 0) or 0) if habits.get('offset_reliable') else 0.0
    base_start = min(max(low, start0 + shift_start), end0 - min_len)
    base_end = max(min(high, end0 + shift_end), base_start + min_len)
    before = edge_scores(transcript, start0, end0)
    if not before['known']:
        item = dict(candidate)
        item['edges'] = dict(open=before['open'], close=before['close'], issues=[], known=False)
        item['refinement'] = dict(changed=False, notes=[], known=False)
        return item
    best, best_value = None, -1e9
    for s in _starts(transcript, base_start, low, EXTEND_MAX):
        for e in _ends(transcript, base_end, high):
            length = e - s
            if length < min_len or length > max_len:
                continue
            scores = edge_scores(transcript, s, e)
            move = abs(s - base_start) + abs(e - base_end)
            value = (.55 * scores['open'] + .45 * scores['close'] - .035 * abs(length - target) - (.25 if (shift_start or shift_end) else .05) * move
                     - 1.2 * (scores['flags'].get('mid_end', False)))
            if value > best_value:
                best, best_value = (s, e, scores), value
    if best is None:
        best = (start0, end0, before)
    s, e, scores = best
    notes = []
    if abs(s - start0) >= .3:
        notes.append(f'Começo ajustado em {s - start0:+.1f}s para {"abrir numa frase inteira" if not scores["flags"].get("mid_start") else "melhorar a abertura"}.')
    if abs(e - end0) >= .3:
        notes.append(f'Fim ajustado em {e - end0:+.1f}s para fechar a ideia.')
    if shift_start or shift_end:
        notes.append(f'Preferência aprendida com suas edições: começo {shift_start:+.1f}s, fim {shift_end:+.1f}s.')
    item = dict(candidate)
    item.update(start=round(s, 2), end=round(e, 2), refined=True)
    text = ' '.join(f['text'] for f in _sentence_list(transcript, s, e)) if scores['known'] else item.get('transcript', '')
    if text:
        item['transcript'] = text
    item['boundary_warning'] = bool(scores['flags'].get('mid_start') or scores['flags'].get('mid_end'))
    item['edges'] = dict(open=scores['open'], close=scores['close'], issues=scores['issues'], known=True,
                         dependency=scores['dependency'])
    item['refinement'] = dict(changed=bool(abs(s - start0) >= .3 or abs(e - end0) >= .3), notes=notes,
                              start_from=round(start0, 2), end_from=round(end0, 2), known=True)
    reasons = list(item.get('reasons', []))
    reasons.extend(notes)
    for issue in scores['issues']:
        reasons.append('Atenção: ' + issue)
    item['reasons'] = reasons
    # Um começo ruim ou um fim no ar custam nota; os componentes originais ficam preservados.
    penalty = max(0.0, 6 - scores['open']) * .5 + max(0.0, 6 - scores['close']) * .4
    item['components'] = dict(item.get('components', {}), borda_comeco_fim=round((scores['open'] + scores['close'] - 12) * .25, 3))
    item['score'] = round(float(item.get('score', 0)) + (scores['open'] + scores['close'] - 12) * .25, 2)
    item['edge_penalty'] = round(penalty, 2)
    return item


def _words_of(text):
    return {w for w in re.findall(r'\w+', str(text).casefold()) if len(w) > 3}


def similarity(a, b):
    """Maior entre a sobreposição no tempo e a semelhança do texto (0 a 1)."""
    inter = max(0.0, min(a['end'], b['end']) - max(a['start'], b['start']))
    shorter = max(.1, min(a['end'] - a['start'], b['end'] - b['start']))
    time_overlap = inter / shorter
    wa, wb = _words_of(a.get('transcript', '')), _words_of(b.get('transcript', ''))
    text = len(wa & wb) / max(1, len(wa | wb)) if wa and wb else 0.0
    return max(time_overlap, text)


def diversify(candidates, limit, lam=.6):
    """Seleção por relevância marginal máxima: a lista final não repete o mesmo momento em versões parecidas."""
    pool = sorted(candidates, key=lambda c: -float(c.get('score', 0)))
    if not pool:
        return []
    top = max(float(pool[0].get('score', 0)), 1e-6)
    chosen = []
    while pool and len(chosen) < limit:
        best, best_value = None, -1e9
        for c in pool:
            sim = max((similarity(c, x) for x in chosen), default=0.0)
            if sim > .5:
                continue
            value = float(c.get('score', 0)) / top - lam * sim
            if value > best_value:
                best, best_value = c, value
        if best is None:
            break
        chosen.append(best)
        pool.remove(best)
    return chosen


def tier_of(value):
    for floor, name in TIERS:
        if value >= floor:
            return name
    return 'baixa'


def calibrate(raw, table):
    """Aproxima a confiança da taxa real de aprovação do streamer quando há histórico suficiente."""
    for row in table or []:
        if row['low'] <= raw < row['high'] and row['n'] >= 10:
            return round(.5 * raw + .5 * row['rate'], 3)
    return raw


def confidence(candidate, margin=0.0, table=None):
    """0 a 1 + faixa (alta, média, baixa) + motivos. Mede o quanto cada pista independente concorda."""
    moment = float(candidate.get('moment_confidence', .4))
    edges = candidate.get('edges') or {}
    open_score, close_score = float(edges.get('open', 5)), float(edges.get('close', 5))
    narrative = (candidate.get('narrative') or {}).get('historia_completa', 5)
    components = candidate.get('components') or {}
    evidence = sum(1 for k, v in components.items()
                   if v and float(v) > 0 and k not in ('cobertura_fala', 'ajuste_duracao', 'borda_comeco_fim'))
    value = (.28 * moment + .22 * min(1.0, evidence / 5) + .18 * (open_score / 10) + .14 * (close_score / 10) +
             .10 * min(1.0, narrative / 8) + .08 * min(1.0, max(0.0, margin)))
    why = []
    if candidate.get('fallback') or candidate.get('low_confidence'):
        value = min(value, .4)
        why.append('Sem pista forte: é um candidato exploratório.')
    if edges.get('known') and open_score < 5:
        why.append('Começo fraco ou dependente de contexto.')
    if edges.get('known') and close_score < 5:
        why.append('Fim pouco conclusivo.')
    if candidate.get('boundary_warning'):
        value -= .06
        why.append('Fala atravessando um dos limites.')
    if evidence <= 1:
        why.append('Pouca evidência: só um tipo de pista.')
    llm = candidate.get('llm')
    if llm:
        value += (float(llm.get('score', 5)) - 5) * .02
    value = round(max(0.0, min(.99, value)), 3)
    value = calibrate(value, table)
    return dict(value=value, tier=tier_of(value), reasons=why)


def finalize(chosen, limit=4, table=None):
    """Confiança, faixa e ordem final (confiança baixa vai para o fim da lista)."""
    chosen = list(chosen)
    for c in chosen:
        others = [float(x.get('score', 0)) for x in chosen if x is not c]
        margin = (float(c.get('score', 0)) - max(others, default=0.0)) / max(1.0, abs(float(c.get('score', 0)))) + .5
        c['confidence'] = confidence(c, margin=max(0.0, min(1.0, margin)), table=table)
        c['reasons'] = [r for r in c.get('reasons', []) if not r.startswith('Confiança baixa')]
        c.pop('low_confidence', None) if not c.get('fallback') else None
        if c['confidence']['tier'] == 'baixa':
            c['low_confidence'] = True
            c['reasons'] = c['reasons'] + ['Confiança baixa: assista com atenção antes de aprovar.']
    order = {'alta': 0, 'média': 1, 'baixa': 2}
    chosen.sort(key=lambda c: (order[c['confidence']['tier']], -float(c.get('score', 0))))
    return chosen[:limit]


def curate(candidates, transcript, bounds, limit=4, clip_format='short', habits=None, table=None):
    """Refina, diversifica e rotula a confiança de cada sugestão."""
    refined = [refine(c, transcript, bounds, clip_format, habits) for c in candidates]
    chosen = diversify(refined, limit * 2)
    return finalize(chosen, limit, table) if chosen else []


def table_from(samples):
    """Tabela de calibração a partir de [(confiança, aprovado)]."""
    bins = ((0.0, .45), (.45, .66), (.66, 1.01))
    result = []
    for low, high in bins:
        group = [ok for value, ok in samples if low <= value < high]
        result.append(dict(low=low, high=high, n=len(group), rate=round(sum(group) / len(group), 3) if group else 0.0,
                           tier=tier_of(low)))
    return result
