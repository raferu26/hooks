"""Agentes de apoio à edição: gancho, títulos, limites limpos, cadência de planos e teaser.

Tudo é determinístico e explicável: cada sugestão traz o motivo e o trecho da fala em que
se baseia. Nenhum texto é inventado; os títulos são frases ditas no próprio clipe.
Os tempos retornados são relativos ao início do clipe, salvo indicação.
"""
import math
import re

from .captions import HOOK_WORDS, plain

OPENERS = {'entao', 'tipo', 'e', 'ah', 'eh', 'ne', 'assim', 'bom', 'bem', 'olha', 'hm', 'hmm', 'aham', 'ok', 'entendeu'}
GREETINGS = ('fala galera', 'e ai galera', 'e ai pessoal', 'salve', 'fala pessoal', 'bom dia', 'boa tarde', 'boa noite',
             'fala chat', 'oi gente', 'ola pessoal', 'hello guys', 'hey guys')
DIRECT = {'voce', 'voces', 'vc', 'tu', 'seu', 'sua', 'you', 'your'}
REACTION = ('meu deus', 'nao acredito', 'que isso', 'caraca', 'caramba', 'impossivel', 'socorro', 'nossa',
            'olha isso', 'cara', 'what', 'no way', 'oh my god')
END_MARKS = ('.', '!', '?', '…')


def _words(transcript, start, end):
    result = []
    for segment in transcript or []:
        for word in segment.get('words') or []:
            try:
                a, b = float(word['start']), float(word['end'])
            except (KeyError, TypeError, ValueError):
                continue
            text = ' '.join(str(word.get('word', '')).split())
            if text and math.isfinite(a + b) and b > a and b > start and a < end:
                result.append(dict(start=max(start, a), end=min(end, b), text=text))
    return sorted(result, key=lambda w: (w['start'], w['end']))


def sentences(transcript, start, end):
    """Frases (tempos absolutos) montadas a partir das palavras: pontuação final ou pausa longa."""
    result, current = [], []
    for word in _words(transcript, start, end):
        if current and word['start'] - current[-1]['end'] > .9:
            result.append(current)
            current = []
        current.append(word)
        if word['text'].rstrip('"”’)»').endswith(END_MARKS):
            result.append(current)
            current = []
    if current:
        result.append(current)
    pieces = []
    for group in result:
        pieces.extend(_split_long(group))
    return [dict(start=s[0]['start'], end=s[-1]['end'], text=' '.join(w['text'] for w in s), words=s) for s in pieces]


MAX_SENTENCE_WORDS = 16


def _split_long(group):
    """Fala sem pontuação vira uma frase gigante; quebra na maior pausa interna (mínimo 5 palavras de cada lado)."""
    if len(group) <= MAX_SENTENCE_WORDS:
        return [group]
    gaps = [(group[i + 1]['start'] - group[i]['end'], i + 1) for i in range(4, len(group) - 5)]
    cut = max(gaps)[1] if gaps else len(group) // 2
    return _split_long(group[:cut]) + _split_long(group[cut:])


def hook_score(text):
    """0 a 10. Mede o quanto a frase prende quem está rolando o feed (heurística, não retenção real)."""
    raw = str(text or '')
    n = plain(raw)
    tokens = [plain(w) for w in raw.split() if plain(w)]
    if not tokens:
        return 0.0
    score = 3.0
    if '?' in raw:
        score += 2
    if re.search(r'\d', raw):
        score += 1.5
    score += min(2.4, 1.2 * sum(t in HOOK_WORDS for t in tokens))
    if any(t in DIRECT for t in tokens):
        score += 1
    if '!' in raw:
        score += 1
    if any(plain(term) in n for term in REACTION):
        score += 2
    if len(tokens) > 16:
        score -= 1.5
    elif len(tokens) > 12:
        score -= .7
    if len(tokens) < 3:
        score -= 1.5
    if tokens[0] in OPENERS:
        score -= 1
    if any(plain(g) in n for g in GREETINGS):
        score -= 2.5
    return round(max(0.0, min(10.0, score)), 1)


def _weak_opening(sentence):
    n = plain(sentence['text'])
    tokens = [plain(w) for w in sentence['text'].split() if plain(w)]
    if any(plain(g) in n for g in GREETINGS):
        return 'cumprimento'
    if len(tokens) <= 2 and tokens and tokens[0] in OPENERS:
        return 'enchimento'
    return ''


def hook_analysis(transcript, start, end):
    """Avalia os primeiros 3 segundos e aponta um começo melhor, se existir."""
    frases = sentences(transcript, start, end)
    if not frases:
        return dict(score=0.0, opening='', issues=['Sem fala temporizada no começo.'], suggestion=None)
    first = frases[0]
    opening = first['text']
    score = hook_score(opening)
    issues = []
    lead = first['start'] - start
    if lead > .8:
        issues.append(f'O corte começa com {lead:.1f}s de silêncio antes da fala.')
    weak = _weak_opening(first)
    if weak:
        issues.append('A primeira frase é um ' + weak + ', que costuma perder gente nos 2 primeiros segundos.')
    if score < 4:
        issues.append('A primeira frase tem pouco gancho (sem pergunta, número, reação ou promessa).')
    suggestion = None
    best, best_score = None, score
    for frase in frases[1:]:
        if frase['start'] - start > 14 or frase['end'] > end - 6:
            continue
        value = hook_score(frase['text'])
        if value >= score + 2 and value > best_score and not _weak_opening(frase):
            best, best_score = frase, value
    if best and (score < 5.5 or weak):
        suggestion = dict(start=round(max(0.0, best['start'] - start - .25), 2), text=best['text'], score=best_score,
                          reason=f'Esta frase tem mais gancho ({best_score:.1f} contra {score:.1f}). Começar nela pula o trecho fraco.')
    return dict(score=score, opening=opening, issues=issues, suggestion=suggestion)


def tighten_bounds(transcript, start, end, pad_start=.25, pad_end=.4):
    """Limites limpos: tira silêncio e enchimento do começo e silêncio do final (sem entrar em frase)."""
    frases = sentences(transcript, start, end)
    if not frases:
        return dict(start=start, end=end, changes=[])
    new_start, new_end, changes = start, end, []
    first = frases[0]
    skip = first
    if _weak_opening(first) and len(frases) > 1 and frases[1]['start'] - first['start'] < 6 and end - frases[1]['start'] > 10:
        skip = frases[1]
        changes.append(f'Começo pulado: “{first["text"][:40]}” é {_weak_opening(first)}.')
    target = max(start, skip['start'] - pad_start)
    if target - start > .5 or skip is not first:
        new_start = round(target, 2)
        if skip is first:
            changes.append(f'Silêncio de {target - start:.1f}s removido do começo.')
    last = frases[-1]
    target_end = min(end, last['end'] + pad_end)
    if end - target_end > .8:
        new_end = round(target_end, 2)
        changes.append(f'Silêncio de {end - target_end:.1f}s removido do final.')
    if new_end - new_start < 8:
        return dict(start=start, end=end, changes=[])
    return dict(start=new_start, end=new_end, changes=changes)


def suggest_titles(transcript, start, end, limit=3, max_chars=44):
    """Títulos extraídos da fala: frases curtas com maior gancho, cortadas em pontuação."""
    options = []
    for frase in sentences(transcript, start, end):
        text = frase['text'].strip()
        if len(text.split()) < 3:
            continue
        pieces = [p.strip() for p in re.split(r'(?<=[,;:])\s+', text) if len(p.split()) >= 3] or [text]
        for piece in pieces:
            piece = piece.rstrip(',;:')
            words = piece.split()
            if len(words) > 8:
                piece = ' '.join(words[:8]).rstrip(',;:') + '…'
            if len(piece) > max_chars or _weak_opening(dict(text=piece)):
                continue
            options.append((hook_score(piece) - .02 * max(0, frase['start'] - start), piece, frase['start'] - start))
    options.sort(key=lambda item: -item[0])
    result, seen = [], set()
    for score, piece, at in options:
        key = plain(piece)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(text=piece, score=round(score, 1), at=round(at, 2)))
        if len(result) >= limit:
            break
    return result


def suggest_teaser(transcript, start, end, min_into=7, longest=3.8):
    """Melhor frase curta da segunda metade do clipe, para abrir o vídeo (reordenamento)."""
    best = None
    for frase in sentences(transcript, start, end):
        a, b = frase['start'] - start, frase['end'] - start
        length = b - a
        if a < min_into or not 1.2 <= length <= longest or b > end - start - .5:
            continue
        value = hook_score(frase['text'])
        if value >= 5 and (best is None or value > best['score']):
            best = dict(start=round(a, 2), end=round(b, 2), text=frase['text'], score=value)
    return best


def cadence_punches(transcript, start, end, preset, existing=(), zoom=1.08, gap=3.2, limit=6):
    """Planos fechados que alternam com o plano aberto, um por frase (ritmo de edição de fala).

    Evita sobrepor zooms existentes e nunca fecha o plano em frases curtas demais.
    """
    result = []
    busy = [(float(p['start']), float(p['end'])) for p in existing]
    toggle = False
    for frase in sentences(transcript, start, end):
        a, b = frase['start'] - start, frase['end'] - start
        if b - a < 1.4 or a < .6:
            continue
        toggle = not toggle
        if not toggle:
            continue
        a = max(0.0, a - .1)
        b = min(b + .1, a + 4.5, end - start)
        if any(a < y + gap * .4 and b > x - gap * .4 for x, y in busy) or (result and a - result[-1]['end'] < 1.2):
            continue
        result.append(dict(start=round(a, 3), end=round(b, 3), zoom=round(min(zoom, preset.get('zoom_max', zoom) + .02), 3),
                           reason='Plano fechado na frase (alterna com o plano aberto).'))
        if len(result) >= limit:
            break
    return result


def snap_to_beats(times, beats, tolerance=.2):
    """Aproxima tempos da batida mais próxima dentro da tolerância; os demais ficam como estão."""
    result = []
    for value in times:
        near = min(beats, key=lambda b: abs(b - value), default=None)
        result.append(round(near, 3) if near is not None and abs(near - value) <= tolerance else round(value, 3))
    return result


def analyze_candidate(transcript, start, end):
    """Resumo usado na mesa de cortes e no editor."""
    return dict(hook=hook_analysis(transcript, start, end), titles=suggest_titles(transcript, start, end),
                tighten=tighten_bounds(transcript, start, end), teaser=suggest_teaser(transcript, start, end))
