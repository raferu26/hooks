"""Orquestra a camada de contexto/ação/reação por sugestão. Nada aqui pode derrubar a análise: cada passo é isolado
(`safe`) e, se falhar, o corte segue sem a anotação (e o motivo fica registrado em `intelligence.erro`)."""

from . import dimensions, face_quality, fusion, handoff, silent_path
from .context_search import required_context
from .context_store import ContextStore
from .episodes import persist

SILENT_BUDGET = 2


def face_for(signals):
    """Qualidade do rosto da janela, a partir do meta de cada segmento. Sem meta = desconhecido (None), nunca 'bom'."""
    metas = [m for m in (signals or {}).get('behavior_meta') or [] if m]
    if not metas:
        return None
    frames = sum(int(m.get('frames') or 0) for m in metas)
    faces = sum(int(m.get('faces') or 0) for m in metas)
    sizes = [m['face_px'] for m in metas if m.get('face_px')]
    fps = [float(m['sampling_fps']) for m in metas if m.get('sampling_fps')]
    return face_quality.assess(dict(frames=frames, faces=faces, face_px=min(sizes) if sizes else None,
                                    sampling_fps=min(fps) if fps else 4))


class Intelligence:
    def __init__(self, root):
        self.ctx = ContextStore(root)

    def prepare(self, session_id, transcript, *, creator=''):
        try:
            return persist(self.ctx, session_id, transcript, creator=creator)
        except Exception as exc:                      # noqa: BLE001 — a análise principal nunca depende disto
            return dict(erro=f'{type(exc).__name__}: {exc}')

    def silent(self, signals, transcript, length, session_id, *, focus, face, profile, mode):
        if profile.get('silent_reactions', True) is False:
            return [], []
        try:
            eps = [e for e in self.ctx.episodes(session_id)]
            eps = [dict(kind=e['kind'], text=e['text'], resolved=e['resolved']) for e in eps]
            return silent_path.propose(signals, transcript, length, focus=focus, episodes=eps, face=face,
                                       max_candidates=SILENT_BUDGET, clip_format=profile.get('clip_format', 'short'),
                                       editorial_style=profile.get('editorial_style', 'clean'), content_mode=mode)
        except Exception:                             # noqa: BLE001
            return [], []

    def annotate(self, candidate, session_id, transcript, signals, face, *, creator='', others=(), creator_signal=None):
        """Preenche `candidate['intelligence']` e `candidate['handoff']`. Devolve o candidato."""
        try:
            start, end = float(candidate['start']), float(candidate['end'])
            eps_all = self.ctx.episodes(session_id)
            related = [e for e in eps_all if e['opened'] <= end and (e['resolved'] is None or e['resolved'] >= start - 5)
                       and end - e['opened'] <= 900]
            open_eps = [e for e in related if e['status'] in ('aberto', 'revisar')]
            chat_unc = max([float(c.get('time_uncertainty_s') or 0) for c in signals.get('chat') or []] or [0.0])
            assessment = fusion.assess((start, end), signals, transcript, face=face, episode_pending=bool(open_eps),
                                       chat_uncertainty_s=chat_unc or 5.0)
            reactions = [dict(apex=b.get('apex', b['time'])) for b in signals.get('behavior') or []
                         if start <= float(b.get('apex', b['time'])) <= end]
            events = [dict(time=v['time'], kind=v.get('kind') or 'visual') for v in signals.get('visual') or []
                      if start - 15 <= float(v['time']) <= end]
            associations = fusion.associate(reactions, events) if reactions else []
            dims = dimensions.compute(candidate, assessment, episodes=[dict(kind=e['kind'], status=e['status']) for e in related],
                                      others=list(others), creator_signal=creator_signal, associations=associations)
            required = required_context(self.ctx, session_id, transcript, start, end, creator=creator)
            candidate['intelligence'] = dict(avaliacao=assessment, dimensoes=dims, associacoes=associations,
                                             episodios=[dict(id=e['id'], kind=e['kind'], status=e['status'], text=e['text'][:160],
                                                             opened=e['opened'], resolved=e['resolved']) for e in related],
                                             contexto_necessario=required, rosto=face)
            candidate['handoff'] = handoff.build(candidate, required=required, assessment=assessment, dimensions=dims)
            self.ctx.trace(candidate.get('id') or f"{session_id}:{start:.1f}", session_id, 'sugestao',
                           dict(estado=dims['estado'], fontes_independentes=assessment['fontes_independentes'],
                                origem=candidate.get('origin', 'fala_e_sinais')))
        except Exception as exc:                      # noqa: BLE001
            candidate['intelligence'] = dict(erro=f'{type(exc).__name__}: {exc}')
        return candidate
