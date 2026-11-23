"""Revisão técnica e editorial ciente do plano (F06, F21, P10, S02).

Duas camadas: (1) verificação técnica determinística do arquivo renderizado, que consulta o plano para separar uma
intervenção PLANEJADA (congelamento, silêncio, preto de transição) de uma falha; (2) revisão editorial por regras
verificáveis sobre plano, fala e legenda. Nenhuma das duas assiste ao vídeo com áudio: o relatório declara isso em
`nao_verificado` e nunca devolve "aprovado" só por regra. Falha crítica bloqueia o estado de pronto.
"""
from . import plan as planlib

SEVERITY = ('critica', 'alta', 'media', 'baixa')
MAX_ATTEMPTS = 2                 # correções automáticas por job (configurável)
READ_CPS_ALARM = 20              # alarme do dossiê (caracteres/s); investigar, não certificar
EFFECTS_PER_10S = 3
SFX_OVER_SPEECH = .6
CRITICAL_ITEMS = ('arquivo', 'audio', 'formato')
TEXT_ITEMS = dict(legenda_cortada='texto_ilegivel', leitura='texto_ilegivel', linhas='texto_ilegivel', zona_inferior='texto_ilegivel', zona_superior='texto_ilegivel')
AUDIO_ITEMS = dict(volume='voz_mascarada', pico='voz_mascarada')
UNVERIFIED = ['audição do vídeo renderizado', 'timing e mixagem em movimento', 'avaliação multimodal do conteúdo']


def issue(id_, dimension, severity, observation, start=None, end=None, evidence='', impact='', fix=None, confidence=.8,
          human=False, defect=None):
    return dict(id=id_, dimension=dimension, severity=severity, interval=None if start is None else [round(start, 3), round(end if end is not None else start, 3)],
                observation=observation, evidence=evidence, impact=impact, fix=fix, confidence=confidence,
                needs_human=human, defect=defect)


def _planned(plan, kind):
    """Intervalos de saída (segundos) ocupados por segmentos de um tipo."""
    return [(planlib.seconds(s['out_start']), planlib.seconds(s['out_end'])) for s in plan.get('segments', []) if s['kind'] == kind]


def _overlaps(a, b, c, d):
    return a < d and c < b


# ───────────── camada técnica ─────────────

def technical(plan, qc_report=None, probe_info=None, black=(), tolerance_frames=2.0, plan_delta_frames=None):
    """Itens técnicos do arquivo final em relação ao plano."""
    issues = []
    for p in planlib.validate(plan):
        issues.append(issue('plano:' + p['code'], 'plano', 'critica', p['message'], evidence=p['where'],
                            impact='o vídeo pode não corresponder ao que foi planejado', defect='render_incompleto', confidence=.95))
    if plan_delta_frames is not None and abs(plan_delta_frames) > tolerance_frames:
        issues.append(issue('duracao', 'tecnica', 'alta', f'O arquivo difere do plano em {plan_delta_frames:+.1f} frames.',
                            evidence=f'tolerância {tolerance_frames:g} frames', impact='legendas e efeitos podem sair do sincronismo',
                            defect='duracao_incorreta', confidence=.9))
    freezes = _planned(plan, 'freeze')
    for a, b in black:
        planned = any(_overlaps(a, b, fa, fb) for fa, fb in freezes)
        if planned:
            continue
        issues.append(issue(f'preto:{a:.2f}', 'tecnica', 'alta', f'Quadros pretos entre {a:.1f}s e {b:.1f}s sem uma intervenção planejada.',
                            a, b, evidence='blackdetect', impact='falha de render ou corte sem material', defect='render_incompleto', confidence=.8,
                            fix=dict(kind='revisar_trecho', start=a, end=b)))
    for it in (qc_report or {}).get('items', []):
        text = it['label'] + (': ' + it['detail'] if it.get('detail') else '')
        defect = TEXT_ITEMS.get(it['id']) or AUDIO_ITEMS.get(it['id'])
        if it['status'] == 'erro':
            issues.append(issue('qc:' + it['id'], 'tecnica', 'critica' if it['id'] in CRITICAL_ITEMS else 'alta', text,
                                evidence='controle de qualidade', defect=defect or 'render_incompleto', confidence=.9))
        elif it['status'] == 'atencao' and it['id'] not in ('duracao',):
            issues.append(issue('qc:' + it['id'], 'tecnica', 'media', text, evidence='controle de qualidade', confidence=.7, defect=defect))
    return issues


def words_for_plan(segments, clip_start, clip_end, parts):
    """Palavras da transcrição (segundos da sessão) -> tempo local de cada arquivo-fonte, que é o que o plano usa.
    Cada palavra leva `part` (índice da parte). Palavras fora do clipe ou fora das partes são ignoradas."""
    spans, cursor = [], 0.0
    for index, part in enumerate(parts):
        length = float(part['out']) - float(part['in'])
        spans.append((index, cursor, cursor + length, float(part['in'])))
        cursor += length
    result = []
    for seg in segments or []:
        for w in seg.get('words') or []:
            try:
                a, b = float(w['start']) - clip_start, float(w['end']) - clip_start
            except (KeyError, TypeError, ValueError):
                continue
            if b <= 0 or a >= clip_end - clip_start:
                continue
            for index, low, high, local in spans:
                if low - 1e-6 <= a < high:
                    result.append(dict(word=w.get('word', ''), start=round(local + a - low, 4), end=round(local + min(b, high) - low, 4), part=index))
                    break
    return result


# ───────────── camada editorial (regras verificáveis) ─────────────

def editorial(plan, function_map=None, project=None, lines=(), words=(), cuts=(), clip_start=0.0):
    """`lines`: legendas na saída (dicts start, end, text em segundos de SAÍDA). `words`: palavras da fonte (segundos)
    para detectar fala cortada. `cuts`: cortes do projeto (segundos do clipe). `clip_start`: início do clipe na sessão, pois as pausas protegidas vêm em segundos absolutos."""
    issues = []
    function_map = function_map or {}
    project = project or {}
    assets = [a['asset_id'] for a in plan.get('source_assets', [])]

    def asset_of(word):
        part = int(word.get('part', 0))
        return assets[part] if 0 <= part < len(assets) else None
    asset = assets[0] if assets else None
    # fala truncada: a palavra só está inteira se a UNIÃO dos trechos mantidos a cobre; trechos vizinhos contínuos não contam como corte
    if asset and words:
        for w in words:
            a, b = planlib.ticks(w['start']), planlib.ticks(w['end'])
            wa = asset_of(w)
            if b <= a or wa is None:
                continue
            spans = sorted((max(a, sg['source_in']), min(b, sg['source_out'])) for sg in plan['segments']
                           if sg['asset_id'] == wa and sg['kind'] != 'freeze' and sg['source_in'] < b and sg['source_out'] > a)
            if not spans:
                continue
            covered, edge = 0, a
            for x, y in spans:
                x = max(x, edge)
                if y > x:
                    covered += y - x
                    edge = y
            if (b - a) - covered > 1:
                first = planlib.timemap(plan).words(wa, [w], keep_cut_overlap=.0)
                at = planlib.seconds(first[0]['out_start']) if first else 0.0
                issues.append(issue(f'fala:{at:.2f}', 'ritmo', 'alta', f'A palavra "{w.get("word", "")}" fica cortada na borda de um trecho.', at,
                                    planlib.seconds(first[0]['out_end']) if first else at, evidence=f'{covered / (b - a):.0%} da palavra mantida',
                                    impact='sílaba truncada', defect='fala_truncada', confidence=.85, fix=dict(kind='mover_corte', word=w.get('word', ''), at=at)))
    if function_map.get('request_more_context'):
        issues.append(issue('contexto', 'narrativa', 'alta', '; '.join(function_map.get('why') or ['Contexto ou resolução fora do corte.']),
                            evidence='mapa de funções', impact='quem não viu a live pode não entender', defect='contexto_insuficiente', confidence=.7, human=True))
    # efeitos demais por janela
    fx = [e for e in plan.get('effects', []) if e['recipe'] in ('punch_in', 'sfx_funcao', 'imagem_apoio')]
    for e in fx:
        near = [x for x in fx if abs(x['start_s'] - e['start_s']) < 5]
        if len(near) > EFFECTS_PER_10S:
            issues.append(issue(f'excesso:{e["id"]}', 'efeitos', 'media', f'{len(near)} efeitos em 10 s: a atenção pode se dispersar.', e['start_s'], e['end_s'],
                                evidence='orçamento de efeitos', defect=None, confidence=.7, fix=dict(kind='remover_efeito', id=e['id'])))
            break
    # SFX por cima da fala
    spoken = []
    for wa in set(filter(None, (asset_of(w) for w in words))):
        spoken += [(planlib.seconds(x['out_start']), planlib.seconds(x['out_end']))
                   for x in planlib.timemap(plan).words(wa, [w for w in words if asset_of(w) == wa])]
    for e in plan.get('effects', []):
        if e['recipe'] == 'sfx_funcao' and (e.get('params') or {}).get('volume', 0) >= SFX_OVER_SPEECH:
            if any(_overlaps(e['start_s'], e['end_s'], a, b) for a, b in spoken):
                issues.append(issue(f'sfx_voz:{e["id"]}', 'audio', 'media', 'Efeito sonoro alto sobre uma palavra falada.', e['start_s'], e['end_s'],
                                    evidence=f'volume {e["params"]["volume"]}', impact='a frase pode ser mascarada', defect='voz_mascarada',
                                    fix=dict(kind='baixar_efeito', id=e['id'], volume=.35), confidence=.75))
    # leitura de legenda
    for line in lines:
        length = max(.1, float(line['end']) - float(line['start']))
        cps = len(str(line['text'])) / length
        if cps > READ_CPS_ALARM:
            issues.append(issue(f'leitura:{line["start"]:.2f}', 'legenda', 'baixa', f'Legenda com {cps:.0f} caracteres por segundo.', line['start'], line['end'],
                                evidence=f'alarme inicial de {READ_CPS_ALARM} cps (não é certificação)', defect='texto_ilegivel', confidence=.6, human=True))
    # pausas narrativas cortadas
    for p in function_map.get('protected', []):
        if p['function'] == 'pausa_narrativa':
            for c in cuts:
                if _overlaps(float(c['start']), float(c['end']), p['start'] - clip_start, p['end'] - clip_start):
                    issues.append(issue(f'pausa:{c["start"]:.2f}', 'ritmo', 'media', 'Um corte automático atinge uma pausa que sustenta o momento.', c['start'], c['end'],
                                        defect='payoff_cortado', fix=dict(kind='restaurar_trecho', start=c['start'], end=c['end']), confidence=.7, human=True))
    return issues


def report(issues, attempt=0, previous=None):
    """Relatório estruturado. `veredito`: bloqueado | corrigir | revisao_humana. Nunca 'aprovado' só por regras."""
    order = {s: i for i, s in enumerate(SEVERITY)}
    issues = sorted(issues, key=lambda i: (order[i['severity']], i['interval'] or [0, 0]))
    critical = [i for i in issues if i['severity'] == 'critica']
    high = [i for i in issues if i['severity'] == 'alta']
    if critical:
        verdict = 'bloqueado'
    elif high:
        verdict = 'corrigir'
    else:
        verdict = 'revisao_humana'       # sem aval de quem viu e ouviu o vídeo, a última palavra é da pessoa
    result = dict(veredito=verdict, problemas=issues, tentativa=attempt, limite_tentativas=MAX_ATTEMPTS, nao_verificado=list(UNVERIFIED),
                  bloqueia_pronto=bool(critical), resumo=_summary(issues))
    if previous is not None:
        result['comparacao'] = compare(previous, result)
    return result


def _summary(issues):
    if not issues:
        return 'Nenhum problema encontrado pelas regras automáticas; ouça e assista antes de aprovar.'
    count = {s: sum(1 for i in issues if i['severity'] == s) for s in SEVERITY}
    return ', '.join(f'{n} {s}' for s, n in count.items() if n) + '.'


def score(report_):
    weights = dict(critica=100, alta=10, media=3, baixa=1)
    return sum(weights[i['severity']] for i in report_['problemas'])


def compare(old, new):
    a, b = score(old), score(new)
    return dict(antes=a, depois=b, melhorou=b < a, piorou=b > a)


# ───────────── correções locais e laço limitado ─────────────

def apply_fix(project, fix):
    """Aplica UMA correção local tipada a uma cópia do projeto. Só toca no item citado; devolve (projeto, texto)."""
    import copy
    project = copy.deepcopy(project or {})
    kind = fix.get('kind')
    if kind == 'baixar_efeito':
        for e in project.get('sfx', []):
            if e.get('id') == fix['id']:
                e['volume'] = min(e.get('volume', .6), float(fix.get('volume', .35)))
                return project, f'Efeito {fix["id"]} com volume reduzido.'
    if kind == 'remover_efeito':
        for key in ('zooms', 'sfx', 'overlays'):
            before = len(project.get(key, []))
            project[key] = [e for e in project.get(key, []) if e.get('id') != fix['id']]
            if len(project[key]) != before:
                return project, f'Efeito {fix["id"]} removido.'
    if kind == 'restaurar_trecho':
        project['cuts'] = [c for c in project.get('cuts', []) if not (c['start'] < fix['end'] and c['end'] > fix['start'])]
        return project, 'Corte manual que atingia a pausa foi desfeito.'
    return None, None


def correct(render_and_review, project, limit=MAX_ATTEMPTS):
    """Laço render → revisar → corrigir → renderizar de novo, no máximo `limit` vezes.

    `render_and_review(project)` -> relatório (de `report`). Mantém todas as versões, compara e recua se a nova for pior."""
    versions = []
    current = project
    rep = render_and_review(current)
    versions.append(dict(project=current, report=rep, note='versão inicial'))
    attempt = 0
    while attempt < limit and rep['veredito'] == 'corrigir':
        fixes = [i['fix'] for i in rep['problemas'] if i.get('fix') and not i.get('needs_human') and i['severity'] in ('alta', 'media')]
        if not fixes:
            break
        candidate = current
        notes = []
        for fix in fixes:
            changed, note = apply_fix(candidate, fix)
            if changed is not None:
                candidate = changed
                notes.append(note)
        if candidate is current:
            break
        attempt += 1
        new = render_and_review(candidate)
        new = dict(new, tentativa=attempt, comparacao=compare(rep, new))
        versions.append(dict(project=candidate, report=new, note='; '.join(notes)))
        if new['comparacao']['piorou'] or (not new['comparacao']['melhorou'] and new['veredito'] == rep['veredito']):
            break        # recua: a versão anterior fica como a melhor
        current, rep = candidate, new
    best = min(versions, key=lambda v: score(v['report']))
    return dict(final=best, versoes=versions, tentativas=attempt)
