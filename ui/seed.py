import json,subprocess,sys,time
from pathlib import Path
import pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from liveclips import media
from liveclips.store import Store,DEFAULT_PROFILE
from liveclips.timeline import build_timeline,plan
from liveclips.editing import plan_edits
import os
LONG=os.environ.get('HOOKS_SEED_LONG')=='1'   # 120 s de fonte, cortes de ate 90 s e ~400 palavras (benchmark N5/V09)
DUR=120 if LONG else 60
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
store=Store(root)
sid_=store.create_streamer('CORINGA')
profile=dict(DEFAULT_PROFILE,min_free_gb=.5,content_mode='video',vocabulary='Coringa')
store.save_profile(sid_,profile)
sid=store.new_session(sid_,'PODCAST DE TESTE')
sess=store.session(sid)
f=Path(sess['source'])/'segmento_00000.ts'
subprocess.run([media.tool('ffmpeg'),'-nostdin','-loglevel','error','-y','-f','lavfi','-i','testsrc2=s=1280x720:r=30:d=%d'%DUR,'-f','lavfi','-i','sine=frequency=300:duration=%d'%DUR,'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(f)],check=True)
text='Gente olha isso aqui agora porque ninguem acredita nisso mas o Koringa fez de novo e foi incrivel mesmo ' \
     'eu nunca tinha visto nada parecido na minha vida inteira tipo sério ' \
     'entao presta atencao porque esse truque muda tudo no final do video e voce vai entender por que'
if LONG:text=(text+' ')*6
words=[];t=10.4
for w in text.split():
    words.append(dict(start=round(t,2),end=round(t+.32,2),word=w));t+=.38
segs=[];i=0
while i<len(words):
    chunk=words[i:i+9];segs.append(dict(start=chunk[0]['start'],end=chunk[-1]['end'],text=' '.join(x['word'] for x in chunk),words=chunk));i+=9
(Path(sess['path'])/'fonte.json').write_text(json.dumps(dict(mode='video',reframe_mode='conservative',url='',title='Podcast de teste',author='CORINGA',file=str(f))))
info=media.probe(f);st=f.stat()
with store.connect(True) as c:
    c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,0,str(f.resolve()),media.sha_file(f),info['duration'],info['signature'],st.st_size,st.st_mtime_ns,'done',json.dumps({'segments':segs,'signals':{'audio':[],'motion':[],'warnings':[]}})))
rows=build_timeline(store.segments(sid));group=rows[0]['group_id']
for k,(a,b,score) in enumerate(([(5,95,9.1),(22,50,7.4),(5,30,6.2)] if LONG else [(10,38,9.1),(22,50,7.4),(5,30,6.2)])):
    data=dict(start=a,end=b,group_id=group,score=score,reasons=['Pico de voz e reação confirmados','Início com pergunta forte'],components={},transcript=' '.join(s['text'] for s in segs),transcript_segments=segs,content_mode='video',reframe_mode='conservative')
    data['edit_plan']=plan_edits(data,{},transcript=segs,profile=profile)
    data['confidence']=[dict(value=.82,tier='alta',reasons=[]),dict(value=.31,tier='baixa',reasons=['Pouca evidência: só um tipo de pista.','Fim pouco conclusivo.']),dict(value=.55,tier='média',reasons=[])][k]
    if k==2:data['ab']=dict(group='x',label='B',change='abertura invertida')
    parts=plan(rows,a,b,group)
    key,_=store.propose(sid,data,parts,dict(profile))
print('ok',sid)
if LONG:   # corte manual de 90 s (os candidatos automáticos se sobrepõem e são fundidos): benchmark V09
    from liveclips.app import App
    a=App(str(root));print('manual90',a.make_manual(a.store.session(sid),5.0,95.0,allow_overlap=True))
