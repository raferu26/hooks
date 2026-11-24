"""Estado persistente e transações de revisão/exportação."""
from contextlib import contextmanager
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid

DEFAULT_PROFILE = dict(camera_rect=None, track_roi=None, auto_replay='off', motion_level='off', export_formats=[], export_srt=False, language=None, model='base', priority='equilibrio',
                       threads=3, font_size=46, caption_margin=340, caption_color='00E8FF',
                       capture_quality='1440p', min_free_gb=3,editorial_style='clean',
                       clip_format='short',permission_policy='review',speaker_mode='name_symbol_color',
                       translation_review=True,credit_note='',content_mode='live',reframe_mode='conservative',
                       vocabulary='',behavior_sensitivity='balanced',auto_zoom=True,auto_silence=True,
                       auto_repetition=False,auto_reframe=True,auto_sfx=False,auto_overlay=False,
                       auto_music=False,music_authorized=False,music_volume=.08,music_path='',
                       sfx_path='',overlay_path='',overlay_position='center',caption_style='auto',auto_grade=True,auto_cadence=True,
                       video_encoder='cpu',whisper_device='auto',hashtags='',ollama=False,ollama_model='',ollama_url='',
                       learned_terms='',second_pass='small',brand=None,quality_mode='equilibrado',corrections='',blur_regions=[],delivery_folder='',
                       ai_mode='padrao',silence_policy='pausas_longas',free_heuristic=True,cover=True,cover_template='destaque',voice_preset='off',auto_color='off',lut='',lut_strength=1.0,cut_fade='off',slow_interp='off',stabilize='off',title_template='')
from . import atomic,buildinfo
from .captions import STYLE_NAMES
if buildinfo.is_sem_ia():   # pacote experimental sem IA: perfis NOVOS já nascem sem modelos (perfis existentes não são tocados)
    DEFAULT_PROFILE.update(ai_mode='sem_ia',second_pass='off',ollama=False)
ACTIVE = ('pending', 'approved', 'exporting', 'done', 'error')
# Motivos de rejeição de um clique. O código fica gravado no corte; o texto é o que a pessoa vê.
REJECT_REASONS = {
    'fraco':'Momento fraco','sem_contexto':'Sem contexto','comeco_ruim':'Começo ruim','fim_ruim':'Final ruim',
    'repetido':'Repetido','legenda_errada':'Legenda errada','imagem_ruim':'Imagem ou áudio ruim',
    'sensivel':'Conteúdo sensível','outro':'Outro motivo'}


def uid():
    return uuid.uuid4().hex[:16]


def folder_name(name):
    name = str(name).strip()
    if not name or len(name) > 60 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(('.', ' ')):
        raise ValueError('Use um nome de 1 a 60 letras/números, sem barras ou caracteres especiais do Windows.')
    if name in ('.', '..') or name.split('.')[0].upper() in {
            'CON','PRN','AUX','NUL', *['COM'+str(i) for i in range(1,10)], *['LPT'+str(i) for i in range(1,10)]}:
        raise ValueError('Este nome é reservado pelo Windows. Escolha outro.')
    if name.startswith('.'):
        raise ValueError('O nome não pode começar com ponto.')
    return name.upper()


MAX_BLUR_REGIONS = 6


def blur_regions_checked(value):
    """Áreas a borrar (frações 0–1 da imagem original). Valor inválido é erro explícito: borrão perdido vaza privacidade."""
    if value in (None,''):return []
    if not isinstance(value,list):raise ValueError('As áreas a borrar estão em formato inválido. Marque de novo.')
    if len(value)>MAX_BLUR_REGIONS:raise ValueError(f'Use no máximo {MAX_BLUR_REGIONS} áreas a borrar.')
    out=[]
    for item in value:
        try:x,y,w,h=[float(item[k]) for k in ('x','y','w','h')]
        except (KeyError,TypeError,ValueError):raise ValueError('Uma das áreas a borrar está incompleta. Marque de novo.')
        if not all(math.isfinite(v) for v in (x,y,w,h)) or not (
                x>=0 and y>=0 and w>=.02 and h>=.02 and x+w<=1.00001 and y+h<=1.00001):
            raise ValueError('Cada área a borrar precisa estar dentro da imagem e ter pelo menos 2% de largura e altura.')
        label=' '.join(str(item.get('label') or '').split())[:40]
        out.append(dict(x=round(x,5),y=round(y,5),w=round(min(w,1-x),5),h=round(min(h,1-y),5),label=label))
    return out


def profile_checked(value):
    p = deepcopy(DEFAULT_PROFILE)
    p.update({k:v for k,v in value.items() if k in p})
    for key,lo,hi in [('threads',1,4),('font_size',24,68),('caption_margin',130,500)]:
        p[key] = int(p[key])
        if not lo <= p[key] <= hi:
            raise ValueError(f'Valor fora do intervalo para {key}: {lo} a {hi}.')
    p['min_free_gb'] = float(p['min_free_gb'])
    if not math.isfinite(p['min_free_gb']) or not .5 <= p['min_free_gb'] <= 100:
        raise ValueError('A reserva de disco deve ficar entre 0,5 e 100 GB.')
    priorities=('equilibrio','humor','reacoes','jogadas','surpresa','tensao','opiniao',
                'historia','educacional','emocional')
    if p['model'] not in ('tiny','base','small','medium','turbo') or p['priority'] not in priorities:
        raise ValueError('Modelo ou prioridade inválidos.')
    if p['language'] not in (None, 'pt', 'en', 'es'):
        raise ValueError('Idioma inválido.')
    if p['editorial_style'] not in ('clean','funny','gameplay','reaction','podcast','interview','hype','creative',
                                    'storytelling','educational','commentary','meme','cinematic'):
        raise ValueError('Estilo editorial inválido.')
    if p['clip_format'] not in ('short','narrative'):
        raise ValueError('Formato de clipe inválido.')
    if p['permission_policy'] not in ('allowed','review','blocked'):
        raise ValueError('Política editorial inválida.')
    if p['speaker_mode'] not in ('name_symbol_color','name_color'):
        raise ValueError('Identificação de falantes inválida.')
    if p['ai_mode'] not in ('padrao','sem_ia'):
        raise ValueError('Modo de análise inválido.')
    if p.get('auto_replay','off') not in ('off','normal','lento'):
        raise ValueError('Replay automático inválido.')
    if p['silence_policy'] not in ('bordas','pausas_longas','dinamica'):
        raise ValueError('Política de pausas inválida.')
    p['free_heuristic']=bool(p['free_heuristic'])
    p['cover']=bool(p['cover'])
    from . import titledata
    p['title_template']=titledata.validate(p['title_template'])
    if p['stabilize'] not in ('off','leve','forte'):
        raise ValueError('Estabilização inválida.')
    if p['slow_interp'] not in ('off','mistura','movimento'):
        raise ValueError('Interpolação de câmera lenta inválida.')
    if p['cut_fade'] not in ('off','suave','media'):
        raise ValueError('Fade das emendas inválido.')
    if p['auto_color'] not in ('off','histograma'):
        raise ValueError('Modo de cor automática inválido.')
    p['lut']=Path(str(p['lut'] or '')).name if p['lut'] else ''
    if p['lut'] and not p['lut'].lower().endswith('.cube'):
        raise ValueError('A LUT precisa ser um arquivo .cube.')
    p['lut_strength']=max(.1,min(1.0,float(p['lut_strength'])))
    if p['voice_preset'] not in ('off','natural','forte'):
        raise ValueError('Predefinição de voz inválida.')
    if p['cover_template'] not in ('limpo','faixa','destaque'):
        raise ValueError('Modelo de capa inválido.')
    if p['content_mode'] not in ('live','video'):
        raise ValueError('Modo de conteúdo inválido.')
    if p['reframe_mode'] not in ('conservative','dynamic','speaker','rastreio'):
        raise ValueError('Modo de enquadramento inválido.')
    if p['behavior_sensitivity'] not in ('precise','balanced','sensitive'):
        raise ValueError('Sensibilidade comportamental inválida.')
    if p['overlay_position'] not in ('top','center','bottom'):
        raise ValueError('Posição da imagem inválida.')
    if p['caption_style'] not in STYLE_NAMES:
        raise ValueError('Estilo de legenda inválido.')
    from . import hardware, ollama
    if p['video_encoder'] not in hardware.CHOICES:
        raise ValueError('Codificador de vídeo inválido.')
    if p['whisper_device'] not in ('auto','cpu','cuda'):
        raise ValueError('Processador da transcrição inválido.')
    p['hashtags']=' '.join(str(p['hashtags']).replace('\x00',' ').split())[:200]
    if p['second_pass'] not in ('off','small','medium','turbo'):
        raise ValueError('Modelo da segunda passagem inválido.')
    from .telemetry import MODES as _modes
    if p['quality_mode'] not in _modes:
        raise ValueError('Modo de qualidade inválido.')
    p['learned_terms']=' '.join(str(p['learned_terms']).replace('\x00',' ').split())[:600]
    from . import brand as _brand
    p['brand']=_brand.clean(p.get('brand'))
    p['ollama']=bool(p['ollama'])
    p['ollama_model']=' '.join(str(p['ollama_model']).split())[:80]
    p['ollama_url']=ollama.checked_url(p['ollama_url']) if p['ollama_url'] else ''
    p['translation_review']=bool(p['translation_review'])
    for key in ('auto_zoom','auto_silence','auto_repetition','auto_reframe','auto_sfx','auto_overlay',
                'auto_music','music_authorized','auto_grade','auto_cadence'):
        p[key]=bool(p[key])
    p['music_volume']=float(p['music_volume'])
    if not math.isfinite(p['music_volume']) or not .02<=p['music_volume']<=.3:
        raise ValueError('O volume da música deve ficar entre 2% e 30%.')
    allowed={'music_path':('.mp3','.wav','.m4a','.aac','.flac','.ogg'),
             'sfx_path':('.mp3','.wav','.m4a','.aac','.flac','.ogg'),
             'overlay_path':('.png','.jpg','.jpeg','.webp')}
    for key,extensions in allowed.items():
        path=' '.join(str(p[key]).replace('\x00',' ').split())[:1000]
        if path and Path(path).suffix.lower() not in extensions:
            raise ValueError(f'Formato de arquivo inválido para {key}.')
        p[key]=path
    if p['auto_music'] and (not p['music_authorized'] or not p['music_path']):
        raise ValueError('Para usar música, selecione o arquivo e confirme que o uso está autorizado.')
    p['credit_note']=' '.join(str(p['credit_note']).split())[:500]
    vocabulary=' '.join(str(p['vocabulary']).replace('\x00',' ').split())
    if len(vocabulary)>800:
        raise ValueError('O dicionário do streamer pode ter no máximo 800 caracteres.')
    p['vocabulary']=vocabulary
    lines=[' '.join(x.split()) for x in str(p.get('corrections') or '').replace('\x00',' ').splitlines()]
    p['corrections']='\n'.join(x for x in lines if x)[:3000]
    if p['capture_quality'] not in ('480p','720p','720p60','1080p','1080p60',
                                     '1440p','1440p60','best'):
        raise ValueError('Qualidade de captura inválida.')
    if not re.fullmatch('[0-9A-Fa-f]{6}', str(p['caption_color'])):
        raise ValueError('Cor inválida. Use seis dígitos no formato ASS BGR.')
    p['blur_regions']=blur_regions_checked(p.get('blur_regions'))
    from .delivery import valid_folder_text
    p['delivery_folder']=valid_folder_text(p.get('delivery_folder'))
    from . import track, multiformat
    p['track_roi']=track.valid_roi(p.get('track_roi'))
    p['export_formats']=multiformat.clean_formats(p.get('export_formats'))
    p['export_srt']=bool(p.get('export_srt'))
    from . import graphics2d
    if p.get('motion_level','off') not in graphics2d.LEVELS:
        raise ValueError('Nível de gráficos animados inválido.')
    rect = p['camera_rect']
    if rect is not None:
        if len(rect) != 4:
            raise ValueError('Marque a webcam novamente.')
        x,y,w,h = [float(v) for v in rect]
        if not all(math.isfinite(v) for v in (x,y,w,h)) or not (
                x>=0 and y>=0 and w>=.02 and h>=.02 and x+w<=1.00001 and y+h<=1.00001):
            raise ValueError('A webcam precisa estar dentro da imagem.')
        p['camera_rect'] = [round(v,6) for v in (x,y,w,h)]
    return p


def habits_terms(profile):
    return ', '.join(x for x in (profile.get('vocabulary',''),profile.get('learned_terms','')) if x)


def analysis_key(profile):
    value={k:profile.get(k) for k in ('model','language','camera_rect','vocabulary','behavior_sensitivity')}
    if profile.get('ai_mode','padrao')!='padrao':value['ai_mode']=profile['ai_mode']   # perfis antigos (sem o campo) mantêm a mesma chave
    if value['camera_rect'] is not None:
        value['camera_rect']=[round(float(v),6) for v in value['camera_rect']]
    return json.dumps(value,sort_keys=True)


def selection_key(profile):
    """Campos que mudam quais momentos o agente escolhe, sem refazer a transcrição."""
    return json.dumps({k:profile.get(k) for k in ('priority','editorial_style','clip_format')},sort_keys=True)


def overlap_ratio(a, b):
    overlap = max(0, min(a['end'],b['end'])-max(a['start'],b['start']))
    return overlap/max(.001,min(a['end']-a['start'],b['end']-b['start']))


def same_content(a, b):
    """Sobreposição nos mesmos bytes de mídia, inclusive em outra sessão/importação."""
    overlap = 0.0
    for x in a:
        for y in b:
            if x.get('sha') and x['sha'] == y.get('sha'):
                overlap += max(0,min(x['out'],y['out'])-max(x['in'],y['in']))
    return overlap/max(.001,min(sum(x['out']-x['in'] for x in a),sum(x['out']-x['in'] for x in b))) >= .55


def fingerprint_of(data):
    """Impressão visual de 16 hexadecimais guardada junto da sugestão (ou '' quando não existe)."""
    value=(data or {}).get('visual_fingerprint')
    if isinstance(value,str) and len(value)==16:
        try:int(value,16);return value
        except ValueError:pass
    return ''


def _hamming(a,b):
    try:return (int(a,16)^int(b,16)).bit_count()
    except (TypeError,ValueError):return 99


def same_recoded_moment(a, b, duration_a, duration_b):
    """Combina imagem e fala para não confundir bordões ou telas estáticas."""
    if not a or not b:
        return False
    fa,fb=a.get('visual_fingerprint'),b.get('visual_fingerprint')
    if not (isinstance(fa,str) and isinstance(fb,str) and len(fa)==len(fb)==16):
        return False
    try:
        visual_distance=(int(fa,16)^int(fb,16)).bit_count()
    except ValueError:
        return False
    ta=set(re.findall(r'\w+',str(a.get('transcript','')).casefold()))
    tb=set(re.findall(r'\w+',str(b.get('transcript','')).casefold()))
    similarity=len(ta&tb)/max(1,len(ta|tb))
    duration_ratio=min(duration_a,duration_b)/max(.001,max(duration_a,duration_b))
    return visual_distance <= 7 and len(ta&tb) >= 5 and similarity >= .72 and duration_ratio >= .72


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'liveclips_v8.sqlite3'
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS streamers(id TEXT PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE,profile TEXT);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,streamer TEXT,name TEXT,source TEXT,
                path TEXT,closed INTEGER DEFAULT 1,status TEXT DEFAULT 'idle',error TEXT DEFAULT '',enabled INTEGER DEFAULT 1,
                frame_status TEXT DEFAULT '',frame_path TEXT DEFAULT '',frame_error TEXT DEFAULT '',created REAL);
            CREATE TABLE IF NOT EXISTS segments(session TEXT,seq INTEGER,path TEXT,sha TEXT,duration REAL,
                signature TEXT,size INTEGER,mtime INTEGER,status TEXT DEFAULT 'new',data TEXT DEFAULT '{}',
                PRIMARY KEY(session,seq));
            CREATE TABLE IF NOT EXISTS centers(session TEXT,seq INTEGER,context_key TEXT,PRIMARY KEY(session,seq));
            CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,session TEXT,streamer TEXT,start REAL,end REAL,
                group_id TEXT,score REAL,status TEXT,data TEXT,parts TEXT,profile TEXT,version INTEGER DEFAULT 1,
                manual INTEGER DEFAULT 0,preview_status TEXT DEFAULT '',preview_path TEXT DEFAULT '',
                preview_version INTEGER DEFAULT 0,export_path TEXT DEFAULT '',error TEXT DEFAULT '',created REAL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,created REAL,kind TEXT,message TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            INSERT OR IGNORE INTO settings VALUES('paused','true');
            ''')
        with self.connect(True) as c:self._migrate(c)
        self._migrate_profiles()
        self.has_json=self._probe_json()
        self.recover()

    @staticmethod
    def _migrate(c):
        """Acrescenta colunas e índices novos sem perder o que já existe. Cada passo pode ser repetido sem efeito."""
        columns={r[1] for r in c.execute('PRAGMA table_info(candidates)')}
        if 'reason' not in columns:
            c.execute("ALTER TABLE candidates ADD COLUMN reason TEXT DEFAULT ''")
        if 'fingerprint' not in columns:
            c.execute("ALTER TABLE candidates ADD COLUMN fingerprint TEXT DEFAULT ''")
        c.execute('CREATE INDEX IF NOT EXISTS candidates_streamer ON candidates(streamer,status)')
        c.execute('CREATE INDEX IF NOT EXISTS candidates_session ON candidates(session,group_id)')
        pending=c.execute("SELECT id,data FROM candidates WHERE fingerprint='' AND data LIKE '%visual_fingerprint%'").fetchall()
        for row in pending:
            try:value=fingerprint_of(json.loads(row[1]))
            except (ValueError,TypeError):continue
            if value:c.execute('UPDATE candidates SET fingerprint=? WHERE id=?',(value,row[0]))

    def _migrate_profiles(self):
        """0.17: a legenda precisa (2ª passagem) passa a ser o padrão. Perfis que estavam em 'Desligada' só por ser o padrão
        antigo ligam uma vez; quem quiser desligar escolhe 'Desligada' de novo e a escolha é respeitada."""
        if self.setting('migracao_0_17_legenda_precisa'):return
        with self.connect(True) as c:
            for row in c.execute('SELECT id,profile FROM streamers').fetchall():
                try:profile=json.loads(row['profile'])
                except (ValueError,TypeError):continue
                if profile.get('second_pass','off')=='off':
                    profile['second_pass']='small'
                    c.execute('UPDATE streamers SET profile=? WHERE id=?',(json.dumps(profile),row['id']))
        self.setting('migracao_0_17_legenda_precisa',True)

    def _probe_json(self):
        """json_remove/json_extract existem na maioria dos SQLite recentes; sem eles o painel usa o caminho lento."""
        try:
            with self.connect() as c:return c.execute("SELECT json_remove('{\"a\":1}','$.a')").fetchone()[0]=='{}'
        except sqlite3.Error:return False

    LIST_COLUMNS='id,session,streamer,start,end,group_id,score,status,version,manual,preview_status,preview_path,preview_version,export_path,error,created,reason'

    def review_stats(self):
        """Por sessão: quantos cortes foram aceitos, rejeitados e o que falta revisar, com os motivos de rejeição.
        Taxa de acerto = aceitos ÷ (aceitos + rejeitados); só existe depois de pelo menos uma decisão."""
        stats={}
        for r in self.rows("SELECT session,status,COUNT(*) AS n FROM candidates WHERE status IN "
                           "('pending','approved','exporting','done','rejected','error') GROUP BY session,status"):
            item=stats.setdefault(r['session'],dict(accepted=0,rejected=0,pending=0,reasons={}))
            if r['status']=='rejected':item['rejected']+=r['n']
            elif r['status']=='pending':item['pending']+=r['n']
            elif r['status']!='error':item['accepted']+=r['n']
        for r in self.rows("SELECT session,reason,COUNT(*) AS n FROM candidates WHERE status='rejected' AND reason!='' GROUP BY session,reason"):
            if r['session'] in stats:stats[r['session']]['reasons'][r['reason']]=r['n']
        for item in stats.values():
            decided=item['accepted']+item['rejected']
            item['rate']=round(item['accepted']/decided,3) if decided else None
        return stats

    def panel_candidates(self,limit=500):
        """Sugestões para o painel, sem as partes pesadas (fala palavra a palavra, perfil copiado, repasse)."""
        if self.has_json:
            rows=self.rows(f"SELECT {self.LIST_COLUMNS},json_extract(data,'$.intelligence.dimensoes.estado') AS estado_contexto,"
                           "json_remove(data,'$.transcript_segments','$.profile','$.intelligence','$.handoff') AS data "
                           "FROM candidates WHERE status NOT IN ('replaced') ORDER BY created DESC LIMIT ?",(limit,))
            for row in rows:
                row['data']=json.loads(row['data']);estado=row.pop('estado_contexto')
                if estado is not None:row['data']['estado_contexto']=estado
            return rows
        rows=self.rows("SELECT * FROM candidates WHERE status NOT IN ('replaced') ORDER BY created DESC LIMIT ?",(limit,))
        for row in rows:
            self.decode(row);row.pop('parts',None);row.pop('profile',None);row.pop('fingerprint',None)
            row['data'].pop('transcript_segments',None);row['data'].pop('profile',None);row['data'].pop('handoff',None)
            intel=row['data'].pop('intelligence',None) or {}
            if intel.get('dimensoes'):row['data']['estado_contexto']=intel['dimensoes'].get('estado')
        return rows

    @property
    def memory(self):
        """Memória editorial persistente (arquivo próprio na pasta de dados), com os fundamentos do dossiê já carregados."""
        if getattr(self,'_memory',None) is None:
            from . import curriculum
            from .memory import Memory
            self._memory=Memory(self.root)
            curriculum.seed(self._memory)
        return self._memory

    @contextmanager
    def connect(self, write=False):
        c = sqlite3.connect(self.db, timeout=20)
        c.row_factory = sqlite3.Row
        c.create_function('hamming',2,_hamming,deterministic=True)
        try:
            if write:
                c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def rows(self, sql, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql,args)]

    def event(self, kind, message):
        with self.connect(True) as c:
            c.execute('INSERT INTO events(created,kind,message) VALUES(?,?,?)',(time.time(),kind,str(message)[:2000]))

    def setting(self, key, value=None):
        with self.connect(value is not None) as c:
            if value is not None:
                c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))
                return value
            row = c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else None

    def streamer(self, streamer_id):
        rows=self.rows('SELECT * FROM streamers WHERE id=?',(streamer_id,))
        if not rows: raise ValueError('Streamer não encontrado.')
        s=rows[0];s['profile']=json.loads(s['profile']);return s

    def create_streamer(self, name):
        name=folder_name(name)
        streamer_id=uid()
        path=self.root/name
        # Não toma posse de uma pasta antiga ou externa por acidente.
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError('Essa pasta já existe sem um perfil V8. Escolha outro nome para preservá-la.')
        with self.connect(True) as c:
            if c.execute('SELECT id FROM streamers WHERE name=? COLLATE NOCASE',(name,)).fetchone():
                raise ValueError('Este streamer já está cadastrado.')
            path.mkdir(exist_ok=True)
            c.execute('INSERT INTO streamers VALUES(?,?,?)',(streamer_id,name,json.dumps(DEFAULT_PROFILE)))
        self.save_profile(streamer_id,DEFAULT_PROFILE)
        return streamer_id

    def save_profile(self, streamer_id, value):
        p=profile_checked(value)
        streamer=self.streamer(streamer_id)
        analysis_changed=analysis_key(p)!=analysis_key(streamer['profile'])
        selection_changed=selection_key(p)!=selection_key(streamer['profile'])
        replaced=0
        with self.connect(True) as c:
            c.execute('UPDATE streamers SET profile=? WHERE id=?',(json.dumps(p),streamer_id))
            if analysis_changed:
                c.execute("UPDATE segments SET status='new',data='{}' WHERE session IN (SELECT id FROM sessions WHERE streamer=?)",(streamer_id,))
                c.execute('DELETE FROM centers WHERE session IN (SELECT id FROM sessions WHERE streamer=?)',(streamer_id,))
                c.execute("UPDATE candidates SET status='replaced' WHERE streamer=? AND status='pending' AND manual=0",(streamer_id,))
                replaced=c.execute('SELECT changes()').fetchone()[0]
            elif selection_changed:
                c.execute('DELETE FROM centers WHERE session IN (SELECT id FROM sessions WHERE streamer=?)',(streamer_id,))
                c.execute("UPDATE candidates SET status='replaced' WHERE streamer=? AND status='pending' AND manual=0",(streamer_id,))
                replaced=c.execute('SELECT changes()').fetchone()[0]
        if analysis_changed or selection_changed:
            self.mark_regeneration(streamer_id,replaced,'análise e seleção' if analysis_changed else 'seleção editorial')
        dest=self.root/streamer['name']/'perfil_v8.json'
        tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(dest)
        return p

    def mark_regeneration(self,streamer_id,replaced,reason):
        state=self.setting('regeneration') or {}
        state[streamer_id]=dict(reason=str(reason),replaced=int(replaced),created=time.time())
        self.setting('regeneration',state)
        self.event('regeneração',f'{self.streamer(streamer_id)["name"]}: {reason}; {replaced} sugestões anteriores preservadas como substituídas.')

    def finish_regeneration(self,streamer_ids):
        state=self.setting('regeneration') or {}
        changed=False
        for streamer_id in streamer_ids:
            if streamer_id in state:state.pop(streamer_id);changed=True
        if changed:self.setting('regeneration',state)

    def regenerate(self,streamer_id,reason='reclassificação solicitada'):
        self.streamer(streamer_id)
        with self.connect(True) as c:
            c.execute('DELETE FROM centers WHERE session IN (SELECT id FROM sessions WHERE streamer=?)',(streamer_id,))
            c.execute("UPDATE candidates SET status='replaced' WHERE streamer=? AND status='pending' AND manual=0",(streamer_id,))
            replaced=c.execute('SELECT changes()').fetchone()[0]
        self.mark_regeneration(streamer_id,replaced,reason)
        return replaced

    def session(self, session_id):
        rows=self.rows('SELECT * FROM sessions WHERE id=?',(session_id,))
        if not rows:raise ValueError('Sessão não encontrada.')
        return rows[0]

    def retry_session(self,session_id):
        session=self.session(session_id)
        with self.connect(True) as c:
            c.execute("UPDATE sessions SET enabled=1,status='idle',error='',frame_error='',"
                      "frame_status=CASE WHEN frame_status='error' THEN '' ELSE frame_status END WHERE id=?",(session_id,))
            c.execute("UPDATE segments SET status='new' WHERE session=? AND status='processing'",(session_id,))
        self.event('sessão',session['name']+' enviada novamente para a fila.')

    def archive_session(self,session_id,archived=True):
        session=self.session(session_id)
        with self.connect(True) as c:
            if archived:c.execute("UPDATE sessions SET enabled=0,status='archived' WHERE id=?",(session_id,))
            else:c.execute("UPDATE sessions SET enabled=1,status='idle',error='' WHERE id=?",(session_id,))
        self.event('sessão',session['name']+(' arquivada.' if archived else ' reativada.'))

    def relink_session(self,session_id,new_source):
        """Religa uma fonte movida somente quando os bytes conhecidos são idênticos."""
        from . import media
        session=self.session(session_id);source=Path(new_source).expanduser().resolve()
        old=Path(session['source']);rows=self.rows('SELECT * FROM segments WHERE session=? ORDER BY seq',(session_id,))
        updates=[]
        if old.suffix or (rows and len(rows)==1 and Path(rows[0]['path']).suffix.casefold()!='.ts'):
            if not source.is_file():raise ValueError('Selecione o arquivo original desta gravação.')
            if len(rows)>1:raise ValueError('Esta sessão depende de uma pasta com vários segmentos.')
            if rows and media.sha_file(source)!=rows[0]['sha']:raise ValueError('O arquivo escolhido não é idêntico ao original registrado.')
            if rows:
                stat=source.stat();updates.append((str(source),stat.st_size,stat.st_mtime_ns,session_id,rows[0]['seq']))
        else:
            if not source.is_dir():raise ValueError('Selecione a pasta que contém os segmentos originais.')
            for row in rows:
                candidate=source/Path(row['path']).name
                if not candidate.is_file():raise ValueError('Falta o arquivo original '+candidate.name+' nesta pasta.')
                if candidate.stat().st_size!=row['size'] or media.sha_file(candidate)!=row['sha']:
                    raise ValueError('O arquivo '+candidate.name+' não é idêntico ao original registrado.')
                stat=candidate.stat();updates.append((str(candidate.resolve()),stat.st_size,stat.st_mtime_ns,session_id,row['seq']))
        with self.connect(True) as c:
            c.execute("UPDATE sessions SET source=?,enabled=1,status='idle',error='' WHERE id=?",(str(source),session_id))
            c.executemany('UPDATE segments SET path=?,size=?,mtime=? WHERE session=? AND seq=?',updates)
        link=Path(session['path'])/'vinculo_origem.json'
        atomic.write_json(link,dict(source=str(source),read_only=True),indent=2)
        self.event('origem',session['name']+' religada a '+str(source))
        return str(source)

    def new_session(self, streamer_id, name, source=None, closed=True):
        streamer=self.streamer(streamer_id)
        name=folder_name(name)
        with self.connect(True) as c:
            if source and c.execute('SELECT id FROM sessions WHERE streamer=? AND source=?',
                                    (streamer_id,str(Path(source).resolve()))).fetchone():
                raise ValueError('Essa gravação já está vinculada a este streamer.')
            if c.execute('SELECT id FROM sessions WHERE streamer=? AND name=?',(streamer_id,name)).fetchone():
                raise ValueError('Já existe uma sessão com este nome para este streamer.')
            session_id=uid()
            path=self.root/streamer['name']/'sessoes'/name
            if path.exists():raise ValueError('A pasta desta sessão já existe. Escolha outro nome.')
            path.mkdir(parents=True)
            (path/'segmentos').mkdir()
            c.execute('INSERT INTO sessions(id,streamer,name,source,path,closed,created) VALUES(?,?,?,?,?,?,?)',
                      (session_id,streamer_id,name,str(Path(source).resolve()) if source else str(path/'segmentos'),
                       str(path),int(closed),time.time()))
        return session_id

    def segment_index(self, session_id):
        """Só o que a leitura da pasta precisa (número, tamanho e data), sem a transcrição de cada trecho."""
        return {r['seq']:r for r in self.rows('SELECT seq,path,size,mtime,status,sha,duration FROM segments WHERE session=?',(session_id,))}

    def next_new_segment(self, session_id):
        """Primeiro trecho ainda não analisado da sessão, ou None."""
        rows=self.rows("SELECT * FROM segments WHERE session=? AND status='new' ORDER BY seq LIMIT 1",(session_id,))
        for row in rows:row['data']=json.loads(row['data'])
        return rows[0] if rows else None

    def segments(self, session_id):
        rows=self.rows('SELECT * FROM segments WHERE session=? ORDER BY seq',(session_id,))
        for row in rows:row['data']=json.loads(row['data'])
        return rows

    def candidate(self, candidate_id):
        rows=self.rows('SELECT * FROM candidates WHERE id=?',(candidate_id,))
        if not rows:raise ValueError('Sugestão não encontrada.')
        return self.decode(rows[0])

    def ranking_preferences(self, streamer_id):
        """Pesos conservadores aprendidos com as decisões (aprovar/rejeitar) e com o desempenho dos posts."""
        from . import learning
        return learning.merge(self._approval_weights(streamer_id), learning.weights(self.performance_samples(streamer_id)))

    def habit_samples(self, streamer_id, limit=60):
        """Um registro por corte que você aprovou: o que mudou em relação ao que o agente propôs."""
        from . import habits
        out=[]
        rows=self.rows("SELECT * FROM candidates WHERE streamer=? AND status IN ('approved','exporting','done') "
                       "ORDER BY created DESC LIMIT ?",(streamer_id,int(limit)))
        for row in rows:
            row=self.decode(dict(row));data=row['data'];project=data.get('project')
            sample=dict(effects=habits.effect_stats(data,project))
            bounds=habits.bounds_delta(data,row['start'],row['end'])
            if bounds:sample['bounds']=bounds
            try:sample['pairs']=habits.caption_corrections(data,row['start'],row['end'],project,row['profile'])
            except (KeyError,TypeError,ValueError):sample['pairs']=[]
            out.append(sample)
        return out

    def habits(self, streamer_id):
        from . import habits
        profile=self.streamer(streamer_id)['profile']
        return habits.learn(self.habit_samples(streamer_id),habits_terms(profile))

    def accept_term(self, streamer_id, term):
        """Põe uma palavra sugerida no dicionário aprendido (não força reanálise)."""
        term=' '.join(str(term).split())[:40]
        if len(term)<3:raise ValueError('Palavra inválida.')
        profile=dict(self.streamer(streamer_id)['profile'])
        current=[t.strip() for t in re.split(r'[,\n;]',profile.get('learned_terms','')) if t.strip()]
        if term.casefold() not in {t.casefold() for t in current}:current.append(term)
        profile['learned_terms']=', '.join(current)
        self.save_profile(streamer_id,profile)
        return profile['learned_terms']

    def confidence_table(self, streamer_id):
        """Taxa real de aprovação por faixa de confiança (para calibrar o que o agente diz saber)."""
        from . import judge
        samples=[]
        for row in self.rows("SELECT status,data FROM candidates WHERE streamer=? AND manual=1 AND status IN "
                             "('approved','exporting','done','rejected')",(streamer_id,)):
            try:value=json.loads(row['data']).get('confidence',{}).get('value')
            except (ValueError,TypeError,AttributeError):continue
            if value is not None:samples.append((float(value),row['status']!='rejected'))
        return judge.table_from(samples)

    def set_render_stats(self, candidate_id, seconds, video_seconds):
        """Quanto tempo a exportação levou (parede) para um vídeo de tal duração. Não muda a versão do corte."""
        with self.connect(True) as c:
            row=c.execute('SELECT data FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not row:return
            data=json.loads(row['data'])
            seconds=max(0.0,float(seconds));video_seconds=max(0.1,float(video_seconds))
            data['render']=dict(seconds=round(seconds,1),video_seconds=round(video_seconds,1),ratio=round(seconds/video_seconds,2),
                                at=round(time.time()))
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),candidate_id))

    def set_delivery(self, candidate_id, result):
        """Resultado da cópia para a pasta de entrega (não muda a versão do corte)."""
        with self.connect(True) as c:
            row=c.execute('SELECT data FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not row:return
            data=json.loads(row['data'])
            if result.get('status')=='desligada':data.pop('delivery',None)
            else:data['delivery']=result
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),candidate_id))

    def set_qc(self, candidate_id, report):
        """Relatório de qualidade da exportação (não muda a versão do corte)."""
        with self.connect(True) as c:
            row=c.execute('SELECT data FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not row:return
            data=json.loads(row['data']);data['qc']=dict(report,at=round(time.time()))
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),candidate_id))

    def set_data(self, candidate_id, key, value):
        """Grava uma chave em `data` sem mudar a versão do corte (aprovação humana de uma exportação, por exemplo)."""
        with self.connect(True) as c:
            row=c.execute('SELECT data FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not row:return
            data=json.loads(row['data']);data[key]=value
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),candidate_id))

    def set_refine(self, candidate_id, info):
        """Estado da revisão da legenda (2ª passagem). Não muda a versão do corte."""
        with self.connect(True) as c:
            row=c.execute('SELECT data FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not row:return
            data=json.loads(row['data']);data['refine']=dict(info,at=round(time.time()));
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),candidate_id))

    def apply_refined(self, candidate_id, segments, model):
        """Troca a transcrição do trecho do corte pela da segunda passagem; mantém o que está fora do corte."""
        import difflib
        def plain(t):  # mantém acentos: corrigir 'incrivel'→'incrível' conta como correção
            return str(t).strip().lower().strip('.,!?;:…"\'()')
        with self.connect(True) as c:
            raw=c.execute('SELECT * FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not raw:raise ValueError('Sugestão não encontrada.')
            row=dict(raw);data=json.loads(row['data']);start,end=row['start'],row['end']
            old=data.get('transcript_segments',[]);kept=[];old_tokens=[]
            for seg in old:
                if seg['end']<=start or seg['start']>=end:kept.append(seg);continue
                words=seg.get('words') or []
                old_tokens+= [plain(w.get('word','')) for w in words if w['end']>start and w['start']<end] or [plain(t) for t in str(seg.get('text','')).split()]
                outside=[w for w in words if w['end']<=start or w['start']>=end]
                if outside:kept.append(dict(seg,words=outside,text=' '.join(w['word'] for w in outside),
                                            start=outside[0]['start'],end=outside[-1]['end']))
            new_tokens=[plain(w.get('word','')) for seg in segments for w in seg.get('words',[])]
            changed=sum(max(i2-i1,j2-j1) for tag,i1,i2,j1,j2 in
                        difflib.SequenceMatcher(a=old_tokens,b=new_tokens,autojunk=False).get_opcodes() if tag!='equal')
            merged=sorted(kept+list(segments),key=lambda s:s['start'])
            data['transcript_segments']=merged
            data['transcript']=' '.join(s['text'] for s in merged if s['start']<end and s['end']>start)
            data['refine']=dict(status='done',model=model,changed=changed,at=round(time.time()))
            version=row['version']+1
            had_preview=row['preview_status'] in ('ready','queued','working')
            c.execute('UPDATE candidates SET data=?,version=?,preview_status=?,preview_path=?,preview_version=0 WHERE id=?',
                      (json.dumps(data),version,'queued' if had_preview else '','',candidate_id))
            return dict(version=version,changed=changed)

    def performance_samples(self, streamer_id):
        result=[]
        for row in self.rows("SELECT data FROM candidates WHERE streamer=? AND status IN ('approved','exporting','done') AND data LIKE '%\"performance\"%'",(streamer_id,)):
            try:data=json.loads(row['data'])
            except (ValueError,TypeError):continue
            if data.get('performance'):result.append((data.get('components',{}),data['performance']))
        return result

    def style_samples(self, streamer_id):
        """Clipes com números de desempenho, com o estilo/momento/gancho que o agente usou."""
        out=[]
        for row in self.rows("SELECT data FROM candidates WHERE streamer=? AND status IN ('approved','exporting','done') AND data LIKE '%\"performance\"%'",(streamer_id,)):
            try:data=json.loads(row['data'])
            except (ValueError,TypeError):continue
            if not data.get('performance'):continue
            hook=data.get('hook') or {}
            out.append(dict(style=data.get('editorial_style') or (data.get('profile') or {}).get('editorial_style') or 'clean',
                            moment=data.get('moment_label') or data.get('moment_type') or '',
                            hook=hook.get('score') if isinstance(hook,dict) else None,perf=data['performance']))
        return out

    def ab_items(self, streamer_id):
        out=[]
        for row in self.rows("SELECT data FROM candidates WHERE streamer=? AND status IN ('approved','exporting','done') AND data LIKE '%\"performance\"%'",(streamer_id,)):
            try:data=json.loads(row['data'])
            except (ValueError,TypeError):continue
            ab=data.get('ab')
            if ab and data.get('performance'):out.append(dict(group=ab.get('group'),label=ab.get('label'),change=ab.get('change',''),perf=data['performance']))
        return out

    def style_report(self, streamer_id):
        from . import learning
        profile=self.streamer(streamer_id)['profile']
        return learning.style_report(self.style_samples(streamer_id),profile.get('editorial_style','clean'))

    def learning_summary(self, streamer_id):
        from . import learning
        return learning.summary(self.performance_samples(streamer_id))

    def save_performance(self, candidate_id, value):
        """Guarda os números do post (sem mudar a versão nem refazer o vídeo)."""
        from . import learning
        perf=learning.clean(value)
        with self.connect(True) as c:
            row=c.execute('SELECT data,status FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not row:raise ValueError('Sugestão não encontrada.')
            if row['status'] not in ('approved','exporting','done'):
                raise ValueError('Registre o resultado só de clipes aprovados ou exportados.')
            data=json.loads(row['data']);data['performance']=perf
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(data),candidate_id))
        return perf

    def acceptance_history(self, streamer_id, weeks=12, now=None):
        """Taxa de aprovação por semana (segunda a domingo) em que o corte foi sugerido: aprovados ÷ (aprovados + rejeitados).
        Só conta o que você já decidiu; pendentes ficam de fora. Semanas sem decisão não entram."""
        import datetime
        now=time.time() if now is None else float(now)
        weeks=max(1,min(52,int(weeks)))
        def monday(ts):
            d=datetime.datetime.fromtimestamp(ts).date()
            return d-datetime.timedelta(days=d.weekday())
        first=monday(now)-datetime.timedelta(weeks=weeks-1)
        buckets={}
        rows=self.rows("SELECT status,created FROM candidates WHERE streamer=? AND status IN "
                       "('approved','exporting','done','rejected') AND created>0",(streamer_id,))
        for row in rows:
            week=monday(row['created'])
            if week<first or week>monday(now):continue
            yes,no=buckets.get(week,(0,0))
            buckets[week]=(yes+(row['status']!='rejected'),no+(row['status']=='rejected'))
        series=[]
        for week in sorted(buckets):
            yes,no=buckets[week]
            series.append(dict(week=week.isoformat(),approved=yes,rejected=no,n=yes+no,rate=round(yes/(yes+no),3)))
        total_yes=sum(r['approved'] for r in series);total=sum(r['n'] for r in series)
        return dict(weeks=series,approved=total_yes,decided=total,rate=round(total_yes/total,3) if total else None)

    def _approval_weights(self, streamer_id):
        rows=self.rows("SELECT status,data FROM candidates WHERE streamer=? AND manual=1 AND status IN "
                       "('approved','exporting','done','rejected')",(streamer_id,))
        if len(rows)<4:return {}
        positives=sum(row['status']!='rejected' for row in rows)
        base=(positives+2)/(len(rows)+4)
        samples={}
        for row in rows:
            try:parts=json.loads(row['data']).get('components',{})
            except (ValueError,TypeError):continue
            for name,value in parts.items():
                if float(value)<=0:continue
                yes,total=samples.get(name,(0,0))
                samples[name]=(yes+(row['status']!='rejected'),total+1)
        weights={}
        for name,(yes,total) in samples.items():
            if total<2:continue
            rate=(yes+2)/(total+4)
            weights[name]=round(max(.75,min(1.30,rate/max(.01,base))),3)
        return weights

    @staticmethod
    def decode(row):
        for key in ('data','parts','profile'):
            row[key]=json.loads(row[key])
        return row

    @staticmethod
    def duplicates(c, streamer, session, group_id, start, end, parts, exclude=None, statuses=None, data=None):
        statuses=statuses or (*ACTIVE,'rejected')
        # Só lê as sugestões que podem ser iguais: mesmo trecho da mesma gravação, mesmos bytes de mídia
        # (em qualquer sessão) ou impressão visual parecida. O histórico inteiro não precisa ser relido.
        conditions=['(session=? AND group_id=? AND start<? AND end>?)'];extra=[session,group_id,end,start]
        for sha in sorted({str(p['sha']) for p in parts if p.get('sha')}):
            conditions.append('instr(parts,?)>0');extra.append(sha)
        fingerprint=fingerprint_of(data)
        if fingerprint:
            conditions.append("(fingerprint!='' AND hamming(fingerprint,?)<=7)");extra.append(fingerprint)
        rows=c.execute('SELECT * FROM candidates WHERE streamer=? AND status IN ('+
                       ','.join('?' for _ in statuses)+') AND ('+' OR '.join(conditions)+')',
                       (streamer,*statuses,*extra)).fetchall()
        matches=[]
        for row in rows:
            if row['id']==exclude:continue
            recoded=same_recoded_moment(data,json.loads(row['data']),end-start,row['end']-row['start'])
            if ((row['session']==session and row['group_id']==group_id and
                 overlap_ratio(dict(start=start,end=end),dict(row))>=.55) or
                    same_content(parts,json.loads(row['parts'])) or recoded):
                matches.append(dict(row))
        return matches

    @staticmethod
    def duplicate(c,*args,**kwargs):
        matches=Store.duplicates(c,*args,**kwargs)
        return matches[0] if matches else None

    def propose(self, session_id, data, parts, profile):
        session=self.session(session_id)
        with self.connect(True) as c:
            current=c.execute('SELECT profile FROM streamers WHERE id=?',(session['streamer'],)).fetchone()
            current_profile=json.loads(current['profile'])
            if (analysis_key(profile)!=analysis_key(current_profile) or
                    selection_key(profile)!=selection_key(current_profile)):
                return None,False
            matches=self.duplicates(c,session['streamer'],session_id,data['group_id'],data['start'],data['end'],parts,
                                    data=data)
            if matches:
                existing=max(matches,key=lambda r:r['score'])
                # Somente uma sugestão intocada pode ser atualizada por uma melhor.
                editable=all(r['status']=='pending' and not r['manual'] and r['session']==session_id and
                             r['group_id']==data['group_id'] for r in matches)
                if editable and data['score']>existing['score']+.01:
                    c.execute("UPDATE candidates SET start=?,end=?,score=?,data=?,parts=?,fingerprint=?,version=version+1,"
                              "preview_status='',preview_path='' WHERE id=?",
                              (data['start'],data['end'],data['score'],json.dumps(data),json.dumps(parts),
                               fingerprint_of(data),existing['id']))
                    for other in matches:
                        if other['id']!=existing['id']:
                            c.execute("UPDATE candidates SET status='replaced',error=? WHERE id=?",
                                      ('Representado pela sugestão '+existing['id'],other['id']))
                return existing['id'],False
            candidate_id=uid()
            c.execute('INSERT INTO candidates(id,session,streamer,start,end,group_id,score,status,data,parts,profile,created,fingerprint) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (candidate_id,session_id,session['streamer'],data['start'],data['end'],data['group_id'],
                       data['score'],'pending',json.dumps(data),json.dumps(parts),json.dumps(profile),time.time(),
                       fingerprint_of(data)))
            return candidate_id,True

    def trim_fallbacks(self,session_id,limit=5):
        """Mantem apenas os exploratorios mais promissores e intocados."""
        limit=max(1,min(10,int(limit)))
        with self.connect(True) as c:
            rows=c.execute("SELECT id,score,data,created FROM candidates WHERE session=? AND status='pending' AND manual=0",
                           (session_id,)).fetchall()
            weak=[]
            for row in rows:
                try:
                    if json.loads(row['data']).get('fallback'):weak.append(dict(row))
                except (ValueError,TypeError):continue
            weak.sort(key=lambda row:(-float(row['score']),row['created'],row['id']))
            for row in weak[limit:]:
                c.execute("UPDATE candidates SET status='replaced',error=? WHERE id=?",
                          ('Substituído por um candidato exploratório mais promissor.',row['id']))
        return min(limit,len(weak))

    def create_manual(self, session_id, data, parts, profile, allow_overlap=False):
        """Cria um corte escolhido pelo usuário sem depender do ranking automático."""
        session=self.session(session_id)
        with self.connect(True) as c:
            matches=[] if allow_overlap else self.duplicates(c,session['streamer'],session_id,data['group_id'],data['start'],data['end'],
                                                             parts,data=data)
            if matches:
                existing=max(matches,key=lambda row:row['score'])
                return existing['id'],False
            candidate_id=uid()
            c.execute('INSERT INTO candidates(id,session,streamer,start,end,group_id,score,status,data,parts,profile,'
                      'manual,created,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (candidate_id,session_id,session['streamer'],data['start'],data['end'],data['group_id'],
                       data['score'],'pending',json.dumps(data),json.dumps(parts),json.dumps(profile),1,time.time(),
                       fingerprint_of(data)))
            return candidate_id,True

    def review(self, candidate_id, version, start, end, parts, action='save', profile=None, transcript=None,
               editorial_confirmed=False,edit_overrides=None,reason=''):
        if action not in ('save','approve','reject','preview','retry'):
            raise ValueError('Ação de revisão inválida.')
        reason=str(reason or '').strip()
        if reason and reason not in REJECT_REASONS:raise ValueError('Motivo de rejeição desconhecido.')
        start,end=float(start),float(end)
        if not all(math.isfinite(v) for v in (start,end)) or start<0 or not 1<=end-start<=90:
            raise ValueError('O corte deve durar entre 1 e 90 segundos, dentro da sessão.')
        with self.connect(True) as c:
            raw=c.execute('SELECT * FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not raw:raise ValueError('Sugestão não encontrada.')
            row=dict(raw)
            if row['version']!=int(version):raise ValueError('A sugestão mudou. Atualize o painel antes de salvar.')
            if row['status'] in ('exporting','done'):
                raise ValueError('Esse corte já está em exportação ou concluído; o arquivo foi preservado.')
            selected_profile=profile_checked(profile or json.loads(row['profile']))
            if action in ('approve','retry'):
                if selected_profile['permission_policy']=='blocked':
                    raise ValueError('A política deste perfil bloqueia a exportação. Altere somente após confirmar os direitos.')
                data_before=json.loads(row['data'])
                if data_before.get('editorial_audit',{}).get('requires_review') and not editorial_confirmed:
                    raise ValueError('Confirme a revisão editorial, os créditos e a política antes de exportar.')
            status='rejected' if action=='reject' else 'approved' if action in ('approve','retry') else 'pending'
            data=json.loads(row['data'])
            if action in ('approve','retry'):
                track=(data.get('project') or {}).get('music')
                if track and not track.get('authorized'):
                    raise ValueError('Confirme, no editor, que você pode usar a música escolhida antes de exportar.')
            if isinstance(data.get('project'),dict) and (abs(start-row['start'])>.0001 or abs(end-row['end'])>.0001):
                from .project import rebase
                data['project']=rebase(data['project'],row['start']-start,end-start)
            previous_overrides=data.get('edit_overrides',{}) if isinstance(data.get('edit_overrides',{}),dict) else {}
            if edit_overrides is not None:
                if not isinstance(edit_overrides,dict) or len(edit_overrides)>40:
                    raise ValueError('As decisões de edição são inválidas.')
                allowed={str(item.get('id')) for item in data.get('edit_plan',{}).get('decisions',[])
                         if item.get('id')}
                unknown=set(map(str,edit_overrides))-allowed
                if unknown:raise ValueError('Uma decisão de edição não pertence a este corte.')
                data['edit_overrides']={str(key):bool(value) for key,value in edit_overrides.items()}
            if transcript is not None:
                refine=data.get('refine') or {}
                if refine.get('status')=='done':
                    # A legenda revisada (2ª passagem) vale enquanto o corte continuar dentro do trecho revisado.
                    # Se o corte foi esticado para fora dele, a revisão não cobre mais tudo e precisa ser refeita.
                    if start>=row['start']-.01 and end<=row['end']+.01 and data.get('transcript_segments'):
                        transcript=data['transcript_segments']
                    else:data.pop('refine',None)
                data['transcript_segments']=transcript
                data['transcript']=' '.join(s['text'] for s in transcript if s['start']<end and s['end']>start)
            if action in ('approve','retry'):
                if selected_profile.get('content_mode','live')=='live' and selected_profile['camera_rect'] is None:
                    raise ValueError('A webcam deste streamer não está marcada. Vá em Ajustes → Webcam e quadro, marque a webcam e salve; depois aprove de novo.')
                duplicate=self.duplicate(c,row['streamer'],row['session'],row['group_id'],start,end,parts,
                                         exclude=candidate_id,statuses=('approved','exporting','done'),data=data)
                if duplicate:
                    raise ValueError('Este momento já foi aprovado/exportado em outro corte: '+duplicate['id'])
            new_version=row['version']+1
            keep_preview=(action!='preview' and row['preview_status']=='ready' and
                          row['preview_version']==row['version'] and abs(start-row['start'])<.0001 and abs(end-row['end'])<.0001)
            if data.get('edit_overrides',{})!=previous_overrides:keep_preview=False
            # O motivo só vale enquanto o corte está rejeitado; reabrir ou aprovar limpa.
            kept_reason=(reason if action=='reject' else row.get('reason','') if action=='save' and row['status']=='rejected' else '')
            c.execute('UPDATE candidates SET start=?,end=?,parts=?,profile=?,status=?,manual=1,version=?,error=?,data=?, '
                      'preview_status=?,preview_path=?,preview_version=?,reason=? WHERE id=?',
                      (start,end,json.dumps(parts),json.dumps(selected_profile),status,new_version,'',json.dumps(data),
                       'queued' if action=='preview' else 'ready' if keep_preview or (row['preview_path'] and row['preview_status'] in ('ready','queued','working')) else '',
                       # A prévia anterior fica no disco como desatualizada (preview_version antiga) até a nova ficar pronta.
                       row['preview_path'],new_version if keep_preview else row['preview_version'],kept_reason,candidate_id))
            return new_version

    def save_project(self, candidate_id, version, value, queue_preview=True, music_exists=None, image_exists=None, learn=True):
        """Grava o projeto de edição do corte (cortes, zooms, títulos, legendas, música...).

        Salvar não apaga a prévia: o arquivo anterior fica disponível (desatualizado, `preview_version` antiga) até
        uma nova ficar pronta. `queue_preview` pede a nova prévia. `learn=False` (salvamento automático) não ensina
        nada à memória do streamer: o ponto de partida fica guardado e o próximo salvamento explícito aprende a
        diferença inteira, uma vez só."""
        from .project import clean
        with self.connect(True) as c:
            raw=c.execute('SELECT * FROM candidates WHERE id=?',(candidate_id,)).fetchone()
            if not raw:raise ValueError('Sugestão não encontrada.')
            row=dict(raw)
            if row['version']!=int(version):raise ValueError('O corte mudou. Atualize o editor antes de salvar.')
            if row['status'] in ('exporting','done'):
                raise ValueError('Esse corte já está em exportação ou concluído; o arquivo foi preservado.')
            data=json.loads(row['data'])
            previous=data.get('project')
            data['project']=clean(value,row['end']-row['start'],music_exists,image_exists)
            if learn:
                base=data.pop('learn_base',previous) if 'learn_base' in data else previous
            else:
                data.setdefault('learn_base',previous)
                base=None
            new_version=row['version']+1
            status='pending' if row['status'] in ('approved','rejected','error','duplicate') else row['status']
            had_preview=bool(row['preview_path']) and row['preview_status'] in ('ready','queued','working')
            preview_status='queued' if queue_preview else ('ready' if had_preview else '')
            # Projeto idêntico (ex.: salvar ao sair depois do salvamento automático): a prévia atual continua atual.
            same=(data['project']==previous and row['preview_status']=='ready' and row['preview_version']==row['version'])
            preview_version=new_version if same and not queue_preview else row['preview_version']
            if same and not queue_preview:preview_status='ready'
            c.execute('UPDATE candidates SET status=?,manual=1,version=?,error=?,data=?,preview_status=?,preview_version=? WHERE id=?',
                      (status,new_version,'',json.dumps(data),preview_status,preview_version,candidate_id))
        if learn:self._learn_from_save(candidate_id,base,data['project'])
        return new_version

    def _learn_from_save(self, candidate_id, old, new):
        """Registra na memória o que a pessoa mudou. Nunca derruba o salvamento."""
        try:
            from . import feedback
            changes=feedback.diff(old,new)
            if not changes:return
            candidate=self.candidate(candidate_id)
            for change in changes:
                self.memory.learn(candidate_id,candidate['streamer'],change)
        except Exception:pass

    def recover(self):
        with self.connect(True) as c:
            c.execute("UPDATE segments SET status='new' WHERE status='processing'")
            c.execute("UPDATE candidates SET status='approved' WHERE status='exporting'")
            c.execute("UPDATE candidates SET preview_status='queued' WHERE preview_status='working'")
            c.execute("UPDATE sessions SET closed=1,status='idle',error='Captura interrompida; arquivos existentes preservados.' "
                      "WHERE status='capturing'")
        self.clean_partial_renders()
        # Pausa após reinício para o usuário conferir antes de continuar.
        self.setting('paused',True)

    def clean_partial_renders(self):
        """Na partida nada está renderizando: pastas `render_*` são restos de uma exportação interrompida
        (queda de energia, fechamento à força). A exportação final só aparece depois de pronta (renomeada de uma vez),
        então apagar o resto nunca toca em um corte concluído. Retorna quantas pastas foram removidas."""
        removed=0
        try:rows=self.rows('SELECT path FROM sessions')
        except sqlite3.Error:return 0
        for row in rows:
            for sub in ('cortes','previas'):
                base=Path(row['path'])/sub
                try:leftovers=[p for p in base.glob('render_*') if p.is_dir()]
                except OSError:continue
                for folder in leftovers:
                    shutil.rmtree(folder,ignore_errors=True);removed+=1
        if removed:self.event('limpeza',f'{removed} pasta(s) de exportação interrompida removida(s)')
        return removed
