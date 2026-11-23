import json
import os
from pathlib import Path
import time

from liveclips import media
from liveclips.store import DEFAULT_PROFILE


def setup_session(store,name='CORINGA',session_name='TESTE',durations=(62.4,58.1),numbers=None,status='done'):
    existing=store.rows('SELECT id FROM streamers WHERE name=?',(name,))
    streamer=existing[0]['id'] if existing else store.create_streamer(name)
    profile=dict(DEFAULT_PROFILE,camera_rect=[0,.3,.25,.3],min_free_gb=.5)
    store.save_profile(streamer,profile)
    sid=store.new_session(streamer,session_name)
    session=store.session(sid)
    for i,duration in enumerate(durations):
        seq=numbers[i] if numbers else i
        file=Path(session['source'])/f'segmento_{seq:05}.ts'
        file.write_bytes(bytes([i+1])*130000)
        os.utime(file,(time.time()-100,time.time()-100))
        stat=file.stat()
        data={'segments':[],'signals':{'audio':[],'motion':[],'warnings':[]}}
        with store.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (sid,seq,str(file.resolve()),media.sha_file(file),duration,'same-format',stat.st_size,stat.st_mtime_ns,status,json.dumps(data)))
    return streamer,sid,profile


def candidate(store,sid,start=10,end=30,score=10):
    from liveclips.timeline import build_timeline,plan
    rows=build_timeline(store.segments(sid))
    group=next(r['group_id'] for r in rows if r['start']<=start<r['end'])
    data=dict(start=start,end=end,group_id=group,score=score,reasons=['Teste'],transcript='fala de teste')
    parts=plan(rows,start,end,group)
    profile=store.streamer(store.session(sid)['streamer'])['profile']
    key,created=store.propose(sid,data,parts,profile)
    return store.candidate(key),created
