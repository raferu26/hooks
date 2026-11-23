"""Benchmark do agente com conteúdo real.

Você marca, num CSV, os trechos que seriam bons clipes (o gabarito). A ferramenta analisa os mesmos vídeos
com o agente e mede o quanto as sugestões batem com o seu julgamento. Serve para comparar versões e ajustes
com números, em vez de impressão. Só funciona bem com o SEU conteúdo: com poucos trechos marcados
(menos de ~20) os números oscilam muito, e o relatório avisa isso.

Uso:  python -m liveclips bench modelo --videos PASTA --saida gabarito.csv     (cria o CSV para preencher)
      python -m liveclips bench rodar  --videos PASTA --gabarito gabarito.csv [--dados PASTA] [--estilo clean]
                                       [--comparar]  (compara agente completo × só o ranking básico)
"""
import csv
import json
from pathlib import Path
import time

VIDEO_EXT = ('.mp4', '.mkv', '.mov', '.webm', '.ts', '.m4v')
IOU_MIN = .30
KS = (1, 3, 5)
MIN_RELIABLE = 20


def parse_time(value):
    """'1:02:03', '12:34', '754', '754,5' → segundos. Levanta ValueError em português."""
    text = str(value).strip().replace(',', '.')
    if not text:
        raise ValueError('tempo vazio')
    try:
        parts = [float(p) for p in text.split(':')]
    except ValueError:
        raise ValueError(f'tempo inválido: "{value}"') from None
    if len(parts) > 3 or any(p < 0 for p in parts):
        raise ValueError(f'tempo inválido: "{value}"')
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def _delimiter(sample):
    return ';' if sample.count(';') >= sample.count(',') else ','


def load_gold(path):
    """CSV com colunas video, inicio, fim (e opcionalmente nota). → ({video_sem_extensao: [(ini, fim)]}, [avisos])."""
    text = Path(path).read_text(encoding='utf-8-sig')
    rows = list(csv.reader(text.splitlines(), delimiter=_delimiter(text.splitlines()[0] if text else ';')))
    if not rows:
        raise ValueError('O gabarito está vazio.')
    header = [h.strip().casefold() for h in rows[0]]
    for need in ('video', 'inicio', 'fim'):
        if need not in header:
            raise ValueError(f'Faltou a coluna "{need}" no gabarito (colunas: video, inicio, fim, nota).')
    idx = {name: header.index(name) for name in ('video', 'inicio', 'fim')}
    gold, warnings = {}, []
    for number, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row) or row[0].strip().startswith('#'):
            continue
        try:
            name = Path(row[idx['video']].strip()).stem.casefold()
            if not row[idx['inicio']].strip() and not row[idx['fim']].strip():
                continue  # linha de modelo ainda sem preencher
            a, b = parse_time(row[idx['inicio']]), parse_time(row[idx['fim']])
        except (ValueError, IndexError) as exc:
            warnings.append(f'Linha {number} ignorada: {exc}.')
            continue
        if b - a < 5:
            warnings.append(f'Linha {number} ignorada: trecho com menos de 5 s.')
            continue
        gold.setdefault(name, []).append((a, b))
    if not gold:
        raise ValueError('O gabarito não tem nenhum trecho preenchido.')
    return gold, warnings


def template(videos_dir, out):
    """Cria o CSV para você preencher: uma linha por vídeo encontrado, com os tempos em branco."""
    files = sorted(p for p in Path(videos_dir).iterdir() if p.suffix.casefold() in VIDEO_EXT)
    if not files:
        raise ValueError('Nenhum vídeo (mp4, mkv, mov, webm, ts, m4v) encontrado nessa pasta.')
    with Path(out).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(['video', 'inicio', 'fim', 'nota'])
        for p in files:
            writer.writerow([p.name, '', '', ''])
        writer.writerow(['# Preencha inicio e fim (mm:ss ou h:mm:ss) para CADA bom clipe do vídeo; repita a linha do vídeo quantas vezes precisar.'])
    return len(files)


def iou(a, b):
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def evaluate(by_video, gold, iou_min=IOU_MIN, ks=KS):
    """by_video: {video: [dict(start,end,confidence?)]} em ordem de ranking. gold: {video: [(ini, fim)]}.

    hit@k: fração dos momentos do gabarito achados entre as k primeiras sugestões (IoU ≥ iou_min).
    precision@k: fração das k primeiras sugestões que batem com algum momento do gabarito.
    Para cada momento achado, mede o erro de começo/fim em segundos e o IoU.
    """
    total_gold = sum(len(v) for v in gold.values())
    result = dict(gold=total_gold, videos=len(gold), iou_min=iou_min, hit={}, precision={}, start_error=None, end_error=None,
                  mean_iou=None, per_tier={}, reliable=total_gold >= MIN_RELIABLE)
    found = {k: 0 for k in ks}
    prec_num = {k: 0 for k in ks}
    prec_den = {k: 0 for k in ks}
    starts, ends, ious = [], [], []
    tiers = {}
    for video, moments in gold.items():
        cands = by_video.get(video, [])
        for g in moments:
            scores = [iou((c['start'], c['end']), g) for c in cands]
            for k in ks:
                if any(s >= iou_min for s in scores[:k]):
                    found[k] += 1
            hits = [(s, c) for s, c in zip(scores, cands) if s >= iou_min]
            if hits:
                best_s, best_c = max(hits, key=lambda x: x[0])
                starts.append(abs(best_c['start'] - g[0]))
                ends.append(abs(best_c['end'] - g[1]))
                ious.append(best_s)
        for k in ks:
            top = cands[:k]
            prec_den[k] += len(top)
            prec_num[k] += sum(1 for c in top if any(iou((c['start'], c['end']), g) >= iou_min for g in moments))
        for c in cands[:max(ks)]:
            tier = c.get('tier') or 'sem'
            ok = any(iou((c['start'], c['end']), g) >= iou_min for g in moments)
            tiers.setdefault(tier, [0, 0])
            tiers[tier][0] += int(ok)
            tiers[tier][1] += 1
    for k in ks:
        result['hit'][k] = round(found[k] / total_gold, 3) if total_gold else None
        result['precision'][k] = round(prec_num[k] / prec_den[k], 3) if prec_den[k] else None
    if ious:
        result['start_error'] = round(sum(starts) / len(starts), 2)
        result['end_error'] = round(sum(ends) / len(ends), 2)
        result['mean_iou'] = round(sum(ious) / len(ious), 3)
    result['per_tier'] = {t: dict(hits=a, total=b, rate=round(a / b, 3) if b else None) for t, (a, b) in tiers.items()}
    return result


def as_text(report, title='Benchmark do agente'):
    lines = [title, '=' * len(title), '']
    for label, r in report.items():
        lines.append(f'[{label}]')
        lines.append(f"  Momentos no gabarito: {r['gold']} em {r['videos']} vídeo(s) · acerto = IoU ≥ {r['iou_min']}")
        lines.append('  Achou o momento entre as k primeiras: ' + ' · '.join(
            f'top{k}: {v * 100:.0f}%' if v is not None else f'top{k}: —' for k, v in r['hit'].items()))
        lines.append('  Sugestões que batem com o gabarito: ' + ' · '.join(
            f'top{k}: {v * 100:.0f}%' if v is not None else f'top{k}: —' for k, v in r['precision'].items()))
        if r['mean_iou'] is not None:
            lines.append(f"  Nos acertos: erro médio de começo {r['start_error']}s, de fim {r['end_error']}s, IoU médio {r['mean_iou']}")
        if r['per_tier']:
            lines.append('  Acerto por confiança: ' + ' · '.join(
                f"{t}: {v['hits']}/{v['total']}" for t, v in sorted(r['per_tier'].items())))
        if not r['reliable']:
            lines.append(f'  AVISO: só {r["gold"]} momentos no gabarito. Com menos de {MIN_RELIABLE} os percentuais oscilam muito; '
                         'não conclua nada de diferenças pequenas.')
        lines.append('')
    return '\n'.join(lines)


def candidates_by_video(store, sessions):
    """{video: [candidatos em ordem de ranking]} a partir das sugestões atuais de cada sessão."""
    out = {}
    for name, sid in sessions.items():
        rows = store.rows("SELECT start,end,score,data FROM candidates WHERE session=? AND status!='replaced'", (sid,))
        items = []
        for r in rows:
            try:
                data = json.loads(r['data'])
            except (ValueError, TypeError):
                data = {}
            conf = data.get('confidence') or {}
            items.append(dict(start=r['start'], end=r['end'], score=r['score'], tier=conf.get('tier'), confidence=conf.get('value')))
        items.sort(key=lambda c: (-c['score']))
        out[name] = items
    return out


def _drain(app, progress, label, timeout=6 * 3600):
    """Roda o trabalho do agente na hora, até não sobrar nada na fila."""
    begin = time.time()
    while time.time() - begin < timeout:
        if not app.engine.work_once():
            return
        progress(f'{label}: {app.engine.state().get("stage", "")} {app.engine.state().get("detail", "")}'.strip()[:100])
    raise RuntimeError('A análise passou do limite de tempo do benchmark.')


def run(videos_dir, gold_csv, data_dir, style='clean', clip_format='short', compare=False, progress=print):
    """Analisa os vídeos do gabarito (reusa o que já foi analisado em `data_dir`) e devolve {rótulo: métricas}."""
    from .app import App
    from . import judge
    gold, warnings = load_gold(gold_csv)
    for w in warnings:
        progress(w)
    videos = {p.stem.casefold(): p for p in Path(videos_dir).iterdir() if p.suffix.casefold() in VIDEO_EXT}
    missing = [n for n in gold if n not in videos]
    if missing:
        raise ValueError('Vídeos do gabarito que não estão na pasta: ' + ', '.join(sorted(missing)))
    app = App(data_dir, worker=False)
    try:
        existing = app.store.rows("SELECT id FROM streamers WHERE name='BENCHMARK'")
        streamer = existing[0]['id'] if existing else app.store.create_streamer('BENCHMARK')
        profile = dict(app.store.streamer(streamer)['profile'], editorial_style=style, clip_format=clip_format, ollama=False)
        app.store.save_profile(streamer, profile)
        have = {r['name']: r['id'] for r in app.store.rows('SELECT id,name FROM sessions WHERE streamer=?', (streamer,))}
        sessions = {}
        for name in gold:
            if name in have:
                sessions[name] = have[name]
            else:
                sessions[name] = app.action('/api/video/import', dict(streamer=streamer, path=str(videos[name]), name=name))['id']
        app.store.setting('paused', False)
        progress('Analisando (a primeira vez demora; as próximas reaproveitam a análise)...')
        _drain(app, progress, 'análise')
        for name, sid in sessions.items():
            session = app.store.session(sid)
            if session['status'] == 'error':
                raise RuntimeError(f'A análise de {name} falhou: {session["error"]}')
            rows = app.store.segments(sid)
            if not rows or any(r['status'] != 'done' for r in rows):
                raise RuntimeError(f'O vídeo {name} não foi analisado por completo (arquivo muito pequeno, ainda sendo gravado ou com '
                                   'modificação nos últimos 25 segundos?). Confira e rode de novo.')
        report = {}
        report['agente completo'] = evaluate(candidates_by_video(app.store, sessions), gold)
        if compare:
            real_curate = judge.curate
            judge.curate = lambda candidates, transcript, bounds, limit, *a, **k: candidates[:limit]
            try:
                app.store.regenerate(streamer, 'benchmark: ranking básico')
                _drain(app, progress, 'ranking básico')
                report['só ranking básico'] = evaluate(candidates_by_video(app.store, sessions), gold)
            finally:
                judge.curate = real_curate
        return report
    finally:
        app.close()


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(prog='liveclips bench')
    sub = parser.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('modelo', help='cria o CSV de gabarito para preencher')
    a.add_argument('--videos', required=True)
    a.add_argument('--saida', default='gabarito.csv')
    b = sub.add_parser('rodar', help='analisa os vídeos e mede contra o gabarito')
    b.add_argument('--videos', required=True)
    b.add_argument('--gabarito', required=True)
    b.add_argument('--dados', default=str(Path.home() / 'LiveClips_benchmark'))
    b.add_argument('--estilo', default='clean')
    b.add_argument('--formato', default='short', choices=('short', 'narrative'))
    b.add_argument('--comparar', action='store_true')
    b.add_argument('--relatorio', default='')
    args = parser.parse_args(argv)
    if args.cmd == 'modelo':
        count = template(args.videos, args.saida)
        print(f'Criado {args.saida} com {count} vídeo(s). Preencha inicio e fim de cada bom clipe e rode "bench rodar".')
        return 0
    report = run(args.videos, args.gabarito, args.dados, args.estilo, args.formato, args.comparar, progress=print)
    text = as_text(report)
    print('\n' + text)
    if args.relatorio:
        Path(args.relatorio).write_text(text, encoding='utf-8-sig')
        print('Relatório salvo em', args.relatorio)
    return 0
