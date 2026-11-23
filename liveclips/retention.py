"""Planejador de limpeza: SÓ SIMULA. Nunca apaga nada.

Lista o que poderia sair e o que está protegido (mídia usada por cortes ativos, por episódios ou por sessão aberta).
Quem decide e executa a limpeza é a pessoa."""
import time
from pathlib import Path


def _size(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def plan(store, *, keep_days=30, now=None):
    now = time.time() if now is None else now
    limit = now - keep_days * 86400
    protected, removable, reasons = set(), [], {}
    active = store.rows("SELECT * FROM candidates WHERE status NOT IN ('rejected','replaced')")
    for c in active:
        store.decode(c)
        for p in c.get('parts') or []:
            protected.add(str(Path(p['path']).resolve()))
            reasons[str(Path(p['path']).resolve())] = 'usada por um corte ativo'
    for s in store.rows('SELECT * FROM sessions'):
        folder = Path(s['path'])
        # temporários de legenda/áudio de trabalho: sempre refazíveis
        for tmp in sorted(folder.glob('tmp_*')):
            if tmp.is_dir():
                for f in tmp.rglob('*'):
                    if f.is_file() and f.stat().st_mtime < limit:
                        removable.append(dict(path=str(f), bytes=_size(f), motivo='temporário refazível'))
        if not s['closed'] or not s['enabled']:
            continue                                   # sessão aberta ou pausada: nada da origem sai
        for seg in store.rows('SELECT path FROM segments WHERE session=?', (s['id'],)):
            p = Path(seg['path'])
            key = str(p.resolve()) if p.exists() else seg['path']
            if key in protected or not p.is_file() or p.stat().st_mtime >= limit:
                continue
            removable.append(dict(path=str(p), bytes=_size(p), motivo=f'original de sessão encerrada sem cortes ativos, > {keep_days} dias'))
    total = sum(r['bytes'] for r in removable)
    return dict(simulacao=True, apagou_algo=False, liberaria_bytes=total, itens=removable,
                protegidos=len(protected), aviso='Nada foi apagado. Confira a lista antes de decidir.')
