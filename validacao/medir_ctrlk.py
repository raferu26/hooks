"""Eficiência do Ctrl+K: para cada ação, o menor nº de letras (de qualquer palavra do nome) para ela ser a primeira da lista
(+ Ctrl+K e Enter). Uso: ui/fresh.sh 8790 && PORT=8790 python3 validacao/medir_ctrlk.py"""
import json, os
from playwright.sync_api import sync_playwright
PORT = os.environ.get('PORT', '8790')
JS = r"""()=>{ST.sel={a:2,b:5};ST.item={kind:'zoom',id:'x'};ST.undo=[1];ST.redo=[1];
 const items=commands();const res=[];const input=document.getElementById('cmdInput');
 for(const c of items){const words=[...new Set(norm(c.label).replace(/[^a-z0-9 ]/g,'').split(' ').filter(w=>w.length>2))];let best=null;
  for(const word of words)for(let k=1;k<=word.length;k++){input.value=word.slice(0,k);CMDK.items=items;CMDK.at=0;cmdRender();if(CMDK.shown[0]&&CMDK.shown[0].label===c.label){if(best==null||k<best)best=k;break}}
  const n=best,found=best!=null;
  res.push({acao:c.label,letras:found?n:null,atalho:c.key||''})}
 return res}"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1200)
    pg.click('[data-clip]')
    for _ in range(100):
        if pg.evaluate("typeof ST!=='undefined'&&ST.open&&!!ST.data"): break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(600)
    r = pg.evaluate(JS); b.close()
ok = [x['letras'] for x in r if x['letras']]; sem = [x['acao'] for x in r if not x['letras']]
print(json.dumps(dict(acoes=len(r), letras_media=round(sum(ok) / len(ok), 1), ate_3_letras=sum(1 for n in ok if n <= 3), ate_5_letras=sum(1 for n in ok if n <= 5),
                      nunca_primeira=sem, mais_longas=sorted(r, key=lambda x: -(x['letras'] or 99))[:6]), ensure_ascii=False, indent=1))
