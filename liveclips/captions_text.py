"""Legenda a partir de TEXTO colado/digitado pelo usuário, sem reconhecimento de fala (Hook's sem IA, fase 1).

Entrada: o texto que o usuário forneceu + a atividade de fala do áudio (envelope de energia, `technical.py`) + opcionalmente
"toques" (instantes em que o usuário marcou o início de cada frase enquanto ouvia).
Saída: segmentos `{start, end, text, words, source:'texto colado', timing:'estimado'|'toques'}` e um SRT.

O que é e o que NÃO é: é uma **estimativa**. As frases são distribuídas no tempo de fala detectado, com peso pelo número de sílabas
(contagem por grupos de vogais, português). Não ouve o que foi dito: se o texto não corresponder ao áudio, a legenda sai errada.
Os toques corrigem o início de cada frase; palavras dentro da frase continuam estimadas. Sem modelos, sem rede."""
import re


from . import technical

MAX_CHARS = 42          # largura de uma linha de legenda para vídeo vertical
MAX_TEXT = 60000
_VOWELS = re.compile(r'[aeiouáéíóúâêôãõàü]+', re.I)


def syllables(word):
    """Sílabas estimadas por grupos de vogais (heurística do português; hiatos comuns contam como duas)."""
    w = re.sub(r'[^a-záéíóúâêôãõàçü]', '', word.lower())
    if not w:
        return 0
    groups = _VOWELS.findall(w)
    n = len(groups)
    for g in groups:                       # hiatos frequentes: ia/io/ua/uo entre consoantes, aí/aú, oa, ea
        if len(g) >= 3 and not re.search(r'(ai|ei|oi|ui|au|eu|iu|ou)', g):
            n += 1
    return max(1, n)


def split_phrases(text, max_chars=MAX_CHARS):
    """Linhas do usuário mandam; linha longa quebra em pontuação e depois em limite de caracteres (nunca no meio da palavra)."""
    text = str(text or '').replace('\r\n', '\n').replace('\r', '\n')[:MAX_TEXT]
    out = []
    for line in text.split('\n'):
        line = ' '.join(line.split())
        if not line:
            continue
        parts = [p for p in re.split(r'(?<=[.!?…;:])\s+', line) if p]
        for part in parts:
            words, cur = part.split(' '), ''
            for w in words:
                if cur and len(cur) + 1 + len(w) > max_chars:
                    out.append(cur); cur = w
                else:
                    cur = (cur + ' ' + w).strip()
            if cur:
                out.append(cur)
    # frases de uma palavra só colam na vizinha (evita legenda piscando)
    merged = []
    for p in out:
        if merged and len(p.split()) == 1 and len(merged[-1]) + 1 + len(p) <= max_chars and not re.search(r'[.!?…]$', merged[-1]):
            merged[-1] += ' ' + p
        else:
            merged.append(p)
    return merged


def speech_spans(db, step, t0=0.0, min_gap_s=.25, pad_s=.04):
    """Intervalos com fala (complemento dos silêncios) em segundos, a partir de `t0`. Sem contraste → o clipe todo."""
    total = len(db) * step
    if not len(db):
        return []
    quiet = technical.silences(db, step=step, min_s=min_gap_s, pad_s=pad_s)
    spans, cursor = [], 0.0
    for q in quiet:
        if q['start'] - cursor > .08:
            spans.append((cursor, q['start']))
        cursor = max(cursor, q['end'])
    if total - cursor > .08:
        spans.append((cursor, total))
    return [(round(a + t0, 3), round(b + t0, 3)) for a, b in spans] or [(round(t0, 3), round(t0 + total, 3))]


def _clock_map(spans):
    """Mapeia 'tempo de fala acumulado' → instante real, pulando os silêncios."""
    cum, acc = [], 0.0
    for a, b in spans:
        cum.append((acc, a, b)); acc += b - a
    return cum, acc


def _at(cum, tau, end_side=False):
    for acc, a, b in cum:
        if tau < acc + (b - a) or (end_side and tau <= acc + (b - a) + 1e-9):
            return a + max(0.0, tau - acc)
    acc, a, b = cum[-1]
    return b


def _weights(phrase):
    ws = phrase.split()
    return [max(1, syllables(w)) for w in ws] or [1]


def align(phrases, spans):
    """Distribui as frases (peso = sílabas + 0,5 por palavra) no tempo de fala. Devolve segmentos com `words` estimadas."""
    if not phrases or not spans:
        return []
    cum, total = _clock_map(spans)
    weights = [sum(_weights(p)) + .5 * len(p.split()) for p in phrases]
    scale = total / sum(weights)
    edges = [0.0]
    for wt in weights:
        edges.append(edges[-1] + wt * scale)
    # as pausas do áudio são fronteiras naturais de frase: cada fronteira estimada gruda na pausa mais próxima (se perto o bastante)
    gaps = [acc for acc, _, _ in cum[1:]]
    used = set()
    for k in range(1, len(phrases)):
        lo, hi = edges[k - 1], edges[k + 1]
        tol = .45 * min(edges[k] - lo, hi - edges[k])
        best = min((g for g in gaps if g not in used and lo + .05 < g < hi - .05), key=lambda g: abs(g - edges[k]), default=None)
        if best is not None and abs(best - edges[k]) <= tol:
            edges[k] = best; used.add(best)
    out = []
    for phrase, a_tau, b_tau in zip(phrases, edges, edges[1:]):
        start, end = _at(cum, a_tau), _at(cum, b_tau, end_side=True)
        ws, sy = phrase.split(), _weights(phrase); tot = float(sum(sy)); k = 0.0; words = []
        for w, s in zip(ws, sy):
            wa, wb = a_tau + (b_tau - a_tau) * k / tot, a_tau + (b_tau - a_tau) * (k + s) / tot; k += s
            words.append(dict(start=round(_at(cum, wa), 3), end=round(_at(cum, wb, end_side=True), 3), word=w))
        out.append(dict(start=round(start, 3), end=round(max(end, start + .3), 3), text=phrase, words=words,
                        source='texto colado', timing='estimado'))
    return out


def retime_with_taps(phrases, taps, spans, clip_end):
    """Cada toque fixa o início de uma frase; frases sem toque ficam distribuídas entre os toques vizinhos."""
    taps = [float(t) for t in taps if t is not None]
    n = min(len(taps), len(phrases))
    if n == 0:
        return align(phrases, spans)
    taps = sorted(taps[:n]); out = []
    for i in range(n):
        last = i == n - 1
        a = taps[i]
        group_end = (len(phrases) if last else i + 1)
        group = phrases[i:group_end] if last else [phrases[i]]
        b = clip_end if last else taps[i + 1]
        inside = [(max(x, a), min(y, b)) for x, y in spans if y > a and x < b] or [(a, max(a + .3, b))]
        segs = align(group, inside)
        for s in segs:
            s['timing'] = 'toques'
        out.extend(segs)
    for prev, nxt in zip(out, out[1:]):       # sem sobreposição entre frases
        if prev['end'] > nxt['start']:
            prev['end'] = round(max(prev['start'] + .2, nxt['start'] - .02), 3)
    return out


def _stamp(t):
    ms = int(round(max(0.0, t) * 1000))
    return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def to_srt(segments):
    return '\n'.join('%d\n%s --> %s\n%s\n' % (i, _stamp(s['start']), _stamp(s['end']), s['text']) for i, s in enumerate(segments, 1))


def build(text, db, step, offset=0.0, taps=None, clip_end=None):
    """Alto nível: texto + envelope de energia do trecho → {segments, srt, warnings}. `offset` = tempo da sessão do início do envelope."""
    phrases = split_phrases(text)
    if not phrases:
        raise ValueError('Cole ou digite o texto da legenda.')
    spans = speech_spans(db, step, offset)
    end = clip_end if clip_end is not None else offset + len(db) * step
    warnings = []
    if len(spans) == 1 and spans[0][1] - spans[0][0] >= (len(db) * step) * .98:
        warnings.append('Não encontrei pausas no áudio: as frases foram distribuídas por igual no trecho inteiro.')
    segments = retime_with_taps(phrases, taps, spans, end) if taps else align(phrases, spans)
    speech_s = sum(b - a for a, b in spans); syl = sum(sum(_weights(p)) for p in phrases)
    if speech_s > 0 and syl / speech_s > 9.5:
        warnings.append('O texto parece longo demais para o tempo de fala (%.1f sílabas/s): confira se ele corresponde a este trecho.' % (syl / speech_s))
    if speech_s > 0 and syl / speech_s < 1.5:
        warnings.append('O texto parece curto demais para o tempo de fala (%.1f sílabas/s): confira se ele corresponde a este trecho.' % (syl / speech_s))
    return dict(segments=segments, srt=to_srt(segments), warnings=warnings, spans=[list(s) for s in spans], phrases=len(phrases))
