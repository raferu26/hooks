"""Fusão de pistas com origem e dependência, e associação ação → reação (N21, N23).

Regras do dossiê:
- Movimento genérico, movimento facial e comportamento vêm dos MESMOS pixels da webcam: são UMA fonte, não três
  confirmações. Só linhagens diferentes (webcam, jogo, áudio, fala, chat) confirmam uma à outra.
- Som alto do jogo com câmera mexendo não vira confirmação humana. Perda de modalidade reduz cobertura, não fabrica negativo.
- Proximidade temporal NÃO é causa: a associação lista alternativas e nunca marca `causal`.
- Os escores continuam heurísticos (nada aqui é probabilidade calibrada). O sistema pode se abster:
  `desconhecido`, `nao_observavel`, `associacao_incerta`, `aguardando_contexto`.
"""
LINEAGE = dict(motion='webcam_pixels', facial='webcam_pixels', behavior='webcam_pixels', visual='game_pixels',
               audio='audio_mix', fala='transcript', chat='chat_text', contexto='session_memory', humano='human_marker')
ABSTENTIONS = ('desconhecido', 'nao_observavel', 'associacao_incerta', 'aguardando_contexto')
STRONG_GLOBAL = 1.5
NEAR_SPEECH_S = 1.0
ASSOC_BACK_S = 6.0         # a reação pode vir até 6 s depois da causa possível
ASSOC_FORWARD_S = .5


def _norm(value, cap=3.0):
    return round(max(0.0, min(1.0, float(value or 0) / cap)), 3)


def _speech_spans(transcript, start, end):
    return [(max(start, float(s['start'])), min(end, float(s['end']))) for s in transcript or []
            if float(s['end']) > start and float(s['start']) < end and str(s.get('text', '')).strip()]


def _near_speech(t, spans, margin=NEAR_SPEECH_S):
    return any(a - margin <= t <= b + margin for a, b in spans)


def assess(window, signals, transcript=None, *, face=None, episode_pending=False, chat_uncertainty_s=0.0):
    """Tabela de evidências do trecho [start, end] com linhagem, conflitos, estados e abstenção.

    `face` = saída de face_quality.assess (ou None se não houver webcam)."""
    start, end = float(window[0]), float(window[1])
    signals = signals or {}
    span = max(.001, end - start)
    speech = _speech_spans(transcript, start, end)
    speech_cov = round(min(1.0, sum(b - a for a, b in speech) / span), 3)
    evidence, conflicts, notes = [], [], []

    def inside(key):
        return [p for p in signals.get(key) or [] if start <= float(p.get('time', -1)) <= end]

    cams = {k: inside(k) for k in ('motion', 'facial', 'behavior')}
    audio = inside('audio')
    visual = [p for p in inside('visual') if p.get('kind') in ('flash', 'rajada', None)]
    chat = inside('chat')
    face_unobservable = bool(face and face.get('nao_observavel'))
    states = dict(rosto='desconhecido' if face is None else 'nao_observavel' if face_unobservable else 'observado',
                  audio='observado' if signals.get('audio_ok', bool(audio)) else 'desconhecido',
                  jogo='observado' if signals.get('visual_ok') else 'desconhecido',
                  chat='observado' if chat else 'desconhecido', atribuicao_ao_streamer='nao_verificada')

    # movimento global (cabeça/câmera/cadeira) — não é reação local
    heads = [b for b in cams['behavior'] if b.get('cue') == 'virada_cabeca' and float(b.get('strength', 0)) >= STRONG_GLOBAL]
    global_motion = []
    for m in cams['motion']:
        if float(m.get('strength', 0)) >= STRONG_GLOBAL and any(abs(float(m['time']) - float(h['time'])) <= .6 for h in heads):
            global_motion.append(m)
    if global_motion:
        conflicts.append('movimento_global_possivel')
        notes.append('Cabeça/câmera/cadeira mexeram junto com o movimento da webcam: reduz o peso de qualquer pista facial.')
    cam_weight = 0.0 if face_unobservable else (.5 if global_motion else 1.0)
    if face_unobservable and any(cams.values()):
        conflicts.append('rosto_nao_observavel')
        notes.append('Qualidade do rosto insuficiente: as pistas faciais deste trecho não contam.')

    for key, points in cams.items():
        for p in points:
            evidence.append(dict(modality=key, lineage=LINEAGE[key], time=float(p['time']), strength=_norm(p.get('strength')),
                                 weight=cam_weight, confidence=p.get('confidence')))
    for p in audio:
        near = _near_speech(float(p['time']), speech)
        evidence.append(dict(modality='audio', lineage='audio_mix', time=float(p['time']), strength=_norm(p.get('strength')),
                             weight=1.0, attribution='voz_provavel' if near else 'indeterminada'))
    for p in visual:
        evidence.append(dict(modality='visual', lineage='game_pixels', time=float(p['time']), strength=_norm(p.get('strength')), weight=1.0))
    for p in chat:
        evidence.append(dict(modality='chat', lineage='chat_text', time=float(p['time']), strength=_norm(p.get('strength')),
                             weight=.6, time_uncertainty_s=round(chat_uncertainty_s, 2)))
    if speech:
        evidence.append(dict(modality='fala', lineage='transcript', time=speech[0][0], strength=min(1.0, speech_cov * 1.5), weight=1.0))

    counted = [e for e in evidence if e['weight'] > 0]
    lineages = sorted({e['lineage'] for e in counted})
    webcam_modalities = {e['modality'] for e in counted if e['lineage'] == 'webcam_pixels'}
    dependent_only = len(webcam_modalities) >= 2 and lineages == ['webcam_pixels']
    if dependent_only:
        notes.append('Movimento, rosto e comportamento vêm da mesma webcam: contam como UMA fonte, não como confirmação independente.')

    # som sem evidência humana nem visual (pista de cabeça que coincide com movimento global não prova reação humana)
    human_behavior = [b for b in cams['behavior'] if not (global_motion and b in heads)]
    lone_sound = []
    for p in audio:
        t = float(p['time'])
        human = _near_speech(t, speech) or any(abs(float(b['time']) - t) <= 3 for b in human_behavior) or \
            any(abs(float(v['time']) - t) <= 3 for v in visual)
        if not human:
            lone_sound.append(p)
    if lone_sound:
        conflicts.append('som_sem_evidencia_humana')
        notes.append('Pico de som sem fala, reação ou evento visual por perto: pode ser jogo/música, não reação do streamer.')

    # força combinada: o MELHOR de cada linhagem, e só linhagens diferentes somam
    per_lineage = {}
    for e in counted:
        per_lineage[e['lineage']] = max(per_lineage.get(e['lineage'], 0.0), e['strength'] * e['weight'])
    strength = round(min(1.0, sum(per_lineage.values()) / 2.0), 3)

    abstention = None
    if not counted:
        abstention = 'nao_observavel' if face_unobservable else 'desconhecido'
    elif face_unobservable and lineages == []:
        abstention = 'nao_observavel'
    elif episode_pending:
        abstention = 'aguardando_contexto'
    result = dict(janela=[round(start, 3), round(end, 3)], evidencias=evidence, linhagens=lineages,
                  fontes_independentes=len(lineages), somente_dependentes=dependent_only, conflitos=sorted(set(conflicts)),
                  estados=states, cobertura_fala=speech_cov, forca_observacao=strength, abstencao=abstention, notas=notes,
                  escore_calibrado=False)
    return result


def associate(reactions, events, *, back=ASSOC_BACK_S, forward=ASSOC_FORWARD_S):
    """Liga cada reação (instante `apex`/`time`) a causas POSSÍVEIS anteriores, sem afirmar causalidade.

    `events`: dicts com time e kind (visual, fala_desfecho, audio_voz...). Devolve uma ligação por reação, com intervalo de
    atraso, alternativas e `incerta` quando há mais de um evento plausível ou atraso longo. Sem evento: 'sem_evento_anterior'."""
    links = []
    for r in reactions:
        t = float(r.get('apex', r.get('time', 0)))
        cands = [e for e in events if -forward <= t - float(e['time']) <= back]
        cands.sort(key=lambda e: abs(t - float(e['time'])))
        if not cands:
            links.append(dict(reacao=t, estado='sem_evento_anterior', evento=None, alternativas=[], causal=False, incerta=True,
                              nota='Nenhum evento observado antes da reação; ela pode responder a algo fora do que foi capturado.'))
            continue
        main, rest = cands[0], cands[1:]
        delay = round(t - float(main['time']), 2)
        links.append(dict(reacao=t, estado='associada_possivel', evento=main, atraso_s=delay,
                          intervalo_atraso_s=[round(max(0, t - float(c['time'])), 2) for c in (cands[-1], cands[0])],
                          alternativas=rest, causal=False, incerta=bool(rest) or delay > 3.0,
                          nota='Proximidade temporal não prova causa.' + (' Há mais de um evento plausível.' if rest else '')))
    return links
