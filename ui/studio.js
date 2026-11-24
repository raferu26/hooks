/* ───── ESTÚDIO ───── */
const CAP_LABELS={auto:'Automático (segue o estilo)',dynamic:'Dinâmica',clean:'Limpa',bold:'Impactante',minimal:'Minimalista',impact:'Caixa alta animada',pop:'Entrada animada',box:'Faixa escura'};
const TITLE_LABELS={big:'Grande',bar:'Faixa',top:'Topo'},POS_LABELS={top:'Topo',center:'Centro',bottom:'Base'},CURVES={smooth:'Suave',snap:'Seco',punch:'Impacto',ease:'Gradual',linear:'Linear'};
const ST={open:false,id:'',data:null,proj:null,lines:[],linesEdited:false,overrides:{},start:0,end:0,sel:null,item:null,secs:new Set(),pps:0,fit:0,undo:[],redo:[],dirty:false,music:null,anchor:null,edit:-1,ending:false,videoKey:'',busy:false,raf:0,rev:0,savedRev:0,saving:false,saveErr:'',unlearned:false,saveTimer:0};
const PREF={get autoPrev(){try{return localStorage.getItem('hk-autoprev')!=='0'}catch(e){return true}},set autoPrev(v){try{localStorage.setItem('hk-autoprev',v?'1':'0')}catch(e){}},get tlh(){try{const v=+localStorage.getItem('hk-tlh');return v>0?v:0}catch(e){return 0}},set tlh(v){try{v?localStorage.setItem('hk-tlh',String(Math.round(v))):localStorage.removeItem('hk-tlh')}catch(e){}},get foldTl(){try{return localStorage.getItem('hk-foldtl')==='1'}catch(e){return false}},set foldTl(v){try{localStorage.setItem('hk-foldtl',v?'1':'0')}catch(e){}},get allTracks(){try{return localStorage.getItem('hk-alltracks')==='1'}catch(e){return false}},set allTracks(v){try{localStorage.setItem('hk-alltracks',v?'1':'0')}catch(e){}}};
const clone=o=>JSON.parse(JSON.stringify(o));
const dur=()=>ST.data.duration;
const uidc=p=>p+Math.random().toString(36).slice(2,8);

function applyFold(){const f=PREF.foldTl;$('studio').classList.toggle('tl-folded',f);const b=$('tlFold');b.setAttribute('aria-pressed',f);b.textContent=f?'Mostrar linha do tempo':'Ampliar prévia';if(!f&&ST.open)fitTimeline()}
function applyTlh(){const v=PREF.tlh,s=$('studio');if(v){s.style.setProperty('--tlh',v+'px');s.classList.add('tl-sized')}else{s.style.removeProperty('--tlh');s.classList.remove('tl-sized')}}
(()=>{const sp=$('tlSplit');const maxH=()=>Math.round(innerHeight*.5);const set=v=>{PREF.tlh=clamp(v,64,maxH());applyTlh();if(ST.open)fitTimeline()};
 sp.addEventListener('pointerdown',e=>{e.preventDefault();sp.setPointerCapture(e.pointerId);sp.classList.add('drag');const y0=e.clientY,h0=$('tlWrap').getBoundingClientRect().height;
  const mv=ev=>set(h0-(ev.clientY-y0));const up=()=>{sp.classList.remove('drag');sp.removeEventListener('pointermove',mv);sp.removeEventListener('pointerup',up)};sp.addEventListener('pointermove',mv);sp.addEventListener('pointerup',up)});
 sp.addEventListener('dblclick',()=>{PREF.tlh=0;applyTlh();if(ST.open)fitTimeline()});
 sp.addEventListener('keydown',e=>{if(e.key==='ArrowUp'||e.key==='ArrowDown'){e.preventDefault();const h=$('tlWrap').getBoundingClientRect().height;set(h+(e.key==='ArrowUp'?24:-24))}})})();
function toggleFold(){PREF.foldTl=!PREF.foldTl;applyFold()}
async function openStudio(id){
 try{const d=await api('/api/project/get',{id});clearTimeout(ST.saveTimer);Object.assign(ST,{plan:null,chat:null,open:true,id,data:d,proj:normProject(d.project),lines:clone(d.lines),linesEdited:d.lines_edited,overrides:{...d.overrides},start:d.start,end:d.end,sel:null,item:null,undo:[],redo:[],dirty:false,music:d.music,anchor:null,edit:-1,videoKey:'',rev:0,savedRev:0,saving:false,saveErr:'',unlearned:false});
 document.body.style.overflow='hidden';$('studio').classList.remove('hide');fillQuality(d);ST.pps=0;ST.cursor=0;fitTimeline();drawAll();applyTlh();applyFold();drawFlow();ensurePreview();cancelAnimationFrame(ST.raf);loop()}catch(e){toast(e.message,true)}}
function fillQuality(d){const q=$('stQuality'),modes=d.catalog.quality_modes||[];q.innerHTML=modes.map(m=>`<option value="${m.id}" title="${esc(m.note)}">${esc(m.label)}</option>`).join('');q.value=d.profile.quality_mode||'equilibrado';q.title=(modes.find(m=>m.id===q.value)||{}).note||''}
$('stQuality').onchange=()=>{const m=(ST.data.catalog.quality_modes||[]).find(x=>x.id===$('stQuality').value);$('stQuality').title=m?.note||'';if(m)toast(m.label+': '+m.note)};
$('stStaleGo').onclick=()=>refreshPreview();
function normProject(p){p=clone(p||{});p.cuts=p.cuts||[];p.zooms=p.zooms||[];p.titles=p.titles||[];p.sfx=p.sfx||[];p.voice=p.voice||{clean:false};p.layout=p.layout||null;p.speeds=p.speeds||[];p.freezes=p.freezes||[];p.overlays=p.overlays||[];p.formats=p.formats||[];p.captions=Object.assign({enabled:true,style:null,size:null,margin:null,color:null,lines:null},p.captions||{});p.cuts.forEach(c=>c._k=uidc('c'));return p}
function snap(){return JSON.stringify({p:ST.proj,l:ST.lines,e:ST.linesEdited,o:ST.overrides})}
function restore(s){const v=JSON.parse(s);ST.proj=v.p;ST.lines=v.l;ST.linesEdited=v.e;ST.overrides=v.o;ST.item=null;changed();drawAll()}
function mutate(fn){ST.undo.push(snap());if(ST.undo.length>80)ST.undo.shift();ST.redo=[];fn();ST.proj.cuts.sort((a,b)=>a.start-b.start);ST.proj.zooms.sort((a,b)=>a.start-b.start);ST.proj.titles.sort((a,b)=>a.start-b.start);ST.proj.sfx.sort((a,b)=>a.at-b.at);ST.proj.speeds.sort((a,b)=>a.start-b.start);ST.proj.freezes.sort((a,b)=>a.at-b.at);ST.proj.overlays.sort((a,b)=>a.start-b.start);changed();drawAll()}
function undo(){if(!ST.undo.length)return;ST.redo.push(snap());restore(ST.undo.pop())}
function redo(){if(!ST.redo.length)return;ST.undo.push(snap());restore(ST.redo.pop())}
const r2=v=>Math.round(v*100)/100,clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

/* mapa de tempo: vídeo da prévia (final) ↔ tempo do clipe (antes dos cortes) — usa o que a prévia mostra */
function keepIntervals(cuts,D){let cur=0;const out=[];for(const c of cuts){if(c.start>cur+.04)out.push([cur,c.start]);cur=Math.max(cur,c.end)}if(D>cur+.04)out.push([cur,D]);return out}
function TM(){const p=ST.data.preview;return(!p.ready&&p.timing)?p.timing:ST.data.timing}
function pieces(){const T=TM(),D=dur(),sp=T.speeds||[],fr=T.freezes||[];const out=[];let cur=T.lead;
 for(const [a,b] of keepIntervals(T.cuts,D)){const marks=[...new Set([a,b,...sp.flatMap(v=>[v.start,v.end]).filter(x=>x>a&&x<b),...fr.map(f=>f.at).filter(x=>x>a&&x<b)])].sort((p,q)=>p-q);
  for(let i=0;i<marks.length-1;i++){const x=marks[i],y=marks[i+1],rate=(sp.find(v=>v.start<=(x+y)/2&&(x+y)/2<v.end)||{rate:1}).rate;
   for(const f of fr)if(Math.abs(f.at-x)<1e-3){out.push({a:x,b:x,out:cur,rate:0,hold:f.duration});cur+=f.duration}
   out.push({a:x,b:y,out:cur,rate,hold:0});cur+=(y-x)/rate}}
 return {list:out,length:cur}}
function finalToClip(f){const T=TM(),tz=ST.data.project?.teaser;if(f<T.lead)return tz?tz.start+f:0;const {list}=pieces();for(const p of list){if(p.hold)continue;const len=(p.b-p.a)/p.rate;if(f<p.out+len)return p.a+(f-p.out)*p.rate}return dur()}
function clipToFinal(t){const {list,length}=pieces();for(const p of list){if(p.hold)continue;if(t<p.a)return p.out;if(t<=p.b)return p.out+(t-p.a)/p.rate}return length}
function autoCuts(){return (ST.data.decisions||[]).filter(d=>['silence','repetition'].includes(d.kind)&&(ST.overrides[d.id]??d.enabled)).map(d=>({start:+d.start,end:Math.min(dur(),+d.end),kind:d.kind}))}
const allCuts=()=>autoCuts().concat(ST.proj.cuts.map(c=>({start:c.start,end:c.end,kind:'manual'})));
const inCut=(a,b)=>allCuts().some(c=>a>=c.start-.02&&b<=c.end+.02);

/* ───── desenho geral ───── */
function drawAll(){drawBar();drawLeft();drawRight();drawTimeline();drawStage()}
function drawBar(){const d=ST.data,p=d.preview;$('stName').textContent=(ST.proj.titles[0]?.text)||d.suggestions?.hook?.opening||'Corte '+ST.id.slice(0,4);
 const sv=ST.saveErr?['bad','Não salvou · tentar de novo']:ST.saving?['info','Salvando…']:ST.dirty?['warn','Alterações não salvas']:['good',ST.data.saved?'Salvo':'Sem edições'];
 $('stState').className='chip '+sv[0];$('stState').textContent=sv[1];$('stState').title=ST.saveErr||'Cada alteração é salva sozinha em instantes (Ctrl+S salva na hora).';$('stState').disabled=!ST.saveErr;
 const pv=p.ready&&!ST.dirty?['good','Prévia atualizada']:['queued','working'].includes(p.status)?['info','Gerando prévia…']:p.status==='error'?['bad','A prévia falhou']:p.available?['warn','Prévia anterior']:['','Sem prévia'];
 $('stPrev').className='chip '+pv[0];$('stPrev').textContent=pv[1]+` · ${clock(ST.end-ST.start)}`;
 $('stUndo').disabled=!ST.undo.length;$('stRedo').disabled=!ST.redo.length;$('stApprove').disabled=ST.busy;$('stRefresh').disabled=ST.busy;
 $('stRefresh').classList.toggle('primary',!!(ST.dirty||(!p.ready&&!['queued','working'].includes(p.status))));
 $('stStale').classList.toggle('hide',!(p.available&&(!p.ready||ST.dirty)&&!['queued','working'].includes(p.status)));
 $('stBusy').classList.toggle('hide',!(p.available&&['queued','working'].includes(p.status)));
 if($('stAuto'))$('stAuto').checked=PREF.autoPrev;drawSteps()}
/* Etapa atual, do estado real: exportando/pronto → Exportar; alterações ou prévia desatualizada → Editar; senão → Conferir */
function stepNow(){const d=ST.data,p=d.preview;if(['approved','exporting','done'].includes(d.status))return 'exportar';return(ST.dirty||ST.saving||!p.ready)?'editar':'conferir'}
function drawSteps(){const el=$('stSteps');if(!el)return;const now=stepNow(),d=ST.data;
 const label={editar:'Editar',conferir:'Conferir',exportar:d.status==='done'?'Exportado':['approved','exporting'].includes(d.status)?'Exportando…':'Exportar'};
 const tip={importar:'O vídeo já foi importado.',editar:'Ajuste cortes, zoom, legendas e títulos. Salva sozinho.',conferir:'Assista à prévia e confira os avisos antes de exportar.',exportar:'Escolha a qualidade e exporte (Ctrl+Enter duas vezes).'};
 const order=['importar','editar','conferir','exportar'],at=order.indexOf(now);
 el.innerHTML=order.map((k,i)=>{const cls=i<at?'done':i===at?'now':'';const text=k==='importar'?'Importar':label[k];return `<li class="${cls}" title="${esc(tip[k])}"${i===at?' aria-current="step"':''}>${i<at?'✓ ':''}${i===at?`<b>${esc(text)}</b>`:esc(text)}</li>`}).join('')}
function drawStage(){const d=ST.data,w=$('stWait'),v=$('stVideo');const p=d.preview,st=p.status;
 if(p.available){w.classList.add('hide');const key='/media/preview?id='+ST.id+'&pv='+p.version;if(ST.videoKey!==key){const at=v.currentTime||0,was=!v.paused;ST.videoKey=key;v.src=key;if(at){v.addEventListener('loadedmetadata',()=>{try{v.currentTime=Math.min(at,v.duration||at)}catch(e){}if(was)v.play().catch(()=>{})},{once:true})}}}
 else{w.classList.remove('hide');if(st==='queued'||st==='working')w.innerHTML='<strong>Gerando a prévia…</strong><span class="muted small">Leva alguns segundos. Ela aparece aqui sozinha. Você já pode editar: legendas e títulos aparecem ao vivo.</span>';
  else if(st==='error')w.innerHTML=`<strong>A prévia falhou</strong><span class="muted small">${esc(d.error||'Erro ao renderizar.')}</span><button id="stRetryPrev" class="small">Tentar de novo</button>${/webcam/i.test(d.error||'')?'<button class="small primary" id="stGoCam">Marcar a webcam</button>':''}`;
  else w.innerHTML='<strong>Sem prévia ainda</strong><button id="stRetryPrev" class="primary small">Gerar prévia</button>'}}
async function ensurePreview(){const d=ST.data,p=d.preview;if(p.ready||['queued','working'].includes(p.status))return;if(d.status==='done'||d.status==='exporting')return;if(p.available&&!PREF.autoPrev)return;
 try{const r=await api('/api/review',{id:ST.id,version:d.version,start:ST.start,end:ST.end,action:'preview'});d.version=r.version;p.status='queued';drawBar();drawStage();await refresh(true)}catch(e){toast(e.message,true)}}
async function syncPreview(){try{const f=await api('/api/project/get',{id:ST.id});const d=ST.data;d.preview=f.preview;d.error=f.error;if(f.version===d.version&&!ST.dirty){d.timing=f.timing;d.project=f.project}}catch(e){}drawBar();drawStage();drawTimeline()}
window.studioTick=async()=>{if(!ST.open||ST.busy||ST.saving)return;const c=state.candidates.find(x=>x.id===ST.id);if(!c)return;const d=ST.data;
 if(c.version>d.version&&!ST.dirty){const f=await api('/api/project/get',{id:ST.id});d.version=f.version;d.timing=f.timing;d.project=f.project;d.preview=f.preview}
 const sig=c.preview_status+':'+c.preview_version+':'+c.version;if(sig!==ST.pvSig){ST.pvSig=sig;await syncPreview()}}

/* ───── transcrição ───── */
function drawLeft(){const el=$('stLeft'),top=el.scrollTop;const d=ST.data;let html='';
 html+=`<h3 aria-level="2">Fala e legendas</h3><p class="help" style="padding:0 14px">Clique numa palavra para marcar. Shift+clique estende. Depois use <b>Cortar</b>, <b>Zoom</b> ou <b>Título</b>.</p>`;
 if(d.vocabulary_fixes&&d.vocabulary_fixes.length)html+=`<p class="help" style="padding:0 14px"><span class="chip info">${d.vocabulary_fixes.length} nome${d.vocabulary_fixes.length>1?'s':''} corrigido${d.vocabulary_fixes.length>1?'s':''} pelo dicionário</span></p>`;
 html+='<div class="lines" id="lines">';
 ST.lines.forEach((l,i)=>{if(ST.edit===i){html+=`<div class="line edit"><span class="tc">${clock(l.start,1)}</span><div><textarea id="lineText" rows="2">${esc(l.text)}</textarea><div class="row" style="margin-top:6px"><button class="small primary" data-lsave="${i}">Salvar</button><button class="small" data-lcancel>Cancelar</button><button class="small quiet" data-lmerge="${i}" ${i===ST.lines.length-1?'disabled':''}>Juntar com a próxima</button><button class="small quiet danger" data-ldel="${i}">Apagar legenda</button></div></div></div>`;return}
  const ws=(l.words&&l.words.length?l.words:[{start:l.start,end:l.end,word:l.text}]);
  html+=`<div class="line" data-line="${i}"><span class="tc" data-seek="${l.start}">${clock(l.start,1)}</span><div>${ws.map((w,k)=>{const s=wordSel(i,k);return `<span class="w${inCut(w.start,w.end)?' cutw':''}${w.p!=null&&w.p<.5?' low':''}${s?' sel':''}" data-l="${i}" data-w="${k}" data-a="${w.start}" data-b="${w.end}">${esc(w.word)}</span> `}).join('')}<button class="quiet small" data-ledit="${i}" title="Editar texto" style="padding:0 6px">✎</button></div></div>`});
 if(!ST.lines.length)html+='<p class="help" style="padding:10px">Não há fala temporizada neste corte.</p>';
 html+='</div>';
 if(ST.sel)html+=`<div class="sel-bar"><span class="small">${clock(ST.sel.a,1)}–${clock(ST.sel.b,1)} (${(ST.sel.b-ST.sel.a).toFixed(1)}s) · ações no painel à direita · C corta</span><button class="small quiet" data-op="clear">Limpar</button></div>`;
 el.innerHTML=html;el.scrollTop=top}
function wordSel(i,k){const a=ST.anchor;if(!a||!a.end)return a&&a.l===i&&a.k===k;const [p,q]=[a.from,a.to];const pos=i*10000+k;return pos>=p&&pos<=q}
function setWordSel(from,to){const f=Math.min(from.l*10000+from.k,to.l*10000+to.k),t=Math.max(from.l*10000+from.k,to.l*10000+to.k);const w=(l,k)=>{const L=ST.lines[l],W=(L.words&&L.words.length?L.words:[{start:L.start,end:L.end}])[k];return W};const A=w(Math.floor(f/10000),f%10000),B=w(Math.floor(t/10000),t%10000);ST.anchor={l:from.l,k:from.k,end:true,from:f,to:t};ST.sel={a:A.start,b:B.end};ST.item=null;drawLeft();drawTimeline();drawRight();seekClip(A.start)}
let wdrag=null;
$('stLeft').addEventListener('pointerdown',e=>{const w=e.target.closest('.w');if(!w)return;const p={l:+w.dataset.l,k:+w.dataset.w};if(e.shiftKey&&ST.anchor)wdrag={from:{l:ST.anchor.l,k:ST.anchor.k}};else wdrag={from:p};setWordSel(wdrag.from,p)});
$('stLeft').addEventListener('pointerover',e=>{if(!wdrag||e.buttons!==1)return;const w=e.target.closest('.w');if(w)setWordSel(wdrag.from,{l:+w.dataset.l,k:+w.dataset.w})});
document.addEventListener('pointerup',()=>{wdrag=null});
$('stLeft').addEventListener('click',e=>{const t=e.target;
 const s=t.closest('[data-seek]');if(s)seekClip(+s.dataset.seek);
 const ed=t.closest('[data-ledit]');if(ed){ST.edit=+ed.dataset.ledit;drawLeft();$('lineText')?.focus()}
 if(t.closest('[data-lcancel]')){ST.edit=-1;drawLeft()}
 const sv=t.closest('[data-lsave]');if(sv){const i=+sv.dataset.lsave,txt=$('lineText').value.trim();if(!txt)return toast('A legenda não pode ficar vazia. Use Apagar legenda.',true);mutate(()=>{ST.lines[i]=retextLine(ST.lines[i],txt);ST.linesEdited=true;ST.edit=-1})}
 const dl=t.closest('[data-ldel]');if(dl)mutate(()=>{ST.lines.splice(+dl.dataset.ldel,1);ST.linesEdited=true;ST.edit=-1});
 const mg=t.closest('[data-lmerge]');if(mg)mutate(()=>{const i=+mg.dataset.lmerge,a=ST.lines[i],b=ST.lines[i+1];ST.lines.splice(i,2,{start:a.start,end:b.end,text:a.text+' '+b.text,words:(a.words||[]).concat(b.words||[])});ST.linesEdited=true;ST.edit=-1});
 const op=t.closest('[data-op]');if(op)selectionOp(op.dataset.op)});
function retextLine(l,text){const ws=text.split(/\s+/).filter(Boolean),old=l.words||[];let words;if(old.length===ws.length)words=old.map((w,i)=>({...w,word:ws[i]}));else{const tot=ws.reduce((a,w)=>a+w.length,0)||1;let t=l.start;words=ws.map(w=>{const d=(l.end-l.start)*w.length/tot,o={start:r2(t),end:r2(t+d),word:w};t+=d;return o})}return{start:l.start,end:l.end,text:ws.join(' '),words}}

/* ───── operações sobre a seleção ───── */
function range(def=3){if(ST.sel)return[ST.sel.a,ST.sel.b];const c=curClip();return[c,Math.min(dur(),c+def)]}
function selectionOp(op){const [a0,b0]=range();const a=r2(a0),b=r2(b0);
 if(op==='clear'){ST.sel=null;ST.anchor=null;drawLeft();drawTimeline();drawRight();return}
 if(op==='cut'){if(b-a<.1)return toast('Selecione pelo menos 0,1 segundo.',true);const total=ST.proj.cuts.reduce((s,c)=>s+c.end-c.start,0)+(b-a);if(total>dur()-1)return toast('Os cortes removeriam quase tudo. Sobre pelo menos 1 segundo.',true);if(ST.proj.cuts.length>=40)return toast('Limite de 40 cortes.',true);mutate(()=>{ST.proj.cuts.push({start:a,end:b,_k:uidc('c')});ST.sel=null;ST.anchor=null})}
 if(op==='zoom'){if(b-a<.4)return toast('Para o zoom, selecione pelo menos 0,4 segundo.',true);if(ST.proj.zooms.length>=30)return toast('Limite de 30 zooms.',true);mutate(()=>{const z={id:uidc('z'),start:a,end:b,zoom:1.12,curve:'smooth'};ST.proj.zooms.push(z);ST.item={kind:'zoom',id:z.id}})}
 if(op==='title'){if(ST.proj.titles.length>=12)return toast('Limite de 12 títulos.',true);mutate(()=>{const t={id:uidc('t'),text:'Seu título',start:a,end:Math.max(a+.6,Math.min(b,a+4)),style:'big',position:'top',color:'#FFFFFF'};ST.proj.titles.push(t);ST.item={kind:'title',id:t.id}})}
 if(op==='teaser'){if(b-a<.8||b-a>4.5)return toast('A abertura precisa ter entre 0,8 e 4,5 segundos.',true);mutate(()=>{ST.proj.teaser={start:a,end:b};ST.item={kind:'teaser'}})}}

/* ───── painel direito ───── */
/* ───── inspetor contextual: o item selecionado no topo; o resto do corte em seções recolhíveis ───── */
const SECTIONS=[['style','Estilo, cor e som','style'],['caps','Legendas','caps'],['titles','Títulos','title'],['music','Música','music'],['fx','Cortes e efeitos','fx'],['frame','Layout e imagens','frame'],['ai','Sugestões','agent'],['why','Por quê','shield'],['pub','Publicar','send']];
const KIND_LABEL={cut:'Corte manual',zoom:'Zoom',title:'Título',teaser:'Abertura',sfx:'Efeito sonoro',speed:'Velocidade',freeze:'Imagem congelada',image:'Imagem'};
function secSummary(id){const P=ST.proj,d=ST.data;
 if(id==='style'){const st=(d.catalog.styles.find(x=>x.id===(P.style||d.profile.style))||{}).label||'';return st+(P.voice.clean?' · voz limpa':'')+(P.teaser?' · com abertura':'')}
 if(id==='caps')return P.captions.enabled?(CAP_LABELS[P.captions.style||d.profile.caption_style]||'Ligadas'):'Desligadas';
 if(id==='titles')return P.titles.length?P.titles.length+' na tela':'Nenhum';
 if(id==='music')return ST.music?ST.music.title+(P.music&&!P.music.authorized?' · falta autorizar':''):'Sem música';
 if(id==='fx'){const n=[[P.cuts.length,'corte'],[P.zooms.length,'zoom'],[P.speeds.length,'velocidade'],[P.freezes.length,'congelamento'],[P.sfx.length,'som']].filter(x=>x[0]).map(x=>x[0]+' '+x[1]+(x[0]>1&&x[1]!=='som'?'s':x[0]>1?'s':''));return n.join(', ')||'Nada manual'}
 if(id==='frame'){const L=P.layout;return (L?LAYOUT_LABELS[L.mode]?.[0]:'Layout padrão')+(P.overlays.length?` · ${P.overlays.length} imagem${P.overlays.length>1?'ns':''}`:'')}
 if(id==='ai'){const h=d.suggestions.hook;return 'Gancho '+(h.score<4?'fraco':h.score<6?'médio':'forte')+((d.cut_warnings||[]).length?' · '+d.cut_warnings.length+' aviso(s)':'')}
 if(id==='why')return 'Decisões e revisão';
 if(id==='pub')return 'Pacote e resultado';return ''}
function itemEditor(){const it=ST.item,P=ST.proj;if(!it)return '';const o=getItem(it);if(!o&&it.kind!=='teaser')return '';
 const num=(path,label,val,step='.1')=>`<div><label>${label}</label><input type="number" step="${step}" min="0" data-f="${path}" data-t="num" value="${val}"></div>`;
 const rng=(path,label,min,max,step,val,f)=>`<div class="field"><label>${label}: <b data-out="${path}">${f(val)}</b></label><input type="range" data-f="${path}" data-t="num" min="${min}" max="${max}" step="${step}" value="${val}"></div>`;
 let b='',del='';
 if(it.kind==='cut'){const i=P.cuts.findIndex(c=>c._k===it.k);b=`<div class="two">${num(`cuts.${i}.start`,'De (s)',o.start)}${num(`cuts.${i}.end`,'Até (s)',o.end)}</div><p class="help" style="margin:0">${(o.end-o.start).toFixed(1)} s removidos do vídeo.</p>`;del=`cuts:${i}`}
 if(it.kind==='zoom'){const i=P.zooms.findIndex(z=>z.id===it.id);b=`<div class="two">${num(`zooms.${i}.start`,'De (s)',o.start)}${num(`zooms.${i}.end`,'Até (s)',o.end)}</div>${rng(`zooms.${i}.zoom`,'Força',1.02,1.35,.01,o.zoom,v=>(+v).toFixed(2)+'×')}<div class="field"><label>Curva</label><select data-f="zooms.${i}.curve" data-t="str">${ST.data.catalog.zoom_curves.map(c=>`<option value="${c}" ${o.curve===c?'selected':''}>${CURVES[c]||c}</option>`).join('')}</select></div>`;del=`zooms:${i}`}
 if(it.kind==='title'){const i=P.titles.findIndex(z=>z.id===it.id);b=`<div class="field"><label>Texto</label><input data-f="titles.${i}.text" data-t="str" value="${esc(o.text)}" maxlength="90"></div><div class="two"><div><label>Estilo</label><select data-f="titles.${i}.style" data-t="str">${ST.data.catalog.title_styles.map(x=>`<option value="${x}" ${o.style===x?'selected':''}>${TITLE_LABELS[x]||x}</option>`).join('')}</select></div><div><label>Posição</label><select data-f="titles.${i}.position" data-t="str">${['top','center','bottom'].map(x=>`<option value="${x}" ${o.position===x?'selected':''}>${POS_LABELS[x]}</option>`).join('')}</select></div></div><div class="two">${num(`titles.${i}.start`,'De (s)',o.start)}${num(`titles.${i}.end`,'Até (s)',o.end)}</div><div class="field"><label>Cor</label><input type="color" data-f="titles.${i}.color" data-t="str" value="${o.color}"></div>`;del=`titles:${i}`}
 if(it.kind==='speed'){const i=P.speeds.findIndex(z=>z.id===it.id);b=`<div class="two">${num(`speeds.${i}.start`,'De (s)',o.start)}${num(`speeds.${i}.end`,'Até (s)',o.end)}</div><div class="field"><label>Velocidade</label><select data-f="speeds.${i}.rate" data-t="num">${RATES.map(r=>`<option value="${r}" ${o.rate===r?'selected':''}>${fmtRate(r)}</option>`).join('')}</select></div><p class="help" style="margin:0">${(o.end-o.start).toFixed(1)} s viram ${((o.end-o.start)/o.rate).toFixed(1)} s. O som acompanha.</p>`;del=`speeds:${i}`}
 if(it.kind==='freeze'){const i=P.freezes.findIndex(z=>z.id===it.id);b=`${num(`freezes.${i}.at`,'Em (s)',o.at)}${rng(`freezes.${i}.duration`,'Parada por',.3,3,.1,o.duration,v=>(+v).toFixed(1)+' s')}`;del=`freezes:${i}`}
 if(it.kind==='image'){const i=P.overlays.findIndex(z=>z.id===it.id);b=`<div class="row"><img class="thumb-s" src="/media/image?id=${o.image}" alt=""><div class="two grow">${num(`overlays.${i}.start`,'De (s)',o.start)}${num(`overlays.${i}.end`,'Até (s)',o.end)}</div></div>${rng(`overlays.${i}.x`,'Horizontal',0,1,.01,o.x,v=>Math.round(v*100)+'%')}${rng(`overlays.${i}.y`,'Vertical',0,1,.01,o.y,v=>Math.round(v*100)+'%')}${rng(`overlays.${i}.scale`,'Tamanho',.08,1,.01,o.scale,v=>Math.round(v*100)+'%')}${rng(`overlays.${i}.opacity`,'Opacidade',.1,1,.05,o.opacity,v=>Math.round(v*100)+'%')}`;del=`overlays:${i}`}
 if(it.kind==='sfx'){const i=P.sfx.findIndex(z=>z.id===it.id);b=`<p class="help" style="margin:0">${esc((ST.data.catalog.sfx.find(x=>x.id===o.kind)||{}).label||o.kind)}</p>${num(`sfx.${i}.at`,'Em (s)',o.at)}${rng(`sfx.${i}.volume`,'Volume',.05,1,.05,o.volume,v=>Math.round(v*100)+'%')}`;del=`sfx:${i}`}
 if(it.kind==='teaser'){if(!P.teaser)return '';b=`<p class="help" style="margin:0">Abre com ${clock(P.teaser.start,1)}–${clock(P.teaser.end,1)} (${(P.teaser.end-P.teaser.start).toFixed(1)} s); depois o corte começa do início, com flash e whoosh.</p>`;del='teaser'}
 return `<div class="insp-item" role="region" aria-label="${KIND_LABEL[it.kind]} selecionado"><div class="row"><b class="grow">${KIND_LABEL[it.kind]}</b><button class="small quiet danger" ${del==='teaser'?'data-act="rmteaser"':`data-del="${del}"`} title="Remover (Delete)">Remover</button><button class="small quiet" data-act="deselect" title="Fechar (Esc)" aria-label="Fechar">✕</button></div>${b}</div>`}
function drawRight(){const el=$('stRight'),top=el.scrollTop;const d=ST.data;
 const secs=SECTIONS.filter(([id])=>id!=='pub'||d.status==='done');
 let html=itemEditor();
 if(ST.sel)html+=`<div class="insp-item sel-card"><div class="row"><b class="grow">Trecho ${clock(ST.sel.a,1)}–${clock(ST.sel.b,1)}</b><span class="muted small">${(ST.sel.b-ST.sel.a).toFixed(1)} s</span></div><div class="row"><button class="small" data-op="cut" title="C">Cortar</button><button class="small" data-op="zoom">Zoom</button><button class="small" data-op="title">Título</button><button class="small" data-act="addspeed">Velocidade</button><button class="small" data-op="teaser">Abertura</button><button class="small quiet" data-op="clear">Limpar</button></div></div>`;
 html+=secs.map(([id,label,icon])=>{const open=ST.secs.has(id);return `<section class="sec${open?' open':''}"><button class="sec-h" data-sec="${id}" aria-expanded="${open}">${ico(icon)}<span class="grow"><b>${label}</b><small>${esc(secSummary(id))}</small></span><i class="chev" aria-hidden="true">›</i></button>${open?`<div class="panel">${sectionBody(id)}</div>`:''}</section>`}).join('');
 el.innerHTML=html;el.scrollTop=top;
 if(ST.secs.has('music'))drawMusicTab();if(ST.secs.has('pub')&&d.status==='done')drawPublish();if(ST.secs.has('why')&&!ST.plan&&!ST.planBusy)loadPlan()}
const LAYOUT_LABELS={cam_top:['Câmera em cima','Câmera no terço de cima e jogo embaixo.'],split:['Meio a meio','Câmera e jogo com o mesmo tamanho.'],game_pip:['Jogo + câmera pequena','Jogo em tela cheia com a câmera num canto.'],cam_full:['Só a câmera','A câmera ocupa a tela toda.'],fit:['Vídeo inteiro','Mostra o vídeo todo, com fundo desfocado.'],fill:['Preencher a tela','Corta as laterais para encher a tela.']};
const RATES=[.25,.5,.75,1.25,1.5,2,3,4],FMT_LABELS={'1x1':'Quadrado 1:1 (feed)','4x5':'Retrato 4:5 (Instagram)','16x9':'Horizontal 16:9 (YouTube)'};
const fmtRate=r=>(+r).toLocaleString('pt-BR')+'×';
function sectionBody(tab){const P=ST.proj,d=ST.data;let body='';
 let fieldN=0;
 const field=(label,html)=>{const id='fl'+(++fieldN);return `<div class="field"><label id="${id}">${label}</label>${html.replace(/<(input|select|textarea)(?![^>]*aria-label)/,`<$1 aria-labelledby="${id}"`)}</div>`};
 const sw=(path,checked,label,sub='')=>`<label class="switch"><input type="checkbox" data-f="${path}" data-t="bool" ${checked?'checked':''}><span>${label}${sub?`<small>${sub}</small>`:''}</span></label>`;
 const range_=(path,label,min,max,step,val,fmt=v=>v)=>field(`${label}: <b data-out="${path}">${fmt(val)}</b>`,`<input type="range" data-f="${path}" data-t="num" min="${min}" max="${max}" step="${step}" value="${val}">`);
 if(tab==='style'){const cur=P.style||d.profile.style;const g=P.grade||{contrast:1,saturation:1,brightness:0};
  body=`<h4 aria-level="3">Estilo de edição deste corte</h4><div class="style-grid">${d.catalog.styles.map(s=>`<button class="style-opt" aria-pressed="${s.id===cur}" data-setstyle="${s.id}"><b>${esc(s.label)}</b></button>`).join('')}</div><p class="help">${esc((styleInfo[cur]||[])[1]||'')}</p>
  <h4 aria-level="3">Cor</h4>${range_('grade.contrast','Contraste',.8,1.4,.02,g.contrast,v=>(+v).toFixed(2))}${range_('grade.saturation','Saturação',.5,1.6,.02,g.saturation,v=>(+v).toFixed(2))}${range_('grade.brightness','Brilho',-.2,.2,.01,g.brightness,v=>(+v).toFixed(2))}<div><button class="small" data-act="resetgrade">Voltar à cor do estilo</button></div>
  <h4 aria-level="3">Som</h4>${sw('voice.clean',P.voice.clean,'Limpar a voz','Reduz chiado e ruído grave.')}${P.voice.clean?field('Tipo de limpeza',`<select data-f="voice.mode" data-t="str"><option value="light" ${P.voice.mode!=='neural'?'selected':''}>Clássica (filtros)</option><option value="neural" ${P.voice.mode==='neural'?'selected':''}>Neural (precisa do modelo em Ajustes → Áudio)</option></select>`):''}
  <h4 aria-level="3">Abertura (teaser)</h4>${P.teaser?`<div class="item"><span>Abre com ${clock(P.teaser.start,1)}–${clock(P.teaser.end,1)} (${(P.teaser.end-P.teaser.start).toFixed(1)}s), depois o corte começa do início, com flash e whoosh.</span><div class="row"><button class="small" data-act="rmteaser">Remover abertura</button></div></div>`:`<p class="help">Reordena o clipe: um trecho forte do final entra primeiro para prender nos 2 primeiros segundos. Marque um trecho de 1 a 4,5 s na fala e clique em <b>Abertura</b>.</p>${d.suggestions.teaser?`<div class="item"><span class="small">“${esc(d.suggestions.teaser.text)}” <span class="muted">(${clock(d.suggestions.teaser.start,1)})</span></span><button class="small" data-act="suggteaser">Usar esta abertura</button></div>`:''}`}`}
 if(tab==='caps'){const c=P.captions,pf=d.profile;
  body=`${sw('captions.enabled',c.enabled,'Mostrar legendas')}<div class="${c.enabled?'':'muted'}">${field('Estilo',`<select data-f="captions.style" data-t="strnull">${d.catalog.caption_styles.map(s=>`<option value="${s}" ${(c.style||pf.caption_style)===s?'selected':''}>${CAP_LABELS[s]||s}</option>`).join('')}</select>`)}
  ${range_('captions.size','Tamanho',24,68,1,c.size??pf.font_size??46)}${range_('captions.margin','Distância da base',130,500,5,c.margin??pf.caption_margin??340)}${field('Cor do destaque',`<input type="color" data-f="captions.color" data-t="strnull" value="${c.color||rgb(pf.caption_color||'00E8FF')}">`)}</div>
  <div><button class="small" data-act="resetcaps">Voltar ao padrão do streamer</button></div>
  <h4 aria-level="3">Revisão das palavras</h4>${(()=>{const r=d.refine||{},low=ST.lines.reduce((n,l)=>n+(l.words||[]).filter(w=>w.p!=null&&w.p<.5).length,0);const st=r.status==='working'||r.status==='queued'?`<span class="chip info">${r.status==='queued'?'Na fila':'Revisando…'}</span>`:r.status==='done'?`<span class="chip good">Revisada${r.changed!=null?' · '+r.changed+' palavra'+(r.changed===1?'':'s')+' mudou':''}</span>`:r.status==='error'?`<span class="chip bad">${esc(r.error||'Falhou')}</span>`:'';return `<p class="help" style="margin:0">${low?low+' palavra'+(low===1?'':'s')+' de baixa confiança (sublinhadas em âmbar à esquerda).':'Nenhuma palavra de baixa confiança.'}</p><div class="row"><button class="small" data-act="refine" ${ST.linesEdited?'disabled title="Você editou o texto à mão"':''}>Melhorar legendas (2ª passagem)</button>${st}</div>${ST.linesEdited?'<p class="help">Você editou o texto à mão; a revisão automática não sobrescreve suas edições.</p>':''}`})()}
  <p class="help">${ST.linesEdited?'Você editou o texto das legendas; elas não mudam mais sozinhas.':'Para corrigir uma palavra, clique em ✎ na fala à esquerda.'}</p>${ST.linesEdited?'<div><button class="small" data-act="autolines">Descartar minhas edições de texto</button></div>':''}`}
 if(tab==='titles'){
  body=`<div class="row"><h4 class="grow">Títulos na tela</h4><button class="small" data-op="title">＋ Título</button></div>${P.titles.length?`<div class="list">${P.titles.map((t,i)=>`<div class="item ${ST.item?.kind==='title'&&ST.item.id===t.id?'sel':''}" data-pick="title:${t.id}"><input data-f="titles.${i}.text" data-t="str" value="${esc(t.text)}" maxlength="90"><div class="two"><select data-f="titles.${i}.style" data-t="str">${d.catalog.title_styles.map(s=>`<option value="${s}" ${t.style===s?'selected':''}>${TITLE_LABELS[s]||s}</option>`).join('')}</select><select data-f="titles.${i}.position" data-t="str">${['top','center','bottom'].map(s=>`<option value="${s}" ${t.position===s?'selected':''}>${POS_LABELS[s]}</option>`).join('')}</select></div><div class="two"><div><label>De (s)</label><input type="number" step=".1" min="0" data-f="titles.${i}.start" data-t="num" value="${t.start}"></div><div><label>Até (s)</label><input type="number" step=".1" min="0" data-f="titles.${i}.end" data-t="num" value="${t.end}"></div></div><div class="row"><input type="color" data-f="titles.${i}.color" data-t="str" value="${t.color}"><span class="grow"></span><button class="small quiet danger" data-del="titles:${i}">Remover</button></div></div>`).join('')}</div>`:'<p class="help">Nenhum título. Um bom título nos primeiros 3 segundos ajuda a prender.</p>'}
  ${d.suggestions.titles.length?`<h4 aria-level="3">Sugestões tiradas da sua fala</h4><div class="list">${d.suggestions.titles.map((s,i)=>`<button class="small" style="text-align:left" data-sugtitle="${i}">＋ ${esc(s.text)}</button>`).join('')}</div>`:''}`}
 if(tab==='music')body='<div id="stMusic"></div>';
 if(tab==='fx'){
  const dec=(d.decisions||[]).filter(x=>x.label);
  body=`<div class="row"><h4 class="grow">Cortes manuais</h4><button class="small" data-op="cut">＋ Cortar seleção</button></div>${P.cuts.length?`<div class="list">${P.cuts.map((c,i)=>`<div class="item ${ST.item?.kind==='cut'&&ST.item.k===c._k?'sel':''}" data-pick="cut:${c._k}"><div class="two"><input type="number" step=".1" min="0" data-f="cuts.${i}.start" data-t="num" value="${c.start}"><input type="number" step=".1" min="0" data-f="cuts.${i}.end" data-t="num" value="${c.end}"></div><div class="row"><span class="muted small">${(c.end-c.start).toFixed(1)}s removidos</span><span class="grow"></span><button class="small quiet danger" data-del="cuts:${i}">Remover</button></div></div>`).join('')}</div>`:'<p class="help">Marque um trecho na fala ou na régua e clique em Cortar.</p>'}
  <div class="row"><h4 class="grow">Zooms</h4><button class="small" data-op="zoom">＋ Zoom na seleção</button></div>${P.zooms.length?`<div class="list">${P.zooms.map((z,i)=>`<div class="item ${ST.item?.kind==='zoom'&&ST.item.id===z.id?'sel':''}" data-pick="zoom:${z.id}"><div class="two"><input type="number" step=".1" min="0" data-f="zooms.${i}.start" data-t="num" value="${z.start}"><input type="number" step=".1" min="0" data-f="zooms.${i}.end" data-t="num" value="${z.end}"></div><div class="two"><div><label>Força ${z.zoom.toFixed(2)}×</label><input type="range" min="1.02" max="1.35" step=".01" data-f="zooms.${i}.zoom" data-t="num" value="${z.zoom}"></div><div><label>Curva</label><select data-f="zooms.${i}.curve" data-t="str">${d.catalog.zoom_curves.map(c=>`<option value="${c}" ${z.curve===c?'selected':''}>${CURVES[c]||c}</option>`).join('')}</select></div></div><button class="small quiet danger" data-del="zooms:${i}">Remover</button></div>`).join('')}</div>`:''}
  <div class="row"><h4 class="grow">Velocidade</h4><button class="small" data-act="addspeed">＋ Na seleção</button></div>${P.speeds.length?`<div class="list">${P.speeds.map((v,i)=>`<div class="item ${ST.item?.kind==='speed'&&ST.item.id===v.id?'sel':''}" data-pick="speed:${v.id}"><div class="two"><input type="number" step=".1" min="0" data-f="speeds.${i}.start" data-t="num" value="${v.start}"><input type="number" step=".1" min="0" data-f="speeds.${i}.end" data-t="num" value="${v.end}"></div><div class="row"><select data-f="speeds.${i}.rate" data-t="num" style="width:auto">${RATES.map(r=>`<option value="${r}" ${v.rate===r?'selected':''}>${fmtRate(r)}</option>`).join('')}</select><span class="muted small grow">${(v.end-v.start).toFixed(1)}s viram ${((v.end-v.start)/v.rate).toFixed(1)}s</span><button class="small quiet danger" data-del="speeds:${i}">✕</button></div></div>`).join('')}</div>`:'<p class="help">Marque um trecho e clique em Na seleção. 2× encurta partes paradas; 0,5× faz câmera lenta num lance forte. O som acompanha.</p>'}
  <div class="row"><h4 class="grow">Congelar imagem</h4><button class="small" data-act="addfreeze">＋ No cursor</button></div>${P.freezes.length?`<div class="list">${P.freezes.map((f,i)=>`<div class="item ${ST.item?.kind==='freeze'&&ST.item.id===f.id?'sel':''}" data-pick="freeze:${f.id}"><div class="two"><div><label>Em (s)</label><input type="number" step=".1" min="0" data-f="freezes.${i}.at" data-t="num" value="${f.at}"></div><div><label>Parada por ${(+f.duration).toFixed(1)}s</label><input type="range" min=".3" max="3" step=".1" data-f="freezes.${i}.duration" data-t="num" value="${f.duration}"></div></div><button class="small quiet danger" data-del="freezes:${i}">Remover</button></div>`).join('')}</div>`:'<p class="help">Para a imagem por 0,3 a 3 s (o som fica mudo). Combine com um efeito sonoro de impacto.</p>'}
  <h4 aria-level="3">Efeitos sonoros</h4><div class="row"><select id="sfxKind" style="width:auto">${d.catalog.sfx.map(s=>`<option value="${s.id}">${esc(s.label)}</option>`).join('')}</select><button class="small" data-act="addsfx">＋ No cursor</button></div>${P.sfx.length?`<div class="list">${P.sfx.map((e,i)=>`<div class="item"><div class="two"><span>${esc((d.catalog.sfx.find(s=>s.id===e.kind)||{}).label||e.kind)}</span><input type="number" step=".1" min="0" data-f="sfx.${i}.at" data-t="num" value="${e.at}"></div><div class="row"><input class="grow" type="range" min=".05" max="1" step=".05" data-f="sfx.${i}.volume" data-t="num" value="${e.volume}"><button class="small quiet danger" data-del="sfx:${i}">✕</button></div></div>`).join('')}</div>`:''}
  ${dec.length?`<h4 aria-level="3">Edições automáticas</h4><p class="help">Decididas automaticamente. Desligue o que não quiser.</p><div class="list">${dec.map(x=>`<label class="switch"><input type="checkbox" data-ov="${esc(x.id)}" ${(ST.overrides[x.id]??x.enabled)?'checked':''}><span>${esc(x.label)}<small>${esc(x.reason||'')}</small></span></label>`).join('')}</div>`:''}`}
if(tab==='frame'){const live=d.profile.content_mode!=='video',modes=live?['cam_top','split','game_pip','cam_full']:['fit','fill'],L=P.layout||{mode:modes[0],focus:.5,pip:'tr',pip_size:.36},mode=modes.includes(L.mode)?L.mode:modes[0];
  const diag={cam_top:'<i style="top:0;height:33%;background:#35d0ba"></i><i style="top:33%;bottom:0;background:#4f7aa8"></i>',split:'<i style="top:0;height:50%;background:#35d0ba"></i><i style="top:50%;bottom:0;background:#4f7aa8"></i>',game_pip:'<i style="inset:0;background:#4f7aa8"></i><i style="top:8%;right:8%;width:38%;height:22%;background:#35d0ba;border-radius:4px"></i>',cam_full:'<i style="inset:0;background:#35d0ba"></i>',fit:'<i style="inset:0;background:#26456b"></i><i style="top:30%;bottom:30%;left:0;right:0;background:#4f7aa8"></i>',fill:'<i style="inset:0;background:#4f7aa8"></i>'};
  body=`<h4 aria-level="3">Layout do vídeo</h4>${live&&!d.camera?'<div class="banner">A webcam ainda não foi marcada em Ajustes. Sem ela, o layout de live não exporta.</div>':''}<div class="layout-grid">${modes.map(m=>`<button class="layout-opt" aria-pressed="${m===mode}" data-layout="${m}"><span class="mini">${diag[m]}</span><b>${LAYOUT_LABELS[m][0]}</b><small>${LAYOUT_LABELS[m][1]}</small></button>`).join('')}</div>
  ${range_('layout.focus',live?'Parte do jogo que aparece (esquerda ↔ direita)':'Parte do vídeo quando preenche a tela',0,1,.02,L.focus,v=>Math.round(v*100)+'%')}
  ${mode==='game_pip'?`${field('Canto da câmera',`<select data-f="layout.pip" data-t="str">${[['tr','Cima, à direita'],['tl','Cima, à esquerda'],['br','Baixo, à direita'],['bl','Baixo, à esquerda']].map(([k,l])=>`<option value="${k}" ${L.pip===k?'selected':''}>${l}</option>`).join('')}</select>`)}${range_('layout.pip_size','Tamanho da câmera',.2,.5,.02,L.pip_size,v=>Math.round(v*100)+'%')}`:''}
  ${P.layout?'<div><button class="small" data-act="resetlayout">Voltar ao layout padrão</button></div>':''}
  <h4 aria-level="3">Imagens e memes</h4><div class="row"><button class="small" id="imgAdd">Enviar imagem</button><input type="file" id="imgFile" accept="image/png,image/jpeg,image/webp" hidden><span class="help" style="margin:0">PNG com fundo transparente funciona melhor.</span></div>
  ${d.images.length?`<div class="img-grid">${d.images.map(im=>`<button class="img-opt" data-useimg="${im.id}" title="Colocar no cursor: ${esc(im.name)}"><img src="/media/image?id=${im.id}" alt="${esc(im.name)}"></button>`).join('')}</div><p class="help">Clique numa imagem para colocá-la no ponto atual do vídeo.</p>`:'<p class="help">Nenhuma imagem enviada ainda.</p>'}
  ${P.overlays.length?`<div class="list">${P.overlays.map((o,i)=>`<div class="item ${ST.item?.kind==='image'&&ST.item.id===o.id?'sel':''}" data-pick="image:${o.id}"><div class="row"><img class="thumb-s" src="/media/image?id=${o.image}" alt=""><div class="two grow"><input type="number" step=".1" min="0" data-f="overlays.${i}.start" data-t="num" value="${o.start}"><input type="number" step=".1" min="0" data-f="overlays.${i}.end" data-t="num" value="${o.end}"></div></div>${range_(`overlays.${i}.x`,'Horizontal',0,1,.01,o.x,v=>Math.round(v*100)+'%')}${range_(`overlays.${i}.y`,'Vertical',0,1,.01,o.y,v=>Math.round(v*100)+'%')}${range_(`overlays.${i}.scale`,'Tamanho',.08,1,.01,o.scale,v=>Math.round(v*100)+'%')}${range_(`overlays.${i}.opacity`,'Opacidade',.1,1,.05,o.opacity,v=>Math.round(v*100)+'%')}<button class="small quiet danger" data-del="overlays:${i}">Remover imagem</button></div>`).join('')}</div>`:''}
  <h4 aria-level="3">Outros formatos</h4><p class="help">Além do vertical, o sistema pode entregar o mesmo clipe pronto em outros tamanhos, com as legendas ajustadas. Aparecem só na exportação final.</p>${d.catalog.formats.map(f=>`<label class="switch"><input type="checkbox" data-fmt="${f}" ${P.formats.includes(f)?'checked':''}><span>${FMT_LABELS[f]}</span></label>`).join('')}`}
 if(tab==='pub'){const qc=(state.candidates.find(x=>x.id===ST.id)||{data:{}}).data.qc;const dv=(state.candidates.find(x=>x.id===ST.id)||{data:{}}).data.delivery;body=`${dv?`<h4 aria-level="3">Pasta de entrega</h4><div class="item"><div class="row"><span class="conf ${dv.status==='ok'?'alta':dv.status==='erro'?'baixa':'média'}">${dv.status==='ok'?'copiado':dv.status==='pendente'?'pasta não encontrada':'erro'}</span>${dv.status==='ok'?`<span class="small muted dv-file">${esc(dv.file||'')}</span>`:`<button class="small" id="deliverRetry">Tentar de novo</button>`}</div>${dv.error?`<p class="help" style="margin:6px 0 0">${esc(dv.error)}</p>`:''}</div>`:''}${qc?`<h4 aria-level="3">Controle de qualidade da exportação</h4><div class="item"><div class="row"><span class="conf ${qc.level==='ok'?'alta':qc.level==='erro'?'baixa':'média'}">${qc.level==='ok'?'tudo certo':qc.level==='erro'?'problema encontrado':'atenção'}</span></div>${(qc.samples||[]).length?`<div class="qc-samples">${qc.samples.map((n,k)=>`<a href="/media/sample?id=${ST.id}&n=${k+1}" target="_blank" rel="noopener"><img loading="lazy" alt="Quadro ${k+1} do vídeo exportado" src="/media/sample?id=${ST.id}&n=${k+1}"></a>`).join('')}</div>`:''}${(()=>{const r=(state.candidates.find(x=>x.id===ST.id)||{data:{}}).data.render;return r?`<p class="help" style="margin:4px 0">Exportado em ${Math.round(r.seconds)} s para um vídeo de ${Math.round(r.video_seconds)} s (${String(r.ratio).replace('.',',')}× o tempo do vídeo).</p>`:''})()}${(qc.items||[]).map(i=>`<div class="qc-item ${i.status}"><i></i><span><b>${esc(i.label)}</b> <span class="muted">${esc(i.detail||'')}</span></span></div>`).join('')}${qc.approximate_zones?'<p class="help" style="margin:0">As zonas de legenda/botões do TikTok são aproximadas; confira no celular.</p>':''}</div>`:''}<h4 aria-level="3">Pacote de publicação</h4><div id="pubBox" class="item"><span class="muted small">Carregando…</span></div><h4 aria-level="3">Resultado no TikTok</h4><p class="help">Depois de postar, digite os números. Com 4 ou mais clipes o sistema passa a preferir o tipo de momento que mais rendeu.</p>${(()=>{const q=d.performance||{};const f=(k,l)=>`<div><label>${l}</label><input type="number" min="0" id="pf_${k}" value="${q[k]??''}"></div>`;return `<div class="two">${f('views','Visualizações')}${f('likes','Curtidas')}</div><div class="two">${f('comments','Comentários')}${f('shares','Compartilhamentos')}</div><div class="two">${f('saves','Salvamentos')}${f('watch_pct','Tempo assistido (%)')}</div><div><label>Link do post (opcional)</label><input id="pf_url" value="${esc(q.url||'')}" maxlength="300"></div><div class="row"><button class="small primary" data-act="saveperf">Salvar resultado</button><span class="muted small" id="pfMsg">${q.views?'Salvo.':''}</span></div>`})()}<p class="help" id="learnInfo"></p>`}

 if(tab==='why'){const pl=ST.plan;
  if(!pl)body='<p class="help">Carregando as decisões deste corte…</p>';
  else{const fm=pl.decisoes||{},rv=pl.revisao,st=pl.estado,stLabel={em_revisao:['bad','Em revisão'],pronto_para_revisao:['warn','Pronto para revisão'],aprovado:['good','Aprovado'],pronto_para_publicar:['good','Pronto para publicar']}[st]||['warn',st];
   const sevCls={critica:'bad',alta:'bad',media:'warn',baixa:''};
   body=`<h4 aria-level="3">Estado de entrega</h4><div class="item"><div class="row"><span class="chip ${stLabel[0]}">${stLabel[1]}</span>${pl.aprovacao?`<span class="small muted">aprovado por ${esc(pl.aprovacao.by)}</span>`:''}</div><span class="small muted">Nada é publicado sozinho. “Pronto para publicar” só indica que a versão está aprovada e o pacote confere.</span>
   <div class="row"><button class="small" data-act="approve" ${ST.data.status!=='done'?'disabled title="Exporte o clipe primeiro"':''}>Aprovar esta versão</button><button class="small" data-act="package" ${ST.data.status!=='done'?'disabled':''}>Montar pacote (hashes + linha do tempo)</button><button class="small" data-act="project" ${ST.data.status!=='done'?'disabled':''}>Salvar projeto (só referências)</button><button class="small" data-act="projectfull" ${ST.data.status!=='done'?'disabled':''}>Salvar projeto com as fontes</button></div>${pl.pacote&&!pl.pacote.ok&&ST.data.status==='done'?`<span class="small muted">Pacote: ${esc((pl.pacote.problemas||[]).join('; '))}</span>`:''}</div>
   <h4 aria-level="3">Revisão automática</h4>${rv?`<div class="item"><div class="row"><span class="chip ${rv.veredito==='bloqueado'?'bad':rv.veredito==='corrigir'?'warn':''}">${esc(rv.veredito.replace('_',' '))}</span></div><span class="small">${esc(rv.resumo)}</span>${(rv.problemas||[]).slice(0,8).map(p=>`<span class="small ${sevCls[p.severity]||''}">• [${esc(p.severity)}] ${esc(p.observation)}${p.interval?` (${clock(p.interval[0],1)})`:''}</span>`).join('')}<span class="small muted">Não verificado por regras: ${esc((rv.nao_verificado||[]).join('; '))}. Ouça e assista antes de aprovar.</span></div>`:'<p class="help">Exporte o clipe para gerar a revisão.</p>'}
   <h4 aria-level="3">O que foi decidido automaticamente e por quê</h4><div class="item">${fm.mapa_de_funcoes?`<span class="small">Decisão: <b>${esc(fm.mapa_de_funcoes)}</b></span>`:''}${(fm.motivos||[]).map(x=>`<span class="small muted">• ${esc(x)}</span>`).join('')}${fm.montagem&&fm.montagem.id?`<span class="small">Montagem: ${esc(fm.montagem.id)} — ${esc(fm.montagem.why||'')}</span>`:''}${(fm.protegidos||[]).length?`<span class="small muted">Trechos protegidos: ${fm.protegidos.map(p=>esc(p.function.replace(/_/g,' '))).join(', ')}</span>`:''}${(fm.memorias||[]).length?`<span class="small muted">Memórias usadas: ${fm.memorias.map(m=>esc(m.why||m.id)).join('; ')}</span>`:''}</div>
   ${understoodHtml(pl)}
   <h4 aria-level="3">Plano de edição</h4>${pl.plano?`<div class="item"><span class="small">${pl.plano.resumo.trechos} trecho(s) · ${pl.plano.resumo.duracao_s.toFixed(2)} s · ${pl.plano.resumo.quadros} quadros</span>${(pl.plano.efeitos||[]).map(e=>`<span class="small muted">• ${esc(e.recipe)} ${clock(e.start_s,1)}–${clock(e.end_s,1)}</span>`).join('')}</div>`:'<p class="help">O plano é gravado quando a prévia ou o vídeo é renderizado.</p>'}
   <details><summary class="small">Capacidades do editor (${Object.entries(pl.capacidades||{}).map(([k,v])=>v+' '+k).join(', ')})</summary><p class="help">Cada efeito tem estado honesto: disponível, parcial, ausente ou laboratório. As sugestões não prometem o que está ausente.</p></details>`}}
 if(tab==='ai'){const h=d.suggestions.hook,tg=d.suggestions.tighten;const lvl=h.score<4?['bad','fraco']:h.score<6?['warn','médio']:['good','forte'];
  const cf=d.confidence,cw=d.cut_warnings||[];
  body=`${cf?`<h4 aria-level="3">Confiança da sugestão</h4><div class="item"><div class="row"><span class="conf ${cf.tier}">${cf.tier==='baixa'?'revisar com atenção':'confiança '+cf.tier}</span><span class="small muted">${Math.round(cf.value*100)}%</span></div>${(cf.reasons||[]).map(x=>`<span class="small muted">• ${esc(x)}</span>`).join('')}</div>`:''}
  ${cw.length?`<h4 aria-level="3">Antes de aprovar</h4><div class="list">${cw.map(w=>`<div class="banner ${w.level==='bloqueado'?'error':''}" style="align-items:flex-start"><span class="small"><b>${clock(w.start,1)}–${clock(w.end,1)}</b> ${esc((w.messages||[]).join(' '))}</span></div>`).join('')}</div>`:''}
<h4 aria-level="3">Pedir uma alteração em português</h4><div class="item"><div class="row"><input class="grow" id="chatText" maxlength="400" placeholder="ex.: corta de 8 a 11 · replay de 12 a 15 em câmera lenta · sem zoom"><button class="small" data-act="say">Enviar</button></div>${ST.chat?`${(ST.chat.aplicado||[]).map(x=>`<span class="small">✓ ${esc(x)}</span>`).join('')}${(ST.chat.recusado||[]).map(x=>`<span class="small bad">✕ ${esc(x)}</span>`).join('')}${(ST.chat.aguardando_confirmacao||[]).map(x=>`<span class="small warn">Aguardando confirmação: ${esc(x)}</span>`).join('')}${(ST.chat.pergunta||[]).map(x=>`<span class="small muted">? ${esc(x)}</span>`).join('')}<div class="row">${ST.chat.pendente?'<button class="small" data-act="cconfirm">Confirmar corte grande</button>':''}<button class="small quiet" data-act="cundo" ${ST.chat.pode_desfazer?'':'disabled'}>Desfazer</button><button class="small quiet" data-act="credo" ${ST.chat.pode_refazer?'':'disabled'}>Refazer</button></div><span class="small muted">A alteração entra no corte e é salva sozinha. Nada é publicado.</span>`:'<span class="small muted">Entendo cortar, velocidade, replay, congelar, tirar zoom e baixar efeitos. O que eu não entender volta como pergunta.</span>'}</div>
    <h4 aria-level="3">Gancho (primeiros segundos)</h4><div class="item"><div class="row"><span class="chip ${lvl[0]}">${lvl[1]} · ${h.score.toFixed(1)}</span></div>${h.opening?`<span class="small">“${esc(h.opening)}”</span>`:''}${h.issues.map(x=>`<span class="small muted">• ${esc(x)}</span>`).join('')}${h.suggestion?`<span class="small">${esc(h.suggestion.reason)}</span><button class="small" data-act="hookcut">Começar em “${esc(h.suggestion.text.slice(0,34))}”</button>`:''}</div>
  <h4 aria-level="3">Limites do corte na live</h4><div class="two"><div><label>Início (s)</label><input type="number" step=".1" id="bStart" value="${r2(ST.start)}"></div><div><label>Fim (s)</label><input type="number" step=".1" id="bEnd" value="${r2(ST.end)}"></div></div><div class="row"><button class="small" data-act="bounds">Aplicar limites</button><button class="small" data-act="ext" data-d="-3,0">−3s início</button><button class="small" data-act="ext" data-d="0,3">+3s fim</button></div>
  ${tg.changes.length?`<div class="item"><span class="small">Limites mais limpos sugeridos: ${clock(tg.start,1)}–${clock(tg.end,1)}</span>${tg.changes.map(x=>`<span class="small muted">• ${esc(x)}</span>`).join('')}<button class="small" data-act="tighten">Aplicar sugestão</button></div>`:'<p class="help">Os limites já estão limpos.</p>'}
  <h4 aria-level="3">Variações</h4><p class="help" style="margin:0">Crie cópias do mesmo momento para comparar ou dividir. Elas aparecem na lista de cortes.</p><div class="row"><button class="small" data-act="abtest" ${(state.candidates.find(x=>x.id===ST.id)?.data||{}).variant_of?'disabled title="Esse corte já é uma variação"':''}>Criar teste A/B da abertura</button><button class="small" data-act="series">Dividir em Parte 1 e 2</button></div>
  <h4 aria-level="3">Por que este corte foi escolhido</h4><div class="list">${(d.reasons||[]).map(r=>`<span class="small muted">• ${esc(r)}</span>`).join('')||'<span class="small muted">Corte criado por você.</span>'}</div>`}
 return body}
const DIM_LABEL={forca_da_observacao:['Força da observação','o quanto os sinais (webcam, som, jogo) sustentam que algo aconteceu'],suporte_da_interpretacao:['Suporte da interpretação','o quanto o sentido do momento está apoiado'],prontidao_do_episodio:['Prontidão do episódio','1 = a história do trecho já tem desfecho'],valor_editorial:['Valor editorial','heurística de potencial de corte'],novidade:['Novidade','o quanto difere de outros cortes desta sessão'],afinidade_com_criador:['Afinidade com o criador','só existe depois de aprendizado']};
const STATE_LABEL={aguardando_contexto:['warn','Aguardando contexto'],pronto_para_revisar:['good','Pronto para revisar'],revisao_necessaria:['warn','Revisão necessária'],exploratorio:['warn','Exploratório'],aprovado_para_edicao:['good','Aprovado para edição'],renderizado:['good','Renderizado'],pronto_para_distribuicao:['good','Pronto para distribuição'],revisao_humana:['bad','Precisa de revisão humana']};
function understoodHtml(pl){const ct=pl.contexto,eh=pl.entrega;
 if(!ct)return '<h4 aria-level="3">O que foi entendido do trecho</h4><p class="help">Este corte não tem a leitura de contexto (foi criado à mão ou por uma versão anterior).</p>';
 if(ct.erro)return '<h4 aria-level="3">O que foi entendido do trecho</h4><p class="help">A leitura de contexto falhou neste corte ('+esc(ct.erro)+'). O corte continua válido.</p>';
 const dm=ct.dimensoes||{},av=ct.avaliacao||{},ep=ct.episodios||[],need=(ct.contexto_necessario||{}).intervalos||[],face=ct.rosto;
 const st=STATE_LABEL[dm.estado]||['warn',dm.estado||'—'];
 const dimRow=k=>{const v=dm[k],l=DIM_LABEL[k];return `<span class="small" title="${esc(l[1])}">${l[0]}: <b>${v==null?'desconhecido':Math.round(v*100)+'%'}</b></span>`};
 return `<h4 aria-level="3">O que foi entendido do trecho</h4><div class="item"><div class="row"><span class="chip ${st[0]}">${st[1]}</span>${eh?`<span class="small muted">entrega: ${esc((STATE_LABEL[eh.state]||[0,eh.state])[1])}</span>`:''}</div>
 ${Object.keys(DIM_LABEL).map(dimRow).join('')}
 <span class="small muted">Estas notas são heurísticas, não probabilidades: não foram calibradas com dados reais.</span>
 ${(dm.aguardando||[]).map(x=>`<span class="small warn">Esperando: ${esc(x)}</span>`).join('')}
 ${av.abstencao?`<span class="small warn">Sem conclusão: ${esc(av.abstencao.replace(/_/g,' '))}</span>`:''}
 ${(av.conflitos||[]).map(x=>`<span class="small warn">Conflito: ${esc(x.replace(/_/g,' '))}</span>`).join('')}
 ${(av.notas||[]).map(x=>`<span class="small muted">• ${esc(x)}</span>`).join('')}
 <span class="small muted">Fontes independentes: ${av.fontes_independentes??'—'} (${esc((av.linhagens||[]).join(', ')||'nenhuma')}). Atribuição ao streamer: ${esc((av.estados||{}).atribuicao_ao_streamer||'não verificada').replace(/_/g,' ')}.</span>
 ${face?`<span class="small muted">Rosto: qualidade ${esc(face.level)}${face.fine_motion_ok?'':' · movimentos finos não podem ser afirmados com esta amostragem'}</span>`:'<span class="small muted">Rosto: qualidade desconhecida (sem leitura da webcam).</span>'}
 ${(ct.associacoes||[]).map(a=>`<span class="small muted">Reação em ${clock(a.reacao,1)}: ${a.evento?'depois de '+esc(a.evento.kind)+' ('+a.atraso_s+' s) — associação, não causa':'sem evento anterior observado'}</span>`).join('')}</div>
 ${ep.length?`<h4 aria-level="3">Episódios ligados</h4><div class="item">${ep.map(e=>`<span class="small">• ${esc(e.kind)} (${esc(e.status)}): ${esc(e.text)}</span>`).join('')}</div>`:''}
 ${need.length?`<h4 aria-level="3">Contexto anterior que o corte pressupõe</h4><div class="item">${need.map(n=>`<span class="small warn">${clock(n.start,1)}–${clock(n.end,1)}: ${esc(n.motivo)}${n.quote?' — “'+esc(n.quote)+'”':''}</span>`).join('')}<span class="small muted">Estenda o início do corte para incluir esse trecho ou aprove sabendo que o contexto fica de fora.</span></div>`:''}
 <h4 aria-level="3">Corrigir o contexto ou marcar um momento perdido</h4><div class="item">
 <div class="row"><input class="grow" id="ctxText" maxlength="300" placeholder="ex.: o 'ele' da fala é o Zeca, o amigo que entrou na call"><select id="ctxScope" aria-label="Alcance"><option value="job">só este corte</option><option value="session" selected>esta sessão</option><option value="creator">este streamer</option></select><button class="small" data-act="ctxfact">Salvar</button></div>
 <div class="row"><input id="missStart" type="number" min="0" step="0.5" placeholder="início (s)" style="width:110px"><input id="missEnd" type="number" min="0" step="0.5" placeholder="fim (s)" style="width:110px"></div>
 <div class="row"><input class="grow" id="missWhy" maxlength="300" placeholder="o que aconteceu que o programa não sugeriu"><button class="small" data-act="missed">Marcar momento perdido</button></div>
 <span class="small muted">Tempos em segundos da sessão. Isto fica guardado como caso de aprendizado; nada muda sozinho.</span></div>`}
async function loadPlan(){ST.planBusy=true;try{ST.plan=await api('/api/plan/get',{id:ST.id})}catch(e){ST.plan={decisoes:{},capacidades:{},estado:'em_revisao',pacote:{ok:false,problemas:[e.message]}}}finally{ST.planBusy=false;if(ST.secs.has('why'))drawRight()}}
async function chatCall(body){try{const r=await api('/api/converse',Object.assign({id:ST.id},body));ST.chat=r;if((r.aplicado||[]).length&&body.action!=='undo'||body.action==='undo'||body.action==='redo'){mutate(()=>{ST.proj=Object.assign(ST.proj,{cuts:r.projeto.cuts,zooms:r.projeto.zooms,sfx:r.projeto.sfx,speeds:r.projeto.speeds,freezes:r.projeto.freezes,replays:r.projeto.replays})})}else drawRight()}catch(e){toast(e.message,true)}}
function setPath(path,val){const parts=path.split('.');let o=ST.proj;for(let i=0;i<parts.length-1;i++){const k=parts[i];if(o[k]==null)o[k]=(['grade'].includes(k)?{contrast:1,saturation:1,brightness:0}:{});o=o[k]}o[parts[parts.length-1]]=val}
$('stRight').addEventListener('input',e=>{const f=e.target.dataset.f;if(f&&e.target.type==='range'){const o=$('stRight').querySelector(`[data-out="${f}"]`);if(o)o.textContent=(+e.target.value).toFixed(e.target.step&&e.target.step.includes('.')?2:0)}});
$('stRight').addEventListener('change',async e=>{const t=e.target,f=t.dataset.f;
 if(t.id==='imgFile'){const file=t.files[0];if(!file)return;try{const it=await upload('image',file);ST.data.images=(await api('/api/music/list',{})).images;toast('Imagem enviada.');addImage(it.id)}catch(err){toast(err.message,true)}return}
 if(t.dataset.fmt){mutate(()=>{const set=new Set(ST.proj.formats);t.checked?set.add(t.dataset.fmt):set.delete(t.dataset.fmt);ST.proj.formats=[...set]});return}
 if(t.dataset.ov!==undefined){mutate(()=>{ST.overrides[t.dataset.ov]=t.checked});return}
 if(!f)return;let v=t.type==='checkbox'?t.checked:t.value;const ty=t.dataset.t;if(ty==='num')v=+v;if(ty==='strnull'&&v==='')v=null;
 mutate(()=>{if(f.startsWith('layout.')&&!ST.proj.layout)ST.proj.layout=defaultLayout();if(f==='grade.contrast'||f==='grade.saturation'||f==='grade.brightness'){if(!ST.proj.grade)ST.proj.grade={contrast:1,saturation:1,brightness:0}}setPath(f,v);if(f.startsWith('titles.')&&f.endsWith('.end')){}})});
$('stRight').addEventListener('click',e=>{const t=e.target;
 const sec=t.closest('[data-sec]');if(sec){const id=sec.dataset.sec;ST.secs.has(id)?ST.secs.delete(id):ST.secs.add(id);drawRight();return}
 const ly=t.closest('[data-layout]');if(ly)return mutate(()=>{ST.proj.layout=Object.assign(ST.proj.layout||defaultLayout(),{mode:ly.dataset.layout})});
 const ui=t.closest('[data-useimg]');if(ui)return addImage(ui.dataset.useimg);
 if(t.id==='imgAdd')return $('imgFile').click();
 const ss=t.closest('[data-setstyle]');if(ss)return mutate(()=>{ST.proj.style=ss.dataset.setstyle});

 const op=t.closest('[data-op]');if(op)return selectionOp(op.dataset.op);
 const del=t.closest('[data-del]');if(del){const [k,i]=del.dataset.del.split(':');return mutate(()=>{ST.proj[k].splice(+i,1);ST.item=null})}
 const pk=t.closest('[data-pick]');if(pk&&!['INPUT','SELECT','BUTTON'].includes(t.tagName)){const [k,id]=pk.dataset.pick.split(':');ST.item=k==='cut'?{kind:k,k:id}:{kind:k,id};drawTimeline();const it=getItem(ST.item);if(it)seekClip(it.start??it.at)}
 const st=t.closest('[data-sugtitle]');if(st){const s=ST.data.suggestions.titles[+st.dataset.sugtitle];return mutate(()=>{const a=clamp(s.at,0,dur()-1);ST.proj.titles.push({id:uidc('t'),text:s.text,start:r2(a),end:r2(Math.min(dur(),a+3)),style:'big',position:'top',color:'#FFFFFF'})})}
 const a=t.closest('[data-act]');if(a)act_(a.dataset.act,a)});
function defaultLayout(){return{mode:ST.data.profile.content_mode==='video'?'fit':'cam_top',focus:.5,pip:'tr',pip_size:.36}}
function addImage(id){if(ST.proj.overlays.length>=10)return toast('Limite de 10 imagens.',true);const a=r2(curClip()),b=r2(Math.min(dur(),a+3));if(b-a<.3)return toast('Mova o cursor para antes do fim do corte.',true);mutate(()=>{const o={id:uidc('i'),image:id,start:a,end:b,x:.5,y:.4,scale:.45,opacity:1};ST.proj.overlays.push(o);ST.item={kind:'image',id:o.id}})}
async function drawPublish(){const box=$('pubBox');if(!box)return;try{const r=await api('/api/publication',{id:ST.id});box.innerHTML=`<pre class="pub">${esc(r.text)}</pre><div class="row"><button class="small" data-act="copypub">Copiar texto</button></div>`;box.dataset.text=r.text}catch(e){box.innerHTML=`<span class="muted small">${esc(e.message)}</span>`}const L=state.learning?.[state.candidates.find(x=>x.id===ST.id)?.streamer];const li=$('learnInfo');if(li&&L)li.textContent=L.used>=4?`O sistema já aprende com ${L.used} clipes.${L.up.length?' Está dando mais peso a: '+L.up.join(', ')+'.':''}${L.down.length?' Menos peso a: '+L.down.join(', ')+'.':''}`:`Faltam ${L.needed} clipe${L.needed===1?'':'s'} com 100+ visualizações para o sistema começar a aprender.`}
function act_(name,el){const d=ST.data;
 if(name==='deselect'){ST.item=null;drawRight();drawTimeline();return}
 if(name==='resetlayout')mutate(()=>{ST.proj.layout=null});
 if(name==='addspeed'){const [a0,b0]=range(3),a=r2(a0),b=r2(b0);if(b-a<.4)return toast('Selecione pelo menos 0,4 s para mudar a velocidade.',true);if(ST.proj.speeds.some(v=>a<v.end&&b>v.start))return toast('Esse trecho já tem outra velocidade.',true);if(ST.proj.speeds.length>=12)return toast('Limite de 12 trechos.',true);mutate(()=>{const v={id:uidc('v'),start:a,end:b,rate:2};ST.proj.speeds.push(v);ST.item={kind:'speed',id:v.id}})}
 if(name==='addfreeze'){if(ST.proj.freezes.length>=8)return toast('Limite de 8 congelamentos.',true);const at=r2(curClip());if(inCut(at,at))return toast('Esse ponto está dentro de um corte.',true);mutate(()=>{const f={id:uidc('f'),at,duration:1};ST.proj.freezes.push(f);ST.item={kind:'freeze',id:f.id}})}
 if(name==='copypub'){navigator.clipboard?.writeText($('pubBox').dataset.text||'').then(()=>toast('Texto copiado.'),()=>toast('Não consegui copiar. Selecione o texto e use Ctrl+C.',true))}
 if(name==='saveperf'){const g=k=>$('pf_'+k)?.value;api('/api/performance/save',{id:ST.id,views:g('views'),likes:g('likes'),comments:g('comments'),shares:g('shares'),saves:g('saves'),watch_pct:g('watch_pct'),url:g('url')}).then(async r=>{ST.data.performance=r.performance;await refresh(true);$('pfMsg').textContent='Salvo.';drawPublish()}).catch(e=>toast(e.message,true))}

 if(name==='resetgrade')mutate(()=>{ST.proj.grade=null});
 if(name==='refine'){api('/api/captions/refine',{id:ST.id,model:null}).then(()=>{ST.data.refine={status:'queued'};drawRight();toast('Revisão da legenda na fila. Leva alguns instantes.')}).catch(e=>toast(e.message,true))}
 if(name==='abtest'){persist({learn:true}).then(()=>api('/api/variant/ab',{id:ST.id})).then(r=>{toast('Variação B criada: '+r.change);refresh(true)}).catch(e=>toast(e.message,true))}
 if(name==='series'){persist({learn:true}).then(()=>api('/api/variant/series',{id:ST.id})).then(r=>{toast('Corte dividido em duas partes. '+r.reason);refresh(true)}).catch(e=>toast(e.message,true))}
 if(name==='resetcaps')mutate(()=>{Object.assign(ST.proj.captions,{style:null,size:null,margin:null,color:null})});
 if(name==='autolines')mutate(()=>{ST.lines=clone(d.auto_lines);ST.linesEdited=false});
 if(name==='rmteaser')mutate(()=>{ST.proj.teaser=null;if(ST.item?.kind==='teaser')ST.item=null});
 if(name==='suggteaser')mutate(()=>{ST.proj.teaser={start:d.suggestions.teaser.start,end:d.suggestions.teaser.end}});

 if(name==='say'){const t=$('chatText').value.trim();if(!t)return toast('Escreva o pedido.',true);chatCall({text:t,project:ST.proj})}
 if(name==='cconfirm')chatCall({action:'confirm'});
 if(name==='cundo')chatCall({action:'undo'});
 if(name==='credo')chatCall({action:'redo'});
 if(name==='missed'){const a=parseFloat($('missStart').value),b=parseFloat($('missEnd').value);if(!(a>=0&&b>a)){toast('Informe início e fim em segundos (o fim maior que o início).',true);return}
  api('/api/context/missed',{id:ST.id,start:a,end:b,reason:$('missWhy').value}).then(()=>toast('Momento perdido guardado como caso de aprendizado.')).catch(e=>toast(e.message,true));return}
 if(name==='ctxfact'){const t=$('ctxText').value.trim();if(!t){toast('Escreva a correção.',true);return}
  api('/api/context/fact',{session:ST.data.session,text:t,scope:$('ctxScope').value}).then(()=>{$('ctxText').value='';toast('Correção guardada (como hipótese, até você apontar o trecho).')}).catch(e=>toast(e.message,true));return}
 if(name==='approve'){api('/api/approve',{id:ST.id}).then(()=>{ST.plan=null;toast('Versão aprovada. Nada foi publicado.');drawRight()}).catch(e=>toast(e.message,true))}
 if(name==='project'||name==='projectfull'){const full=name==='projectfull';api('/api/package/project',{id:ST.id,include_sources:full,dry_run:full}).then(async r=>{if(full){const gb=(r.bytes_referencias_somente/1024**3).toFixed(2);if(r.ausentes.length){toast('Não achei: '+r.ausentes.join(', '),true);return}if(!confirm('Copiar '+r.fontes.length+' arquivo(s)-fonte, cerca de '+gb+' GB, para a pasta do corte?\nO plano e o perfil também serão salvos.'))return;r=await api('/api/package/project',{id:ST.id,include_sources:true,dry_run:false})}toast('Projeto salvo em '+r.pasta+(r.com_fontes?' (com fontes)':' (só referências: as fontes precisam continuar nos mesmos lugares)'))}).catch(e=>toast(e.message,true))}
 if(name==='package'){api('/api/package/build',{id:ST.id}).then(r=>{ST.plan=null;toast('Pacote montado. Estado: '+r.estado.replace(/_/g,' '));drawRight()}).catch(e=>toast(e.message,true))}
 if(name==='addsfx'){if(ST.proj.sfx.length>=16)return toast('Limite de 16 efeitos.',true);mutate(()=>{ST.proj.sfx.push({id:uidc('s'),kind:$('sfxKind').value,at:r2(curClip()),volume:.6})})}
 if(name==='hookcut'){const s=d.suggestions.hook.suggestion;mutate(()=>{ST.proj.cuts.push({start:0,end:r2(s.start),_k:uidc('c')})})}
 if(name==='bounds')changeBounds(+$('bStart').value,+$('bEnd').value);
 if(name==='ext'){const [a,b]=el.dataset.d.split(',').map(Number);changeBounds(ST.start+a,ST.end+b)}
 if(name==='tighten')changeBounds(d.suggestions.tighten.start,d.suggestions.tighten.end)}
async function changeBounds(a,b){if(!(b-a>=1&&b-a<=90&&a>=0))return toast('O corte precisa ter entre 1 e 90 segundos.',true);if(Math.abs(a-ST.start)<.01&&Math.abs(b-ST.end)<.01)return;
 try{ST.busy=true;drawBar();if(ST.dirty||ST.unlearned)await persist({learn:true,force:true});const r=await api('/api/project/save',{id:ST.id,version:ST.data.version,start:a,end:b});await reloadStudio(r.version);toast('Limites alterados. Gerando nova prévia.')}catch(e){toast(e.message,true)}finally{ST.busy=false;drawBar()}}
async function reloadStudio(){const d=await api('/api/project/get',{id:ST.id});clearTimeout(ST.saveTimer);Object.assign(ST,{plan:null,chat:null,data:d,proj:normProject(d.project),lines:clone(d.lines),linesEdited:d.lines_edited,overrides:{...d.overrides},start:d.start,end:d.end,dirty:false,savedRev:ST.rev,unlearned:false,undo:[],redo:[],music:d.music,sel:null,anchor:null,edit:-1,item:null,videoKey:ST.videoKey,pvSig:''});await refresh(true);drawAll();fitTimeline()}

/* ───── música no estúdio ───── */
async function drawMusicTab(){const box=$('stMusic');if(!box)return;const m=ST.proj.music,t=ST.music;
 if(m&&t){const T=t.duration||1,startMax=Math.max(0,T-5);
  box.innerHTML=`<div class="item" style="border-color:var(--teal)"><b>${esc(t.title)}</b><span class="muted small">${esc(t.uploader||'')} · ${clock(T)} ${t.bpm?'· '+Math.round(t.bpm)+' BPM':'· sem andamento detectado'}</span>${waveSvg(t.waveform,42,'#35d0ba',clamp(m.start/T,0,1),clamp((m.start+dur())/T,0,1))}<span class="help" style="margin:0">Trecho usado: ${clock(m.start)} a ${clock(Math.min(T,m.start+dur()))}</span></div>
  ${(()=>{const o=(path,label,min,max,step,val,f)=>`<div class="field"><label>${label}: <b data-out="${path}">${f(val)}</b></label><input type="range" data-f="${path}" data-t="num" min="${min}" max="${max}" step="${step}" value="${val}"></div>`;return o('music.start','Começar a música em',0,startMax,.5,m.start,v=>clock(+v))+o('music.volume','Volume',.02,.6,.01,m.volume,v=>Math.round(v*100)+'%')+o('music.fade_in','Entrada gradual',0,8,.1,m.fade_in,v=>(+v).toFixed(1)+'s')+o('music.fade_out','Saída gradual',0,8,.1,m.fade_out,v=>(+v).toFixed(1)+'s')})()}
  <label class="switch"><input type="checkbox" data-f="music.duck" data-t="bool" ${m.duck?'checked':''}><span>Abaixar a música quando há fala<small>Mantém a voz sempre clara.</small></span></label>
  <label class="switch" style="${m.authorized?'':'border-color:var(--amber)'}"><input type="checkbox" data-f="music.authorized" data-t="bool" ${m.authorized?'checked':''}><span>Posso usar esta música neste vídeo<small>Obrigatório para exportar. Música comercial pode ser silenciada ou receber reclamação no TikTok.</small></span></label>
  <div class="row"><button class="small" data-mact="best">Usar o melhor trecho</button><button class="small" data-mact="snap">Alinhar cortes às batidas</button><button class="small" data-mact="swap">Trocar</button><button class="small danger" data-mact="remove">Remover música</button></div>
  <div id="stMusicLib" class="hide" style="margin-top:6px"></div>`;
  box.onclick=ev=>{const b=ev.target.closest('[data-mact]');if(!b)return;const a=b.dataset.mact;
   if(a==='remove')mutate(()=>{ST.proj.music=null;ST.music=null});
   if(a==='best')mutate(()=>{ST.proj.music.start=Math.min(t.best_start||0,Math.max(0,t.duration-5))});
   if(a==='snap')snapToBeats();
   if(a==='swap')showLib(true)};
  }else{box.innerHTML='<div id="stMusicLib"></div>';box.onclick=null;showLib(false)}}
async function showLib(open){const lib=$('stMusicLib');if(!lib)return;lib.classList.remove('hide');await loadMusic();lib.innerHTML=musicHtml({pick:true,selected:ST.proj.music?.id});bindMusic(lib,{pick:(t,fresh)=>{mutate(()=>{ST.music=t;const keep=ST.proj.music;ST.proj.music={id:t.id,start:Math.min(t.best_start||0,Math.max(0,t.duration-5)),volume:keep?.volume||.14,fade_in:keep?.fade_in??.6,fade_out:keep?.fade_out??1.2,duck:keep?.duck??true,authorized:keep?.id===t.id?keep.authorized:false}});toast('Música aplicada. Marque a autorização para exportar.')},removed:id=>{if(ST.proj.music?.id===id)mutate(()=>{ST.proj.music=null;ST.music=null})}})}
function beatList(){const m=ST.proj.music,t=ST.music;if(!m||!t||!t.bpm)return[];const p=60/t.bpm,out=[];let i=Math.ceil((m.start-(t.first_beat||0))/p);for(;;i++){const b=(t.first_beat||0)+i*p;if(b>=m.start+dur())break;out.push(r2(b-m.start))}return out}
function snapToBeats(){const bt=beatList();if(!bt.length)return toast('Não detectei um andamento claro nesta música.',true);const near=v=>{let b=v,d=.2;for(const x of bt){if(Math.abs(x-v)<d){d=Math.abs(x-v);b=x}}return b};mutate(()=>{ST.proj.cuts.forEach(c=>{c.start=near(c.start);c.end=Math.max(c.start+.1,near(c.end))});ST.proj.zooms.forEach(z=>{z.start=near(z.start);z.end=Math.max(z.start+.4,near(z.end))});ST.proj.titles.forEach(t=>{t.start=near(t.start);t.end=Math.max(t.start+.5,near(t.end))})});toast('Cortes, zooms e títulos alinhados à batida mais próxima (até 0,2s).')}

/* ───── linha do tempo ───── */
function fitTimeline(){const w=$('tlScroll').clientWidth-24;ST.fit=Math.max(8,w/dur());if(!ST.pps)ST.pps=ST.fit;drawTimeline()}
const X=t=>t*ST.pps,T_=x=>x/ST.pps;
/* 3 pistas fixas (Vídeo, Legendas, Áudio); Zoom, Ritmo, Imagens e Títulos aparecem quando têm conteúdo
   (ou sempre, com "Todas as pistas"). */
function tlRows(){const P=ST.proj,all=PREF.allTracks,autoZ=(ST.data.decisions||[]).some(x=>x.kind==='zoom'&&(ST.overrides[x.id]??x.enabled));
 const r=[['video','Vídeo',30,true],['zoom','Zoom',30,all||P.zooms.length||autoZ],['speed','Ritmo',30,all||P.speeds.length||P.freezes.length],['image','Imagens',30,all||P.overlays.length],['speech','Legendas',30,true],['title','Títulos',30,all||P.titles.length||P.teaser],['audio','Áudio',36,true]].filter(x=>x[3]);
 let top=26;return r.map(([k,label,h])=>{const o={k,label,h,top};top+=h;return o})}
function drawTimeline(){if(!ST.open)return;const D=dur(),W=Math.ceil(D*ST.pps)+24,P=ST.proj,rows=tlRows(),R=Object.fromEntries(rows.map(x=>[x.k,x.top])),H=rows.reduce((a,x)=>a+x.h,26);
 $('tlHeads').innerHTML='<div></div>'+rows.map(x=>`<div style="height:${x.h}px">${x.label}</div>`).join('');
 let h=`<div class="tl" id="tl" style="width:${W}px;height:${H}px"><div class="ruler" id="ruler">`;
 const steps=[.5,1,2,5,10,15,30,60],step=steps.find(s=>s*ST.pps>=64)||60;for(let t=0;t<=D;t+=step)h+=`<div class="tick" style="left:${X(t)}px">${clock(t)}</div>`;h+='</div>';
 for(const x of rows)h+=`<div class="tr" data-row="${x.k}" style="top:${x.top}px;height:${x.h}px"></div>`;
 const blk=(cls,a,b,top,txt,attrs='',handles=true,sel=false)=>`<div class="blk ${cls}${sel?' sel':''}" style="left:${X(a)}px;width:${Math.max(6,X(b-a))}px;top:${top+3}px;bottom:auto;height:24px" ${attrs} title="${esc(txt)}">${handles?'<span class="h l"></span><span class="h r"></span>':''}${esc(txt)}</div>`;
 h+=`<div class="clipbar" style="top:${R.video+3}px;width:${X(D)}px"></div>`;
 autoCuts().forEach(c=>{h+=blk('cut auto',c.start,c.end,R.video,c.kind==='repetition'?'repetição':'pausa','',false)});
 P.cuts.forEach(c=>{h+=blk('cut',c.start,c.end,R.video,'cortar','data-kind="cut" data-key="'+c._k+'"',true,ST.item?.kind==='cut'&&ST.item.k===c._k)});
 ST.lines.forEach(l=>{h+=blk('speech',l.start,l.end,R.speech,l.text,`data-seek="${l.start}"`,false)});
 if(R.zoom!=null){P.zooms.forEach(z=>{h+=blk('zoom',z.start,z.end,R.zoom,z.zoom.toFixed(2)+'×','data-kind="zoom" data-key="'+z.id+'"',true,ST.item?.kind==='zoom'&&ST.item.id===z.id)});
  (ST.data.decisions||[]).filter(x=>x.kind==='zoom'&&(ST.overrides[x.id]??x.enabled)).forEach(x=>{h+=blk('zoom auto',+x.start,+x.end,R.zoom,'auto','',false)})}
 else P.zooms.forEach(z=>{h+=`<div class="tick-mark zoom" style="left:${X(z.start)}px;top:${R.video}px" title="zoom"></div>`});
 if(R.title!=null){P.titles.forEach(t=>{h+=blk('title',t.start,t.end,R.title,t.text,'data-kind="title" data-key="'+t.id+'"',true,ST.item?.kind==='title'&&ST.item.id===t.id)});
  if(P.teaser)h+=blk('teaser',P.teaser.start,P.teaser.end,R.title,'abertura','data-kind="teaser" data-key="t"',true,ST.item?.kind==='teaser')}
 if(R.speed!=null){P.speeds.forEach(v=>{h+=blk('speed',v.start,v.end,R.speed,fmtRate(v.rate),'data-kind="speed" data-key="'+v.id+'"',true,ST.item?.kind==='speed'&&ST.item.id===v.id)});
  P.freezes.forEach(f=>{h+=`<div class="mark freeze${ST.item?.kind==='freeze'&&ST.item.id===f.id?' sel':''}" data-kind="freeze" data-key="${f.id}" style="left:${X(f.at)}px;top:${R.speed+4}px" title="congelar ${f.duration}s">❄</div>`})}
 if(R.image!=null)P.overlays.forEach(o=>{h+=blk('image',o.start,o.end,R.image,'imagem','data-kind="image" data-key="'+o.id+'"',true,ST.item?.kind==='image'&&ST.item.id===o.id)});
 const m=P.music,t=ST.music;
 if(m&&t){const T=t.duration,visible=Math.min(D,T-m.start);h+=`<div class="mtrack" style="top:${R.audio+2}px;height:40px"><div style="position:absolute;left:0;top:0;bottom:0;width:${X(visible)}px;opacity:.85">${waveSvg(t.waveform,40,'#35d0ba',m.start/T,Math.min(1,(m.start+D)/T)).replace('class="wave"','class="wave" style="height:40px"')}</div>${beatList().map(b=>`<div class="beat" style="left:${X(b)}px"></div>`).join('')}</div>`}
 else h+=`<div class="tl-empty" style="top:${R.audio+13}px">Som original${P.sfx.length?'':' · sem música (Música, à direita)'}</div>`;
 P.sfx.forEach(e=>{h+=`<div class="mark${ST.item?.kind==='sfx'&&ST.item.id===e.id?' sel':''}" data-kind="sfx" data-key="${e.id}" style="left:${X(e.at)}px;top:${R.audio+4}px" title="${esc(e.kind)}">♪</div>`});
 if(ST.sel)h+=`<div class="selrange" style="left:${X(ST.sel.a)}px;width:${X(ST.sel.b-ST.sel.a)}px"></div>`;
 h+=`<div class="playhead" id="playhead" style="left:${X(curClip())}px"></div></div>`;
 const sc=$('tlScroll'),left=sc.scrollLeft;$('tl').outerHTML=h;sc.scrollLeft=left;$('selInfo').textContent=ST.sel?`Seleção ${clock(ST.sel.a,1)}–${clock(ST.sel.b,1)} (${(ST.sel.b-ST.sel.a).toFixed(1)}s) · C corta`:'Arraste na régua ou nas pistas para selecionar um trecho.';$('tlAll').setAttribute('aria-pressed',PREF.allTracks)}
function getItem(it){if(!it)return null;const P=ST.proj;if(it.kind==='cut')return P.cuts.find(c=>c._k===it.k);if(it.kind==='zoom')return P.zooms.find(z=>z.id===it.id);if(it.kind==='title')return P.titles.find(z=>z.id===it.id);if(it.kind==='teaser')return P.teaser;if(it.kind==='sfx')return P.sfx.find(e=>e.id===it.id);if(it.kind==='speed')return P.speeds.find(e=>e.id===it.id);if(it.kind==='freeze')return P.freezes.find(e=>e.id===it.id);if(it.kind==='image')return P.overlays.find(e=>e.id===it.id)}
const tlX=e=>e.clientX-$('tl').getBoundingClientRect().left;
/* Durante o arrasto só o bloco movido muda de lugar: evita reconstruir a linha do tempo inteira a cada pointermove (N5). Itens sem bloco (SFX/congelar) caem no redesenho completo. */
function dragPaint(b,it,kind){if(b&&b.isConnected&&b.classList.contains('blk')&&kind!=='sfx'&&kind!=='freeze'){b.style.left=X(it.start)+'px';b.style.width=Math.max(6,X(it.end-it.start))+'px'}else drawTimeline()}
function snapTargets(self){const P=ST.proj,t=[0,dur(),ST.cursor||0];for(const k of ['cuts','zooms','titles','speeds','overlays'])for(const x of P[k]||[])if(x!==self){t.push(x.start,x.end)}for(const k of ['sfx','freezes'])for(const x of P[k]||[])if(x!==self)t.push(x.at);return t}
/* Alinha ao alvo mais próximo (cursor, bordas de outros itens, início/fim) até 8 px. Alt desliga. */
function snapTo(v,self){const th=8/(ST.pps||1);let best=v,d=th;for(const x of snapTargets(self)){const k=Math.abs(x-v);if(k<d){d=k;best=x}}return best}
$('tlScroll').addEventListener('pointerdown',e=>{
 const b=e.target.closest('[data-kind]');
 if(b){const kind=b.dataset.kind,key=b.dataset.key;ST.item=kind==='cut'?{kind,k:key}:{kind,id:key};const it=getItem(ST.item);ST.undo.push(snap());ST.redo=[];const orig={...it},t0=T_(tlX(e)),mode=e.target.classList.contains('l')?'l':e.target.classList.contains('r')?'r':'m';let moved=false;
  const move=ev=>{const dt=T_(tlX(ev))-t0;if(Math.abs(dt)>.02)moved=true;const q=v=>Math.round(v*20)/20;
   const sn=v=>ev.altKey?v:snapTo(v,it);if(kind==='sfx'||kind==='freeze')it.at=clamp(sn(q(orig.at+dt)),0,dur());else{let a=orig.start,bb=orig.end;if(mode==='m'){const L=bb-a;a=q(a+dt);const sa=sn(a),sb=sn(a+L);if(sa!==a||sb!==a+L){a=(sa!==a&&(sb===a+L||Math.abs(sa-a)<=Math.abs(sb-a-L)))?sa:sb-L}a=clamp(a,0,dur()-L);bb=a+L}else if(mode==='l')a=clamp(sn(q(a+dt)),0,bb-.1);else bb=clamp(sn(q(bb+dt)),a+.1,dur());it.start=r2(a);it.end=r2(bb)}dragPaint(b,it,kind)};
  const up=()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);if(moved){changed();ST.proj.cuts.sort((a,b)=>a.start-b.start);ST.proj.zooms.sort((a,b)=>a.start-b.start);ST.proj.titles.sort((a,b)=>a.start-b.start);ST.proj.speeds.sort((a,b)=>a.start-b.start);ST.proj.freezes.sort((a,b)=>a.at-b.at);ST.proj.overlays.sort((a,b)=>a.start-b.start);drawAll()}else{ST.undo.pop();drawRight();drawTimeline();if(kind!=='sfx'&&kind!=='freeze')seekClip(it.start);else seekClip(it.at)}};
  drawRight();
  document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);e.preventDefault();return}
 if(e.target.closest('[data-seek]')){seekClip(+e.target.closest('[data-seek]').dataset.seek)}
 const t0=clamp(T_(tlX(e)),0,dur());let moved=false;ST.sel=null;
 const move=ev=>{const t=clamp(T_(tlX(ev)),0,dur());if(Math.abs(t-t0)>.12){moved=true;ST.sel={a:r2(Math.min(t0,t)),b:r2(Math.max(t0,t))};ST.anchor=null;drawTimeline();drawLeft()}};
 const up=()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);if(!moved){ST.item=null;seekClip(t0);drawRight();drawLeft();drawTimeline()}else{drawLeft();drawRight()}};
 document.addEventListener('pointermove',move);document.addEventListener('pointerup',up)});
$('tlIn').onclick=()=>{ST.pps=Math.min(ST.pps*1.5,400);drawTimeline()};$('tlFold').onclick=toggleFold;$('tlAll').onclick=()=>{PREF.allTracks=!PREF.allTracks;drawTimeline()};$('tlOut').onclick=()=>{ST.pps=Math.max(ST.fit,ST.pps/1.5);drawTimeline()};
window.addEventListener('resize',()=>{if(ST.open)fitTimeline()});

/* ───── player ───── */
const V=()=>$('stVideo');
function curClip(){const v=V();if(!ST.data||!ST.data.preview.available||!v||isNaN(v.currentTime)||!v.readyState)return ST.cursor||0;return finalToClip(v.currentTime)}
function seekClip(t){ST.cursor=t;const v=V();if(ST.data.preview.available&&v.readyState>0)v.currentTime=clipToFinal(t);updatePlayhead()}
function updatePlayhead(){const ph=$('playhead');if(ph){const t=curClip();ph.style.left=X(t)+'px';const sc=$('tlScroll'),x=X(t);if(x>sc.scrollLeft+sc.clientWidth-30||x<sc.scrollLeft)sc.scrollLeft=Math.max(0,x-60)}
 $('stTime').textContent=clock(V().currentTime||0,1)+' / '+clock(V().duration||0,1);
 const t=curClip();document.querySelectorAll('#lines .w.now').forEach(x=>x.classList.remove('now'));for(const w of document.querySelectorAll('#lines .w')){if(+w.dataset.a<=t&&t<+w.dataset.b){w.classList.add('now');break}}}
function loop(){if(!ST.open)return;if(!V().paused)updatePlayhead();drawLive();ST.raf=requestAnimationFrame(loop)}
$('stPlay').onclick=()=>{const v=V();if(!ST.data.preview.available)return toast('Aguarde a prévia ficar pronta.',true);v.paused?v.play():v.pause()};
$('stMute').onclick=()=>{const v=V();v.muted=!v.muted;$('stMute').textContent=v.muted?'🔇':'🔊';$('stMute').setAttribute('aria-label',v.muted?'Ligar o som':'Tirar o som')};
V().addEventListener('play',()=>{$('stPlay').textContent='⏸';$('stPlay').setAttribute('aria-label','Pausar')});V().addEventListener('pause',()=>{$('stPlay').textContent='▶';$('stPlay').setAttribute('aria-label','Reproduzir')});V().addEventListener('click',()=>$('stPlay').click());V().addEventListener('seeked',updatePlayhead);V().addEventListener('loadedmetadata',updatePlayhead);V().addEventListener('timeupdate',updatePlayhead);
$('safeToggle').onchange=()=>$('safe').classList.toggle('hide',!$('safeToggle').checked);
$('phone').addEventListener('click',e=>{if(e.target.id==='stRetryPrev')refreshPreview();if(e.target.id==='stGoCam'){leave();setTimeout(()=>{go('settings');showPane('cam')},50)}});

/* ───── salvar, aprovar, sair ─────
   Cada alteração é salva sozinha (sem ensinar a memória, sem zerar o desfazer). A prévia anterior continua tocando
   enquanto a nova é gerada. Salvar de propósito (Ctrl+S, sair, exportar) ensina a memória uma vez, com a diferença toda. */
function changed(){ST.rev++;ST.dirty=true;ST.saveErr='';clearTimeout(ST.saveTimer);ST.saveTimer=setTimeout(()=>persist({learn:false,preview:PREF.autoPrev}).catch(()=>{}),PREF.autoPrev?1600:900)}
function projectPayload(){const P=clone(ST.proj);P.cuts.forEach(c=>delete c._k);P.captions.lines=ST.linesEdited?ST.lines:null;return P}
let saveChain=Promise.resolve();
function persist({learn=true,preview=false,force=false}={}){clearTimeout(ST.saveTimer);
 const job=saveChain.then(async()=>{if(!ST.open)return;if(!ST.dirty&&!force&&!(learn&&ST.unlearned))return ST.data.version;
  const rev=ST.rev,P=projectPayload(),id=ST.id;ST.saving=true;drawBar();
  try{if(JSON.stringify(ST.overrides)!==JSON.stringify(ST.data.overrides)){const r=await api('/api/review',{id,version:ST.data.version,start:ST.start,end:ST.end,action:'save',edit_overrides:ST.overrides});ST.data.version=r.version;ST.data.overrides={...ST.overrides}}
   const r=await api('/api/project/save',{id,version:ST.data.version,project:P,preview,learn});if(ST.id!==id)return r.version;
   ST.data.version=r.version;ST.data.saved=true;ST.data.project=P;ST.savedRev=rev;ST.dirty=ST.rev!==rev;ST.unlearned=!learn;ST.saveErr='';
   const pv=ST.data.preview;if(pv.ready){pv.timing=ST.data.timing;pv.ready=false;pv.stale=true}if(preview)pv.status='queued';ST.pvSig=''
   return r.version}
  catch(e){ST.saveErr=e.message;if(learn||force)throw e}
  finally{ST.saving=false;if(ST.open)drawBar();refresh(true)}});
 saveChain=job.catch(()=>{});return job}
async function commit(preview=true){ST.dirty=true;const v=await persist({learn:true,preview,force:true});await reloadStudio(v);return v}
async function refreshPreview(){if(ST.busy)return;ST.busy=true;drawBar();try{if(ST.dirty||!ST.data.saved||ST.unlearned){await persist({learn:true,preview:true,force:true})}else{const r=await api('/api/review',{id:ST.id,version:ST.data.version,start:ST.start,end:ST.end,action:'preview'});ST.data.version=r.version;const pv=ST.data.preview;if(pv.ready){pv.timing=ST.data.timing;pv.ready=false;pv.stale=true}pv.status='queued'}toast('Gerando nova prévia…');await refresh(true)}catch(e){toast(e.message,true)}finally{ST.busy=false;drawBar()}}
async function saveNow(){try{await persist({learn:true,preview:false,force:ST.dirty||ST.unlearned});toast('Salvo.')}catch(e){toast(e.message,true)}}
$('stRefresh').onclick=refreshPreview;$('stState').onclick=()=>{if(ST.saveErr)saveNow()};
$('stAuto').onchange=()=>{PREF.autoPrev=$('stAuto').checked;if(PREF.autoPrev&&!ST.data.preview.ready)refreshPreview()};
async function leave(){if(ST.dirty||ST.unlearned){try{await persist({learn:true,preview:false,force:true})}catch(e){if(!confirm('Não consegui salvar ('+e.message+'). Sair mesmo assim e perder as últimas alterações?'))return}}
 closeStudio()}
function closeStudio(){clearTimeout(ST.saveTimer);ST.open=false;ST.decided=new Set();V().pause();cancelAnimationFrame(ST.raf);$('studio').classList.add('hide');document.body.style.overflow='';keys.cards='';refresh(true)}
$('stBack').onclick=leave;$('stUndo').onclick=undo;$('stRedo').onclick=redo;

/* fluxo de revisão: depois de decidir, abre o próximo corte pendente (mesma ordem da biblioteca) */
function reviewIds(){return pendingNow().map(c=>c.id)}
async function nextOrClose(){const list=reviewIds(),i=list.indexOf(ST.id);ST.decided=ST.decided||new Set();ST.decided.add(ST.id);const rest=list.filter(x=>!ST.decided.has(x));const next=rest[i]??rest[rest.length-1];
 if(next){await openStudio(next);toast('Próximo corte para revisar.')}else closeStudio()}
async function goClip(dir){if(ST.busy)return;if(ST.dirty||ST.unlearned){try{await persist({learn:true,force:true})}catch(e){toast(e.message,true);return}}
 const list=reviewIds(),i=list.indexOf(ST.id);const next=list[(i<0?0:i+dir)];if(!next||next===ST.id){toast(dir>0?'Não há próximo corte para revisar.':'Não há corte anterior.');return}await openStudio(next)}
function drawFlow(){const l=reviewIds(),i=l.indexOf(ST.id);$('stFlow').textContent=i>=0?`${i+1} de ${l.length}`:'';$('stFlow').title='[ e ] trocam de corte · R rejeita · ? mostra os atalhos'}
async function rejectClip(reason){closeRejectMenu();try{await api('/api/review',{id:ST.id,version:ST.data.version,start:ST.start,end:ST.end,action:'reject',reason});toast('Corte rejeitado.'+(reason?' Motivo guardado.':''));clearTimeout(ST.saveTimer);ST.dirty=false;ST.unlearned=false;await nextOrClose()}catch(e){toast(e.message,true)}}
function closeRejectMenu(){const m=$('rejectMenu');if(m)m.remove();document.removeEventListener('keydown',rejectKey,true)}
function rejectKey(e){if(e.key==='Escape'){e.stopPropagation();closeRejectMenu();return}if(/^[1-9]$/.test(e.key)){const r=Object.keys(state.reject_reasons||{})[+e.key-1];if(r){e.preventDefault();e.stopPropagation();rejectClip(r)}}}
$('stReject').onclick=()=>{if($('rejectMenu'))return closeRejectMenu();const reasons=state.reject_reasons||{};
 const m=document.createElement('div');m.id='rejectMenu';m.className='reject-menu';m.setAttribute('role','menu');
 m.innerHTML='<p class="help">Por que rejeitar? Um clique já rejeita e ensina o Hook’s.</p>'+Object.entries(reasons).map(([k,v],i)=>`<button role="menuitem" data-reason="${esc(k)}">${i+1} · ${esc(v)}</button>`).join('')+'<button role="menuitem" class="quiet" data-reason="">Rejeitar sem motivo</button>';
 m.onclick=e=>{const b=e.target.closest('[data-reason]');if(b)rejectClip(b.dataset.reason)};
 $('stReject').after(m);const r=$('stReject').getBoundingClientRect();m.style.top=(r.bottom+8)+'px';m.style.right=Math.max(8,innerWidth-r.right)+'px';document.addEventListener('keydown',rejectKey,true);m.querySelector('button').focus()};
document.addEventListener('click',e=>{if($('rejectMenu')&&!e.target.closest('#rejectMenu,#stReject'))closeRejectMenu()});
$('stApprove').onclick=async()=>{if(ST.busy)return;ST.busy=true;drawBar();try{if(ST.dirty||ST.unlearned)await persist({learn:true,force:true});const m=ST.proj.music;if(m&&!m.authorized){ST.secs.add('music');ST.item=null;drawRight();toast('Marque que você pode usar a música para exportar.',true);return}
  const a=ST.data.audit||{};if(a.requires_review){ $('auditList').innerHTML=(a.checks||[]).map(c=>`<div class="item"><span><span class="chip ${c.status==='ok'?'good':c.status==='block'?'bad':'warn'}">${esc(c.label)}</span> <span class="small muted">${esc(c.detail)}</span></span></div>`).join('');$('auditOk').checked=false;$('auditGo').disabled=true;$('confirmDialog').showModal()}else await doApprove(false)}catch(e){toast(e.message,true)}finally{ST.busy=false;drawBar()}};
$('auditOk').onchange=()=>$('auditGo').disabled=!$('auditOk').checked;
$('auditGo').onclick=async()=>{$('confirmDialog').close();try{await doApprove(true)}catch(e){toast(e.message,true)}};
async function doApprove(ok){const q=$('stQuality').value;await api('/api/review',{id:ST.id,version:ST.data.version,start:ST.start,end:ST.end,action:'approve',editorial_confirmed:ok,edit_overrides:ST.overrides,quality_mode:q});toast('Exportação na fila ('+($('stQuality').selectedOptions[0]?.textContent||q)+'). Acompanhe em Cortes → Na fila.');ST.dirty=false;ST.unlearned=false;await nextOrClose()}
let approveArmed=0;
const SHORTCUTS=[['Espaço','reproduzir / pausar'],['← →','voltar / avançar 1 s (Shift: 5 s)'],['C','cortar o trecho selecionado'],['Delete','remover o item selecionado'],['Esc','limpar seleção'],['Ctrl+Z / Ctrl+Shift+Z','desfazer / refazer'],['Ctrl+S','salvar agora (salva sozinho também)'],['P','atualizar a prévia'],['F','recolher/mostrar a linha do tempo (prévia maior)'],['[ ]','corte anterior / próximo'],['R','rejeitar'],['Ctrl+Enter (2×)','exportar'],['+ −','zoom da linha do tempo'],['Alt (ao arrastar)','desliga o alinhamento magnético'],['Ctrl+K','buscar e executar qualquer ação'],['?','mostrar estes atalhos']];
/* ── Busca de ações (Ctrl+K): lista só o que se pode fazer agora; acentos e maiúsculas não importam ── */
const norm=x=>String(x).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
function commands(){const P=ST.proj,sel=!!ST.sel,d=ST.data,list=[
 ['Cortar o trecho selecionado','C','remover apagar tirar',sel,()=>selectionOp('cut')],
 ['Dar zoom no trecho selecionado','','aproximar ampliar',sel,()=>selectionOp('zoom')],
 ['Adicionar título no trecho selecionado','','texto na tela',sel,()=>selectionOp('title')],
 ['Limpar seleção','Esc','desmarcar',sel||!!ST.item,()=>{ST.sel=null;ST.anchor=null;ST.item=null;drawLeft();drawTimeline();drawRight()}],
 ['Remover o item selecionado','Delete','apagar excluir',!!ST.item,()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'Delete',bubbles:true}))],
 ['Desfazer','Ctrl+Z','voltar',ST.undo.length>0,undo],['Refazer','Ctrl+Shift+Z','',ST.redo.length>0,redo],
 ['Salvar agora','Ctrl+S','gravar',true,()=>saveNow()],
 ['Atualizar a prévia','P','renderizar gerar',!ST.busy,()=>refreshPreview()],
 ['Reproduzir / pausar','Espaço','play tocar',true,()=>$('stPlay').click()],
 ['Corte anterior','[','voltar clipe',true,()=>goClip(-1)],['Próximo corte','] ','avancar clipe',true,()=>goClip(1)],
 ['Recolher / mostrar a linha do tempo (prévia maior)','F','ampliar previa foco',true,toggleFold],
 ['Aproximar a linha do tempo','+','zoom timeline',true,()=>$('tlIn').click()],['Afastar a linha do tempo','−','zoom timeline',true,()=>$('tlOut').click()],
 ['Mostrar todas as pistas','','pistas vazias',true,()=>$('tlAll').click()],
 ['Mostrar / esconder zonas seguras','','margens tiktok',true,()=>$('safeToggle').click()],
 ['Ligar / desligar legendas ao vivo','','previa legenda',true,()=>$('liveToggle').click()],
 ['Ligar / desligar prévia automática','','autoprevia',true,()=>$('stAuto').click()],
 ['Rejeitar este corte','R','descartar',true,()=>$('stReject').click()],
 ['Ir para Exportar (confirme com Enter no botão)','Ctrl+Enter ×2','aprovar enviar',!ST.busy,()=>{$('stApprove').focus();toast('Exportar: pressione Enter no botão destacado para confirmar.')}],
 ['Mostrar os atalhos do teclado','?','ajuda',true,showKeys],
 ['Voltar à biblioteca','','sair fechar',true,()=>leave()]];
 for(const [id,label] of SECTIONS)if(id!=='pub'||d.status==='done')list.push(['Abrir seção: '+label,'','inspetor painel',true,()=>{ST.secs.add(id);drawRight();const e=document.querySelector('[data-sec="'+id+'"]');if(e)e.scrollIntoView({block:'nearest'})}]);
 return list.filter(x=>x[3]).map(([label,key,words,,run])=>({label,key:key.trim(),words,run,hay:norm(label+' '+words+' '+key)}))}
const CMDK={items:[],shown:[],at:0};
function cmdRender(){const q=norm($('cmdInput').value).split(/\s+/).filter(Boolean);
 CMDK.shown=CMDK.items.filter(c=>q.every(t=>c.hay.includes(t))).sort((a,b)=>(norm(b.label).startsWith(q[0]||'~')?1:0)-(norm(a.label).startsWith(q[0]||'~')?1:0));
 CMDK.at=Math.min(CMDK.at,Math.max(0,CMDK.shown.length-1));
 $('cmdList').innerHTML=CMDK.shown.length?CMDK.shown.map((c,i)=>`<li role="option" id="cmd${i}" data-i="${i}" class="${i===CMDK.at?'on':''}" aria-selected="${i===CMDK.at}"><span class="lbl">${esc(c.label)}</span>${c.key?`<kbd>${esc(c.key)}</kbd>`:''}</li>`).join(''):'<li class="empty" role="option" aria-disabled="true">Nenhuma ação encontrada.</li>';
 $('cmdInput').setAttribute('aria-activedescendant',CMDK.shown.length?'cmd'+CMDK.at:'')}
function cmdOpen(){const d=$('cmdDialog');if(d.open)return;CMDK.items=commands();CMDK.at=0;$('cmdInput').value='';cmdRender();d.showModal();$('cmdInput').focus()}
function cmdRun(i){const c=CMDK.shown[i];if(!c)return;$('cmdDialog').close();setTimeout(()=>{try{c.run()}catch(e){toast(e.message,true)}},0)}
$('cmdInput').addEventListener('input',()=>{CMDK.at=0;cmdRender()});
$('cmdInput').addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=CMDK.shown.length;if(n){CMDK.at=(CMDK.at+(e.key==='ArrowDown'?1:n-1))%n;cmdRender();const el=$('cmd'+CMDK.at);if(el)el.scrollIntoView({block:'nearest'})}}else if(e.key==='Enter'){e.preventDefault();cmdRun(CMDK.at)}});
$('cmdList').addEventListener('click',e=>{const li=e.target.closest('li[data-i]');if(li)cmdRun(+li.dataset.i)});
$('stCmd').onclick=cmdOpen;
document.addEventListener('keydown',e=>{if(ST.open&&(e.ctrlKey||e.metaKey)&&!e.shiftKey&&!e.altKey&&e.key.toLowerCase()==='k'&&!document.querySelector('dialog[open]')){e.preventDefault();cmdOpen()}});
function showKeys(){const d=$('keysDialog');$('keysList').innerHTML=SHORTCUTS.map(([k,v])=>`<div class="row"><kbd>${k}</kbd><span class="grow">${v}</span></div>`).join('');d.showModal()}
document.addEventListener('keydown',e=>{if(!ST.open||document.querySelector('dialog[open]'))return;const tag=(e.target.tagName||'');const typing=['INPUT','TEXTAREA','SELECT'].includes(tag);const mod=e.ctrlKey||e.metaKey;
 if(mod&&e.key.toLowerCase()==='z'){if(typing)return;e.preventDefault();e.shiftKey?redo():undo();return}
 if(mod&&e.key.toLowerCase()==='y'){if(typing)return;e.preventDefault();redo();return}
 if(mod&&e.key.toLowerCase()==='s'){e.preventDefault();saveNow();return}
 if(mod&&e.key==='Enter'){e.preventDefault();const now=Date.now();if(now-approveArmed<2500){approveArmed=0;$('stApprove').click()}else{approveArmed=now;toast('Pressione Ctrl+Enter de novo para exportar este corte.')}return}
 if(typing||mod||e.altKey)return;
 const k=e.key;
 if(k===']'){e.preventDefault();goClip(1);return}
 if(k==='['){e.preventDefault();goClip(-1);return}
 if(k.toLowerCase()==='r'){e.preventDefault();$('stReject').click();return}
 if(k.toLowerCase()==='p'){e.preventDefault();refreshPreview();return}
 if(k.toLowerCase()==='f'){e.preventDefault();toggleFold();return}
 if(k==='?'){e.preventDefault();showKeys();return}
 if(k===' '){e.preventDefault();$('stPlay').click();return}
 if(k==='ArrowLeft'||k==='ArrowRight'){e.preventDefault();const step=(e.shiftKey?5:1)*(k==='ArrowLeft'?-1:1);seekClip(clamp(curClip()+step,0,dur()));return}
 if(k==='+'||k==='='){ $('tlIn').click();return}
 if(k==='-'){ $('tlOut').click();return}
 if(k==='Delete'||k==='Backspace'){const it=ST.item;if(!it)return;e.preventDefault();mutate(()=>{const P=ST.proj;if(it.kind==='cut')P.cuts=P.cuts.filter(c=>c._k!==it.k);if(it.kind==='zoom')P.zooms=P.zooms.filter(z=>z.id!==it.id);if(it.kind==='title')P.titles=P.titles.filter(z=>z.id!==it.id);if(it.kind==='teaser')P.teaser=null;if(it.kind==='sfx')P.sfx=P.sfx.filter(z=>z.id!==it.id);if(it.kind==='speed')P.speeds=P.speeds.filter(z=>z.id!==it.id);if(it.kind==='freeze')P.freezes=P.freezes.filter(z=>z.id!==it.id);if(it.kind==='image')P.overlays=P.overlays.filter(z=>z.id!==it.id);ST.item=null});return}
 if(k.toLowerCase()==='c'&&ST.sel){selectionOp('cut');return}
 if(k==='Escape'){ST.sel=null;ST.anchor=null;ST.item=null;drawLeft();drawTimeline();drawRight()}});
$('stKeys').onclick=showKeys;

document.addEventListener('click',async e=>{if(e.target.id!=='deliverRetry')return;e.target.disabled=true;try{const r=await api('/api/delivery/retry',{id:ST.id});toast(r.delivery.status==='ok'?'Copiado para a pasta de entrega.':'Ainda não deu: '+(r.delivery.error||r.delivery.status),r.delivery.status!=='ok');await refresh(true);if(ST.open)drawRight()}catch(err){toast(err.message,true);e.target.disabled=false}});
