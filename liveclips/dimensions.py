"""Dimensões separadas de um candidato (N14, N23): observação, interpretação, prontidão, valor, novidade, afinidade.

Nada aqui é probabilidade de viralização nem certeza emocional. Cada valor tem sua base declarada; quando falta dado
a dimensão é None ("desconhecido"), não um número inventado. O estado geral só diz o que fazer com o candidato.
"""

BASIS = 'heuristico_nao_calibrado'


def _clip(v):
    return round(max(0.0, min(1.0, float(v))), 3)


def _overlap(a, b):
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    return inter / max(1e-6, min(a[1] - a[0], b[1] - b[0]))


def novelty(candidate, others):
    """1 = nada parecido na sessão; cai com sobreposição temporal e termos repetidos. Retomada com valor novo não zera."""
    window = (float(candidate['start']), float(candidate['end']))
    words = set(str(candidate.get('transcript', '')).lower().split())
    worst = 0.0
    for o in others or []:
        ow = (float(o['start']), float(o['end']))
        ov = _overlap(window, ow)
        ot = set(str(o.get('transcript', '')).lower().split())
        sim = len(words & ot) / max(1, len(words | ot))
        worst = max(worst, ov * .7 + sim * .3)
    return _clip(1 - worst)


def compute(candidate, assessment=None, *, episodes=None, others=None, creator_signal=None, associations=None):
    """`episodes`: lista de episódios ligados ao trecho (status aberto/resolvido/revisar). `creator_signal`: 0–1 ou None."""
    score = float(candidate.get('score') or 0)
    obs = assessment['forca_observacao'] if assessment else None
    conflicts = list((assessment or {}).get('conflitos') or [])
    conf = float(candidate.get('moment_confidence') or 0)
    interp = conf * (1 - .2 * len(conflicts))
    if assessment and assessment.get('somente_dependentes'):
        interp *= .8
    if associations and any(a.get('incerta') for a in associations):
        interp *= .85
    interp = _clip(interp) if conf else None
    if episodes:
        open_ep = [e for e in episodes if e.get('status') in ('aberto', 'revisar')]
        ready = 0.3 if open_ep else 1.0
        wait_reason = [f"{e['kind']} sem desfecho ({e['status']})" for e in open_ep] or None
    else:
        ready, wait_reason = None, None
    value = _clip(score / (score + 12.0)) if score > 0 else 0.0
    nov = novelty(candidate, others)
    fit = None if creator_signal is None else _clip(creator_signal)
    exploratory = bool(candidate.get('fallback') or candidate.get('low_confidence') or candidate.get('exploratory'))
    if assessment and assessment.get('abstencao') == 'aguardando_contexto' or (ready is not None and ready < .5):
        status = 'aguardando_contexto'
    elif exploratory:
        status = 'exploratorio'
    elif conflicts or (interp is not None and interp < .35):
        status = 'revisao_necessaria'
    else:
        status = 'pronto_para_revisar'
    return dict(base=BASIS, nota_nao_e_probabilidade=True, forca_da_observacao=obs, suporte_da_interpretacao=interp,
                prontidao_do_episodio=ready, aguardando=wait_reason, valor_editorial=value, novidade=nov,
                afinidade_com_criador=fit, conflitos=conflicts, estado=status,
                abstencao=(assessment or {}).get('abstencao'))
