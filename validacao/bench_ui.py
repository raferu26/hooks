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
    t0 = time.time(); pg.locator('[data-clip]').nth(int(os.environ.get('CLIP','0'))).click()
    pg.wait_for_function("typeof ST!=='undefined'&&ST.open&&!!ST.data", timeout=15000)
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
    for k in ('mutate_ms', 'undo_ms'):
        v = r.pop(k); r[k.replace('_ms', '')] = dict(p50=round(statistics.median(v), 2), p95=pct(v, .95), max=round(max(v), 2))
    out.update(r)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    b.close()
