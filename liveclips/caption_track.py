"""Contrato e medição das legendas (P05/F11): o que foi dito, o que é exibido, quão firme é o tempo.

Separa transcrição literal, texto de exibição (vocabulário/correção manual) e agrupamento visual. Cada palavra carrega
confiança, origem e o NÍVEL de alinhamento: 'palavra' (tempo do ASR por palavra), 'estimado' (repartido dentro da frase)
ou 'bloco' (só a frase tem tempo). Tempo desconhecido nunca é apresentado como alinhamento comprovado.
Também mede erro de texto (WER) e de tempo contra uma amostra revisada por pessoa.
"""
import json
import math
import re

READ_CPS = 20.0           # alarme inicial do dossiê (caracteres/s); não é certificação
MIN_WORD = .04            # palavra mais curta que isso é tratada como tempo não confiável
LOW_CONFIDENCE = .35


def _norm(text):
    return re.sub(r'[^\wà-ÿ]+', '', str(text).lower())


def words_of(segment):
    """Palavras de um segmento com nível de alinhamento honesto.

    Palavras com tempo próprio, crescente e plausível ficam 'palavra'. Se algum tempo falha, o segmento inteiro cai para
    'estimado' (repartição por tamanho) e, sem palavras, para 'bloco'."""
    raw = [w for w in segment.get('words') or [] if str(w.get('word', '')).strip()]
    a, b = float(segment['start']), float(segment['end'])
    if raw:
        ok, last = True, a - 1e-6
        for w in raw:
            try:
                s, e = float(w['start']), float(w['end'])
            except (KeyError, TypeError, ValueError):
                ok = False
                break
            if not (math.isfinite(s) and math.isfinite(e)) or e - s < MIN_WORD or s < last - .02 or e > b + .5:
                ok = False
                break
            last = e
        if ok:
            return [dict(literal=str(w['word']).strip(), display=str(w['word']).strip(), start=float(w['start']), end=float(w['end']),
                         confidence=w.get('p'), origin='asr', alignment='palavra') for w in raw]
        weights = [max(1, len(_norm(w['word']))) for w in raw]
        total, cursor, out = sum(weights), a, []
        for w, weight in zip(raw, weights):
            end = cursor + (b - a) * weight / total
            out.append(dict(literal=str(w['word']).strip(), display=str(w['word']).strip(), start=round(cursor, 3), end=round(end, 3),
                            confidence=w.get('p'), origin='asr', alignment='estimado'))
            cursor = end
        return out
    text = str(segment.get('text', '')).strip()
    return [dict(literal=text, display=text, start=a, end=b, confidence=None, origin='asr', alignment='bloco')] if text else []


def apply_display(words, vocabulary=(), manual=None):
    """Texto de exibição. A transcrição literal NÃO muda; cada alteração é registrada com a origem.

    `vocabulary`: termos do canal (grafia correta). Só corrige palavras que já foram ditas e parecem o termo (mesma grafia
    sem acento/caixa); nunca acrescenta palavra. `manual`: {índice: texto} editado por pessoa."""
    terms = {_norm(t): t for t in vocabulary if _norm(t)}
    changes = []
    for i, w in enumerate(words):
        if manual and i in manual:
            changes.append(dict(index=i, de=w['display'], para=manual[i], origem='manual'))
            w.update(display=manual[i], origin='manual')
        elif _norm(w['literal']) in terms and terms[_norm(w['literal'])] != w['literal']:
            changes.append(dict(index=i, de=w['display'], para=terms[_norm(w['literal'])], origem='vocabulario'))
            w.update(display=terms[_norm(w['literal'])], origin='vocabulario')
    return words, changes


def reading(lines, cps_limit=READ_CPS):
    """Velocidade de leitura por legenda. Devolve só os pontos de atenção; é alarme, não certificação."""
    flagged = []
    for ln in lines:
        length = max(.05, float(ln['end']) - float(ln['start']))
        cps = len(str(ln['text']).replace('\n', ' ')) / length
        if cps > cps_limit:
            flagged.append(dict(start=ln['start'], end=ln['end'], cps=round(cps, 1), text=ln['text'][:40]))
    return flagged


def collisions(lines, caption_box, regions):
    """Legendas cujo retângulo (x0,y0,x1,y1 normalizados 0–1) cruza uma região protegida (rosto, HUD).

    `regions`: [{'name', 'box', 'start', 'end'}] com tempo opcional. A caixa da legenda é a mesma para todas (posição fixa)."""
    hits = []
    for ln in lines:
        for r in regions:
            if r.get('start') is not None and not (float(ln['start']) < r['end'] and float(ln['end']) > r['start']):
                continue
            ax0, ay0, ax1, ay1 = caption_box
            bx0, by0, bx1, by1 = r['box']
            if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
                hits.append(dict(start=ln['start'], end=ln['end'], region=r['name']))
    return hits


def summary(words):
    """Quanto da legenda tem tempo realmente alinhado por palavra, estimado ou só por bloco."""
    n = len(words)
    count = {k: sum(1 for w in words if w['alignment'] == k) for k in ('palavra', 'estimado', 'bloco')}
    low = sum(1 for w in words if w.get('confidence') is not None and w['confidence'] < LOW_CONFIDENCE)
    return dict(palavras=n, alinhamento=count, baixa_confianca=low,
                aviso=None if n == 0 or count['palavra'] == n else 'Parte da legenda tem tempo estimado, não alinhado por palavra.')


def review_document(segments, vocabulary=(), manual=None):
    """Documento revisável (JSON) com literal, exibição, confiança, origem e alinhamento por palavra."""
    all_words, items = [], []
    for seg in segments or []:
        words = words_of(seg)
        words, changes = apply_display(words, vocabulary, manual)
        all_words += words
        items.append(dict(start=seg['start'], end=seg['end'], words=words, alteracoes=changes))
    return dict(schema='liveclips.legendas', version=1, resumo=summary(all_words), segmentos=items)


def wer(reference, hypothesis):
    """Taxa de erro de palavras (distância de edição / palavras de referência). Compara texto sem acento de caixa/pontuação."""
    ref = [_norm(w) for w in str(reference).split() if _norm(w)]
    hyp = [_norm(w) for w in str(hypothesis).split() if _norm(w)]
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return round(prev[-1] / len(ref), 4)


def timing_error(reference, hypothesis):
    """Erro de tempo (ms) entre palavras revisadas e as do sistema, pareadas por ordem e texto. Palavras sem par são contadas."""
    ref = [(_norm(w['word']), float(w['start']), float(w['end'])) for w in reference if _norm(w['word'])]
    hyp = [(_norm(w['word']), float(w['start']), float(w['end'])) for w in hypothesis if _norm(w['word'])]
    errors, j, missing = [], 0, 0
    for text, s, e in ref:
        k = next((x for x in range(j, len(hyp)) if hyp[x][0] == text), None)
        if k is None:
            missing += 1
            continue
        errors.append(max(abs(hyp[k][1] - s), abs(hyp[k][2] - e)) * 1000)
        j = k + 1
    errors.sort()
    pct = lambda q: round(errors[min(len(errors) - 1, int(math.ceil(q * len(errors))) - 1)], 1) if errors else None
    return dict(pareadas=len(errors), sem_par=missing, mediano_ms=pct(.5), p95_ms=pct(.95),
                dentro_de_100ms=round(sum(e <= 100 for e in errors) / len(errors), 3) if errors else None,
                dentro_de_200ms=round(sum(e <= 200 for e in errors) / len(errors), 3) if errors else None)


def dump(document):
    return json.dumps(document, ensure_ascii=False, indent=1)
