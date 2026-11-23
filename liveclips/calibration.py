"""Confiabilidade das notas: só afirma 'calibrado' com dados RESERVADOS e em quantidade suficiente.

Hoje as notas do programa são heurísticas. Este módulo mede quão perto elas estão da realidade quando existirem casos
revisados por pessoas; antes disso, o estado correto é 'nao_calibrado'."""
MIN_HELDOUT = 30


def brier(pairs):
    pairs = [(float(p), 1.0 if y else 0.0) for p, y in pairs]
    return round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4) if pairs else None


def reliability(pairs, bins=5):
    pairs = [(min(1.0, max(0.0, float(p))), 1.0 if y else 0.0) for p, y in pairs]
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        rows = [(p, y) for p, y in pairs if lo <= p < hi or (i == bins - 1 and p == 1.0)]
        out.append(dict(faixa=[round(lo, 2), round(hi, 2)], n=len(rows),
                        previsto=round(sum(p for p, _ in rows) / len(rows), 3) if rows else None,
                        observado=round(sum(y for _, y in rows) / len(rows), 3) if rows else None))
    return out


def ece(pairs, bins=5):
    total = len(pairs)
    if not total:
        return None
    return round(sum(b['n'] / total * abs(b['previsto'] - b['observado']) for b in reliability(pairs, bins) if b['n']), 4)


def status(pairs_heldout, ece_limit=.1):
    """Estado honesto: sem dados reservados suficientes, 'nao_calibrado' — mesmo que a medida pareça boa."""
    n = len(pairs_heldout)
    if n < MIN_HELDOUT:
        return dict(estado='nao_calibrado', motivo=f'{n} caso(s) reservado(s); mínimo {MIN_HELDOUT}.', n=n)
    e = ece(pairs_heldout)
    return dict(estado='calibrado' if e <= ece_limit else 'descalibrado', ece=e, brier=brier(pairs_heldout), n=n,
                curva=reliability(pairs_heldout))
