"""Diferença entre o projeto proposto e o salvo pela pessoa -> mudanças tipadas para a memória (F22/S03).

Só registra o que mudou. Sem motivo declarado a memória guarda um caso LOCAL do corte e uma hipótese fraca; nada vira
preferência do streamer sem pedido explícito. Textos de legenda e transcrição não entram (são dados, não regras).
"""
LIMIT = 6


def _ids(items):
    return {i.get('id'): i for i in items or [] if i.get('id')}


def _key(item):
    return (round(float(item.get('start', item.get('at', 0))), 1), round(float(item.get('end', item.get('at', 0))), 1))


def diff(old, new):
    old, new = old or {}, new or {}
    out = []

    def sets(name, kind_add, kind_del, label):
        a = {_key(i): i for i in old.get(name) or []}
        b = {_key(i): i for i in new.get(name) or []}
        for k in b.keys() - a.keys():
            out.append(dict(kind=kind_add, detail=dict(item=label, inicio=k[0], fim=k[1])))
        for k in a.keys() - b.keys():
            out.append(dict(kind=kind_del, detail=dict(item=label, inicio=k[0], fim=k[1])))

    sets('cuts', 'corte_adicionado', 'corte_removido', 'corte')
    sets('zooms', 'zoom_adicionado', 'zoom_removido', 'zoom')
    sets('replays', 'replay_adicionado', 'replay_removido', 'replay')
    sets('speeds', 'velocidade_adicionada', 'velocidade_removida', 'velocidade')
    sets('freezes', 'congelamento_adicionado', 'congelamento_removido', 'congelamento')
    before, after = _ids(old.get('sfx')), _ids(new.get('sfx'))
    for i in before.keys() - after.keys():
        out.append(dict(kind='efeito_sonoro_removido', detail=dict(tipo=before[i].get('kind'))))
    for i in after.keys() & before.keys():
        if float(after[i].get('volume', .6)) < float(before[i].get('volume', .6)) - .05:
            out.append(dict(kind='efeito_sonoro_mais_baixo', detail=dict(tipo=after[i].get('kind'), de=before[i].get('volume'), para=after[i].get('volume'))))
    if (old.get('teaser') or None) and not new.get('teaser'):
        out.append(dict(kind='abertura_removida', detail={}))
    return out[:LIMIT]
