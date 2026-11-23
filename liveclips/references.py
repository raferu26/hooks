"""Catálogo de referências e tendências (P15/F16) com proveniência, escopo e validade.

Roda só quando solicitado; este módulo guarda e consulta, não pesquisa sozinho nem publica nada. Cada referência registra
o que foi VISTO (URL, data da observação), separa frequência observada, hipótese e exemplo inspirador, e declara os limites
da inferência. Tendência sempre expira. Nada aqui prova dominância no feed ou representatividade estatística.
"""
import time
from urllib.parse import urlparse

from . import capabilities

KINDS = ('frequencia_observada', 'hipotese', 'exemplo_inspirador', 'contraexemplo', 'sinal_saturacao')
TREND_DAYS = 30            # validade padrão de uma tendência (ajustável)
FOUNDATION_DAYS = 180      # fundamentos são revistos com menos frequência
CYCLE = (30, 50)           # tamanho proposto do ciclo exploratório
REQUIRED = ('url', 'platform', 'niche', 'region', 'observed_at', 'kind', 'structure', 'inference_limits')
# técnicas nomeadas nas referências -> receita do registro de capacidades
TECHNIQUE_RECIPE = {'zoom': 'punch_in', 'punch_in': 'punch_in', 'replay': 'replay', 'camera_lenta': 'velocidade', 'rampa': 'velocidade_rampa',
                    'congelar': 'congelar', 'sfx': 'sfx_funcao', 'titulo': 'titulo_contexto', 'imagem_apoio': 'imagem_apoio', 'musica': 'musica_ducking'}


class ReferenceError_(ValueError):
    pass


def validate(ref, now=None):
    """Problemas de uma referência (vazio = aceita)."""
    problems = [f'falta {k}' for k in REQUIRED if not ref.get(k)]
    url = urlparse(str(ref.get('url') or ''))
    if ref.get('url') and (url.scheme not in ('http', 'https') or not url.netloc):
        problems.append('URL inválida')
    if ref.get('kind') and ref['kind'] not in KINDS:
        problems.append('tipo desconhecido')
    if ref.get('kind') == 'frequencia_observada' and not ref.get('seen'):
        problems.append('frequência observada exige registrar que o conteúdo foi realmente visto')
    if ref.get('observed_at') and ref['observed_at'] > (time.time() if now is None else now) + 86400:
        problems.append('data de observação no futuro')
    return problems


def add(memory, ref, valid_days=None):
    """Guarda uma referência como memória de tendência (origem humana, escopo global, com validade)."""
    problems = validate(ref, memory.clock())
    if problems:
        raise ReferenceError_('; '.join(problems))
    days = valid_days or (FOUNDATION_DAYS if ref.get('foundation') else TREND_DAYS)
    expires = memory.clock() + days * 86400
    body = {k: ref[k] for k in ('url', 'platform', 'niche', 'region', 'observed_at', 'kind', 'structure', 'inference_limits', 'language',
                                'published_at', 'duration_s', 'layout', 'rhythm', 'text', 'sound', 'techniques', 'objective', 'seen') if k in ref}
    body['representativa'] = False
    key = f"ref {ref['platform']}/{ref['niche']}: {ref['url'][:80]}"
    return memory.put('tendencias', key, body, origin='avaliacao_humana', scope='global', valid_until=expires,
                      tags=(ref['platform'], ref['niche'], ref['kind']), confidence=.4 if ref['kind'] != 'frequencia_observada' else .5,
                      evidence=ref['url'])


def query(memory, niche=None, platform=None, region=None, kind=None, language=None, limit=20):
    """Referências vigentes filtradas (a validade é aplicada antes: expirada não aparece)."""
    now = memory.clock()
    out = []
    for item in memory.list('tendencias', limit=500):
        if item.get('valid_until') and item['valid_until'] < now:
            continue
        b = item['body']
        if not b.get('url'):
            continue
        if (niche and b.get('niche') != niche) or (platform and b.get('platform') != platform) or (region and b.get('region') != region):
            continue
        if (kind and b.get('kind') != kind) or (language and b.get('language') not in (None, language)):
            continue
        out.append(item)
    return out[:limit]


def usable_suggestions(refs, authorized_assets=()):
    """Transforma referências em receitas adaptáveis respeitando as capacidades reais e os ativos autorizados.

    Técnica sem receita disponível vira nota ("não aplicável hoje") em vez de promessa. Ativos de som/imagem da referência
    nunca são copiados: só entram se estiverem na lista autorizada."""
    ok = set(authorized_assets)
    out = []
    for item in refs:
        b = item['body']
        apply, skip = [], []
        for t in b.get('techniques') or []:
            recipe = TECHNIQUE_RECIPE.get(str(t).lower())
            if recipe and capabilities.PLAN_RECIPES.get(recipe) and capabilities.usable(capabilities.PLAN_RECIPES[recipe]['recipe']):
                apply.append(recipe)
            else:
                skip.append(str(t))
        out.append(dict(id=item['id'], niche=b.get('niche'), kind=b.get('kind'), aplicar=apply, nao_aplicavel_hoje=skip,
                        estrutura=b.get('structure'), validade=item.get('valid_until'), ativos_da_referencia='só inspiração; não copiar identidade, trilha ou marcas',
                        limites=b.get('inference_limits'), asset_ok=bool(ok)))
    return out


def cycle_plan(niches, platforms, size=40):
    """Plano de um ciclo exploratório: cotas por nicho e plataforma, com contraexemplos e sinais de saturação reservados."""
    low, high = CYCLE
    size = max(low, min(high, int(size)))
    cells = [(n, p) for n in niches for p in platforms]
    if not cells:
        raise ReferenceError_('Informe ao menos um nicho e uma plataforma.')
    reserved = max(2, size // 5)               # ~20%: contraexemplos e saturação
    base, extra = divmod(size - reserved, len(cells))
    quotas = [dict(niche=n, platform=p, amostras=base + (1 if i < extra else 0)) for i, (n, p) in enumerate(cells)]
    return dict(total=size, cotas=quotas, reservado_contraexemplos_e_saturacao=reserved,
                aviso='Ciclo exploratório: não representa o feed nem prova dominância de uma técnica.')
