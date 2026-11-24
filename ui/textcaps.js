/* Legenda a partir de TEXTO (sem IA). O app NÃO ouve a fala: distribui as frases do usuário pelas pausas e pela energia do áudio
   (servidor: captions_text.py) ou pelos TOQUES que o usuário marca. Tempos são estimados e dizem isso na tela. */
const TX={on:false,phr:[],tp:[],applied:false};
function txtText(){return $('txtIn').value}
function openTextCaps(){const d=$('textDialog');if(d.open)return;$('txtRes').innerHTML='';$('txtWarn').innerHTML='';$('txtNote').textContent='';TX.applied=false;d.showModal();$('txtIn').focus()}
async function txtApply(taps){
 if(!txtText().trim()){toast('Cole ou digite o texto da legenda.',true);return null}
 try{const r=await api('/api/captions/from-text',{id:ST.id,text:txtText(),taps:taps||[]});
  mutate(()=>{ST.lines=r.lines;ST.linesEdited=true;ST.edit=-1});TX.applied=true;txtShow(r);return r}
 catch(e){toast(e.message,true);return null}}
function txtShow(r){
 $('txtWarn').innerHTML=((r&&r.warnings)||[]).map(w=>`<div class="banner"><span>${esc(w)}</span></div>`).join('');
 TX.timing=(r&&r.timing)||TX.timing||'estimado';txtRender();
 $('txtNote').textContent=TX.timing==='toques'?'Início das frases: marcado por você. Palavras dentro de cada frase: estimadas.':TX.timing==='arquivo'?'Tempos IMPORTADOS do arquivo (não estimados). Palavras individuais não têm tempo.':'Tempos ESTIMADOS pelas pausas e pela energia do áudio — não é transcrição. Corrija aqui ou arraste os blocos na linha do tempo.'}
/* lista editável das frases (sempre a partir de ST.lines): início, fim, texto, dividir, unir com a próxima, excluir; tudo desfaz com Ctrl+Z */
function txtRender(){$('txtRes').innerHTML=ST.lines.map((l,i)=>`<div class="item" data-i="${i}"><input type="number" step="0.1" min="0" data-f="start" value="${l.start.toFixed(2)}" aria-label="Início da frase ${i+1} (s)"><input type="number" step="0.1" min="0" data-f="end" value="${l.end.toFixed(2)}" aria-label="Fim da frase ${i+1} (s)"><input type="text" class="grow" data-f="text" value="${esc(l.text)}" aria-label="Texto da frase ${i+1}"><button class="small quiet" data-a="split" title="Dividir ao meio">✂</button><button class="small quiet" data-a="merge" title="Unir com a próxima" ${i===ST.lines.length-1?'disabled':''}>⤓</button><button class="small quiet danger" data-a="del" title="Excluir">✕</button></div>`).join('')||'<p class="muted small">Nenhuma frase ainda.</p>'}
function lineSpan(l,a,z){/* muda início/fim da frase e reescala as palavras dentro do novo intervalo */const o={s:l.start,e:l.end},k=(z-a)/Math.max(.01,o.e-o.s);l.start=r2(a);l.end=r2(z);(l.words||[]).forEach(w=>{w.start=r2(a+(w.start-o.s)*k);w.end=r2(a+(w.end-o.s)*k)})}
function lineSplit(l){const ws=l.words&&l.words.length?l.words:null,tx=l.text.split(/\s+/).filter(Boolean);if(tx.length<2)return null;const k=Math.ceil(tx.length/2);
 let cut;if(ws&&ws.length===tx.length)cut=(ws[k-1].end+ws[k].start)/2;else{const c=tx.slice(0,k).join(' ').length/l.text.length;cut=l.start+(l.end-l.start)*c}
 cut=r2(cut);const A={start:l.start,end:cut,text:tx.slice(0,k).join(' '),words:ws?ws.slice(0,k).map(w=>({...w})):[]},B={start:cut,end:l.end,text:tx.slice(k).join(' '),words:ws?ws.slice(k).map(w=>({...w})):[]};return[A,B]}
$('txtRes').addEventListener('change',e=>{const inp=e.target.closest('input[data-f]');if(!inp)return;const row=inp.closest('[data-i]'),i=+row.dataset.i,l=ST.lines[i];if(!l)return;const f=inp.dataset.f;
 /* só mexe (e só cria um passo de desfazer) se o valor realmente mudou */
 if(f==='text'){const tx=inp.value.trim()||l.text;if(tx===l.text){inp.value=l.text;return}mutate(()=>{ST.linesEdited=true;ST.lines[i]=retextLine(l,tx)})}
 else if(f==='start'){const v=Math.max(0,Math.min(l.end-.2,+inp.value||0));if(Math.abs(v-l.start)<.005){txtRender();return}mutate(()=>{ST.linesEdited=true;lineSpan(l,v,l.end)})}
 else{const v=Math.max(l.start+.2,Math.min(dur(),+inp.value||0));if(Math.abs(v-l.end)<.005){txtRender();return}mutate(()=>{ST.linesEdited=true;lineSpan(l,l.start,v)})}
 txtRender()});
$('txtRes').addEventListener('click',e=>{const b=e.target.closest('button[data-a]');if(!b)return;const i=+b.closest('[data-i]').dataset.i,l=ST.lines[i];if(!l)return;const a=b.dataset.a;
 if(a==='del')mutate(()=>{ST.lines.splice(i,1);ST.linesEdited=true});
 else if(a==='merge'&&ST.lines[i+1])mutate(()=>{const n=ST.lines[i+1];ST.lines.splice(i,2,{start:l.start,end:Math.max(l.end,n.end),text:l.text+' '+n.text,words:(l.words||[]).concat(n.words||[])});ST.linesEdited=true});
 else if(a==='split'){const p=lineSplit(l);if(!p)return toast('Essa frase tem uma palavra só: não dá para dividir.',true);mutate(()=>{ST.lines.splice(i,1,p[0],p[1]);ST.linesEdited=true})}
 txtRender()});
$('txtGo').onclick=async()=>{$('txtGo').disabled=true;try{await txtApply()}finally{$('txtGo').disabled=false}};
$('txtDone').onclick=()=>$('textDialog').close();
$('txtFile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;if(f.size>400000)return toast('Arquivo grande demais para legenda (limite 400 KB).',true);const txt=await f.text();
 if(/\.txt$/i.test(f.name)||!/\.(srt|vtt|ass|ssa)$/i.test(f.name)){$('txtIn').value=txt.slice(0,20000);return}
 try{const r=await api('/api/captions/from-file',{id:ST.id,name:f.name,content:txt,relative:$('txtRel').checked});mutate(()=>{ST.lines=r.lines;ST.linesEdited=true;ST.edit=-1});TX.applied=true;txtShow(r)}catch(err){toast(err.message,true)}};
/* ── marcar o início de cada frase ao tocar ── */
async function txtTapStart(){
 if(!txtText().trim())return toast('Cole ou digite o texto da legenda.',true);
 try{const r=await api('/api/captions/from-text',{id:ST.id,text:txtText(),taps:[]});TX.phr=r.lines.map(l=>l.text)}catch(e){return toast(e.message,true)}
 TX.tp=[];TX.on=true;$('textDialog').close();tapDraw();seekClip(0);const v=V();if(v&&v.paused)$('stPlay').click()}
$('txtTap').onclick=txtTapStart;
function tapDraw(){const el=$('tapBar'),k=TX.tp.length,n=TX.phr.length;el.classList.toggle('hide',!TX.on);if(!TX.on)return;
 el.innerHTML=`<div class="muted small">Marcando o início das frases · ${Math.min(k+1,n)} de ${n} · só o início (o fim vem da pausa seguinte)</div><div class="ph">${esc(TX.phr[Math.min(k,n-1)]||'')}</div><div class="row"><button class="primary small" id="tapNow">Marcar agora (Enter)</button><button class="small" id="tapBack">Voltar uma (Backspace)</button><button class="small quiet" id="tapEnd">Terminar (Esc)</button></div>`}
function tapMark(){if(!TX.on)return;TX.tp.push(r2(curClip()));if(TX.tp.length>=TX.phr.length)tapFinish();else tapDraw()}
function tapBack(){if(TX.tp.length){TX.tp.pop();tapDraw()}}
async function tapFinish(){if(!TX.on)return;const taps=TX.tp.slice();TX.on=false;tapDraw();const v=V();if(v&&!v.paused)$('stPlay').click();
 if(!taps.length){openTextCaps();return}
 const r=await txtApply(taps);openTextCaps();if(r)txtShow(r)}
function tapKey(e){if(e.key==='Enter'){e.preventDefault();tapMark()}else if(e.key==='Backspace'){e.preventDefault();tapBack()}else if(e.key==='Escape'){e.preventDefault();tapFinish()}else if(e.key===' '){e.preventDefault()}}
$('tapBar').addEventListener('click',e=>{const t=e.target.closest('button');if(!t)return;if(t.id==='tapNow')tapMark();else if(t.id==='tapBack')tapBack();else if(t.id==='tapEnd')tapFinish()});
/* ── arrastar os blocos de fala na linha do tempo (mover / ajustar início e fim); as palavras acompanham ── */
$('tlScroll').addEventListener('pointerdown',e=>{
 const b=e.target.closest('.blk.speech[data-line]');if(!b||e.button)return;e.stopImmediatePropagation();
 const i=+b.dataset.line,l=ST.lines[i];if(!l)return;const orig=JSON.parse(JSON.stringify(l)),t0=T_(tlX(e)),mode=e.target.classList.contains('l')?'l':e.target.classList.contains('r')?'r':'m',q=v=>Math.round(v*20)/20;
 ST.undo.push(snap());ST.redo=[];let moved=false;
 const move=ev=>{const dt=T_(tlX(ev))-t0;if(Math.abs(dt)>.02)moved=true;if(!moved)return;const sn=v=>{if(ev.altKey){SNAP.hit=null;return v}return snapTo(v,null)};
  let a=orig.start,z=orig.end;
  if(mode==='m'){const L=z-a;a=clamp(sn(q(a+dt)),0,dur()-L);z=a+L}else if(mode==='l')a=clamp(sn(q(a+dt)),0,z-.2);else z=clamp(sn(q(z+dt)),a+.2,dur());
  const k=(z-a)/Math.max(.01,orig.end-orig.start);l.start=r2(a);l.end=r2(z);
  (l.words||[]).forEach((w,j)=>{const o=orig.words[j];w.start=r2(a+(o.start-orig.start)*k);w.end=r2(a+(o.end-orig.start)*k)});
  b.style.left=X(l.start)+'px';b.style.width=Math.max(6,X(l.end-l.start))+'px';paintGuide()};
 const up=()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);SNAP.hit=null;
  if(moved){ST.linesEdited=true;ST.lines.sort((x,y)=>x.start-y.start);changed();drawAll()}else{ST.undo.pop();seekClip(l.start)}};
 document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);e.preventDefault()},true);
