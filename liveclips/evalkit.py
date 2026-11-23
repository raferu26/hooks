"""Kit de avaliação editorial comparativa (P14/F23).

Mede se uma versão do editor é melhor que outra NOS MESMOS trechos, com ordem A/B embaralhada e escondida, justificativa
obrigatória, empate aceito e concordância entre avaliadores. Nada aqui avalia vídeo sozinho: as notas vêm de pessoas.
A nota do próprio modelo não entra, e nenhum resultado declara o editor "profissional".
Pesos da rubrica e tamanhos mínimos são propostas ajustáveis do dossiê, não normas.
"""
import hashlib
import json
import random
from collections import defaultdict

DIMENSIONS = dict(narrativa=.25, ritmo=.20, composicao=.15, audio=.15, texto=.10, acabamento=.10, perfil=.05)
FAMILIES = ('reacao_forte', 'reacao_discreta', 'fala_sobreposta', 'silencio_expressivo', 'preparacao_piada', 'webcam_posicoes',
            'baixa_resolucao', 'ruido', 'falha_temporal')
MIN_CASES = 60                  # proposta do dossiê: 60 a 100 trechos
MIN_RATERS = 2
WIN_MARGIN = .10                # vantagem ponderada mínima para "manter"
CHOICES = ('A', 'B', 'empate')
REQUIRED_CASE = ('id', 'family', 'streamer', 'session', 'source', 'context', 'important_regions', 'defects_that_matter')


def validate_case(case):
    """Lista de problemas de um caso de avaliação (vazia = aceito)."""
    problems = [f'falta {k}' for k in REQUIRED_CASE if not case.get(k)]
    if case.get('family') and case['family'] not in FAMILIES:
        problems.append('família desconhecida')
    if not case.get('authorized'):
        problems.append('sem autorização de uso do material')
    if not case.get('transcript_reviewed'):
        problems.append('transcrição não revisada por pessoa')
    return problems


def split(cases, seed=7, test_fraction=.4):
    """Separa desenvolvimento e teste por (streamer, sessão): a mesma sessão nunca cai nos dois lados."""
    groups = sorted({(c['streamer'], c['session']) for c in cases})
    rng = random.Random(seed)
    rng.shuffle(groups)
    cut = max(1, int(round(len(groups) * test_fraction))) if len(groups) > 1 else 0
    test_groups = set(groups[:cut])
    dev = [c for c in cases if (c['streamer'], c['session']) not in test_groups]
    test = [c for c in cases if (c['streamer'], c['session']) in test_groups]
    return dev, test


def leakage(dev, test):
    """Sessões ou streamers presentes nos dois lados. Streamers repetidos são aviso; sessões repetidas são vazamento."""
    sessions = {(c['streamer'], c['session']) for c in dev} & {(c['streamer'], c['session']) for c in test}
    streamers = {c['streamer'] for c in dev} & {c['streamer'] for c in test}
    return dict(sessoes=sorted(sessions), streamers=sorted(streamers), vazou=bool(sessions))


def blind_pairs(case_ids, seed=11):
    """Para cada caso, qual versão aparece como A. Posições alternadas e embaralhadas; a chave fica separada dos avaliadores."""
    rng = random.Random(seed)
    ids = list(case_ids)
    flags = [i % 2 == 0 for i in range(len(ids))]
    rng.shuffle(flags)
    key = {cid: ('baseline' if flag else 'candidata') for cid, flag in zip(ids, flags)}      # versão exibida como A
    order = ids[:]
    rng.shuffle(order)
    return dict(ordem=order, chave_A=key)


def valid_rating(r):
    """Uma nota válida tem escolha geral, escolha por dimensão conhecida e justificativa quando houver preferência."""
    if r.get('overall') not in CHOICES or not r.get('evaluator') or not r.get('case'):
        return False
    if any(d not in DIMENSIONS or v not in CHOICES for d, v in (r.get('dims') or {}).items()):
        return False
    return r['overall'] == 'empate' or len((r.get('justification') or '').strip()) >= 10


def _winner(choice, a_is):
    """'A'/'B'/'empate' + qual versão estava em A -> 'baseline' | 'candidata' | 'empate'."""
    if choice == 'empate':
        return 'empate'
    shown = {'A': a_is, 'B': 'candidata' if a_is == 'baseline' else 'baseline'}
    return shown[choice]


def kappa(pairs):
    """Kappa de Cohen sobre listas de pares (escolha1, escolha2). Sem variação possível -> None."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    cats = {c for p in pairs for c in p}
    expected = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return None if expected >= 1 else round((observed - expected) / (1 - expected), 3)


def agreement(ratings, key, cases_family=None):
    by_case = defaultdict(dict)
    for r in ratings:
        by_case[r['case']][r['evaluator']] = _winner(r['overall'], key[r['case']])
    pairs = []
    for votes in by_case.values():
        names = sorted(votes)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pairs.append((votes[names[i]], votes[names[j]]))
    return dict(pares=len(pairs), concordancia=round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None, kappa=kappa(pairs))


def evaluate(ratings, key, cases, version_a='baseline', version_b='candidata', critical=None):
    """Resultado agregado de uma comparação. `critical`: {caso: 'baseline'|'candidata'} com falha crítica registrada por pessoa."""
    cases = {c['id']: c for c in cases}
    good = [r for r in ratings if valid_rating(r) and r['case'] in key]
    discarded = len(ratings) - len(good)
    per_case = defaultdict(list)
    for r in good:
        per_case[r['case']].append(r)
    weighted, wins, family = [], defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    dims = defaultdict(lambda: defaultdict(int))
    for cid, items in per_case.items():
        score = 0.0
        for r in items:
            side = _winner(r['overall'], key[cid])
            wins[side]['n'] += 1
            family[cases.get(cid, {}).get('family', '?')][side] += 1
            for d, w in DIMENSIONS.items():
                choice = _winner((r.get('dims') or {}).get(d, 'empate'), key[cid])
                dims[d][choice] += 1
                score += w * {'candidata': 1, 'baseline': -1, 'empate': 0}[choice]
        weighted.append(score / len(items))
    n_cases = len(per_case)
    raters = len({r['evaluator'] for r in good})
    advantage = round(sum(weighted) / len(weighted), 3) if weighted else 0.0
    critical = dict(critical or {})
    cand_fail = [c for c, side in critical.items() if side == 'candidata']
    reasons = []
    if cand_fail and not any(side == 'baseline' for c, side in critical.items() if c in cand_fail):
        decision = 'recuar'
        reasons.append(f'Falha crítica só na candidata em {len(cand_fail)} caso(s): vale mais que a média.')
    elif n_cases < MIN_CASES or raters < MIN_RATERS:
        decision = 'inconclusivo'
        reasons.append(f'Amostra insuficiente ({n_cases} casos, {raters} avaliador(es); mínimo proposto {MIN_CASES} e {MIN_RATERS}).')
    elif advantage >= WIN_MARGIN:
        decision = 'manter'
        reasons.append(f'Vantagem ponderada {advantage:+.2f} (limite {WIN_MARGIN:+.2f}).')
    elif advantage <= -WIN_MARGIN:
        decision = 'recuar'
        reasons.append(f'Desvantagem ponderada {advantage:+.2f}.')
    else:
        decision = 'inconclusivo'
        reasons.append('Diferença pequena demais para decidir; empate é um resultado válido.')
    return dict(decisao=decision, motivos=reasons, vantagem_ponderada=advantage, casos=n_cases, avaliadores=raters, notas_descartadas=discarded,
                vitorias={k: v['n'] for k, v in wins.items()}, por_dimensao={d: dict(v) for d, v in dims.items()},
                por_familia={f: dict(v) for f, v in family.items()}, concordancia=agreement(good, key),
                limites=['Notas humanas sobre um conjunto pequeno; não prova qualidade geral.',
                         'VMAF e métricas de codificação não medem história, humor ou ritmo; avalie-as à parte e com referência comparável.',
                         'Resultados de posts diferentes não provam causalidade de um efeito.'])


def ablation_plan(effects):
    """Variantes para testar o peso de cada efeito: tudo ligado, e cada efeito desligado sozinho."""
    effects = list(effects)
    return [dict(id='tudo', desligados=[])] + [dict(id='sem_' + e, desligados=[e]) for e in effects]


def report_digest(version, cases, ratings):
    """Hash do que entrou no relatório, para reproduzi-lo e detectar mudança silenciosa."""
    payload = json.dumps(dict(version=version, cases=sorted(c['id'] for c in cases), ratings=sorted((r['case'], r['evaluator'], r['overall']) for r in ratings)),
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
