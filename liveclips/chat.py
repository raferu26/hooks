"""Chat como sinal auxiliar. Nunca decide um corte sozinho."""
import json
import os
from pathlib import Path
from . import clockmap
import re
import socket
import ssl
import statistics
import threading
import time
from urllib.parse import urlsplit


REACTION_RE=re.compile(r'\b(?:k{3,}|(?:ha){3,}|lol+|lmao+|wtf|pog|poggers|clutch|insane|gg|mds|meu deus|caraca)\b',re.I)
CHAT_PATTERNS={
    'risada':re.compile(r'\b(?:k{3,}|(?:ha){3,}|lol+|lmao+|rsrs+)\b',re.I),
    'surpresa':re.compile(r'\b(?:wtf|mds|meu deus|caraca|como assim|no way|what)\b',re.I),
    'jogada':re.compile(r'\b(?:pog|poggers|clutch|insane|gg|ace|mvp|ganhou|vitoria)\b',re.I),
    'tensao':re.compile(r'\b(?:corre|cuidado|vai vai|quase|socorro|nao nao)\b',re.I),
}


def twitch_channel(url):
    parsed=urlsplit(str(url))
    if parsed.hostname not in ('twitch.tv','www.twitch.tv'):return None
    channel=parsed.path.strip('/').split('/')[0].casefold()
    return channel if re.fullmatch(r'[a-z0-9_]{3,25}',channel) else None


def reaction_points(messages, length, bucket=2.0):
    """Converte volume, diversidade e texto reativo em picos explicáveis."""
    count=max(1,int(float(length)/bucket)+1)
    bins=[[] for _ in range(count)]
    for item in messages:
        try:
            at=float(item['time'])
            if 0<=at<float(length):bins[min(count-1,int(at/bucket))].append(item)
        except (KeyError,TypeError,ValueError):pass
    volumes=[len({str(x.get('user','')).casefold() for x in rows if x.get('user')}) for rows in bins]
    baseline=statistics.median(volumes) if volumes else 0
    mad=statistics.median(abs(v-baseline) for v in volumes) if volumes else 0
    scale=max(1.0,mad*3)
    result=[]
    for index,rows in enumerate(bins):
        users=volumes[index]
        reactions=sum(bool(REACTION_RE.search(str(x.get('text','')))) for x in rows)
        emotes=sum(int(x.get('emotes',0) or 0) for x in rows)
        reaction_types={name:sum(bool(pattern.search(str(x.get('text','')))) for x in rows)
                        for name,pattern in CHAT_PATTERNS.items()}
        strength=min(3.0,max(0.0,(users-baseline)/scale)+min(1.5,(reactions+emotes*.35)/3))
        if strength<.8 or (users<2 and reactions<2):continue
        result.append({'time':round(index*bucket+bucket/2,2),'strength':round(strength,3),
                       'messages':len(rows),'users':users,'reactions':reactions,'emotes':emotes,
                       'reaction_types':reaction_types})
    return result


def load_signals(session_path, length):
    path=Path(session_path)/'chat.jsonl';messages=[]
    if path.is_file():
        for line in path.read_text(encoding='utf-8',errors='replace').splitlines():
            try:messages.append(json.loads(line))
            except json.JSONDecodeError:pass
    clock=clockmap.clock_for(messages,clockmap.load_saved(session_path))
    points=reaction_points(clockmap.apply(messages,clock),length)
    return [dict(p,time_uncertainty_s=clock['uncertainty_s']) for p in points]


class TwitchChatCapture:
    """Leitura oficial via IRC quando o usuário fornece OAuth chat:read."""
    def __init__(self,url,session_path):
        self.channel=twitch_channel(url);self.path=Path(session_path)/'chat.jsonl'
        self.token=os.environ.get('LIVECLIPS_TWITCH_TOKEN','').removeprefix('oauth:')
        self.user=os.environ.get('LIVECLIPS_TWITCH_USER','').casefold()
        self.stop_event=threading.Event();self.thread=None;self.sock=None
        self.status='indisponível' if not self.channel else 'aguardando conexão' if self.token and self.user else 'não conectado'
        self.started=time.monotonic();self.seen=set()

    def start(self):
        if not (self.channel and self.token and self.user):return False
        self.thread=threading.Thread(target=self._run,name='LiveClips-chat',daemon=True);self.thread.start();return True

    def stop(self):
        self.stop_event.set()
        try:
            if self.sock:self.sock.shutdown(socket.SHUT_RDWR);self.sock.close()
        except OSError:pass
        if self.thread:self.thread.join(3)

    def _run(self):
        self.status='conectando'
        try:
            raw=socket.create_connection(('irc.chat.twitch.tv',6697),timeout=15)
            self.sock=ssl.create_default_context().wrap_socket(raw,server_hostname='irc.chat.twitch.tv')
            send=lambda value:self.sock.sendall((value+'\r\n').encode())
            send('PASS oauth:'+self.token);send('NICK '+self.user)
            send('CAP REQ :twitch.tv/tags twitch.tv/commands');send('JOIN #'+self.channel)
            self.status='capturando';buffer=b''
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open('a',encoding='utf-8',buffering=1) as output:
                while not self.stop_event.is_set():
                    data=self.sock.recv(65536)
                    if not data:break
                    buffer+=data
                    while b'\r\n' in buffer:
                        raw_line,buffer=buffer.split(b'\r\n',1);line=raw_line.decode('utf-8',errors='replace')
                        if line.startswith('PING '):send('PONG '+line[5:]);continue
                        if ' PRIVMSG #' not in line:continue
                        tags=line[1:].split(' ',1)[0] if line.startswith('@') else ''
                        values=dict(item.split('=',1) for item in tags.split(';') if '=' in item)
                        message_id=values.get('id','')
                        if message_id and message_id in self.seen:continue
                        if message_id:self.seen.add(message_id)
                        prefix=line.split(' PRIVMSG ',1)[0]
                        user=values.get('display-name') or prefix.rsplit(':',1)[-1].split('!',1)[0]
                        text=line.split(' PRIVMSG ',1)[1].split(' :',1)[-1]
                        emotes=values.get('emotes','')
                        emote_count=0 if not emotes else sum(len(x.split(',')) for x in emotes.split('/') if ':' in x)
                        output.write(json.dumps({'time':round(time.monotonic()-self.started,3),'user':user,
                                                 'text':text,'emotes':emote_count,'wall':round(time.time(),3),
                                                 'sent_ts':int(values['tmi-sent-ts']) if values.get('tmi-sent-ts','').isdigit() else None},ensure_ascii=False)+'\n')
            self.status='encerrado'
        except Exception as exc:
            self.status='erro: '+str(exc)[:120]
        finally:
            try:
                if self.sock:self.sock.close()
            except OSError:pass

