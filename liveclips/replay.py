"""Reprodução causal e avaliação: confere se o sistema olharia o futuro e mede acerto contra casos humanos.

`no_lookahead`: roda a função só com dados até T e com todos; o resultado para eventos < T tem de ser o mesmo.
`ablate`: remove famílias de sinais e compara. `evaluate`: cobertura de momentos humanos e rejeitados."""
import copy


def truncate(transcript, signals, upto):
    t = [s for s in transcript if float(s['end']) <= upto]
    sig = {k: ([p for p in v if float(p.get('time', 0)) <= upto] if isinstance(v, list) and v and isinstance(v[0], dict) and 'time' in v[0] else v)
           for k, v in (signals or {}).items()}
    return t, sig


def no_lookahead(fn, transcript, signals, upto, key=lambda c: (round(c['start'], 1), round(c['end'], 1))):
    """`fn(transcript, signals) -> lista de candidatos`. Devolve violações: candidatos antes de `upto` que só existem com o futuro."""
    full = {key(c) for c in fn(transcript, signals) if c['end'] <= upto}
    cut = {key(c) for c in fn(*truncate(transcript, signals, upto)) if c['end'] <= upto}
    return dict(ok=full == cut, so_com_futuro=sorted(full - cut), so_sem_futuro=sorted(cut - full))


def ablate(fn, transcript, signals, families):
    base = fn(transcript, signals)
    out = {}
    for fam in families:
        s = copy.deepcopy(signals)
        s[fam] = []
        got = fn(transcript, s)
        out[fam] = dict(candidatos=len(got), delta=len(got) - len(base))
    return dict(base=len(base), sem=out)


def _overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0])) / max(1e-6, min(a[1] - a[0], b[1] - b[0]))


def evaluate(candidates, cases, min_overlap=.5):
    """Cobertura dos momentos humanos (approved/missed) e quantos candidatos caíram em rejeitados. Sem casos = sem número."""
    want = [c['human_intervals'][0] for c in cases if c.get('case_kind') in ('approved', 'missed') and c.get('human_intervals')]
    bad = [(c.get('human_intervals') or [[0, 0]])[0] for c in cases if c.get('case_kind') == 'rejected' and c.get('human_intervals')]
    spans = [(c['start'], c['end']) for c in candidates]
    if not want and not bad:
        return dict(estado='sem_casos', cobertura=None, nota='Sem casos revisados, nenhuma métrica é calculada.')
    hit = sum(any(_overlap(w, s) >= min_overlap for s in spans) for w in want)
    return dict(estado='medido', n_humanos=len(want), cobertura=round(hit / len(want), 3) if want else None,
                perdidos=len(want) - hit, candidatos=len(spans),
                sobre_rejeitados=sum(any(_overlap(b, s) >= min_overlap for b in bad) for s in spans))
