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
 $('txtWarn').innerHTML=(r.warnings||[]).map(w=>`<div class="banner"><span>${esc(w)}</span></div>`).join('');
 $('txtRes').innerHTML=r.lines.map((l,i)=>`<div class="item"><input type="number" step="0.1" min="0" data-ti="${i}" value="${l.start.toFixed(1)}" aria-label="Início da frase ${i+1} (segundos)"><span class="grow">${esc(l.text)}</span><span class="muted small">${l.end.toFixed(1)} s</span></div>`).join('');
 $('txtNote').textContent=r.timing==='toques'?'Início das frases: marcado por você. Palavras dentro de cada frase: estimadas.':'Tempos ESTIMADOS pelas pausas e pela energia do áudio — não é transcrição. Corrija o início aqui ou arraste os blocos na linha do tempo.'}
/* corrigir o início de uma frase à mão: a frase inteira (e suas palavras) anda junto, sem mudar a duração */
$('txtRes').addEventListener('change',e=>{const inp=e.target.closest('input[data-ti]');if(!inp)return;const i=+inp.dataset.ti,l=ST.lines[i];if(!l)return;const v=Math.max(0,Math.min(dur()-.2,+inp.value||0)),dt=v-l.start;if(Math.abs(dt)<.001)return;
 mutate(()=>{l.start=r2(l.start+dt);l.end=r2(l.end+dt);(l.words||[]).forEach(w=>{w.start=r2(w.start+dt);w.end=r2(w.end+dt)});ST.lines.sort((a,b)=>a.start-b.start);ST.linesEdited=true})});
$('txtGo').onclick=async()=>{$('txtGo').disabled=true;try{await txtApply()}finally{$('txtGo').disabled=false}};
$('txtDone').onclick=()=>$('textDialog').close();
$('txtFile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;if(f.size>200000)return toast('Arquivo grande demais para legenda (limite 200 KB).',true);$('txtIn').value=(await f.text()).slice(0,20000)};
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
