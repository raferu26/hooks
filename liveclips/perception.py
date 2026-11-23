"""Observações de cena a serviço do editor (P08/F13–F15).

Não rotula emoção interna. Cada observação é um fato mensurável (som, pausa, fala, movimento, gesto observável) com
intervalo, fonte, confiança, cobertura da amostragem e qualidade da evidência. Pontos de atenção são HIPÓTESES
contextuais sugeridas ao editor (close, crop, timing), sempre marcadas como tais. Sem modelo validado para a tarefa,
landmarks/blendshapes não viram porcentagem de felicidade ou surpresa.
"""

KINDS = ('fala', 'pausa', 'energia_sonora', 'evento_visual', 'comportamento_observavel')
QUALITY = ('alta', 'media', 'baixa')
FORBIDDEN_DETAIL = ('felicidade', 'surpresa', 'raiva', 'tristeza', 'emocao', 'emoção', 'feliz', 'humor_pct', 'happiness', 'surprise')
MIN_FACE_PX = 64           # abaixo disso, rosto pequeno: confiança cai e o layout não deve reagir a ele
LONG_PAUSE = 1.0


def observation(kind, start, end, source, confidence, coverage=1.0, quality='media', detail=None):
    if kind not in KINDS:
        raise ValueError('Tipo de observação desconhecido.')
    detail = dict(detail or {})
    text = ' '.join(f'{k} {v}' for k, v in detail.items()).lower()
    if any(word in text for word in FORBIDDEN_DETAIL):
        raise ValueError('Emoção interna não é uma observação; descreva o sinal geométrico ou sonoro.')
    if quality not in QUALITY:
        raise ValueError('Qualidade da evidência inválida.')
    return dict(kind=kind, start=round(float(start), 3), end=round(max(float(end), float(start)), 3), source=source,
                confidence=round(min(1.0, max(0.0, float(confidence))), 2), coverage=round(min(1.0, max(0.0, float(coverage))), 2),
                quality=quality, fact=True, detail=detail)


def face_confidence(base, face_px):
    """Rosto pequeno reduz a confiança. Devolve (confiança, layout_estavel): com rosto pequeno o layout deve ficar parado."""
    if face_px is None or face_px < MIN_FACE_PX:
        return round(base * .4, 2), True
    return base, False


def from_signals(signals, transcript, start, end, analysed_until=None):
    """Observações do trecho [start, end] (segundos da sessão) a partir dos sinais já extraídos.

    `analysed_until`: até onde a análise de sinais olhou (a extração limita a janela); fora disso a cobertura é zero e
    nada é inferido. Frequência de amostragem limita o que se pode afirmar: não há microexpressão entre quadros não analisados."""
    signals = signals or {}
    limit = end if analysed_until is None else min(end, analysed_until)
    coverage = 0.0 if limit <= start else min(1.0, (limit - start) / max(end - start, .001))
    obs = []
    for seg in transcript or []:
        a, b = max(start, float(seg['start'])), min(end, float(seg['end']))
        if b > a and str(seg.get('text', '')).strip():
            obs.append(observation('fala', a, b, 'transcricao', .8, 1.0, 'media', dict(texto=str(seg['text']).strip()[:80])))
    words = sorted((float(w['start']), float(w['end'])) for seg in transcript or [] for w in seg.get('words') or []
                   if start <= float(w.get('start', -1)) <= end)
    for (a0, b0), (a1, _) in zip(words, words[1:]):
        if a1 - b0 >= LONG_PAUSE:
            obs.append(observation('pausa', b0, a1, 'transcricao', .7, 1.0, 'media', dict(duracao=round(a1 - b0, 2))))
    for p in signals.get('audio') or []:
        t = float(p['time'])
        if start <= t <= end:
            strength = float(p.get('strength', 0))
            obs.append(observation('energia_sonora', t, t, 'audio', min(1, strength / 3), coverage if t > limit else 1.0,
                                   'alta' if strength >= 2 else 'media', dict(forca=round(strength, 2))))
    for e in (signals.get('motion') or []) + (signals.get('visual') or []):
        t = float(e.get('time', -1))
        if start <= t <= end:
            obs.append(observation('evento_visual', t, t, 'quadro', min(1, float(e.get('strength', 1)) / 3), 1.0 if t <= limit else 0.0,
                                   'media', dict(tipo=e.get('kind', 'movimento'))))
    for e in signals.get('behavior') or []:
        t = float(e.get('time', -1))
        if start <= t <= end:
            obs.append(observation('comportamento_observavel', t, t, 'rosto_geometria', min(1, float(e.get('strength', 1)) / 3), coverage,
                                   'baixa' if not signals.get('behavior_ok') else 'media', dict(sinal=e.get('cue', '?'))))
    return sorted(obs, key=lambda o: (o['start'], o['kind']))


def _near(obs, kinds, start, end, margin):
    return [o for o in obs if o['kind'] in kinds and o['start'] <= end + margin and o['end'] >= start - margin]


def attention_points(obs):
    """Hipóteses para o editor, com as observações que as sustentam. Nunca são afirmadas como fato."""
    points = []

    def add(kind, a, b, evidence, why, use, counter=False):
        points.append(dict(kind=kind, start=a, end=b, hipotese=True, contraexemplo=counter, confianca=round(min(o['confidence'] for o in evidence), 2),
                           evidencias=[(o['kind'], o['start']) for o in evidence], leitura=why, sugestao=use))

    for o in obs:
        if o['kind'] == 'comportamento_observavel' and not _near(obs, ('fala', 'energia_sonora'), o['start'], o['end'], 1.5):
            add('reacao_silenciosa', o['start'], o['end'], [o], 'Sinal facial/postural sem fala nem pico de som por perto.', 'close na webcam')
        if o['kind'] == 'evento_visual' and not _near(obs, ('energia_sonora', 'comportamento_observavel', 'fala'), o['start'], o['end'], 2.0):
            add('jogada_sem_reacao', o['start'], o['end'], [o], 'Evento no jogo sem reação audível ou visível de quem joga.', 'manter o jogo em destaque')
        if o['kind'] == 'energia_sonora' and o['quality'] == 'alta' and not _near(obs, ('evento_visual', 'comportamento_observavel'), o['start'], o['end'], 3.0):
            add('som_alto_sem_evento', o['start'], o['end'], [o], 'Pico de som sem evento visual ou facial: o grito pode não corresponder ao que aparece.',
                'não cortar só por esse pico', counter=True)
        if o['kind'] == 'pausa':
            before = _near(obs, ('fala',), o['start'] - 2, o['start'], 0)
            after = _near(obs, ('fala', 'energia_sonora'), o['end'], o['end'] + 2, 0)
            if before and after:
                add('preparacao_comica', o['start'], o['end'], [o, before[-1], after[0]],
                    'Pausa entre falas seguida de resposta: pode sustentar a expectativa de uma piada ou virada.', 'preservar a pausa no timing')
    return sorted(points, key=lambda p: (p['start'], p['kind']))


def report(obs, points):
    """Contagem e limites, para o painel e para o relatório de falsos positivos."""
    count = {}
    for o in obs:
        count[o['kind']] = count.get(o['kind'], 0) + 1
    return dict(observacoes=count, pontos=len(points), contraexemplos=sum(1 for p in points if p['contraexemplo']),
                limites=['São hipóteses de apoio ao editor, não leitura de emoção.', 'Sem análise de quadros fora da janela amostrada, nada é afirmado.',
                         'Utilidade para close, crop e timing precisa ser avaliada em casos revisados.'])
