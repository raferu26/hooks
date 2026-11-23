"""Segurança semântica dos cortes: nenhum corte pode mudar o sentido do que foi dito.

Antes de um corte automático (pausa ou repetição) valer, e ao revisar cortes manuais, o texto
removido é conferido: negações ("não", "nunca"), números e palavras com conteúdo nunca somem em
silêncio, e nenhum corte entra no meio de uma palavra. As checagens são regras simples sobre a
transcrição temporizada; elas apontam o risco, o revisor decide.
"""
import math
import re
import unicodedata


def _plain(value):
    value = unicodedata.normalize('NFKD', str(value).lower())
    return ''.join(c for c in value if not unicodedata.combining(c))


def _fillers():
    from .editing import FILLERS
    return {_plain(x) for x in FILLERS}

NEGATIONS = {'nao', 'nunca', 'jamais', 'nem', 'ninguem', 'nada', 'sem', 'nenhum', 'nenhuma', 'not', 'never',
             'no', 'nobody', 'nothing', 'dont', 'cant', 'wont', 'isnt', 'didnt'}
BLOCKING = ('remove_negacao', 'remove_numero')
LABELS = {
    'remove_negacao': 'remove uma negação',
    'remove_numero': 'remove um número',
    'remove_fala': 'remove palavras ditas',
    'palavra_cortada': 'corta uma palavra ao meio',
    'junta_frases': 'junta duas frases diferentes sem pausa',
}


def _word_rows(transcript, start, end):
    rows = []
    for segment in transcript or []:
        for word in segment.get('words') or []:
            try:
                a, b = float(word['start']), float(word['end'])
            except (KeyError, TypeError, ValueError):
                continue
            text = ' '.join(str(word.get('word', '')).split())
            if text and math.isfinite(a + b) and b > a and b > start and a < end:
                rows.append(dict(start=a, end=b, text=text, normal=re.sub(r'[^a-z0-9]+', '', _plain(text))))
    rows.sort(key=lambda r: (r['start'], r['end']))
    return rows


def check_cut(words, a, b):
    """Problemas de um corte [a, b] (tempos absolutos, no mesmo relógio das palavras)."""
    issues = []
    removed = []
    for w in words:
        overlap = min(b, w['end']) - max(a, w['start'])
        span = w['end'] - w['start']
        if overlap <= 0:
            continue
        if overlap >= .5 * span:
            removed.append(w)
        elif overlap > .06:
            issues.append(dict(kind='palavra_cortada', word=w['text'], at=round(w['start'], 2)))
    for w in removed:
        if w['normal'] in NEGATIONS:
            issues.append(dict(kind='remove_negacao', word=w['text'], at=round(w['start'], 2)))
        elif re.search(r'\d', w['text']):
            issues.append(dict(kind='remove_numero', word=w['text'], at=round(w['start'], 2)))
        elif w['normal'] not in _fillers():
            issues.append(dict(kind='remove_fala', word=w['text'], at=round(w['start'], 2)))
    before = [w for w in words if w['end'] <= a + .03]
    after = [w for w in words if w['start'] >= b - .03]
    if before and after and not removed:
        left, right = before[-1], after[0]
        if left['text'].rstrip('"”’)»').endswith(('.', '!', '?', '…')) and right['start'] - left['end'] > .3:
            # Uma pausa entre frases é parte do ritmo; só avisamos se o corte engole quase toda ela.
            if (right['start'] - left['end']) - (b - a) < .1:
                issues.append(dict(kind='junta_frases', word=right['text'], at=round(right['start'], 2)))
    return issues


def describe(issue):
    return f'{LABELS.get(issue["kind"], issue["kind"])} (“{issue["word"]}” em {issue["at"]:.1f}s)'


def verdict(issues):
    if any(i['kind'] in BLOCKING for i in issues):
        return 'bloqueado'
    return 'atenção' if issues else 'ok'


def filter_decisions(decisions, transcript, start, end):
    """Confere as decisões automáticas de corte (tempos relativos ao clipe) e bloqueia as perigosas."""
    words = _word_rows(transcript, start, end)
    result = []
    for item in decisions:
        if item.get('kind') not in ('silence', 'repetition'):
            result.append(item)
            continue
        issues = check_cut(words, start + float(item['start']), start + float(item['end']))
        state = verdict(issues)
        updated = dict(item, safety=state)
        if issues:
            updated['safety_issues'] = [describe(i) for i in issues][:4]
            updated['requires_review'] = True
            updated['confidence'] = min(float(updated.get('confidence', .7)), .5)
        if state == 'bloqueado':
            updated['enabled'] = False
            updated['reason'] = updated['reason'] + ' Bloqueado pela checagem de sentido: ' + describe(issues[0]) + '.'
        elif state == 'atenção':
            updated['reason'] = updated['reason'] + ' Confira: ' + describe(issues[0]) + '.'
        result.append(updated)
    return result


def analyze_cuts(transcript, start, end, cuts):
    """Avisos para uma lista de cortes (relativos ao clipe), para o editor mostrar ao revisor."""
    words = _word_rows(transcript, start, end)
    warnings = []
    for cut in cuts:
        issues = check_cut(words, start + float(cut['start']), start + float(cut['end']))
        if issues:
            warnings.append(dict(start=round(float(cut['start']), 2), end=round(float(cut['end']), 2),
                                 level=verdict(issues), messages=[describe(i) for i in issues][:4]))
    return warnings
