"""Hábitos do revisor: o sistema aprende com o que você corrige, sem esperar métricas de post.

Cada corte aprovado é comparado com o que o agente propôs:
- começo/fim: se você quase sempre tira (ou acrescenta) o mesmo tanto, o agente passa a propor assim;
- legenda: palavras que você troca viram sugestões de dicionário (você aceita ou ignora);
- efeitos: se você apaga a maioria dos zooms automáticos, o agente passa a usar menos.
Tudo exige repetição (nunca uma edição isolada), é limitado e fica visível em Ajustes.
"""
import difflib
from collections import Counter
from statistics import median

from .captions import lines_from_transcript, plain, vocabulary_terms

MIN_SAMPLES = 3
CONSISTENCY = .7
MAX_OFFSET = 3.0
MIN_OFFSET = .5
MIN_CORRECTIONS = 2
EFFECT_KINDS = ('zoom', 'silence', 'repetition', 'sfx', 'overlay')


def bounds_delta(data, start, end):
    """(Δ começo, Δ fim) em segundos entre o que o agente propôs e o corte final; None se não houver registro."""
    base = data.get('agent_bounds')
    if not base or len(base) != 2:
        return None
    return round(float(start) - float(base[0]), 3), round(float(end) - float(base[1]), 3)


def _consistent(values):
    """Mediana limitada se ao menos 70% dos valores têm o mesmo sinal e a mediana é relevante."""
    if len(values) < MIN_SAMPLES:
        return 0.0, False
    mid = median(values)
    if abs(mid) < MIN_OFFSET:
        return 0.0, False
    same = sum(1 for v in values if v * mid > 0 and abs(v) >= MIN_OFFSET / 2)
    if same / len(values) < CONSISTENCY:
        return 0.0, False
    return round(max(-MAX_OFFSET, min(MAX_OFFSET, mid)), 2), True


def caption_corrections(data, start, end, project, profile):
    """Pares (palavra do agente, palavra sua) a partir das legendas que você editou."""
    lines = ((project or {}).get('captions') or {}).get('lines')
    if not lines:
        return []
    from .captions import caption_terms
    auto, _ = lines_from_transcript(data.get('transcript_segments', []), start, end, caption_terms(profile), corrections=profile.get('corrections', ''))
    before = [w.get('word', '') for ln in auto for w in (ln.get('words') or [])] or \
             [t for ln in auto for t in str(ln.get('text', '')).split()]
    after = [t for ln in lines for t in str(ln.get('text', '')).split()]
    a = [plain(x) for x in before]
    b = [plain(x) for x in after]
    pairs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == 'replace' and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                old, new = before[i1 + k].strip('.,!?;:…"'), after[j1 + k].strip('.,!?;:…"')
                if old and new and plain(old) != plain(new):
                    pairs.append((old, new))
    return pairs


def effect_stats(data, project=None):
    """{tipo: (decisões do agente, desligadas por você)} neste corte."""
    overrides = data.get('edit_overrides') or {}
    stats = {}
    for item in data.get('edit_plan', {}).get('decisions', []):
        kind = item.get('kind')
        if kind not in EFFECT_KINDS or item.get('budget') or item.get('safety') == 'bloqueado':
            continue
        total, off = stats.get(kind, (0, 0))
        default = bool(item.get('enabled'))
        now = bool(overrides.get(item['id'], default))
        stats[kind] = (total + 1, off + (1 if default and not now else 0))
    return stats


def learn(samples, vocabulary=''):
    """Resumo dos hábitos. `samples`: lista de dicts com bounds, pairs, effects (um por corte aprovado)."""
    starts = [s['bounds'][0] for s in samples if s.get('bounds')]
    ends = [s['bounds'][1] for s in samples if s.get('bounds')]
    start_offset, start_ok = _consistent(starts)
    end_offset, end_ok = _consistent(ends)
    counts = Counter(pair for s in samples for pair in set(s.get('pairs') or []))
    known = {plain(t) for t in vocabulary_terms(vocabulary)}
    corrections, suggestions = [], []
    for (old, new), n in counts.most_common(20):
        if n < MIN_CORRECTIONS:
            continue
        corrections.append(dict(de=old, para=new, n=n))
        close = difflib.SequenceMatcher(a=plain(old), b=plain(new)).ratio() >= .7
        if close and len(plain(new)) >= 4 and plain(new) not in known:
            suggestions.append(dict(term=new, de=old, n=n))
    factors, notes = {}, []
    for kind in EFFECT_KINDS:
        total = sum(s['effects'].get(kind, (0, 0))[0] for s in samples if s.get('effects'))
        off = sum(s['effects'].get(kind, (0, 0))[1] for s in samples if s.get('effects'))
        if total >= 6:
            rate = off / total
            factors[kind] = .5 if rate >= .6 else .75 if rate >= .35 else 1.0
            if factors[kind] < 1:
                label = {'zoom': 'zooms', 'silence': 'cortes de pausa', 'repetition': 'cortes de repetição',
                         'sfx': 'efeitos sonoros', 'overlay': 'imagens'}[kind]
                notes.append(f'Você desligou {off} de {total} {label} automáticos; o agente passa a usar menos.')
    if start_ok:
        notes.append(f'Você costuma {"cortar" if start_offset > 0 else "recuar"} ~{abs(start_offset):.1f}s do começo; o agente aplica isso.')
    if end_ok:
        notes.append(f'Você costuma {"encurtar" if end_offset < 0 else "esticar"} ~{abs(end_offset):.1f}s do fim; o agente aplica isso.')
    if suggestions:
        notes.append('Palavras que você corrige com frequência podem entrar no dicionário.')
    return dict(samples=len(samples), start_offset=start_offset, end_offset=end_offset,
                offset_reliable=bool(start_ok or end_ok), corrections=corrections,
                dictionary_suggestions=suggestions[:6], effect_factor={k: v for k, v in factors.items() if v < 1},
                notes=notes)
