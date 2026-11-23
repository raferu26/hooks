"""Aprendizado com o desempenho real dos posts: você registra os números e o ranking se ajusta.

Não há ligação com o TikTok (a plataforma não permite publicar nem ler métricas por aqui): os números
são digitados por você na tela do clipe. O ajuste é conservador: precisa de pelo menos 4 clipes com
100+ visualizações, usa medianas (um post viral isolado não domina) e limita cada peso a 0,80–1,25.
"""
from statistics import mean, median
import time

MIN_CLIPS = 4
MIN_VIEWS = 100
WEIGHT_RANGE = (.80, 1.25)
LABELS = {
    'humor_na_fala': 'humor na fala', 'risada_na_transcricao': 'risada', 'jogada_na_fala': 'jogadas',
    'reacao_na_fala': 'reações', 'comportamento_observavel': 'movimento da câmera', 'opiniao_na_fala': 'opinião',
    'historia_pessoal': 'histórias pessoais', 'explicacao_util': 'explicações', 'estrutura_narrativa': 'começo-meio-fim',
    'preparacao_e_desfecho': 'preparação e desfecho', 'variacao_audio': 'variação de áudio',
    'crescendo_audio': 'crescendo de áudio', 'reacao_chat': 'reação do chat', 'cobertura_fala': 'fala contínua',
    'movimento_facial_breve': 'expressão facial', 'evento_visual': 'eventos na tela do jogo',
}


def clean(raw):
    """Valida os números digitados. Levanta ValueError em português."""
    if not isinstance(raw, dict):
        raise ValueError('Resultado inválido.')
    result = {}
    for key, label in (('views', 'Visualizações'), ('likes', 'Curtidas'), ('comments', 'Comentários'),
                       ('shares', 'Compartilhamentos'), ('saves', 'Salvamentos')):
        try:
            value = int(float(raw.get(key) or 0))
        except (TypeError, ValueError):
            raise ValueError(f'{label} precisa ser um número.') from None
        if not 0 <= value <= 10 ** 10:
            raise ValueError(f'{label} fora do intervalo.')
        result[key] = value
    if result['views'] <= 0:
        raise ValueError('Informe as visualizações (maior que zero).')
    if max(result['likes'], result['comments'], result['shares'], result['saves']) > result['views'] * 3:
        raise ValueError('Curtidas, comentários, compartilhamentos ou salvamentos estão muito acima das visualizações. Confira os números.')
    watch = raw.get('watch_pct')
    if watch not in (None, ''):
        try:
            watch = float(watch)
        except (TypeError, ValueError):
            raise ValueError('Tempo médio assistido precisa ser um número (porcentagem).') from None
        if not 0 <= watch <= 100:
            raise ValueError('Tempo médio assistido deve ficar entre 0 e 100%.')
        result['watch_pct'] = round(watch, 1)
    result['url'] = ' '.join(str(raw.get('url') or '').split())[:300]
    result['note'] = ' '.join(str(raw.get('note') or '').split())[:200]
    result['recorded'] = round(time.time())
    return result


def engagement(perf):
    views = max(1, int(perf['views']))
    return (perf['likes'] + 2 * perf['comments'] + 3 * perf['shares'] + 3 * perf['saves']) / views


def scores(samples):
    """Nota relativa de cada clipe (1 = mediano). Mistura engajamento e alcance, ambos contra a mediana."""
    eligible = [(c, p) for c, p in samples if p and int(p.get('views', 0)) >= MIN_VIEWS]
    if len(eligible) < MIN_CLIPS:
        return []
    med_views = median(int(p['views']) for _, p in eligible) or 1
    med_eng = median(engagement(p) for _, p in eligible) or 1e-9
    result = []
    for components, perf in eligible:
        reach = min(3.0, int(perf['views']) / med_views)
        quality = min(3.0, engagement(perf) / med_eng)
        result.append((components, .6 * quality + .4 * reach))
    return result


def weights(samples):
    """{componente: peso} a partir de [(componentes, desempenho)]. Vazio se faltarem dados."""
    graded = scores(samples)
    if not graded:
        return {}
    base = mean(score for _, score in graded)
    if base <= 0:
        return {}
    found = {}
    for components, score in graded:
        for name, value in (components or {}).items():
            try:
                present = float(value) > 0
            except (TypeError, ValueError):
                continue
            if present:
                found.setdefault(name, []).append(score)
    result = {}
    for name, values in found.items():
        if len(values) < 2:
            continue
        rate = (sum(values) + 2 * base) / ((len(values) + 2) * base)
        result[name] = round(max(WEIGHT_RANGE[0], min(WEIGHT_RANGE[1], rate)), 3)
    return result


def summary(samples):
    """Texto para a interface: quantos clipes já ensinaram o sistema e o que subiu/desceu."""
    counted = sum(1 for _, p in samples if p and int(p.get('views', 0)) >= MIN_VIEWS)
    given = sum(1 for _, p in samples if p)
    mapping = weights(samples)
    ups = sorted(((w, n) for n, w in mapping.items() if w >= 1.04), reverse=True)
    downs = sorted((w, n) for n, w in mapping.items() if w <= .96)
    return dict(recorded=given, used=counted, needed=max(0, MIN_CLIPS - counted),
                up=[LABELS.get(n, n.replace('_', ' ')) for _, n in ups[:4]],
                down=[LABELS.get(n, n.replace('_', ' ')) for _, n in downs[:4]])


def merge(approval, performance):
    """Combina pesos de aprovação e de desempenho (multiplicando), dentro dos limites do ranking."""
    names = set(approval) | set(performance)
    return {n: round(max(.75, min(1.30, approval.get(n, 1.0) * performance.get(n, 1.0))), 3) for n in names}


STYLE_MIN_N = 3
STYLE_MIN_VIEWS = 100
STYLE_SUGGEST_MIN = 8
STYLE_SUGGEST_LIFT = 1.2
HOOK_BANDS = (('gancho fraco (0–4)', 0, 4), ('gancho médio (4–7)', 4, 7), ('gancho forte (7–10)', 7, 10.01))
STYLE_LABELS = {'clean': 'limpo', 'funny': 'engraçado', 'gameplay': 'gameplay', 'reaction': 'reação', 'podcast': 'podcast',
                'interview': 'entrevista', 'hype': 'hype', 'creative': 'criativo', 'storytelling': 'narrativa',
                'educational': 'educativo', 'commentary': 'comentário', 'meme': 'meme', 'cinematic': 'cinemático'}


def _group_stats(rows):
    """rows: [(chave, nota relativa, visualizações)] → lista ordenada, só grupos com n suficiente."""
    groups = {}
    for key, score, views in rows:
        groups.setdefault(key, []).append((score, views))
    out = []
    for key, items in groups.items():
        if len(items) < STYLE_MIN_N:
            continue
        out.append(dict(key=key, n=len(items), score=round(median(s for s, _ in items), 2),
                        views=round(median(v for _, v in items))))
    return sorted(out, key=lambda x: (-x['score'], -x['n']))


def style_report(samples, current_style=None):
    """samples: [{style, moment, hook, perf}]. Compara estilos, tipos de momento e força do gancho.

    A nota é relativa à mediana do canal (1 = mediano). Só entram clipes com 100+ visualizações e grupos
    com pelo menos 3 clipes. Sugerir trocar de estilo exige 8+ clipes no total e vantagem de 20%: abaixo
    disso o relatório descreve, mas não recomenda.
    """
    eligible = [s for s in samples if s.get('perf') and int(s['perf'].get('views', 0)) >= STYLE_MIN_VIEWS]
    report = dict(total=len(eligible), styles=[], moments=[], hooks=[], suggestion=None, enough=len(eligible) >= STYLE_SUGGEST_MIN,
                  needed=max(0, STYLE_SUGGEST_MIN - len(eligible)))
    if len(eligible) < STYLE_MIN_N:
        return report
    perfs = [(s['perf']) for s in eligible]
    med_views = median(int(p['views']) for p in perfs) or 1
    med_eng = median(engagement(p) for p in perfs) or 1e-9
    graded = []
    for s in eligible:
        p = s['perf']
        score = .6 * min(3.0, engagement(p) / med_eng) + .4 * min(3.0, int(p['views']) / med_views)
        graded.append((s, score, int(p['views'])))
    report['styles'] = [dict(x, id=x['key'], label=STYLE_LABELS.get(x['key'], x['key']))
                        for x in _group_stats([(s.get('style') or 'clean', sc, v) for s, sc, v in graded])]
    report['moments'] = [dict(x, label=x['key']) for x in _group_stats([(s['moment'], sc, v) for s, sc, v in graded if s.get('moment')])]
    hooks = []
    for s, sc, v in graded:
        try:
            value = float(s.get('hook'))
        except (TypeError, ValueError):
            continue
        for label, lo, hi in HOOK_BANDS:
            if lo <= value < hi:
                hooks.append((label, sc, v))
                break
    report['hooks'] = [dict(x, label=x['key']) for x in _group_stats(hooks)]
    if report['enough'] and len(report['styles']) >= 2:
        best = report['styles'][0]
        base = next((x for x in report['styles'] if x['id'] == (current_style or 'clean')), None) or report['styles'][-1]
        if best['id'] != base['id'] and base['score'] > 0 and best['score'] / base['score'] >= STYLE_SUGGEST_LIFT:
            report['suggestion'] = dict(style=best['id'], label=best['label'], from_style=base['id'], lift=round(best['score'] / base['score'], 2),
                                        text=f"Seus clipes em estilo {best['label']} ({best['n']} clipes) ficaram {round((best['score'] / base['score'] - 1) * 100)}% acima do estilo {STYLE_LABELS.get(base['id'], base['id'])} ({base['n']} clipes). Vale testar como padrão, mas com poucos clipes pode ser acaso.")
    return report


AB_MIN_VIEWS = 300
AB_MIN_DIFF = .20


def ab_report(items):
    """items: [dict(group, label, change, perf)]. Um par A/B vira veredito só com 300+ visualizações nos dois lados e
    diferença de 20%+ na nota; mesmo assim, UM par não prova nada (o acaso do algoritmo pesa muito)."""
    groups = {}
    for it in items:
        if it.get('perf'):
            groups.setdefault(it['group'], {})[it['label']] = it
    out = []
    for group, pair in groups.items():
        if 'A' not in pair or 'B' not in pair:
            continue
        a, b = pair['A'], pair['B']
        va, vb = int(a['perf']['views']), int(b['perf']['views'])
        ea, eb = engagement(a['perf']), engagement(b['perf'])
        row = dict(group=group, change=b.get('change', ''), a=dict(views=va, engagement=round(ea, 3)), b=dict(views=vb, engagement=round(eb, 3)),
                   verdict='sem dados suficientes', winner=None)
        if min(va, vb) >= AB_MIN_VIEWS:
            score_a = .6 * ea + .4 * va / max(va, vb)
            score_b = .6 * eb + .4 * vb / max(va, vb)
            top = max(score_a, score_b)
            if top > 0 and abs(score_a - score_b) / top >= AB_MIN_DIFF:
                row['winner'] = 'A' if score_a > score_b else 'B'
                row['verdict'] = f"{row['winner']} foi melhor em alcance e engajamento combinados"
            else:
                row['verdict'] = 'empate técnico'
        out.append(row)
    wins = [r['winner'] for r in out if r['winner']]
    return dict(pairs=out, tested=len(out), decided=len(wins),
                note='Um único par não prova nada; só repita a mudança se ela ganhar em vários pares.' if len(wins) < 5 else '')
