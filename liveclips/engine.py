"""Pistas de trabalho independentes (análise das lives, edição, exportação, revisão de legenda); estado recuperável.

Cada pista tem o seu trabalhador, então exportar não atrasa a análise de uma live nem a prévia que você está editando.
O modo antigo (um trabalhador só) continua disponível em `work_once`, usado pelos testes e pela opção "pista única".
"""
import collections
import gc
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from . import agents,cache,progress,camera_detect,cover,delivery,judge,markers,media,ollama,qc,review,subtitles,support,technical,titledata
from .chat import load_signals
from .editorial import audit,source_info
from .editing import plan_edits
from .narrative import story_plan
from . import narrative_skill
from .telemetry import Telemetry
from .ranking import rank
from .signals import extrair
from .camada_contexto import Intelligence,face_for
from .store import analysis_key
from .timeline import build_timeline,contexts,expand_context,plan,shifted_signals,shifted_transcript


def _confidence(word):
    try:return round(max(0.0,min(1.0,float(getattr(word,'probability',1.0)))),2)
    except (TypeError,ValueError):return 1.0


def serialize(segments):
    """Segmentos do faster-whisper em dicionários; cada palavra guarda `p` (confiança do reconhecimento, 0 a 1)."""
    return [dict(start=float(s.start),end=float(s.end),text=s.text.strip(),
                 words=[dict(start=float(w.start),end=float(w.end),word=w.word.strip(),p=_confidence(w)) for w in (s.words or [])])
            for s in segments if s.text.strip()]


def cuda_devices():
    """Quantas placas NVIDIA o CTranslate2 (usado pelo faster-whisper) enxerga; 0 se não houver ou der erro."""
    try:
        import ctranslate2
        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def whisper_plan(profile,devices=None):
    """(dispositivo, tipo de cálculo) da transcrição: placa de vídeo quando existe, senão processador."""
    choice=profile.get('whisper_device','auto')
    if choice=='cpu':return 'cpu','int8'
    count=cuda_devices() if devices is None else devices
    if choice=='cuda' or (choice=='auto' and count>0):
        return 'cuda','float16'
    return 'cpu','int8'


def transcription_prompt(profile):
    """Orienta grafia sem pedir ao modelo que invente palavras ausentes."""
    vocabulary=' '.join(str(profile.get('vocabulary','')).split())[:800]
    if not vocabulary:
        return None
    return 'Grafias esperadas de nomes próprios, jogos, marcas e termos: '+vocabulary


def _manifest_value(video,key):
    try:return json.loads((Path(video).parent/'manifesto.json').read_text(encoding='utf-8')).get(key)
    except Exception:return None


LANES=('analise','edicao','exportacao','exportacao2','refino')
LANE_LABEL=dict(analise='Análise das lives',edicao='Edição e prévias',exportacao='Exportação',exportacao2='Exportação 2',refino='Revisão de legenda')


class ModelGate:
    """Só uma transcrição por vez usa o modelo de voz (ele não é compartilhável entre threads). A análise das lives tem
    prioridade: uma revisão de legenda espera enquanto houver análise na vez."""
    def __init__(self):
        self.cv=threading.Condition();self.busy=False;self.waiting_high=0

    def acquire(self,high=False):
        with self.cv:
            if high:self.waiting_high+=1
            try:
                while self.busy or (not high and self.waiting_high):self.cv.wait(1)
                self.busy=True
            finally:
                if high:self.waiting_high-=1

    def release(self):
        with self.cv:
            self.busy=False;self.cv.notify_all()


def ai_free(profile):
    """Modo estritamente sem IA: nada de Whisper, MediaPipe, RNNoise, Ollama nem outro modelo é iniciado."""
    return (profile or {}).get('ai_mode','padrao')=='sem_ia'


class Engine:
    def __init__(self,store):
        self.store=store
        self.stop=threading.Event()
        self.info=dict(stage='Parado',detail='A análise começa quando você clicar em Iniciar análise.',busy=False)
        self.guard=threading.Lock();self.model=None;self.model_key=None;self.turn=0
        self.thread=None;self.threads=[];self.task_streamer=None;self.refine_queue=[]
        self.failures={}
        self.lane_info={};self.local=threading.local();self.board=progress.Board()
        self.claimed=set();self.claim_lock=threading.Lock();self.session_lock=threading.Lock()
        self.rot={};self.gate=ModelGate();self.rtf=collections.deque(maxlen=20)
        self.license=None   # licensing.Licensing, ligado pelo App; None = sem limites (testes e modo livre)

    def mode(self):
        """'pistas' (padrão): cada tipo de trabalho tem o seu trabalhador. 'unico': um trabalhador faz tudo, como antes."""
        return 'unico' if self.store.setting('lanes')=='unico' else 'pistas'

    def export_workers(self):
        try:return 2 if int(self.store.setting('export_workers') or 1)>=2 else 1
        except (TypeError,ValueError):return 1

    def state(self):
        now=time.time()
        with self.guard:
            lanes=[]
            for name in LANES:
                cur=self.lane_info.get(name)
                if cur:
                    item=dict(cur['info'],lane=name,label=LANE_LABEL[name])
                    item['elapsed_s']=round(now-cur['since']) if item.get('busy') else 0
                    lanes.append(item)
            busy=[l for l in lanes if l.get('busy')]
            head=dict(busy[0]) if busy else dict(self.info)
            if not busy:head['elapsed_s']=0
            head['lanes']=lanes
        head['mode']=self.mode()
        try:head['capacity']=self.capacity()
        except Exception:head['capacity']=None
        return head

    def capacity(self):
        """Estimativa MEDIDA de quanto o PC aguenta: segundos de transcrição por segundo de live. Com N lives abertas, o
        trabalho por minuto é N vezes isso; acima de ~0,8 a análise não acompanha e o atraso só cresce."""
        samples=list(self.rtf)
        lives=len(self.store.rows("SELECT id FROM sessions WHERE enabled=1 AND closed=0"))
        if len(samples)<2:return dict(rtf=None,lives=lives,ok=None)
        rtf=sum(samples)/len(samples)
        needed=rtf*max(lives,1)
        return dict(rtf=round(rtf,2),lives=lives,needed=round(needed,2),ok=needed<=0.8,samples=len(samples))

    def progress(self,stage,detail='',busy=True,percent=None,eta=None):
        lane=getattr(self.local,'lane',None) or 'analise'
        info=dict(stage=stage,detail=detail,busy=busy)
        if percent is not None:info.update(percent=percent,eta=eta,eta_text=support.human(eta))
        key=(stage,' · '.join(detail.split(' · ')[:2]))
        with self.guard:
            cur=self.lane_info.get(lane)
            since=cur['since'] if cur and cur['key']==key and cur['info'].get('busy') else time.time()
            self.lane_info[lane]=dict(info=info,key=key,since=since)
            self.info=info

    def start(self):
        """Um thread por pista. Em modo 'unico' só o principal trabalha; nas pistas, o principal fica parado (e vice-versa)."""
        loops=[('principal',self.loop)]
        for lane,fn in (('analise',self.lane_analysis),('edicao',self.lane_edit),('exportacao',lambda:self.lane_export('exportacao',0)),
                        ('exportacao2',lambda:self.lane_export('exportacao2',1)),('refino',self.lane_refine)):
            loops.append((lane,fn))
        for name,fn in loops:
            t=threading.Thread(target=self.run_lane,args=(name,fn),name='LiveClips-'+name,daemon=True)
            t.start();self.threads.append(t)
        self.thread=self.threads[0]

    def run_lane(self,name,fn):
        self.local.lane=name if name!='principal' else 'analise'
        fn()

    def idle(self,lane,text,detail=''):
        self.progress(text,detail,False)

    def lane_loop(self,lane,step,idle_text,idle_detail,needs_mode='pistas'):
        """Corpo comum das pistas: executa `step()`; se não houve trabalho, espera. Erros de uma pista não derrubam as outras."""
        while not self.stop.is_set():
            try:
                if self.mode()!=needs_mode:
                    self.stop.wait(1);continue
                if step():continue
                self.idle(lane,*(idle_text() if callable(idle_text) else (idle_text,idle_detail)))
            except media.LowSpace as exc:
                self.progress('Processamento aguardando espaço',str(exc),False)
            except Exception as exc:
                self.store.event('erro',str(exc));self.progress('Atenção',str(exc),False)
                support.log_error('Falha no processamento ('+lane+'): '+str(exc),exc)
            self.stop.wait(2 if lane!='edicao' else 1)

    def lane_analysis(self):
        def step():
            if self.store.setting('paused'):return False
            return self._session_step([])
        def idle():
            paused=self.store.setting('paused')
            return (('Análise pausada','As prévias e as exportações continuam funcionando.') if paused else
                    ('Aguardando segmentos','Um segmento em gravação só entra depois de ficar estável.'))
        self.lane_loop('analise',step,idle,'')

    def lane_edit(self):
        def step():
            blocked=[]
            if self._render_jobs((0,1),blocked):return True
            if blocked:raise blocked[0]
            return self._camera_step()
        self.lane_loop('edicao',step,'Edição livre','Prévias e imagens da webcam saem aqui, sem esperar a exportação.')

    def lane_export(self,lane,index):
        def step():
            if index and self.export_workers()<2:return False
            blocked=[]
            if self._render_jobs((2,),blocked):return True
            if blocked:raise blocked[0]
            return False
        self.lane_loop(lane,step,'Exportação livre' if not index else 'Segunda exportação desligada',
                       'Os cortes aprovados são exportados aqui.' if not index else 'Ajustes → Sistema → exportações ao mesmo tempo.')

    def lane_refine(self):
        self.lane_loop('refino',self._refine_step,'Revisão de legenda livre','Cortes aprovados ganham a segunda passagem de legenda aqui.')

    def loop(self):
        """Pista única (modo antigo): o trabalhador faz tudo em sequência."""
        while not self.stop.is_set():
            try:
                if self.mode()!='unico':
                    self.stop.wait(1);continue
                if self.work_once():continue
                paused=self.store.setting('paused')
                self.progress('Análise pausada' if paused else 'Aguardando segmentos',
                              'Prévias e exportações aprovadas continuam disponíveis.' if paused else
                              'Um segmento em gravação só entra depois de ficar estável.',False)
            except media.LowSpace as exc:
                self.progress('Processamento aguardando espaço',str(exc),False)
            except Exception as exc:
                self.store.event('erro',str(exc));self.progress('Atenção',str(exc),False)
                support.log_error('Falha no processamento: '+str(exc),exc)
            self.stop.wait(2)

    FAIR_STREAK=3

    def work_once(self):
        """Modo antigo: uma tarefa por chamada, na ordem revisão → imagens/prévias/exportações → sessões."""
        blocked=[]
        if self._refine_step():return True
        # Justiça: uma fila longa de exportações aprovadas não pode segurar a análise das lives para sempre.
        # A cada FAIR_STREAK trabalhos de edição seguidos, a análise tem a vez de andar um passo.
        if getattr(self,'render_streak',0)>=self.FAIR_STREAK and not self.store.setting('paused'):
            self.render_streak=0
            if self._session_step([]):return True
        if self._render_jobs((0,1,2),blocked):
            self.render_streak=getattr(self,'render_streak',0)+1
            return True
        self.render_streak=0
        if self._camera_step():return True
        if self.store.setting('paused'):
            if blocked:raise blocked[0]
            return False
        return self._session_step(blocked)

    def _claim(self,key):
        with self.claim_lock:
            if key in self.claimed:return False
            self.claimed.add(key);return True

    def _release(self,key):
        with self.claim_lock:self.claimed.discard(key)

    def _refine_step(self):
        with self.guard:pending=self.refine_queue.pop(0) if self.refine_queue else None
        if not pending:return False
        key=('c',pending[0])
        if not self._claim(key):
            with self.guard:self.refine_queue.append(pending)
            return False
        try:self.do_refine(*pending)
        finally:self._release(key)
        return True

    def _render_jobs(self,kinds,blocked):
        """Executa UM trabalho de imagem (0), prévia (1) ou exportação (2). Nunca dois trabalhos no mesmo corte ao mesmo tempo."""
        jobs=[]
        if 0 in kinds:
            for row in self.store.rows("SELECT * FROM sessions WHERE frame_status='queued' ORDER BY created"):
                jobs.append(dict(kind=0,streamer=row['streamer'],created=row['created'],row=row,key=('f',row['id'])))
        if 1 in kinds:
            for row in self.store.rows("SELECT id,streamer,created FROM candidates WHERE preview_status='queued' ORDER BY created"):
                jobs.append(dict(kind=1,streamer=row['streamer'],created=row['created'],row=row,key=('c',row['id'])))
        if 2 in kinds:
            for row in self.store.rows("SELECT id,streamer,created FROM candidates WHERE status='approved' ORDER BY created"):
                jobs.append(dict(kind=2,streamer=row['streamer'],created=row['created'],row=row,key=('c',row['id'])))
        lane=getattr(self.local,'lane',None)
        last=self.rot.get(lane) if lane else self.task_streamer
        # Alterna também as exportações entre perfis, sem uma live ocupar a fila inteira.
        streamers=sorted({j['streamer'] for j in jobs})
        if last in streamers:
            index=streamers.index(last)+1
            streamers=streamers[index:]+streamers[:index]
        order={sid:i for i,sid in enumerate(streamers)}
        for job in sorted(jobs,key=lambda j:(order[j['streamer']],j['kind'],j['created'])):
            if not self._claim(job['key']):continue
            try:
                if job['kind']==0:self.do_frame(job['row'])
                else:self.do_render(job['row']['id'],job['kind']==1)
            except media.LowSpace as exc:
                blocked.append(exc);continue
            finally:self._release(job['key'])
            if lane:self.rot[lane]=job['streamer']
            else:self.task_streamer=job['streamer']
            return True
        return False

    CAMERA_TRY_AT=(0,4,9)         # índice do segmento usado em cada tentativa (1ª, 5ª e 10ª peça registrada)

    def _camera_step(self):
        """Procura a webcam sozinho em sessões de live cujo streamer ainda não a marcou. 'alta' confiança e nada analisado ainda:
        aplica; senão deixa uma sugestão para o usuário confirmar (aplicar mexe na análise, que é refeita)."""
        for session in self.store.rows("SELECT * FROM sessions WHERE enabled=1 ORDER BY closed ASC,created"):
            sid=session['streamer'];profile=self.store.streamer(sid)['profile']
            if profile.get('content_mode','live')!='live' or profile.get('camera_rect') or ai_free(profile):continue
            if self.store.setting('camera_sugestao:'+sid):continue
            key='camera_tentativa:'+session['id'];tries=int(self.store.setting(key) or 0)
            if tries>=len(self.CAMERA_TRY_AT):continue
            segments=self.store.segments(session['id']);target=self.CAMERA_TRY_AT[tries]
            if len(segments)<=target:continue
            claim=('cam',session['id'])
            if not self._claim(claim):continue
            try:
                self.store.setting(key,tries+1)
                self.progress('Procurando a webcam',self.label(session))
                result=camera_detect.detect(segments[target]['path'])
                if not result['found']:
                    self.store.event('webcam','Não localizei a webcam sozinho (tentativa '+str(tries+1)+' de '+str(len(self.CAMERA_TRY_AT))+'): '+result['reason'])
                    return True
                untouched=not any(seg['status']=='done' for other in self.store.rows('SELECT id FROM sessions WHERE streamer=?',(sid,))
                                  for seg in self.store.segments(other['id']))
                if result['level']=='alta' and untouched:
                    self.store.save_profile(sid,dict(profile,camera_rect=result['rect']))
                    self.store.event('webcam','Webcam localizada automaticamente ('+result['reason']+'). Confira em Ajustes → Webcam e quadro.')
                else:
                    self.store.setting('camera_sugestao:'+sid,dict(rect=result['rect'],level=result['level'],reason=result['reason'],session=session['id']))
                    self.store.event('webcam','Achei uma webcam provável ('+result['reason']+'); falta você confirmar.')
                return True
            finally:self._release(claim)
        return False

    def _session_step(self,blocked):
        """Executa UMA etapa de análise (ler, sugerir ou transcrever) de uma sessão. Só um chamador por vez."""
        if not self.session_lock.acquire(blocking=False):return False
        try:return self._session_step_locked(blocked)
        finally:self.session_lock.release()

    def _session_step_locked(self,blocked):
        sessions=self.store.rows("SELECT * FROM sessions WHERE enabled=1 AND (status!='error' OR closed=0) ORDER BY created")
        if not sessions:return False
        # Lives abertas passam na frente das sessões encerradas: os cortes precisam chegar enquanto a live ainda grava.
        # Dentro de cada grupo o rodízio continua; sessões antigas só trabalham quando nenhuma live tem o que fazer.
        ordered=[]
        for group in ([x for x in sessions if not x['closed']],[x for x in sessions if x['closed']]):
            if group:
                k=self.turn%len(group);ordered+=group[k:]+group[:k]
        now=time.time()
        for i,session in enumerate(ordered):
            profile=self.store.streamer(session['streamer'])['profile']
            fail=self.failures.get(session['id'])
            try:
                media.require_space(self.store.root,profile['min_free_gb'],100*1024**2)
                mode=source_info(session['path']).get('mode','live')
                if session['status']=='error' or (fail and fail['next_at']>now):
                    # Falha na análise não pode parar a gravação: uma live aberta continua cadastrando os pedaços novos.
                    if not session['closed'] and self.scan_one(session):
                        self.turn=(self.turn+1)%len(sessions);return True
                    continue
                # Links de VOD podem baixar dezenas de segmentos muito mais
                # rápido que a transcrição. Neles, analisar antes de cadastrar
                # o próximo arquivo evita uma fila 0/N sem sugestões até o fim
                # do download. Lives preservam a leitura imediata do segmento
                # recém-fechado para não atrasar a captura contínua.
                worked=(self.suggest_one(session,profile) or self.analyze_one(session,profile) or
                        self.scan_one(session)) if mode=='video' else (
                        self.scan_one(session) or self.suggest_one(session,profile) or
                        self.analyze_one(session,profile))
                if worked:
                    self.failures.pop(session['id'],None)
                    self.turn=(self.turn+1)%len(sessions);return True
            except media.LowSpace as exc:
                blocked.append(exc);continue
            except Exception as exc:
                self.register_failure(session,exc)
                return True
        if blocked:raise blocked[0]
        # Se nenhuma sessão ativa tinha mais contexto pendente, a
        # reclassificação solicitada terminou e o aviso pode desaparecer.
        failed={row['streamer'] for row in self.store.rows("SELECT streamer FROM sessions WHERE enabled=1 AND status='error'")}
        self.store.finish_regeneration({session['streamer'] for session in sessions}-failed)
        return False

    RETRY_DELAYS=(30,120,300)

    def register_failure(self,session,exc):
        """Falha na análise: tenta de novo sozinho (30 s, 2 min, 5 min) antes de parar a sessão com erro visível."""
        fail=self.failures.get(session['id'],dict(count=0))
        count=fail['count']+1
        message=str(exc)[:2000]
        support.log_error('Falha no processamento: '+message,exc)
        if count<=len(self.RETRY_DELAYS):
            delay=self.RETRY_DELAYS[count-1]
            self.failures[session['id']]=dict(count=count,next_at=time.time()+delay,message=message)
            self.store.event('erro',f"{session['name']}: tentativa {count} de {len(self.RETRY_DELAYS)+1} falhou ({message[:160]}); nova tentativa em {delay} s.")
            self.progress('Falha temporária',f"{self.label(session)} · {message[:120]} · tentando de novo em {delay} s",False)
            return
        self.failures.pop(session['id'],None)
        with self.store.connect(True) as c:
            c.execute("UPDATE sessions SET status='error',error=? WHERE id=?",(message,session['id']))
        self.store.event('erro',session['name']+': '+message)

    def waiting_note(self,session):
        """Quando uma sessão encerrada está sendo analisada e há uma live aberta, diz isso (a live entra no rodízio)."""
        try:
            if not session['closed']:return ''
            live=[r for r in self.store.rows("SELECT * FROM sessions WHERE closed=0 AND enabled=1 AND id!=?",(session['id'],))]
            if not live:return ''
            names=', '.join(r['name'] for r in live[:2])
            return f' · a live ({names}) espera a vez. Para pular esta sessão: Gerenciar → Pausar esta sessão'
        except Exception:return ''

    def label(self,session):
        return self.store.streamer(session['streamer'])['name']+' / '+session['name']

    def do_frame(self,session):
        profile=self.store.streamer(session['streamer'])['profile']
        media.require_space(self.store.root,profile['min_free_gb'])
        self.progress('Preparando imagem da webcam',self.label(session))
        try:
            files=sorted(Path(session['source']).glob('segmento_*.ts'))
            stable=[p for p in files if p.is_file() and time.time()-p.stat().st_mtime>25]
            if not stable:raise ValueError('Aguarde o primeiro segmento completo da gravação.')
            target=Path(session['path'])/'imagem_webcam.jpg'
            media.frame(stable[0],target)
            with self.store.connect(True) as c:
                c.execute("UPDATE sessions SET frame_status='ready',frame_path=?,frame_error='' WHERE id=?",(str(target),session['id']))
        except Exception as exc:
            with self.store.connect(True) as c:
                c.execute("UPDATE sessions SET frame_status='error',frame_error=? WHERE id=?",(str(exc),session['id']))

    def scan_one(self,session):
        source=Path(session['source'])
        if source.is_file():files=[(0,source)]
        elif source.is_dir():
            files=[]
            for file in source.glob('segmento_*.ts'):
                match=re.fullmatch(r'segmento_(\d+)\.ts',file.name,re.IGNORECASE)
                if match and file.is_file():files.append((int(match[1]),file))
        else:raise ValueError('A origem não está disponível: '+str(source))
        files.sort(key=lambda x:x[0])
        known=self.store.segment_index(session['id'])
        for seq,file in files:
            stat=file.stat()
            if seq in known:
                row=known[seq]
                if stat.st_size!=row['size'] or stat.st_mtime_ns!=row['mtime']:
                    raise ValueError('Um segmento já registrado mudou. Preserve os originais e importe como nova sessão.')
                continue
            # Uma live pode travar sem fechar o arquivo. Estabilidade sozinha não
            # prova que o último .ts terminou: aguarde o seguinte ou o encerramento.
            if not session['closed'] and seq==files[-1][0]:continue
            # Não reordena uma linha do tempo que já teve sugestões.
            if known and seq<max(known):
                raise ValueError('Chegou um arquivo antigo fora de ordem. Importe novamente em outra sessão para reconstruir os tempos.')
            if time.time()-stat.st_mtime<25:continue
            if stat.st_size<128000:
                # O último pedaço de uma live encerrada costuma ser curto. Só entra se ainda tiver vídeo legível (>= 3 s).
                if not session['closed']:continue
                try:
                    if float(media.probe(file)['duration'])<3:continue
                except Exception:continue
            self.progress('Lendo gravação',self.label(session)+' · '+file.name)
            info=media.probe(file)
            digest=media.sha_file(file)
            after=file.stat()
            if after.st_size!=stat.st_size or after.st_mtime_ns!=stat.st_mtime_ns:return False
            with self.store.connect(True) as c:
                c.execute('INSERT OR IGNORE INTO segments(session,seq,path,sha,duration,signature,size,mtime) VALUES(?,?,?,?,?,?,?,?)',
                          (session['id'],seq,str(file.resolve()),digest,info['duration'],info['signature'],stat.st_size,stat.st_mtime_ns))
            return True
        missing=[r for r in known.values() if not Path(r['path']).is_file()]
        if missing:raise ValueError('Um segmento original foi removido ou movido. Os cortes dependem dele.')
        return False

    CUDA_ERROR=re.compile(r'cublas|cudnn|cudart|cuda|\.dll',re.I)

    def run_transcribe(self,profile,call,name=None,high=False):
        """Executa `call(modelo)` por inteiro, uma transcrição por vez (o modelo é único). `high=True` (análise das lives) passa
        na frente da revisão de legenda. Se a placa de vídeo falhar NA HORA de transcrever (DLL do CUDA ausente, como
        cublas64_12.dll), passa para o processador e repete uma vez, em vez de travar a análise com erro."""
        self.gate.acquire(high)
        try:
            for attempt in (0,1):
                model=self.get_model(profile,name)
                try:
                    return call(model)
                except Exception as exc:
                    device,_=whisper_plan(profile)
                    if attempt==0 and device=='cuda' and not getattr(self,'cuda_broken',False) and self.CUDA_ERROR.search(str(exc)):
                        self.cuda_broken=True;self.model=None;self.model_key=None;self.spare=None;gc.collect()
                        self.store.event('transcrição','Placa de vídeo sem os componentes CUDA ('+str(exc)[:100]+'); usando o processador.')
                        continue
                    raise
        finally:self.gate.release()

    def get_model(self,profile,name=None):
        if ai_free(profile):raise RuntimeError('O modo sem IA não carrega modelos de voz. Mude o modo de análise em Ajustes → Avançado.')
        name=name or profile['model']
        device,compute=whisper_plan(profile)
        if getattr(self,'cuda_broken',False):device,compute='cpu','int8'
        key=(name,profile['threads'],device)
        spare=getattr(self,'spare',None)
        if key!=self.model_key and spare and spare[0]==key:
            # O modelo da análise e o da legenda precisa se alternam: trocar de um para o outro não recarrega nada.
            self.spare=(self.model_key,self.model) if self.model is not None else None
            self.model_key,self.model=spare
            return self.model
        if key!=self.model_key:
            small=('tiny','base','small')
            # Guarda o modelo anterior só quando os dois são leves; com um modelo grande a memória fala mais alto.
            self.spare=(self.model_key,self.model) if (self.model is not None and name in small and self.model_key and self.model_key[0] in small) else None
            self.model=None;gc.collect()
            from faster_whisper import WhisperModel
            self.progress('Preparando modelo de voz',f"{name} · {'placa de vídeo' if device=='cuda' else 'processador'}"
                          ' · o primeiro uso pode baixar o modelo')
            try:
                self.model=WhisperModel(name,device=device,compute_type=compute,
                                        cpu_threads=profile['threads'],num_workers=1)
            except Exception as exc:
                if device!='cuda':raise
                # Placa de vídeo sem os componentes CUDA instalados: volta para o processador sem travar a análise.
                self.store.event('transcrição','Placa de vídeo indisponível ('+str(exc)[:120]+'); usando o processador.')
                device,compute='cpu','int8';key=(name,profile['threads'],device)
                self.model=WhisperModel(name,device=device,compute_type=compute,
                                        cpu_threads=profile['threads'],num_workers=1)
            self.model_key=key
        return self.model

    def analyze_one(self,session,profile):
        row=self.store.next_new_segment(session['id'])
        if row is None:return False
        if self.license is not None and not self.license.allow_analysis():
            self.progress('Análise pausada pelo plano',self.license.analysis_block_reason()[:160]);return False   # a gravação segue; só a análise espera
        with self.store.connect(True) as c:
            c.execute("UPDATE segments SET status='processing' WHERE session=? AND seq=?",(session['id'],row['seq']))
        try:
            if ai_free(profile):return self._analyze_free(session,profile,row)
            self.progress('Transcrevendo',self.label(session)+' · segmento '+str(row['seq'])+self.waiting_note(session))
            def transcribe_all(model):
                iterator,info=model.transcribe(row['path'],language=profile['language'],beam_size=1,best_of=1,
                                              vad_filter=True,condition_on_previous_text=False,word_timestamps=True,
                                              initial_prompt=transcription_prompt(profile))
                found=[];clock=support.Eta()
                for segment in iterator:
                    found.extend(serialize([segment]))
                    step=clock.update(segment.end/max(1.0,float(row['duration'])))
                    self.progress('Transcrevendo',f"{self.label(session)} · segmento {row['seq']} · {step['percent']}%"
                                  +(f" · faltam {support.human(step['eta'])}" if step['eta'] is not None else ''),percent=step['percent'],eta=step['eta'])
                return found,info
            started=time.time()
            segments,info=self.run_transcribe(profile,transcribe_all,high=True)
            if float(row['duration'] or 0)>5:self.rtf.append((time.time()-started)/float(row['duration']))
            self.progress('Analisando voz, vídeo e comportamento',self.label(session)+' · segmento '+str(row['seq']))
            signals=extrair(row['path'],row['duration'],profile if profile.get('camera_rect') else None,
                            speech=[(float(x['start']),float(x['end'])) for x in segments if 'start' in x and 'end' in x])
            if analysis_key(profile)!=analysis_key(self.store.streamer(session['streamer'])['profile']):
                with self.store.connect(True) as c:
                    c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=?",(session['id'],row['seq']))
                return True
            data=dict(segments=segments,signals=signals,language=info.language,model=profile['model'],profile=profile)
            target=Path(session['path'])/'analise';target.mkdir(exist_ok=True)
            path=target/(f"segmento_{row['seq']:05}.json")
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
            with self.store.connect(True) as c:
                current=c.execute('SELECT profile FROM streamers WHERE id=?',(session['streamer'],)).fetchone()
                if analysis_key(profile)!=analysis_key(json.loads(current['profile'])):
                    c.execute("UPDATE segments SET status='new',data='{}' WHERE session=? AND seq=?",(session['id'],row['seq']))
                    return True
                c.execute("UPDATE segments SET status='done',data=? WHERE session=? AND seq=?",
                          (json.dumps(data),session['id'],row['seq']))
            if self.license is not None:   # horas de live analisadas: o id é fixo por trecho, então refazer a análise não cobra de novo
                self.license.record('analise_s',min(7200.0,max(1.0,float(row['duration'] or 0))),f"a:{session['id']}:{row['seq']}")
        except Exception:
            with self.store.connect(True) as c:
                c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=?",(session['id'],row['seq']))
            raise
        return True

    def _analyze_free(self,session,profile,row):
        """Análise do modo sem IA: só medidas clássicas (energia, movimento, silêncio, preto, imagem parada).
        Não transcreve; legendas importadas, se existirem, entram em `suggest`."""
        self.progress('Medindo sinais técnicos',self.label(session)+' · segmento '+str(row['seq'])+' · sem IA')
        signals=extrair(row['path'],row['duration'],profile if profile.get('camera_rect') else None,ai=False)
        signals['technical']=self.cached_technical(row)
        if analysis_key(profile)!=analysis_key(self.store.streamer(session['streamer'])['profile']):
            with self.store.connect(True) as c:
                c.execute("UPDATE segments SET status='new' WHERE session=? AND seq=?",(session['id'],row['seq']))
            return True
        data=dict(segments=[],signals=signals,language='',model='sem_ia',profile=profile,ai_mode='sem_ia')
        target=Path(session['path'])/'analise';target.mkdir(exist_ok=True)
        path=target/(f"segmento_{row['seq']:05}.json")
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
        with self.store.connect(True) as c:
            c.execute("UPDATE segments SET status='done',data=? WHERE session=? AND seq=?",(json.dumps(data),session['id'],row['seq']))
        if self.license is not None:
            self.license.record('analise_s',min(7200.0,max(1.0,float(row['duration'] or 0))),f"a:{session['id']}:{row['seq']}")
        return True

    def cached_technical(self,row):
        """Análise técnica com cache por conteúdo do arquivo: o mesmo vídeo importado de novo não é medido outra vez."""
        sha=row.get('sha') if hasattr(row,'get') else None
        version=getattr(technical,'VERSION',1)
        if sha:
            hit=cache.get(self.store.root,'tecnica',sha,dict(v=version,duration=round(float(row['duration'] or 0),2)))
            if hit is not None:return hit
        result=technical.analyze(row['path'],row['duration'])
        if sha:cache.put(self.store.root,'tecnica',sha,result,dict(v=version,duration=round(float(row['duration'] or 0),2)))
        return result

    def _suggest_free(self,session,profile):
        """Sugestões do modo sem IA (P04): marcadores do arquivo/atalho primeiro; depois, se o perfil permitir, picos técnicos
        marcados como heurística. Legendas importadas só alimentam a legenda do corte; não escolhem o momento."""
        timeline=build_timeline(self.store.segments(session['id']))
        completed={r['seq']:r['context_key'] for r in self.store.rows('SELECT * FROM centers WHERE session=?',(session['id'],))}
        marks,mark_warnings=markers.for_session(session['path'])
        subs,sub_warnings=subtitles.for_session(session['path'])
        fingerprint=hashlib.sha256(json.dumps([marks,[(x['start'],x['end'],x['text']) for x in subs]],sort_keys=True).encode()).hexdigest()
        source=source_info(session['path']);mode=source.get('mode','live');reframe=source.get('reframe_mode','conservative')
        clip_format=profile.get('clip_format','short')
        for center,rows,key in contexts(timeline,bool(session['closed'])):
            key=hashlib.sha256((key+json.dumps(profile,sort_keys=True)+fingerprint).encode()).hexdigest()
            if completed.get(center['seq'])==key:continue
            self.progress('Montando cortes (sem IA)',self.label(session)+' · contexto do segmento '+str(center['seq']))
            low,high=rows[0]['start'],rows[-1]['end']
            signals=shifted_signals(rows)
            signals['chat']=load_signals(session['path'],high)
            if mark_warnings or sub_warnings:signals['warnings']=list(signals['warnings'])+mark_warnings+sub_warnings
            mine=[m for m in marks if center['start']<=m['time']<center['end'] or (m['time']>=high-1e-6 and center is timeline[-1])]
            found=markers.candidates_from_markers(mine,low,high,center['group_id'],clip_format)
            if profile.get('free_heuristic',True):
                found+=markers.candidates_from_signals(dict(signals,audio=[p for p in signals['audio'] if center['start']<=p['time']<center['end']],
                                                            motion=[p for p in signals['motion'] if center['start']<=p['time']<center['end']]),
                                                       low,high,center['group_id'],clip_format,existing=found)
            transcript=[dict(x) for x in subs if x['end']>low and x['start']<high]
            for candidate in found:
                candidate['transcript_segments_origin']='importada' if transcript else 'nenhuma'
                candidate['transcript']=' '.join(x['text'] for x in transcript if x['start']<candidate['end'] and x['end']>candidate['start'])
                candidate['edit_plan']=plan_edits(candidate,signals,transcript=transcript,profile=profile,habits=self.memory_habits(session['streamer'],self.store.habits(session['streamer'])),
                                                  protected_spans=[tuple(x) for x in candidate.get('protected',[])])
                candidate['warnings']=signals['warnings']
                candidate['profile']=profile
                candidate['transcript_segments']=transcript
                candidate['content_mode']=mode;candidate['reframe_mode']=reframe
                candidate['editorial_audit']=audit(candidate,profile,source)
                candidate['ai_mode']='sem_ia'
                parts=plan(timeline,candidate['start'],candidate['end'],center['group_id'])
                try:
                    fp=media.visual_fingerprint(parts)
                    if fp:candidate['visual_fingerprint']=fp
                except (OSError,RuntimeError,ValueError):pass
                _,created=self.store.propose(session['id'],candidate,parts,dict(profile,content_mode=mode,reframe_mode=reframe))
                if created and candidate.get('heuristic'):self.store.trim_fallbacks(session['id'],5)
            with self.store.connect(True) as c:
                c.execute('INSERT OR REPLACE INTO centers VALUES(?,?,?)',(session['id'],center['seq'],key))
            return True
        return False

    def suggest_one(self,session,profile):
        if ai_free(profile):return self._suggest_free(session,profile)
        timeline=build_timeline(self.store.segments(session['id']))
        completed={r['seq']:r['context_key'] for r in self.store.rows('SELECT * FROM centers WHERE session=?',(session['id'],))}
        for center,rows,key in contexts(timeline,bool(session['closed'])):
            key=hashlib.sha256((key+json.dumps(profile,sort_keys=True)).encode()).hexdigest()
            if completed.get(center['seq'])==key:continue
            self.progress('Conectando os momentos',self.label(session)+' · contexto do segmento '+str(center['seq']))
            transcript=shifted_transcript(rows);signals=shifted_signals(rows)
            signals['chat']=load_signals(session['path'],rows[-1]['end'])
            preferences=self.store.ranking_preferences(session['streamer'])
            source=source_info(session['path']);mode=source.get('mode','live')
            reframe=source.get('reframe_mode','conservative')
            habits=self.store.habits(session['streamer'])
            table=self.store.confidence_table(session['streamer'])
            clip_format=profile.get('clip_format','short')
            selected=rank(transcript,rows[-1]['end'],signals,profile['priority'],
                          focus=(center['start'],center['end']),max_candidates=8,
                          learned_weights=preferences,clip_format=clip_format,
                          editorial_style=profile.get('editorial_style','clean'),content_mode=mode)
            self.progress('Refinando começo e fim dos cortes',self.label(session)+' · contexto do segmento '+str(center['seq']))
            selected=judge.curate(selected,transcript,(rows[0]['start'],rows[-1]['end']),limit=6,
                                  clip_format=clip_format,habits=habits,table=table)
            intel=Intelligence(self.store.root)
            face=face_for(signals)
            intel.prepare(session['id'],transcript,creator=session['streamer'])
            silent,_rejected=intel.silent(signals,transcript,rows[-1]['end'],session['id'],focus=(center['start'],center['end']),
                                          face=face,profile=profile,mode=mode)
            if profile.get('ollama'):
                self.progress('Avaliando ganchos com o modelo local',self.label(session)+' · '+str(profile.get('ollama_model','')))
                selected=judge.finalize(ollama.rerank(selected,profile),4,table)
            else:
                selected=selected[:4]
            # Caminho de reação silenciosa: exploratório, no máximo 2, e nunca por cima de um corte já escolhido.
            selected=list(selected)+[s for s in silent if not any(
                min(s['end'],o['end'])-max(s['start'],o['start'])>.5*min(s['end']-s['start'],o['end']-o['start']) for o in selected)]
            chosen=[]
            for candidate in selected:
                candidate=expand_context(candidate,rows)

                candidate['agent_bounds']=[candidate['start'],candidate['end']]
                candidate['story_plan']=story_plan(candidate,transcript,signals,rows[0]['start'],rows[-1]['end'])
                candidate['function_map']=narrative_skill.function_map(candidate,candidate['story_plan'],transcript,signals)
                candidate['edit_plan']=plan_edits(candidate,signals,transcript=transcript,profile=profile,
                                                  habits=self.memory_habits(session['streamer'],habits),protected=candidate['function_map']['protected'])
                candidate['memory_refs']=self.memory_refs(session['streamer'],candidate)
                if candidate['function_map']['decision']=='conservador':
                    candidate['reasons']=list(candidate.get('reasons',[]))+candidate['function_map']['why']
                if profile.get('ollama') and profile.get('ollama_model'):
                    candidate['llm_titles']=ollama.titles(candidate.get('transcript',''),profile['ollama_model'],profile.get('ollama_url'))
                candidate['warnings']=signals['warnings']
                candidate['profile']=profile
                candidate['transcript_segments']=transcript
                candidate['content_mode']=mode
                candidate['reframe_mode']=reframe
                candidate['editorial_audit']=audit(candidate,profile,source)
                candidate['hook']=agents.hook_analysis(transcript,candidate['start'],candidate['end'])
                intel.annotate(candidate,session['id'],transcript,signals,face,creator=session['streamer'],others=chosen)
                chosen.append(dict(start=candidate['start'],end=candidate['end'],transcript=candidate.get('transcript','')))
                parts=plan(timeline,candidate['start'],candidate['end'],center['group_id'])
                try:
                    fingerprint=media.visual_fingerprint(parts)
                    if fingerprint:candidate['visual_fingerprint']=fingerprint
                except (OSError,RuntimeError,ValueError):
                    # A seleção continua funcional sem fingerprint; a deduplicação
                    # temporal/SHA existente permanece como proteção principal.
                    pass
                candidate_profile=dict(profile,content_mode=mode,reframe_mode=reframe)
                _,created=self.store.propose(session['id'],candidate,parts,candidate_profile)
                if created and candidate.get('fallback'):self.store.trim_fallbacks(session['id'],5)
            with self.store.connect(True) as c:
                c.execute('INSERT OR REPLACE INTO centers VALUES(?,?,?)',(session['id'],center['seq'],key))
            return True
        return False

    def memory_habits(self,streamer,habits):
        """Hábitos aprendidos + preferências confirmadas na memória editorial (a regra explícita limita o orçamento de efeitos)."""
        try:prefs=self.store.memory.streamer_prefs(streamer)
        except Exception:return habits
        factor=prefs.get('fator_zoom')
        if not isinstance(factor,(int,float)):return habits
        result=dict(habits or {});table=dict(result.get('effect_factor') or {})
        table['zoom']=min(float(table.get('zoom',1.0)),max(.25,min(1.0,float(factor))))
        result['effect_factor']=table
        return result

    def memory_refs(self,streamer,candidate):
        """IDs das memórias relevantes para este corte (sem registrar uso: o uso conta no render)."""
        try:
            hits=self.store.memory.retrieve(dict(streamer=streamer,task='corte',text=' '.join([candidate.get('moment_type',''),candidate.get('transcript','')[:200]])),
                                           limit=5,record_use=False)
            return [dict(id=h['id'],version=h['version'],why=h['why']) for h in hits]
        except Exception:return []

    def queue_refine(self,candidate_id,name=None):
        """Pede a revisão da legenda de um corte (modelo do perfil; se estiver desligado, o `small`)."""
        profile=self.store.streamer(self.store.candidate(candidate_id)['streamer'])['profile']
        if ai_free(profile):
            self.store.set_refine(candidate_id,dict(status='skipped',reason='modo sem IA'));return
        name=name or (profile.get('second_pass') if profile.get('second_pass')!='off' else 'small')
        with self.guard:
            if not any(item[0]==candidate_id for item in self.refine_queue):self.refine_queue.append((candidate_id,name))
        self.store.set_refine(candidate_id,dict(status='queued',model=name))

    def do_refine(self,candidate_id,name=None):
        candidate=self.store.candidate(candidate_id)
        profile=self.store.streamer(candidate['streamer'])['profile']
        name=name or profile.get('second_pass','off')
        if name=='off' or ai_free(profile):return False
        session=self.store.session(candidate['session'])
        self.store.set_refine(candidate_id,dict(status='working',model=name))
        wav=None
        try:
            media.require_space(self.store.root,profile['min_free_gb'],100*1024**2)
            folder=Path(session['path'])/'tmp_legenda'
            wav=media.clip_audio(candidate['parts'],folder/(candidate_id+'.wav'))
            self.progress('Revisando a legenda',self.label(session)+' · modelo '+name+' · só o trecho do corte')
            def refine_all(model):
                iterator,_=model.transcribe(str(wav),language=profile['language'],beam_size=5,best_of=5,vad_filter=True,
                                            condition_on_previous_text=False,word_timestamps=True,
                                            initial_prompt=transcription_prompt(profile))
                return serialize(list(iterator))
            segments=self.run_transcribe(profile,refine_all,name)
            offset=float(candidate['start'])
            for seg in segments:
                seg['start']+=offset;seg['end']+=offset
                for word in seg['words']:word['start']+=offset;word['end']+=offset
            result=self.store.apply_refined(candidate_id,segments,name)
            self.store.event('legenda revisada',f"{candidate_id} · {result['changed']} palavras mudaram")
            return True
        except media.LowSpace:
            self.store.set_refine(candidate_id,dict(status='error',error='Pouco espaço em disco.'));raise
        except Exception as exc:
            self.refine_failed_at=time.time()
            self.store.set_refine(candidate_id,dict(status='error',error=str(exc)[:300]))
            self.store.event('erro na revisão da legenda',str(exc)[:300])
            return False
        finally:
            if wav:
                try:Path(wav).unlink()
                except OSError:pass

    def run_qc(self,candidate_id,video):
        """Checagem automática do arquivo exportado. Falha aqui nunca derruba a exportação."""
        try:
            video=Path(video);started=time.time()
            report=qc.check_export(video,video.parent/'legendas.ass',planned_freezes=self.planned_freezes(video.parent/'plano.json'),
                                   fonts_dir=self.store.root/'fontes',samples_dir=video.parent/'amostras',ai=not self._ai_free_for(candidate_id))
            extra=qc.manifest_checks(video.parent)
            if extra:
                items=report['items']+extra;report=dict(report,**qc.summarize(items),items=items)
            report['seconds']=round(time.time()-started,1)
            report=self.review_export(candidate_id,video,report)
            self.store.set_qc(candidate_id,report)
            (video.parent/'qualidade.txt').write_text(qc.as_text(report),encoding='utf-8-sig')
            if report['level']!='ok':self.store.event('qualidade: '+report['level'],report['summary'][:160])
        except Exception as exc:
            self.store.set_qc(candidate_id,dict(level='atencao',errors=0,warnings=1,summary='A checagem automática falhou: '+str(exc)[:120],items=[]))

    def apply_auto_title(self,candidate,session):
        """Título automático por modelo do perfil (P15), só se o corte não tem título feito à mão. Falha = sem título."""
        try:
            template=(candidate.get('profile') or {}).get('title_template') or ''
            if not template or ((candidate['data'].get('project') or {}).get('titles')):return
            ordered=self.store.rows("SELECT id FROM candidates WHERE session=? AND status!='rejected' ORDER BY start,id",(session['id'],))
            number=next((i+1 for i,row in enumerate(ordered) if row['id']==candidate['id']),None)
            name=self.store.streamer(candidate['streamer'])['name']
            text=titledata.render(template,titledata.values_for(candidate,name,session['name'],number))
            if text:candidate['data']=dict(candidate['data'],auto_title=text)
        except Exception:pass

    def make_cover(self,candidate_id,video):
        """Capas (P20) a partir de quadros do vídeo pronto. Falha aqui nunca derruba a exportação."""
        try:
            candidate=self.store.candidate(candidate_id)
            if not (candidate.get('profile') or {}).get('cover',True):return None
            with Telemetry(self.store.root).stage('capa',candidate=candidate_id):
                from . import multiformat
                aspects=tuple(dict.fromkeys(('9x16','1x1','4x5')+tuple(f for f in multiformat.selected(candidate.get('profile'),(candidate.get('data') or {}).get('project')) if f=='16x9')))
                report=cover.make_for_export(video,candidate,self.store.root,aspects=aspects)
            if report:self.store.set_data(candidate_id,'cover',dict(files=report['files'],template=report['template'],weak=report['weak'],chosen=report['chosen']['time']))
            return report
        except Exception as exc:
            self.store.event('capa','Não consegui montar a capa: '+str(exc)[:120]);return None

    def _ai_free_for(self,candidate_id):
        try:return ai_free(self.store.streamer(self.store.candidate(candidate_id)['streamer'])['profile'])
        except Exception:return False

    @staticmethod
    def planned_freezes(plan_file):
        """Congelamentos pedidos no editor (quadro parado de propósito), em segundos do vídeo final."""
        try:
            from . import plan as planlib
            data=json.loads(Path(plan_file).read_text(encoding='utf-8'))
            return [(planlib.seconds(s['out_start']),planlib.seconds(s['out_end'])) for s in data.get('segments',[]) if s.get('kind')=='freeze']
        except Exception:return []

    def deliver_one(self,candidate_id,video=None):
        """Copia o clipe pronto para a pasta de entrega do streamer (se houver). Nunca derruba a exportação."""
        try:
            candidate=self.store.candidate(candidate_id)
            profile=self.store.streamer(candidate['streamer'])['profile']
            folder=profile.get('delivery_folder') or ''
            if not folder:return None
            video=video or candidate.get('export_path')
            if not video:return None
            result=delivery.deliver(folder,candidate,video,self.store.streamer(candidate['streamer'])['name'])
            self.store.set_delivery(candidate_id,result)
            self.store.event('entrega' if result['status']=='ok' else 'entrega pendente',candidate_id+' · '+result['status'])
            return result
        except Exception as exc:
            try:self.store.set_delivery(candidate_id,dict(status='erro',error=str(exc)[:300],at=round(time.time())))
            except Exception:pass
            return None

    def deliver_ready(self,streamer_id):
        """Entrega os cortes já prontos que ainda não foram copiados. Retorna quantos foram tentados."""
        rows=self.store.rows("SELECT id,data,export_path FROM candidates WHERE streamer=? AND status='done' AND export_path!=''",(streamer_id,))
        n=0
        for row in rows:
            try:state=(json.loads(row['data']).get('delivery') or {}).get('status')
            except ValueError:state=None
            if state=='ok':continue
            if self.deliver_one(row['id'],row['export_path']) is not None:n+=1
        return n

    def review_export(self,candidate_id,video,report):
        """Revisão ciente do plano (técnica + regras editoriais). Nunca derruba a exportação; grava revisao.json."""
        try:
            plan_file=video.parent/'plano.json'
            if not plan_file.exists():return report
            candidate=self.store.candidate(candidate_id);data=candidate['data']
            plan=json.loads(plan_file.read_text(encoding='utf-8'))
            project=data.get('project') or {}
            words=review.words_for_plan(data.get('transcript_segments'),candidate['start'],candidate['end'],candidate['parts'])
            issues=review.technical(plan,qc_report=report,plan_delta_frames=_manifest_value(video,'plan_delta_frames'))
            issues+=review.editorial(plan,function_map=data.get('function_map'),project=project,words=words,cuts=project.get('cuts') or [],
                                     clip_start=float(candidate['start']))
            result=review.report(issues)
            (video.parent/'revisao.json').write_text(json.dumps(result,ensure_ascii=False,indent=1),encoding='utf-8')
            report=dict(report,review=dict(veredito=result['veredito'],resumo=result['resumo'],bloqueia_pronto=result['bloqueia_pronto'],
                                           nao_verificado=result['nao_verificado'],problemas=len(result['problemas'])))
            if result['bloqueia_pronto'] and report.get('level')=='ok':report['level']='atencao'
        except Exception as exc:
            report=dict(report,review=dict(veredito='indisponivel',resumo='A revisão automática falhou: '+str(exc)[:120],bloqueia_pronto=False,
                                           nao_verificado=list(review.UNVERIFIED),problemas=0))
        return report

    def do_render(self,candidate_id,preview):
        """Uma tarefa de render com progresso real: cada execução tem identificador próprio e o quadro guarda só a mais recente."""
        row=self.store.candidate(candidate_id)
        try:label=str(row['data'].get('moment_label') or row['data'].get('title') or candidate_id)[:60]
        except Exception:label=candidate_id
        task=self.board.start(candidate_id,'previa' if preview else 'exportacao',label)
        try:
            with progress.scope(task):
                self._do_render(candidate_id,preview)
        except media.LowSpace:
            task.requeue('Sem espaço livre no disco; tenta de novo quando houver.')
            raise
        except BaseException as exc:
            task.finish('falhou',f'{type(exc).__name__}: {exc}');raise
        after=self.store.candidate(candidate_id)
        field=after['preview_status'] if preview else after['status']
        if task.state=='cancelado':return
        if field in ('done','ready'):task.finish('concluido')
        elif field in ('error','duplicate'):task.finish('falhou',after.get('error') or 'O corte não pôde ser gerado.')
        else:self.board.discard(task)         # a versão mudou ou o corte saiu da fila antes de começar: não há o que mostrar

    def renders(self):
        return self.board.snapshot()

    def cancel_render(self,candidate_id):
        """Cancela a execução ATUAL do corte (se estiver rodando) ou tira da fila (se ainda não começou). As escolhas ficam salvas."""
        if self.board.cancel(candidate_id):return 'cancelando'
        with self.store.connect(True) as c:
            done=c.execute("UPDATE candidates SET status='pending' WHERE id=? AND status='approved'",(candidate_id,)).rowcount
            done+=c.execute("UPDATE candidates SET preview_status='' WHERE id=? AND preview_status='queued'",(candidate_id,)).rowcount
        return 'removido da fila' if done else 'nada para cancelar'

    def _do_render(self,candidate_id,preview):
        candidate=self.store.candidate(candidate_id)
        try:   # o kit de marca vale o do streamer AGORA, não o do dia em que o corte foi proposto
            current_profile=self.store.streamer(candidate['streamer'])['profile']
            # marca, webcam e áreas a borrar valem as do streamer AGORA: marcar a webcam depois de o corte existir tem que destravar a prévia
            candidate['profile']=dict(candidate['profile'],brand=current_profile.get('brand'),camera_rect=current_profile.get('camera_rect'),
                                       blur_regions=current_profile.get('blur_regions') or [])
            # opcionais novos: só entram no perfil do corte quando ligados (cortes antigos mantêm a mesma assinatura de exportação)
            for key in ('track_roi','export_formats','export_srt'):
                if current_profile.get(key):candidate['profile'][key]=current_profile[key]
                else:candidate['profile'].pop(key,None)
            if current_profile.get('motion_level','off')!='off':
                candidate['profile']['motion_level']=current_profile['motion_level']
                candidate['data']=dict(candidate['data'],motion_context=dict(streamer=self.store.streamer(candidate['streamer'])['name'],
                                                                          label=str(candidate['data'].get('moment_label') or '')[:50]))
            else:
                candidate['profile'].pop('motion_level',None)
        except Exception:pass
        try:   # memória editorial: vocabulário do canal e registro de quais memórias orientaram este render
            memory=self.store.memory
            terms=', '.join(memory.vocabulary(candidate['streamer']))
            if terms:candidate['profile']=dict(candidate['profile'],memory_terms=terms)
            hits=memory.retrieve(dict(job_id=candidate_id,streamer=candidate['streamer'],task='corte',
                                      text=' '.join([candidate['data'].get('moment_type',''),str(candidate['data'].get('transcript',''))[:200]])),limit=5)
            candidate['data']=dict(candidate['data'],memory_refs=[dict(id=h['id'],version=h['version'],why=h['why']) for h in hits])
        except Exception:pass
        if not preview and candidate['profile'].get('second_pass','off')!='off':
            # Segunda passagem de legenda só nos cortes aprovados, antes de exportar (uma vez por versão de limites).
            state=candidate['data'].get('refine',{})
            # Se o modelo preciso acabou de falhar (sem internet para baixar, por exemplo), não tenta de novo em cada corte.
            if state.get('status') not in ('done','error') and time.time()-getattr(self,'refine_failed_at',0)>600:
                # O corte é relido do banco depois da revisão; marca, webcam, áreas a borrar e memória
                # do streamer (que valem os de AGORA) têm que sobreviver a essa releitura.
                keep_profile={k:candidate['profile'][k] for k in ('brand','camera_rect','blur_regions','memory_terms') if k in candidate['profile']}
                keep_refs=candidate['data'].get('memory_refs')
                try:self.do_refine(candidate_id,candidate['profile']['second_pass'])
                except media.LowSpace:raise
                candidate=self.store.candidate(candidate_id)
                candidate['profile']=dict(candidate['profile'],**keep_profile)
                if keep_refs is not None:candidate['data']=dict(candidate['data'],memory_refs=keep_refs)
        session=self.store.session(candidate['session'])
        self.apply_auto_title(candidate,session)
        try:reserve=float(self.store.streamer(candidate['streamer'])['profile']['min_free_gb'])   # vale a reserva de AGORA, não a do dia da sugestão
        except Exception:reserve=candidate['profile']['min_free_gb']
        media.require_space(self.store.root,reserve,200*1024**2)
        try:
            timeline=build_timeline(self.store.segments(session['id']))
            current_parts=plan(timeline,candidate['start'],candidate['end'],candidate['group_id'])
            if current_parts!=candidate['parts']:raise ValueError('A origem mudou desde a revisão. Confira a sessão novamente.')
            for part in current_parts:
                file=Path(part['path'])
                if not file.is_file():
                    raise ValueError(f'O arquivo original não está mais em "{file}". Se você o moveu ou renomeou, volte para a sessão e use "Religar original"; ele precisa ser idêntico ao analisado.')
                if media.sha_file_cached(file)!=part['sha']:
                    raise ValueError(f'O arquivo "{file.name}" foi alterado depois da análise (outro conteúdo, tamanho ou regravação). '
                                     'Para não gerar um corte de um vídeo diferente do revisado, a prévia e a exportação foram bloqueadas. '
                                     'Importe o arquivo atual como uma nova sessão ou restaure o original.')
        except Exception as exc:
            with self.store.connect(True) as c:
                c.execute("UPDATE candidates SET "+("preview_status='error'" if preview else "status='error'")+",error=? WHERE id=? AND version=?",
                          (str(exc),candidate_id,candidate['version']))
            return
        with self.store.connect(True) as c:
            current=c.execute('SELECT * FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if current['version']!=candidate['version'] or (current['preview_status']!='queued' if preview else current['status']!='approved'):
                return
            if not preview:
                # Variações de A/B e partes de série existem justamente sobre o mesmo momento: não contam como duplicata.
                variant=bool(candidate['data'].get('variant_of') or candidate['data'].get('series') or candidate['data'].get('ab'))
                duplicate=None if variant else self.store.duplicate(c,candidate['streamer'],candidate['session'],candidate['group_id'],
                    candidate['start'],candidate['end'],candidate['parts'],exclude=candidate_id,
                    statuses=('exporting','done'),data=candidate['data'])
                if duplicate:
                    c.execute("UPDATE candidates SET status='duplicate',error=? WHERE id=?",
                              ('Momento já exportado: '+duplicate['id'],candidate_id));return
            c.execute("UPDATE candidates SET "+("preview_status='working'" if preview else "status='exporting'")+" WHERE id=?",(candidate_id,))
        self.progress('Gerando prévia' if preview else 'Exportando aprovado',
                      self.label(session)+' · um trabalho por vez para poupar CPU')
        try:
            render_started=time.time()
            with Telemetry(self.store.root).stage('previa' if preview else 'exportacao',candidate=candidate_id):
                result=media.render(candidate,candidate['data'].get('transcript_segments',shifted_transcript(timeline)),session['path'],
                                    'draft' if preview else False,root=self.store.root)
            with self.store.connect(True) as c:
                if preview:
                    done=c.execute("UPDATE candidates SET preview_status='ready',preview_path=?,preview_version=? WHERE id=? AND version=?",
                              (str(result),candidate['version'],candidate_id,candidate['version']))
                    if done.rowcount:
                        # Guarda o mapa de tempo desta prévia: se o corte for editado depois, ela continua navegável
                        # (desatualizada) com o relógio certo até a próxima ficar pronta.
                        try:
                            from .editing import timing_for
                            row=c.execute('SELECT data FROM candidates WHERE id=? AND version=?',(candidate_id,candidate['version'])).fetchone()
                            if row:
                                fresh=json.loads(row['data']);fresh['preview_timing']=timing_for(candidate)
                                c.execute('UPDATE candidates SET data=? WHERE id=? AND version=?',(json.dumps(fresh),candidate_id,candidate['version']))
                        except Exception:pass
                else:
                    c.execute("UPDATE candidates SET status='done',export_path=?,error='' WHERE id=?",(str(result),candidate_id))
            if not preview:
                try:self.store.set_render_stats(candidate_id,time.time()-render_started,candidate['end']-candidate['start'])
                except Exception:pass
            if not preview and self.license is not None:
                self.license.record('clipe',1,f"clip:{candidate_id}:{candidate['version']}")
            if not preview:
                progress.phase('Criando a capa',96,97,'finalizando')
                self.make_cover(candidate_id,result)
                progress.phase('Conferindo a qualidade do arquivo',97,99,'finalizando')
                with Telemetry(self.store.root).stage('qualidade',candidate=candidate_id):self.run_qc(candidate_id,result)
                progress.phase('Entregando os arquivos',99,99.5,'finalizando')
                self.deliver_one(candidate_id,result)
            self.store.event('prévia' if preview else 'exportado',session['name']+' · '+candidate_id)
        except media.LowSpace:
            with self.store.connect(True) as c:
                c.execute("UPDATE candidates SET "+("preview_status='queued'" if preview else "status='approved'")+" WHERE id=? AND version=?",(candidate_id,candidate['version']))
            raise
        except progress.Cancelled:
            with self.store.connect(True) as c:
                c.execute("UPDATE candidates SET "+("preview_status='error'" if preview else "status='error'")+",error=? WHERE id=? AND version=?",
                          ('Cancelado por você. As escolhas do corte foram mantidas; use "Tentar novamente" quando quiser.',candidate_id,candidate['version']))
            self.store.event('render cancelado',session['name']+' · '+candidate_id)
            task=progress.current()
            if task:task.finish('cancelado')
        except Exception as exc:
            with self.store.connect(True) as c:
                c.execute("UPDATE candidates SET "+("preview_status='error'" if preview else "status='error'")+",error=? WHERE id=? AND version=?",
                          (str(exc)[:2000],candidate_id,candidate['version']))
            self.store.event('erro de exportação',str(exc))
