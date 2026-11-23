"""Tempos reais, continuidade explícita e planos de corte entre arquivos."""
import copy
import hashlib
import json
import math


def build_timeline(segments):
    result=[];cursor=0.0;previous=None;group=''
    for raw in sorted(segments,key=lambda s:s['seq']):
        row=dict(raw)   # cópia rasa: as linhas são planas e quem chama não altera o conteúdo aninhado
        duration=float(row['duration'])
        if not math.isfinite(duration) or duration<=0:
            raise ValueError('Duração inválida. Refaça a leitura desta gravação.')
        broken=previous is None or row['seq']!=previous['seq']+1 or row['signature']!=previous['signature']
        if broken:
            group=hashlib.sha256(f"{row['seq']}:{row['sha']}:{row['signature']}".encode()).hexdigest()[:16]
        row.update(start=cursor,end=cursor+duration,group_id=group,
                   discontinuity=bool(previous is not None and broken))
        result.append(row);cursor+=duration;previous=row
    return result


def plan(timeline,start,end,group_id=None):
    start,end=float(start),float(end)
    if not math.isfinite(start+end) or start<0 or end<=start:
        raise ValueError('Intervalo de corte inválido.')
    parts=[];cursor=start;groups=set()
    for row in timeline:
        a,b=max(start,row['start']),min(end,row['end'])
        if b-a<.00001:continue
        if abs(a-cursor)>.03:raise ValueError('Falta um trecho na linha do tempo.')
        groups.add(row['group_id'])
        if group_id and row['group_id']!=group_id:
            raise ValueError('O corte atravessa uma quebra de continuidade. Escolha outro limite.')
        parts.append(dict(path=row['path'],sha=row['sha'],seq=row['seq'],
                          **{'in':round(a-row['start'],6),'out':round(b-row['start'],6)},
                          global_start=row['start'],global_end=row['end'],group_id=row['group_id']))
        cursor=b
    if len(groups)!=1:raise ValueError('Não é possível juntar arquivos separados por lacuna ou formato diferente.')
    if abs(cursor-end)>.03:raise ValueError('O próximo segmento ainda não está disponível ou o limite ultrapassa a sessão.')
    return parts


def shifted_transcript(rows):
    result=[]
    for row in rows:
        for raw in row.get('data',{}).get('segments',[]):
            seg=copy.deepcopy(raw)
            seg['start']=float(raw['start'])+row['start'];seg['end']=float(raw['end'])+row['start']
            for word in seg.get('words') or []:
                word['start']=float(word['start'])+row['start'];word['end']=float(word['end'])+row['start']
            result.append(seg)
    return sorted(result,key=lambda s:s['start'])


def shifted_signals(rows):
    result={'audio':[],'motion':[],'facial':[],'behavior':[],'chat':[],'warnings':[],
            'behavior_meta':[],'technical':{'silence':[],'black':[],'freeze':[]}}
    for row in rows:
        data=row.get('data',{}).get('signals',{})
        for kind in ('silence','black','freeze'):
            for event in (data.get('technical') or {}).get(kind,[]):
                result['technical'][kind].append(dict(event,start=event['start']+row['start'],end=event['end']+row['start']))
        for key in ('audio','motion','facial','behavior'):
            result[key].extend(dict(p,time=p['time']+row['start']) for p in data.get(key,[]))
        if data.get('behavior_meta'):
            result['behavior_meta'].append(dict(data['behavior_meta'],seq=row['seq']))
        result['warnings'].extend(f"Segmento {row['seq']}: {w}" for w in data.get('warnings',[]))
    return result


def contexts(timeline,closed):
    """Espera o próximo segmento analisado; ao encerrar, libera a cauda."""
    for i,center in enumerate(timeline):
        if center['status']!='done':continue
        before=timeline[i-1] if i>0 and timeline[i-1]['group_id']==center['group_id'] else None
        after=timeline[i+1] if i+1<len(timeline) and timeline[i+1]['group_id']==center['group_id'] else None
        if before and before['status']!='done':continue
        if after and after['status']!='done':continue
        if not after and i==len(timeline)-1 and not closed:continue
        rows=[row for row in (before,center,after) if row]
        key=hashlib.sha256(json.dumps([(r['seq'],r['sha'],r['start'],r['end'],r['data']) for r in rows],
                                     sort_keys=True).encode()).hexdigest()
        yield center,rows,key


def expand_context(candidate,rows):
    """Acrescenta preparação/desfecho, respeitando as frases e o grupo disponível."""
    low,high=rows[0]['start'],rows[-1]['end']
    segments=shifted_transcript(rows)
    if candidate.get('refined'):
        # O juiz já alinhou começo e fim às frases: só garante que o corte fica dentro do material disponível.
        start=max(low,candidate['start']);end=min(high,candidate['end'])
    else:
        start=max(low,candidate['start']-4);end=min(high,candidate['end']+5)
        for seg in segments:
            if seg['start']<start<seg['end'] and start-seg['start']<=3:start=max(low,seg['start']-.25)
            if seg['start']<end<seg['end'] and seg['end']-end<=3:end=min(high,seg['end']+.3)
        limit=90 if candidate.get('clip_format')=='narrative' else 60
        if end-start>limit:end=start+limit
    result=copy.deepcopy(candidate)
    result.update(start=round(start,3),end=round(end,3),group_id=rows[0]['group_id'])
    if not candidate.get('refined'):result['reasons']=list(result.get('reasons',[]))+['Contexto anterior/posterior incluído para revisão.']
    result['boundary_warning']=bool(candidate.get('boundary_warning')) if candidate.get('refined') else any(s['start']<start<s['end'] or s['start']<end<s['end'] for s in segments)
    if result['boundary_warning'] and not candidate.get('refined'):result['reasons'].append('Confira os limites: pode haver fala atravessando o início ou fim.')
    result['context_files']=[r['seq'] for r in rows]
    result['transcript']=' '.join(s['text'] for s in segments if s['start']<end and s['end']>start)
    return result
