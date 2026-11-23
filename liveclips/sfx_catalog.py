"""Catálogo de efeitos sonoros por FUNÇÃO (P06/F12/F28).

Cada efeito tem função narrativa, intensidade, origem e permissão de uso. "Nenhum efeito" é uma decisão válida e é a
padrão quando não há função clara. O catálogo guarda apenas o que o programa realmente sintetiza (sfx.EFFECTS) mais
ativos próprios do canal com permissão declarada; nada é baixado nem presumido livre.
"""
from . import sfx

FUNCTIONS = ('transicao', 'destaque', 'acerto', 'impacto', 'tensao', 'interface')
INTENSITIES = ('leve', 'media', 'forte')
PERMISSIONS = ('livre_proprio', 'licenca_declarada', 'sem_permissao')
VOLUME = dict(leve=.3, media=.5, forte=.7)
MIX = dict(id='voz_primeiro_v1', voice_first=True, sfx_max_over_voice=.35, music_duck_db=-12,
           note='Alvos internos de proposta (não são regras de plataforma); a medição real fica por conta do controle de qualidade.')

# Efeitos sintetizados internamente: função e intensidade são decisão de design, ouvidas e ajustáveis pelo usuário.
BUILTIN = dict(
    whoosh=dict(function='transicao', intensity='media'),
    pop=dict(function='destaque', intensity='leve'),
    ding=dict(function='acerto', intensity='leve'),
    boom=dict(function='impacto', intensity='forte'),
    riser=dict(function='tensao', intensity='media'),
    click=dict(function='interface', intensity='leve'),
)


def catalog(extra_assets=()):
    """Lista completa. `extra_assets`: ativos do canal (dict: id, function, intensity, permission, origin)."""
    items = []
    for name, meta in BUILTIN.items():
        label, duration, _ = sfx.EFFECTS[name]
        items.append(dict(id=name, label=label, duration=duration, origin='sintetizado_interno', permission='livre_proprio',
                          validated_by_ear=False, **meta))
    for a in extra_assets:
        if a.get('function') in FUNCTIONS and a.get('permission') in PERMISSIONS:
            items.append(dict(id=a['id'], label=a.get('label', a['id']), duration=a.get('duration'), function=a['function'],
                              intensity=a.get('intensity', 'media'), origin=a.get('origin', 'canal'), permission=a['permission'],
                              validated_by_ear=bool(a.get('validated_by_ear'))))
    return items


def usable(item):
    return item['permission'] != 'sem_permissao'


def choose(function, intensity='media', extra_assets=(), exclude=()):
    """Escolhe o efeito de uma função ou devolve `nenhum` com o motivo. Nunca inventa um efeito."""
    if function not in FUNCTIONS:
        return dict(effect=None, reason='Sem função narrativa clara: sem efeito.')
    pool = [i for i in catalog(extra_assets) if i['function'] == function and usable(i) and i['id'] not in exclude]
    if not pool:
        return dict(effect=None, reason=f'Nenhum efeito disponível e permitido para a função "{function}".')
    rank = {k: n for n, k in enumerate(INTENSITIES)}
    best = min(pool, key=lambda i: (abs(rank[i['intensity']] - rank.get(intensity, 1)), not i['validated_by_ear'], i['id']))
    return dict(effect=best['id'], volume=VOLUME[best['intensity']], intensity=best['intensity'], permission=best['permission'],
                reason=f'{function}: {best["label"]}.')


def decide(moment_function, budget_left=1, near_speech=False, extra_assets=()):
    """Decisão completa para um ponto do clipe. `near_speech`: há fala nos 0,3 s em volta → volume cai ao teto da mixagem."""
    if budget_left <= 0:
        return dict(effect=None, reason='Orçamento de efeitos esgotado: sem efeito.')
    choice = choose(moment_function, extra_assets=extra_assets)
    if choice['effect'] and near_speech:
        choice['volume'] = min(choice['volume'], MIX['sfx_max_over_voice'])
        choice['reason'] += ' Volume limitado porque há fala por perto.'
    return choice
