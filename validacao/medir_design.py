"""Mede o design do Estúdio (P06): tamanhos de fonte, áreas clicáveis e contraste (WCAG AA 4.5:1 texto normal, 3:1 grande).
Uso: ui/fresh.sh 8790 && PORT=8790 python3 validacao/medir_design.py   (só dados sintéticos; mede o que está visível)"""
import json, os
from playwright.sync_api import sync_playwright
PORT = os.environ.get('PORT', '8790')
JS = r"""()=>{
 const vis=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'};
 const parse=c=>{const m=c.match(/rgba?\(([^)]+)\)/);if(!m)return null;const p=m[1].split(',').map(Number);return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}};
 const lum=({r,g,b})=>{const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};return .2126*f(r)+.7152*f(g)+.0722*f(b)};
 const bgOf=e=>{let base={r:11,g:11,b:14,a:1};const chain=[];for(let n=e;n;n=n.parentElement){const c=parse(getComputedStyle(n).backgroundColor);if(c&&c.a>0){chain.push(c);if(c.a>=.99)break}}
   let out=base;if(chain.length&&chain[chain.length-1].a>=.99)out=chain.pop();while(chain.length){const c=chain.pop();out={r:c.r*c.a+out.r*(1-c.a),g:c.g*c.a+out.g*(1-c.a),b:c.b*c.a+out.b*(1-c.a),a:1}}return out};
 const root=document.getElementById('studio');const sizes={},small=[],lowc=[],targets=[];let texts=0;
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
 while(n=walker.nextNode()){const t=n.textContent.trim();if(!t)continue;const e=n.parentElement;if(!e||!vis(e)||e.closest('video,.blk,.tick,.live,.phone'))continue;texts++;
  const s=getComputedStyle(e),fs=parseFloat(s.fontSize);sizes[fs]=(sizes[fs]||0)+1;if(fs<12)small.push(t.slice(0,24)+' '+fs+'px');
  const fg=parse(s.color),bg=bgOf(e);if(fg){const a=fg.a<1?{r:fg.r*fg.a+bg.r*(1-fg.a),g:fg.g*fg.a+bg.g*(1-fg.a),b:fg.b*fg.a+bg.b*(1-fg.a)}:fg;
   const L1=lum(a),L2=lum(bg),cr=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);const large=fs>=24||(fs>=18.66&&+s.fontWeight>=700);if(cr<(large?3:4.5))lowc.push(t.slice(0,24)+' '+cr.toFixed(2)+':1 '+fs+'px')}}
 for(const e of root.querySelectorAll('button,[role=button],input,select,summary,.sec-h,[data-op],[data-do]')){if(!vis(e)||e.closest('.blk'))continue;const r=e.getBoundingClientRect();if(e.type==='checkbox'||e.type==='radio')continue;if(r.height<28||r.width<28)targets.push((e.id||e.className||e.tagName).toString().slice(0,26)+' '+Math.round(r.width)+'x'+Math.round(r.height))}
 return {textos:texts,tamanhos_fonte:sizes,fontes_menores_que_12px:small.length,exemplos_pequenos:[...new Set(small)].slice(0,8),contraste_abaixo_AA:lowc.length,exemplos_contraste:[...new Set(lowc)].slice(0,8),alvos_menores_que_28px:targets.length,exemplos_alvos:[...new Set(targets)].slice(0,10)}}"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1200)
    pg.click('[data-clip]'); pg.wait_for_function("ST.open&&!!ST.data"); pg.wait_for_timeout(900)
    out = pg.evaluate(JS)
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
