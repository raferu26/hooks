"""Benchmark reproduzível da interface do Estúdio (linha de base de desempenho, V09/N5).
Uso: ui/fresh.sh 8790 && PORT=8790 python3 validacao/bench_ui.py [N_CORTES]
Mede, no Chrome headless: abertura do Estúdio, custo de mutate() (snapshot JSON + redesenho) com N cortes,
custo de desfazer, tamanho do snapshot, nós de DOM e memória JS. Saída: JSON em stdout. Só dados sintéticos."""
import json, os, sys, time, statistics
from playwright.sync_api import sync_playwright

PORT = os.environ.get('PORT', '8790')
N = max(30, int(sys.argv[1]) if len(sys.argv) > 1 else 200)   # >=30: o loop mede 30 mutate()


def pct(v, q):
    v = sorted(v)
    return round(v[min(len(v) - 1, int(len(v) * q))], 2)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome',
                          args=['--no-sandbox', '--enable-precise-memory-info', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1500)
    for _ in range(100):   # o CSP bloqueia wait_for_function com texto: consulta por evaluate
        if pg.evaluate("typeof state!=='undefined'&&!!state&&!!state.candidates&&state.candidates.length>0&&!!document.querySelector('[data-clip]')"): break
        pg.wait_for_timeout(100)
    t0 = time.time(); pg.evaluate("(()=>{const c=[...document.querySelectorAll('[data-clip]')];c.sort((a,b)=>{const f=x=>{const k=state.candidates.find(y=>y.id===x.dataset.clip);return k?(k.end-k.start):0};return f(b)-f(a)});c[0].dataset.pick='1'})()"); pg.locator('[data-clip][data-pick="1"]').click()
    for _ in range(150):
        if pg.evaluate("typeof ST!=='undefined'&&ST.open&&!!ST.data"): break
        pg.wait_for_timeout(100)
    out = dict(abrir_estudio_ms=round((time.time() - t0) * 1000))
    pg.wait_for_timeout(1000)
    r = pg.evaluate("""(N)=>{
      const D=dur(), mem=()=>performance.memory?performance.memory.usedJSHeapSize/1048576:null;
      const m0=mem();
      // N cortes de 0.05 s espaçados (estado sintético; não salva)
      ST.proj.cuts=[];for(let i=0;i<N;i++){const a=(i+0.5)*(D/(N+1));ST.proj.cuts.push({_k:'b'+i,start:a,end:a+0.05})}
      drawAll();
      const t=[];for(let i=0;i<30;i++){const s=performance.now();mutate(()=>{ST.proj.cuts[i].end+=0.001});t.push(performance.now()-s)}
      const u=[];for(let i=0;i<10;i++){const s=performance.now();undo();u.push(performance.now()-s)}
      const sn=snap().length;
      return {duracao_s:D,cortes:N,mutate_ms:t,undo_ms:u,snapshot_bytes:sn,dom_nos:document.getElementsByTagName('*').length,heap_mb_antes:m0,heap_mb_depois:mem(),undo_niveis:ST.undo.length}}""", N)
    # edição que não altera a fala (zoom): com e sem a memorização da lista de fala (sem = limpa a chave a cada ação, como era antes)
    z = pg.evaluate("""()=>{ST.proj.zooms=[{id:'zq',start:2,end:4,zoom:1.12,curve:'smooth'}];drawAll();const L=document.getElementById('stLeft');const run=force=>{const t=[];for(let i=0;i<30;i++){if(force)delete L.dataset.memo;const s=performance.now();mutate(()=>{ST.proj.zooms[0].end+=.001});t.push(performance.now()-s)}t.sort((a,b)=>a-b);return {p50:+t[15].toFixed(2),p95:+t[28].toFixed(2)}};
      const sem=run(true),com=run(false);return {linhas_de_fala:ST.lines.length,sem_memo:sem,com_memo:com}}""")
    r['mutate_zoom'] = z
    for k in ('mutate_ms', 'undo_ms'):
        v = r.pop(k); r[k.replace('_ms', '')] = dict(p50=round(statistics.median(v), 2), p95=pct(v, .95), max=round(max(v), 2))
    out.update(r)
    # arrasto: 60 pointermove sobre um zoom (eventos sintéticos no navegador; mede só o trabalho do manipulador + redesenho)
    d = pg.evaluate("""()=>{ST.proj.zooms=[{id:'zb',start:2,end:4,zoom:1.12,curve:'smooth'}];drawAll();
      const el=document.querySelector('.blk[data-kind=zoom][data-key=zb]'),r=el.getBoundingClientRect();const cx=r.left+r.width/2,cy=r.top+r.height/2;
      let draws=0;const f=window.drawTimeline;window.drawTimeline=function(){draws++;return f.apply(this,arguments)};
      const ev=(t,x)=>new PointerEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:cy,pointerId:1,buttons:1});
      el.dispatchEvent(ev('pointerdown',cx));const t=[];for(let i=1;i<=60;i++){const s0=performance.now();document.dispatchEvent(ev('pointermove',cx+i*2));t.push(performance.now()-s0)}
      const during=draws;document.dispatchEvent(ev('pointerup',cx+120));window.drawTimeline=f;
      t.sort((a,b)=>a-b);return {pointermove_p50_ms:+t[30].toFixed(2),pointermove_p95_ms:+t[57].toFixed(2),pointermove_max_ms:+t[59].toFixed(2),redesenhos_durante_arrasto:during,redesenhos_total:draws,final_start:ST.proj.zooms[0]&&ST.proj.zooms[0].start}}""")
    out['arrasto']=d
    print(json.dumps(out, ensure_ascii=False, indent=1))
    b.close()
