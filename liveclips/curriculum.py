"""Currículo por competência e melhoria por feedback (P18).

Aprender = mudança observável em casos RESERVADOS (que não foram usados como exemplo), por perfil e família de conteúdo.
Aumentar a base de memória não conta como melhoria."""
from collections import Counter, defaultdict

from . import knowledge


def seed(memory):
    from . import capabilities
    return memory.seed(knowledge.FUNDAMENTALS, capabilities.as_rows())


def report(memory):
    """Por competência: exemplos aprovados, contraexemplos e casos reservados (a avaliação precisa de reservados)."""
    result = {key: dict(nome=name, aprovados=0, rejeitados=0, reservados=0, fundamentos=[]) for key, name in knowledge.COMPETENCIES.items()}
    for item in memory.list('fundamentos'):
        skill = item['body'].get('competencia')
        if skill in result:
            result[skill]['fundamentos'].append(item['id'])
    for ns, field in (('casos_aprovados', 'aprovados'), ('casos_rejeitados', 'rejeitados')):
        for item in memory.list(ns):
            skills = {knowledge.DEFECT_SKILL.get(d) for d in item['body'].get('defeitos') or []} or {None}
            for skill in skills:
                key = skill if skill in result else 'corte_fidelidade'
                result[key][field] += 1
                if item['body'].get('reservado'):
                    result[key]['reservados'] += 1
    for row in result.values():
        row['pronto_para_avaliar'] = row['reservados'] >= 3 and (row['aprovados'] + row['rejeitados']) >= 6
    return result


def leakage(train_cases, reserved_cases):
    """Casos reservados não podem compartilhar sessão nem streamer-sessão com os de treino (vazamento por quase-duplicata)."""
    seen = {c.get('session') for c in train_cases if c.get('session')}
    return [c for c in reserved_cases if c.get('session') in seen]


def compare(before, after):
    """`before`/`after`: lista de dicts(case, streamer, family, defects=[...]) avaliados nos MESMOS casos reservados.

    Mostra quais erros diminuíram, quais permaneceram e quais regressões surgiram, por perfil e por família."""
    index = {c['case']: c for c in after}
    fixed, kept, regressed = Counter(), Counter(), Counter()
    by_profile = defaultdict(lambda: Counter())
    by_family = defaultdict(lambda: Counter())
    for old in before:
        new = index.get(old['case'])
        if new is None:
            continue
        a, b = Counter(old.get('defects') or []), Counter(new.get('defects') or [])
        for defect in set(a) | set(b):
            if b[defect] < a[defect]:
                fixed[defect] += a[defect] - b[defect]
                by_profile[old.get('streamer')]['melhorou'] += a[defect] - b[defect]
                by_family[old.get('family')]['melhorou'] += a[defect] - b[defect]
            elif b[defect] > a[defect]:
                regressed[defect] += b[defect] - a[defect]
                by_profile[old.get('streamer')]['piorou'] += b[defect] - a[defect]
                by_family[old.get('family')]['piorou'] += b[defect] - a[defect]
            elif a[defect]:
                kept[defect] += a[defect]
    return dict(diminuiram=dict(fixed), permaneceram=dict(kept), regressoes=dict(regressed),
                por_perfil={k: dict(v) for k, v in by_profile.items()}, por_familia={k: dict(v) for k, v in by_family.items()},
                casos=len([1 for o in before if o['case'] in index]),
                decisao='manter' if sum(fixed.values()) > sum(regressed.values()) and not regressed else
                        'revisar' if regressed else 'sem_ganho')
