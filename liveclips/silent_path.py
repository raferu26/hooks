"""Caminho visual/contextual para reações silenciosas (N12).

O ranking principal exige fala, pico de áudio ou movimento para abrir uma janela; um olhar ou sorriso discreto depois
de um acontecimento pode nunca chegar a ser visto. Este caminho PROPÕE janelas a partir de pistas faciais com início,
ápice e retorno, e as marca como exploratórias: uma pista isolada pede revisão, não vira highlight forte. Rejeita (e
registra por quê) bocejo, amostra única, movimento global de cabeça/câmera, fala em curso e rosto não observável.
A origem de cada candidato fica registrada para medir o recall por caminho.
"""
import re

from .episodes import FAIL, SUCCESS, sentences

REACTIVE = ('sorriso', 'boca_aberta', 'sobrancelhas_elevadas', 'olhos_abertos', 'olhos_apertados', 'sobrancelhas_contraidas')
CO_CUES = ('sobrancelhas_elevadas', 'olhos_abertos', 'sorriso')
TRIGGER_BACK_S = 8.0
PRE_ROLL_S = 3.0
POST_ROLL_S = 2.5
MIN_LEN_S = 8.0
MAX_LEN_S = 40.0
ISOLATED_MIN_STRENGTH = 2.0
ORIGIN = 'reacao_silenciosa'


def _speech(transcript):
    return [(float(s['start']), float(s['end'])) for s in transcript or [] if str(s.get('text', '')).strip()]


def _cover(spans, a, b):
    if b <= a:
        return 0.0
    return sum(max(0.0, min(y, b) - max(x, a)) for x, y in spans) / (b - a)


def _times(e):
    apex = float(e.get('apex', e['time']))
    onset = float(e.get('onset', apex))
    offset = float(e.get('offset', apex + float(e.get('duration', .25))))
    return onset, apex, max(offset, apex)


def _triggers(apex, signals, transcript, episodes):
    lo, hi = apex - TRIGGER_BACK_S, apex + .5
    found = []
    for v in signals.get('visual') or []:
        if lo <= float(v['time']) <= hi and v.get('kind') in ('flash', 'rajada'):
            found.append(dict(kind='evento_visual', time=float(v['time']), weight=.35, detail=v.get('kind')))
    for s in sentences(transcript):
        if lo <= float(s['end']) <= hi:
            out = 'falha' if any(re.search(p, s['plain']) for p in FAIL) else 'sucesso' if any(re.search(p, s['plain']) for p in SUCCESS) else None
            if out:
                found.append(dict(kind='desfecho_falado', time=float(s['end']), weight=.3, detail=out, quote=s['text'][:100]))
    for e in episodes or []:
        r = e.get('resolved')
        if r is not None and lo <= float(r) <= hi:
            found.append(dict(kind='episodio', time=float(r), weight=.4, detail=e.get('kind'), quote=str(e.get('text', ''))[:100]))
    sp = _speech(transcript)
    for a in signals.get('audio') or []:
        t = float(a['time'])
        if lo <= t <= hi and not any(x - 1 <= t <= y + 1 for x, y in sp):
            found.append(dict(kind='som_do_jogo', time=t, weight=.15, detail='energia sem fala por perto (pode ser jogo)'))
    return sorted(found, key=lambda f: f['time'])


def propose(signals, transcript, length, *, focus=None, episodes=None, face=None, max_candidates=2,
            clip_format='short', priority='equilibrio', editorial_style='clean', content_mode='live'):
    """Devolve (candidatos, rejeitados). `rejeitados` registra cada pista descartada e o motivo (auditável)."""
    signals = signals or {}
    sp = _speech(transcript)
    events = [e for e in signals.get('behavior') or [] if e.get('cue') in REACTIVE]
    cands, rejected = [], []
    sampling = float((face or {}).get('sampling_fps') or 4)
    for e in sorted(events, key=lambda x: float(x.get('apex', x['time']))):
        onset, apex, offset = _times(e)
        if focus and not (focus[0] <= apex < focus[1]):
            continue
        def drop(reason):
            rejected.append(dict(time=round(apex, 3), cue=e.get('cue'), motivo=reason))
        if face and face.get('nao_observavel'):
            drop('rosto_nao_observavel'); continue
        if float(e.get('confidence', 0)) < .5 or float(e.get('strength', 0)) < 1.0:
            drop('pista_fraca'); continue
        if int(e.get('samples', 2)) <= 1 and sampling < 8:
            drop('amostra_unica_possivel_artefato'); continue
        dur = max(float(e.get('duration', 0)), offset - onset)
        co = [x for x in signals.get('behavior') or [] if x is not e and x.get('cue') in CO_CUES and abs(float(x.get('apex', x['time'])) - apex) <= 1.0]
        if e.get('cue') == 'boca_aberta' and dur >= 1.2 and not co:
            drop('bocejo_provavel'); continue
        heads = [x for x in signals.get('behavior') or [] if x.get('cue') == 'virada_cabeca' and float(x.get('strength', 0)) >= 1.5
                 and abs(float(x.get('apex', x['time'])) - apex) <= .6]
        moves = [m for m in signals.get('motion') or [] if float(m.get('strength', 0)) >= 1.5 and abs(float(m['time']) - apex) <= .6]
        if heads and moves:
            drop('movimento_global_cabeca_ou_camera'); continue
        if _cover(sp, apex - 1.0, apex + 2.0) >= .6:
            drop('durante_fala'); continue
        trig = _triggers(apex, signals, transcript, episodes)
        isolated = not trig or all(t['kind'] == 'som_do_jogo' for t in trig)
        if isolated and float(e.get('strength', 0)) < ISOLATED_MIN_STRENGTH:
            drop('pista_isolada_sem_gatilho'); continue
        first = min([t['time'] for t in trig if t['kind'] != 'som_do_jogo'] or [onset])
        start = max(0.0, min(onset, first) - PRE_ROLL_S)
        end = min(float(length), offset + POST_ROLL_S)
        if end - start < MIN_LEN_S:
            end = min(float(length), start + MIN_LEN_S)
        if end - start > MAX_LEN_S:
            start = max(0.0, end - MAX_LEN_S)
        for s, t in sp:                      # não corta fala ao meio por pouco
            if s < start < t and start - s <= 3:
                start = max(0.0, s - .25)
            if s < end < t and t - end <= 3:
                end = min(float(length), t + .3)
        score = 1.0 + .5 * float(e.get('strength', 0)) * float(e.get('confidence', .5)) + sum(t['weight'] for t in trig)
        if isolated:
            score = min(score, 1.6)
        included = [s for s in sentences(transcript) if float(s['start']) < end and float(s['end']) > start]
        text = ' '.join(s['text'] for s in included)
        reasons = [('Pista isolada: ' if isolated else 'Reação silenciosa depois de um acontecimento: ') +
                   f"{e.get('label') or e.get('cue')} (início {onset:.1f}s · ápice {apex:.1f}s · retorno {offset:.1f}s). Não indica emoção."]
        if trig and not isolated:
            reasons.append('Gatilho anterior: ' + ', '.join(f"{t['kind']} ({t['detail']})" for t in trig if t['kind'] != 'som_do_jogo'))
        if isolated:
            reasons.append('Sem acontecimento anterior observado: pede revisão humana, não vale como momento forte.')
        reasons.append('Candidato exploratório: confira o contexto antes de usar.')
        cands.append({'start': round(start, 2), 'end': round(end, 2), 'score': round(score, 2), 'transcript': text,
                      'reasons': reasons, 'components': {'reacao_silenciosa': round(score, 3)}, 'speech_ratio': round(_cover(sp, start, end), 3),
                      'boundary_warning': any(s < end < t or s < start < t for s, t in sp), 'priority': priority,
                      'selection_version': 'v0.14-caminho-silencioso', 'moment_type': 'exploratorio',
                      'moment_label': 'Reação silenciosa · revise', 'moment_confidence': .3,
                      'moment_scores': {}, 'narrative': {'gancho': 0, 'preparacao': 0, 'climax': 0, 'encerramento': 0, 'historia_completa': 0},
                      'behavior_evidence': [e], 'learned_weights': {}, 'clip_format': clip_format, 'editorial_style': editorial_style,
                      'content_mode': content_mode, 'fallback': True, 'low_confidence': True, 'exploratory': True,
                      'origin': ORIGIN, 'isolated_cue': isolated, 'triggers': trig,
                      'facial_timing': dict(onset=onset, apex=apex, offset=offset, time_uncertainty_s=e.get('time_uncertainty_s'))})
    cands.sort(key=lambda c: -c['score'])
    out = []
    for c in cands:
        if any(max(0, min(c['end'], o['end']) - max(c['start'], o['start'])) / max(1e-6, min(c['end'] - c['start'], o['end'] - o['start'])) > .5 for o in out):
            continue
        out.append(c)
        if len(out) >= max_candidates:
            break
    return out, rejected
