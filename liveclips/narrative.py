"""Mapa de história e alternativas de duração com limites de fala verificáveis."""
from .intelligence import text_evidence


def story_plan(candidate,segments,signals,low,high):
    rows=sorted((s for s in segments if s.get('text') and low<=s['start']<high),key=lambda s:s['start'])
    if not rows:return {'beats':{},'alternatives':[],'warning':'Sem frases temporizadas suficientes.'}
    start,end=candidate['start'],candidate['end']
    nearby=[s for s in rows if s['end']>=start-8 and s['start']<=end+8]
    kind=candidate.get('moment_type','reacao')
    weights={'humor':'humor','jogada':'jogada','opiniao':'opiniao','historia':'historia',
             'educacional':'educacional','emocional':'emocional','tensao':'tensao','surpresa':'surpresa',
             'reacao':'reacao'}
    target=weights.get(kind,'reacao')
    def evidence(row):
        cues=text_evidence(row['text']);mid=(row['start']+row['end'])/2
        sensory=sum(min(2,float(p.get('strength',0))) for key in ('audio','motion','chat','behavior')
                    for p in signals.get(key,[]) if abs(float(p.get('time',-999))-mid)<2)
        return 3*bool(cues[target])+2*bool(cues['desfecho'])+min(3,sensory)+.6*bool(cues['reacao'])
    inside=[s for s in nearby if s['start']<end and s['end']>start]
    if not inside:return {'beats':{},'alternatives':[],'warning':'Nenhuma fala no intervalo.'}
    climax=max(inside,key=lambda s:(evidence(s),-abs((s['start']+s['end'])/2-(start+end)/2)))
    before=[s for s in nearby if s['end']<=climax['start'] and s['end']>=start-8]
    after=[s for s in nearby if s['start']>=climax['end'] and s['start']<=end+8]
    setup=next((s for s in before if text_evidence(s['text'])['tensao'] or
                text_evidence(s['text'])['historia'] or text_evidence(s['text'])['opiniao'] or
                text_evidence(s['text'])['educacional']),before[0] if before else climax)
    closure=next((s for s in after if text_evidence(s['text'])['desfecho']),
                 after[0] if after else climax)
    # A reação pode prosseguir depois do pico: espera a última frase próxima.
    for row in after:
        if row['start']-closure['end']>3 or row['end']>end+8:break
        if kind in ('reacao','humor','jogada','surpresa'):
            closure=row
            if text_evidence(row['text'])['desfecho']:break
        elif text_evidence(row['text'])['desfecho']:
            closure=row
            break
    beats={name:{'start':round(row['start'],2),'end':round(row['end'],2),'text':row['text']}
           for name,row in (('preparacao',setup),('climax',climax),('encerramento',closure))}
    alternatives=[]
    for duration in (30,45,60):
        if high-low<duration-2:continue
        # Escolhe frases inteiras, com o clímax e o encerramento dentro do corte.
        ends=[s for s in nearby if closure['end']<=s['end']<=min(high,closure['end']+.8)]
        options=[]
        for tail in ends[:15]:
            finish=min(high,tail['end']+.35)
            heads=[s for s in nearby if s['start']<=setup['start'] and
                   finish-duration-1.5<=s['start']<=finish-8]
            for head in heads:
                begin=max(low,head['start']-.25);span=finish-begin
                if duration-5<=span<=duration+1.5:
                    lead=climax['start']-begin
                    score=abs(span-duration)+max(0,lead-duration*.72)*.8+max(0,lead-duration*.48)*.12
                    options.append((score,begin,finish))
        if options:
            _,a,b=min(options)
            alternatives.append({'seconds':duration,'start':round(a,2),'end':round(b,2),
                                 'actual_seconds':round(b-a,1)})
    warning='' if closure['end']<=end+.2 else 'A frase final/reação continua depois do corte sugerido; revise o fim.'
    return {'beats':beats,'alternatives':alternatives,'warning':warning,
            'type':kind,'note':'Limites baseados em frases e sinais observáveis; confira o sentido antes de aprovar.'}
