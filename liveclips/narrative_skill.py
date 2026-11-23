"""Planejamento narrativo (F07, F08, R06, R07): a função de cada trecho, o que não pode sair e quando não editar.

Complementa `narrative.story_plan` (que acha preparação, clímax e encerramento por frases). Aqui o resultado vira
um mapa de FUNÇÕES com evidência, pausas que sustentam o momento e alternativas de montagem escolhidas com justificativa.
Se a evidência não basta, o plano diz isso e fica conservador em vez de fingir certeza.
"""
from .intelligence import text_evidence

PAUSE_BEFORE = 6.0      # s antes do clímax em que uma pausa constrói expectativa
PAUSE_AFTER = 2.5       # s depois do clímax em que o silêncio dá espaço à reação
MIN_PAUSE = .45         # pausa mínima para valer a pena proteger
TEASER_MAX = 3.8


def _words(transcript, start, end):
    result = []
    for seg in transcript or []:
        for w in seg.get('words') or []:
            try:
                a, b = float(w['start']), float(w['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if a >= start - .01 and b <= end + .01 and b > a:
                result.append(dict(start=a, end=b, word=str(w.get('word', '')).strip()))
    return sorted(result, key=lambda x: x['start'])


def function_map(candidate, story, transcript, signals=None):
    """`story`: saída de `narrative.story_plan`. Devolve funções, trechos intocáveis e a decisão editorial."""
    beats = (story or {}).get('beats') or {}
    start, end = float(candidate['start']), float(candidate['end'])
    evidence = []
    if not beats or 'climax' not in beats:
        return dict(status='insuficiente', decision='conservador', functions={}, protected=[],
                    why=['Faltam frases temporizadas para entender a função dos trechos; manter o corte simples e revisar.'],
                    request_more_context=True, evidence=[], alternatives=[], chosen=dict(id='cronologica', why='Sem evidência para outra montagem.'))
    prep, climax, close = beats.get('preparacao') or beats['climax'], beats['climax'], beats.get('encerramento') or beats['climax']
    promise_text = (prep or climax)['text']
    hits = text_evidence(promise_text)
    functions = {
        'promessa': dict(text=promise_text, start=prep['start'], end=prep['end'],
                         truthful=bool(hits['gancho'] or hits['tensao'] or hits['historia'] or hits['opiniao'] or hits['educacional'] or
                                       text_evidence(climax['text'])['reacao'])),
        'contexto': dict(start=prep['start'], end=prep['end'], text=prep['text']),
        'acao_decisiva': dict(start=climax['start'], end=climax['end'], text=climax['text']),
        'resolucao': dict(start=close['start'], end=close['end'], text=close['text']),
    }
    # reação: fala/sinal logo depois do clímax
    reaction = None
    for seg in transcript or []:
        try:
            a, b = float(seg['start']), float(seg['end'])
        except (KeyError, TypeError, ValueError):
            continue
        if climax['end'] - .3 <= a <= climax['end'] + 4 and text_evidence(seg.get('text', ''))['reacao']:
            reaction = dict(start=round(a, 2), end=round(b, 2), text=seg.get('text', ''))
            break
    if reaction:
        functions['reacao'] = reaction
    else:
        for p in (signals or {}).get('audio', []):
            try:
                at, strength = float(p['time']), float(p.get('strength', 0))
            except (KeyError, TypeError, ValueError):
                continue
            if climax['end'] - .3 <= at <= climax['end'] + 4 and strength >= 1.2:
                functions['reacao'] = dict(start=round(at - .3, 2), end=round(at + .9, 2), text='', observado='pico de áudio')
                evidence.append(dict(kind='audio', time=at, strength=strength))
                break
    protected = [dict(function=name, start=v['start'], end=v['end'], why='parte do sentido do momento')
                 for name, v in functions.items() if name in ('contexto', 'acao_decisiva', 'resolucao', 'reacao')]
    pauses = protected_pauses(transcript, start, end, climax['start'], climax['end'])
    protected.extend(pauses)
    why = []
    request_more = False
    if prep['start'] < start - .05:
        request_more = True
        why.append('A preparação começa antes do corte; peça mais contexto ao buffer ou ajuste o início.')
    if close['end'] > end + .2:
        request_more = True
        why.append('A resolução passa do fim do corte; o payoff pode estar cortado.')
    chosen, alternatives = choose_assembly(candidate, functions)
    status = 'ok' if not request_more else 'revisar'
    return dict(status=status, decision='editar' if not request_more else 'conservador', functions=functions, protected=protected,
                why=why or ['Contexto, ação decisiva e resolução estão dentro do corte.'], request_more_context=request_more,
                evidence=evidence, alternatives=alternatives, chosen=chosen)


def protected_pauses(transcript, start, end, climax_start, climax_end):
    """Pausas que constroem expectativa ou dão espaço à reação. Detector de silêncio sugere; aqui se decide proteger."""
    words = _words(transcript, start, end)
    result = []
    for left, right in zip(words, words[1:]):
        gap = right['start'] - left['end']
        if gap < MIN_PAUSE:
            continue
        before_climax = climax_start - PAUSE_BEFORE <= left['end'] <= climax_start + .2 and right['start'] <= climax_start + 1.0
        after_climax = climax_end - .3 <= left['end'] <= climax_end + PAUSE_AFTER
        if before_climax or after_climax:
            result.append(dict(function='pausa_narrativa', start=round(left['end'], 3), end=round(right['start'], 3),
                               why='pausa que sustenta a expectativa' if before_climax else 'respiro para a reação'))
    return result


def overlaps(a_start, a_end, intervals, margin=0.0):
    return any(a_start < i['end'] + margin and a_end > i['start'] - margin for i in intervals)


def filter_decisions(decisions, protected, start):
    """Tira das decisões automáticas de corte o que atinge uma pausa narrativa ou um trecho que sustenta o sentido.

    `protected` está em segundos absolutos da sessão; as decisões estão em segundos do corte."""
    kept, dropped = [], []
    for d in decisions:
        if d.get('kind') in ('silence', 'repetition'):
            a, b = start + float(d['start']), start + float(d['end'])
            hit = next((p for p in protected if p['function'] in ('pausa_narrativa', 'acao_decisiva') and a < p['end'] and b > p['start']), None)
            if hit:
                dropped.append(dict(id=d.get('id'), motivo=f'protegido: {hit["why"]}'))
                continue
        kept.append(d)
    return kept, dropped


def choose_assembly(candidate, functions):
    """Alternativas de montagem com justificativa. A cronológica é sempre a base; a antecipação curta só entra com
    promessa verdadeira, resolução presente e clímax depois dos primeiros segundos."""
    alternatives = [dict(id='cronologica', why='Mantém a ordem real dos acontecimentos.', risk='baixo')]
    chosen = dict(id='cronologica', why='A edição simples é a base; só se troca com ganho claro.')
    climax = functions.get('acao_decisiva')
    close = functions.get('resolucao')
    if not climax or not close:
        return chosen, alternatives
    length = float(candidate['end']) - float(candidate['start'])
    into = climax['start'] - float(candidate['start'])
    peak = min(TEASER_MAX, max(.8, climax['end'] - climax['start']))
    if into >= 7 and functions['promessa'].get('truthful') and close['end'] > climax['end']:
        alternatives.append(dict(id='antecipacao_curta', teaser=dict(start=round(climax['start'], 2), end=round(climax['start'] + peak, 2)),
                                 why='O clímax só chega após %.0f s; uma abertura curta com ele reduz a espera sem entregar a resolução.' % into,
                                 risk='médio: pode antecipar a surpresa'))
        if length >= 20 and not any(w in functions['acao_decisiva'].get('text', '').lower() for w in ('kkk', 'haha')):
            chosen = dict(id='antecipacao_curta', why='Promessa verdadeira, clímax tardio e resolução preservada no fim.',
                          teaser=alternatives[-1]['teaser'])
    return chosen, alternatives
