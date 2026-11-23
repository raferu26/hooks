"""Variações de um corte: teste A/B de abertura e série em partes (Parte 1/2).

Nada é publicado daqui. O A/B cria uma cópia do corte com a abertura (teaser) invertida; você posta as duas
em momentos parecidos e registra os números de cada uma. A divisão em série procura uma pausa natural perto
do meio onde a parte 1 termina deixando vontade de ver a 2 e a parte 2 abre sem depender da anterior.
"""
from . import agents, judge

MIN_PART = 20.0


def best_split(transcript, start, end, min_part=MIN_PART):
    """Melhor ponto de corte (segundo absoluto) entre `start+min_part` e `end-min_part`. None se não houver."""
    if end - start < 2 * min_part:
        return None
    frases = agents.sentences(transcript, start, end)
    mid = (start + end) / 2
    best = None
    for i, frase in enumerate(frases[:-1]):
        at = frase['end']
        if at - start < min_part or end - at < min_part:
            continue
        nxt = frases[i + 1]
        if nxt['start'] - at > 2.5:
            at = (at + nxt['start']) / 2
        left = judge.edge_scores(transcript, start, at + .05)
        right = judge.edge_scores(transcript, at, end)
        score = left['close'] + right['open'] - 6 * abs(at - mid) / max(1.0, (end - start) / 2)
        if best is None or score > best['score']:
            best = dict(at=round(at, 2), score=round(score, 2), close=round(left['close'], 1), open=round(right['open'], 1),
                        reason=f'Pausa natural: a parte 1 fecha com nota {left["close"]:.0f}/10 e a parte 2 abre com nota {right["open"]:.0f}/10.')
    return best


def part_title(index, total, start, end):
    return dict(id=f'serie{index}', text=f'Parte {index}/{total}', start=0.0, end=min(2.5, max(.6, end - start)), style='big',
                position='top', color='#FFFFFF')


def ab_project(project, hook, duration):
    """Projeto da variação B: sem abertura se o A tem; com a frase mais forte como abertura se o A não tem."""
    project = dict(project or {})
    if project.get('teaser'):
        project['teaser'] = None
        return project, 'sem a abertura (teaser)'
    suggestion = (hook or {}).get('suggestion')
    if not suggestion:
        raise ValueError('Não achei uma frase mais forte para usar de abertura neste corte. O teste A/B de abertura precisa de uma candidata.')
    a = float(suggestion['start'])
    b = min(duration, a + 3.5)
    if b - a < .8:
        raise ValueError('A frase candidata é curta demais para abrir o vídeo.')
    project['teaser'] = dict(start=round(a, 2), end=round(b, 2))
    return project, 'com a frase mais forte como abertura'
