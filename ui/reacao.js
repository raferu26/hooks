/* Layout de reação (sem IA): escolher o layout, MARCAR as regiões no quadro ORIGINAL e ajustar a composição.
   A geometria vem do servidor (/api/composition/resolve = o mesmo resolve() do render); aqui só se desenha.
   Coordenadas das regiões: frações 0–1 do quadro de exibição da fonte (origem no canto superior esquerdo).
   Transformação do seletor: ponteiro (px da tela) → retângulo da <img> (getBoundingClientRect) → fração 0–1 → região salva
   → crop em pixels da fonte (servidor) → filtro crop= do FFmpeg. A <img> não tem letterbox, então a fração é direta. */
const RX={presets:null,presetSel:'',applyOpen:false,applyPick:{},plan:null,key:'',frameImg:null,frameKey:'',picker:null,more:false,busy:0,t:null};
const RX_COLORS={webcam:'#35d0ba',conteudo:'#4f9bff',webcam2:'#f5a524'};
const RX_ROLE={webcam:'Webcam',conteudo:'Conteúdo',webcam2:'Webcam 2'};
const RX_DIAG={
 cam_compacta:'<i style="top:0;height:30%;left:0;right:0;background:#35d0ba"></i><i style="top:30%;bottom:0;left:0;right:0;background:#4f7aa8"></i>',
 cam_ampliada:'<i style="top:0;height:45%;left:0;right:0;background:#35d0ba"></i><i style="top:45%;bottom:0;left:0;right:0;background:#4f7aa8"></i>',
 cam_flutuante:'<i style="inset:0;background:#4f7aa8"></i><i style="top:6%;right:6%;width:38%;height:20%;background:#35d0ba;outline:1px solid #fff"></i>',
 cam_embaixo:'<i style="top:0;height:62%;left:0;right:0;background:#4f7aa8"></i><i style="top:62%;bottom:0;left:0;right:0;background:#35d0ba"></i>',
 foco_reacao:'<i style="inset:0;background:#35d0ba"></i><i style="bottom:6%;right:6%;width:42%;height:22%;background:#4f7aa8;outline:1px solid #fff"></i>',
 dueto:'<i style="top:0;bottom:0;left:0;width:49%;background:#35d0ba"></i><i style="top:0;bottom:0;right:0;width:49%;background:#f5a524"></i>',
 duas_cams:'<i style="top:0;height:34%;left:0;width:49%;background:#35d0ba"></i><i style="top:0;height:34%;right:0;width:49%;background:#f5a524"></i><i style="top:35%;bottom:0;left:0;right:0;background:#4f7aa8"></i>',
 cinema:'<i style="top:0;height:28%;left:0;right:0;background:#35d0ba"></i><i style="top:28%;bottom:0;left:0;right:0;background:#1b2a40"></i><i style="top:42%;height:34%;left:0;right:0;background:#4f7aa8"></i>'};
const RX_SPLIT={cam_compacta:'Altura da webcam',cam_ampliada:'Altura da webcam',cam_embaixo:'Altura do conteúdo',cinema:'Altura da webcam',duas_cams:'Altura das webcams',dueto:'Largura da pessoa 1'};
const RX_FITS=[['fill','Preencher','Ocupa a área toda, cortando o que passar. Sem distorcer.'],['fit','Mostrar inteiro','Mostra a região toda; pode sobrar fundo.'],['custom','Personalizado','Preenche com zoom e foco ajustáveis.']];
const rxCat=()=>ST.data.catalog.composition;
const rxLayout=id=>rxCat().layouts.find(l=>l.id===id);
const rxComp=()=>ST.proj&&ST.proj.composition;
const rxMissing=c=>c?rxLayout(c.layout).roles.filter(r=>!c.regions[r]):[];
const rxReady=c=>!!c&&!rxMissing(c).length;
function rxCard(l,sel){return `<button class="layout-opt" aria-pressed="${sel}" data-rxl="${l.id}" title="${esc(l.hint)}"><span class="mini">${RX_DIAG[l.id]}</span><b>${esc(l.label)}</b></button>`}
function rxParams(c){return Object.assign({},rxLayout(c.layout).params,c.params||{})}
function rxRange(key,label,lo,hi,step,val,fmt){return `<div class="fld"><label>${label} <span class="muted small" data-out="rx.${key}">${fmt(val)}</span></label><input type="range" min="${lo}" max="${hi}" step="${step}" value="${val}" data-rxf="${key}" data-t="num"></div>`}
function rxFitBlock(c,p,prefix,label){const fit=p[prefix+'_fit'];
 let h=`<div class="fld"><label>${label}</label><div class="seg">${RX_FITS.map(([k,t,tip])=>`<button type="button" class="small" aria-pressed="${fit===k}" title="${esc(tip)}" data-rxfit="${prefix}:${k}">${t}</button>`).join('')}</div></div>`;
 if(fit==='custom')h+=rxRange(prefix+'_zoom','Zoom',1,4,.05,p[prefix+'_zoom'],v=>(+v).toFixed(2)+'×')+rxRange(prefix+'_fx','Foco horizontal',0,1,.02,p[prefix+'_fx'],v=>Math.round(v*100)+'%')+rxRange(prefix+'_fy','Foco vertical',0,1,.02,p[prefix+'_fy'],v=>Math.round(v*100)+'%');
 else if(fit==='fill')h+=rxRange(prefix+'_fx','Parte que aparece (esq. ↔ dir.)',0,1,.02,p[prefix+'_fx'],v=>Math.round(v*100)+'%')+rxRange(prefix+'_fy','Parte que aparece (cima ↔ baixo)',0,1,.02,p[prefix+'_fy'],v=>Math.round(v*100)+'%');
 return h}
function reacaoHtml(d,P){const cat=rxCat(),c=P.composition,main=cat.layouts.filter(l=>l.group==='main'),more=cat.layouts.filter(l=>l.group==='more');
 let h=`<h4 aria-level="3">Layout de reação</h4><p class="help">Para vídeos de reação: mostre a webcam do streamer e o conteúdo ao mesmo tempo, escolhendo as partes do vídeo original.</p>`;
 h+=`<div class="layout-grid">${main.map(l=>rxCard(l,c&&c.layout===l.id)).join('')}</div>`;
 const moreOpen=RX.more||(c&&more.some(l=>l.id===c.layout));
 h+=`<div class="row"><button class="small quiet" data-rx="more" aria-expanded="${moreOpen}">${moreOpen?'Menos layouts':'Mais layouts'}</button></div>`;
 if(moreOpen)h+=`<div class="layout-grid">${more.map(l=>rxCard(l,c&&c.layout===l.id)).join('')}</div>`;
 h+=rxPresetsHtml(c);
 if(!c)return h+`<p class="help">Escolha um modelo para começar. Depois você marca a webcam e o conteúdo direto no vídeo.</p>`;
 const lay=rxLayout(c.layout),p=rxParams(c),miss=rxMissing(c);
 h+=`<p class="help">${esc(lay.hint)}</p>`;
 h+=`<h4 aria-level="3">Quais partes do vídeo aparecem?</h4><div class="list">${lay.roles.map(r=>{const done=!!c.regions[r];return `<div class="item"><div class="row"><span class="rx-dot" style="background:${RX_COLORS[r]}"></span><b class="grow">${RX_ROLE[r]}</b><span class="muted small">${done?'✓ marcada':'falta marcar'}</span><button class="small ${done?'':'primary'}" data-rx="pick:${r}">${done?'Refazer':'Selecionar'}</button></div></div>`}).join('')}</div>`;
 if(miss.length)return h+`<p class="help">Marque ${miss.map(r=>RX_ROLE[r]).join(' e ')} no vídeo original. Até lá o enquadramento padrão continua valendo.</p>${rxRemove()}`;
 h+=`<h4 aria-level="3">Ajustar composição</h4><div class="rx-prev"><canvas id="rxCanvas" width="216" height="384" aria-label="Prévia imediata da composição"></canvas><div id="rxWarn" class="help"></div></div>`;
 if(RX_SPLIT[c.layout])h+=rxRange('split',RX_SPLIT[c.layout],.15,.85,.01,p.split,v=>Math.round(v*100)+'%');
 if(c.layout==='duas_cams')h+=rxRange('col_split','Largura da webcam 1',.25,.75,.01,p.col_split,v=>Math.round(v*100)+'%');
 if(['cam_compacta','cam_ampliada','cam_embaixo','cinema','duas_cams','dueto'].includes(c.layout))h+=rxRange('gap','Separação entre áreas',0,40,2,p.gap,v=>v+' px');
 if(['cam_flutuante','foco_reacao'].includes(c.layout)){
  h+=`<div class="fld"><label>Posição da janela</label><select data-rxf="pip" data-t="str">${[['tr','Cima, à direita'],['tl','Cima, à esquerda'],['br','Baixo, à direita'],['bl','Baixo, à esquerda'],['free','Livre (X e Y)']].map(([k,t])=>`<option value="${k}" ${p.pip===k?'selected':''}>${t}</option>`).join('')}</select></div>`;
  if(p.pip==='free')h+=rxRange('pip_x','Horizontal',0,1,.01,p.pip_x,v=>Math.round(v*100)+'%')+rxRange('pip_y','Vertical',0,1,.01,p.pip_y,v=>Math.round(v*100)+'%');
  h+=rxRange('pip_size','Tamanho da janela',.15,.7,.01,p.pip_size,v=>Math.round(v*100)+'%')+rxRange('pip_border','Borda',0,12,1,p.pip_border,v=>v+' px');
  if(c.layout==='foco_reacao')h+=`<label class="switch"><input type="checkbox" data-rxf="hide_content" data-t="bool" ${p.hide_content?'checked':''}><span>Ocultar o conteúdo<small>Mostra só o streamer.</small></span></label>`}
 h+=rxFitBlock(c,p,'cam',lay.roles.includes('conteudo')?'Webcam':'Pessoa 1');
 if(lay.roles.includes('webcam2'))h+=rxFitBlock(c,p,'cam2','Webcam 2');
 if(lay.roles.includes('conteudo'))h+=rxFitBlock(c,p,'content','Conteúdo');
 h+=`<div class="fld"><label>Fundo (onde sobra espaço)</label><select data-rxf="bg" data-t="str">${[['black','Preto'],['color','Cor sólida'],['blur','Desfocado (do próprio vídeo)']].map(([k,t])=>`<option value="${k}" ${p.bg===k?'selected':''}>${t}</option>`).join('')}</select></div>`;
 if(p.bg==='color')h+=`<div class="fld"><label>Cor do fundo</label><input type="color" data-rxf="bg_color" data-t="str" value="${p.bg_color}"></div>`;
 h+=rxScenesHtml(c);
 h+=rxApplyHtml();
 return h+`<p class="help">A prévia acima usa um quadro do vídeo e as mesmas regras da exportação. A prévia em vídeo (P) mostra o resultado real.</p>`+rxRemove()}
function rxPresetsHtml(c){const L=RX.presets;if(!L)return '';const sel=L.find(p=>p.id===RX.presetSel);
 let h=`<h4 aria-level="3">Meus layouts</h4><div class="row"><select id="rxPreset" class="grow" aria-label="Layouts salvos"><option value="">Escolher…</option>${L.map(p=>`<option value="${esc(p.id)}" ${p.id===RX.presetSel?'selected':''}>${esc(p.name)}${p.has_regions?(p.compatible?' · com regiões':' · regiões de outro formato'):''}</option>`).join('')}</select><button class="small" data-rx="preset-apply" ${sel?'':'disabled'}>Aplicar</button></div>`;
 if(sel&&!sel.builtin)h+=`<div class="row"><button class="small quiet" data-rx="preset-rename">Renomear</button><button class="small quiet" data-rx="preset-dup">Duplicar</button><button class="small quiet danger" data-rx="preset-del">Excluir</button></div>`;
 if(c)h+=`<div class="row"><input id="rxPresetName" class="grow" type="text" maxlength="60" placeholder="Nome do layout" aria-label="Nome do layout"><button class="small" data-rx="preset-save">Salvar atual</button></div><label class="switch"><input type="checkbox" id="rxPresetRegions"><span>Guardar também as regiões marcadas<small>Só será reaproveitado em vídeos com a mesma proporção.</small></span></label>`;
 return h}
function rxApplyHtml(){const me=state.candidates.find(x=>x.id===ST.id);if(!me)return '';const others=state.candidates.filter(x=>x.session===me.session&&x.id!==ST.id&&!['exporting','done','replaced'].includes(x.status));
 if(!others.length)return '';
 let h=`<div class="row"><button class="small" data-rx="apply-toggle" aria-expanded="${RX.applyOpen}">Aplicar a outros cortes…</button></div>`;
 if(RX.applyOpen)h+=`<div class="list">${others.slice(0,40).map(x=>`<label class="switch"><input type="checkbox" data-rxa="${esc(x.id)}" ${RX.applyPick[x.id]?'checked':''}><span>${clock(x.start,1)}–${clock(x.end,1)}<small>${esc((x.title||x.hook||'').toString().slice(0,60))}</small></span></label>`).join('')}</div><div class="row"><button class="small" data-rx="apply-sel">Aplicar nos marcados</button><button class="small primary" data-rx="apply-all">Aplicar em todos (${others.length})</button></div><p class="help">Cortes já exportados não são alterados. Se a proporção do vídeo for diferente, as regiões não são copiadas.</p>`;
 return h}
async function rxLoadPresets(){try{RX.presets=(await api('/api/composition/presets',{action:'list',id:ST.id})).presets;drawRight()}catch(e){RX.presets=[]}}
async function rxPresetCall(body){try{RX.presets=(await api('/api/composition/presets',Object.assign({id:ST.id},body))).presets;drawRight();return true}catch(e){toast(e.message,true);return false}}
const RX_FADES=[[0,'Corte direto'],[.3,'Suave (0,3 s)'],[.6,'Suave (0,6 s)']];
function rxSceneEditor(o,i){const c=rxComp(),L=rxCat().layouts,base=`composition.scenes.${i}`;
 const miss=rxMissing({layout:o.layout,regions:c.regions});
 return `<div class="field"><label>Layout nesta cena</label><select data-f="${base}.layout" data-t="str">${L.map(l=>`<option value="${l.id}" ${o.layout===l.id?'selected':''}>${esc(l.label)}</option>`).join('')}</select></div>
 <div class="two"><div><label>De (s)</label><input type="number" step=".1" min="0" data-f="${base}.start" data-t="num" value="${o.start}"></div><div><label>Até (s)</label><input type="number" step=".1" min="0" data-f="${base}.end" data-t="num" value="${o.end}"></div></div>
 <div class="field"><label>Transição ao entrar e ao sair</label><select data-f="${base}.fade" data-t="num">${RX_FADES.map(([v,t])=>`<option value="${v}" ${(+o.fade||0)===v?'selected':''}>${t}</option>`).join('')}</select></div>
 ${miss.length?`<div class="banner">Este layout precisa de ${miss.map(r=>RX_ROLE[r]).join(' e ')}, que ainda não foi marcada. A cena é ignorada até lá.</div>`:''}
 <div class="row"><button class="small" data-rx="scene-copy:${o.id}" title="Copia o layout e os ajustes desta cena">Copiar</button><button class="small" data-rx="scene-params:${o.id}" title="Usa os ajustes do layout principal nesta cena">Usar ajustes do principal</button></div>
 <p class="help" style="margin:0">${(o.end-o.start).toFixed(1)} s. Ao exportar, a cena acompanha cortes, velocidade e replays.</p>`}
function rxScenesHtml(c){const sc=(c.scenes||[]);
 let h=`<h4 aria-level="3">Cenas de reação</h4><p class="help">Troque o layout em partes do clipe (por exemplo, foco na reação enquanto o streamer comenta). Fora das cenas vale o layout principal.</p>`;
 h+=`<div class="row"><button class="small" data-rx="scene-add">＋ Cena na seleção</button>${RX.sceneClip?`<button class="small" data-rx="scene-paste">Colar na seleção</button>`:''}</div>`;
 if(sc.length)h+=`<div class="list">${sc.map(x=>`<div class="item ${ST.item?.kind==='scene'&&ST.item.id===x.id?'sel':''}" data-pick="scene:${x.id}"><div class="row"><b class="grow">${esc(rxLayout(x.layout).label)}</b><span class="muted small">${clock(x.start,1)}–${clock(x.end,1)}${x.fade?' · suave':''}</span></div></div>`).join('')}</div>`;
 const bad=sc.some((a,k)=>k&&a.start<sc[k-1].end-.001);if(bad)h+=`<div class="banner">Há cenas sobrepostas: ajuste os tempos (não é possível salvar assim).</div>`;
 return h}
function rxPickSceneLayout(){const c=rxComp();return c.layout==='foco_reacao'?'cam_ampliada':'foco_reacao'}
function rxNewScene(layout,params){const sorted=((ST.proj.composition.scenes)||[]).slice().sort((a,b)=>a.start-b.start);const [a0,b0]=range(3),a=r2(a0),b=r2(b0);
 if(b-a<.4)return toast('Selecione pelo menos 0,4 s na linha do tempo (ou posicione o cursor antes do fim).',true);
 if(sorted.some(x=>a<x.end&&b>x.start))return toast('Esse trecho já tem outra cena.',true);
 const sc={id:uidc('e'),start:a,end:b,layout,params:Object.assign({},params||{}),fade:0};
 mutate(()=>{const c=ST.proj.composition;c.scenes=(c.scenes||[]).concat([sc]).sort((x,y)=>x.start-y.start);ST.item={kind:'scene',id:sc.id}})}
function rxRemove(){return `<div><button class="small quiet danger" data-rx="remove">Voltar ao enquadramento padrão</button></div>`}

/* ───────── prévia imediata (canvas) ───────── */
function rxFrameUrl(t){return `/media/srcframe?id=${encodeURIComponent(ST.id)}&t=${(+t||0).toFixed(2)}`}
function rxLoadFrame(t){const key=rxFrameUrl(t);if(RX.frameKey===key&&RX.frameImg&&RX.frameImg.complete)return Promise.resolve(RX.frameImg);
 return new Promise((ok,bad)=>{const im=new Image();im.onload=()=>{RX.frameImg=im;RX.frameKey=key;ok(im)};im.onerror=()=>bad(new Error('Não consegui carregar um quadro do vídeo original.'));im.src=key})}
let rxTimer=0;
function rxAfterDraw(){const c=rxComp();if(!c||!rxReady(c)||!$('rxCanvas'))return;
 const key=JSON.stringify(c)+'|'+(RX.t??'');   // o painel é redesenhado a cada ajuste: repinta na hora com o plano em cache (sem piscar) e confirma no servidor
 if(RX.plan&&RX.planKey===key&&RX.frameImg){rxDraw($('rxCanvas'),RX.plan,RX.frameImg);const w=$('rxWarn');if(w)w.innerHTML=RX.plan.warnings.map(x=>`<div>⚠ ${esc(x)}</div>`).join('');return}
 if(RX.plan&&RX.frameImg)rxDraw($('rxCanvas'),RX.plan,RX.frameImg);
 clearTimeout(rxTimer);rxTimer=setTimeout(rxPaint,120)}
async function rxPaint(){const c=rxComp(),cv=$('rxCanvas');if(!c||!cv||!rxReady(c))return;const id=++RX.busy;
 try{const t=RX.t??Math.min(dur()*.5,Math.max(0,ST.cursor||0));
  const [r,img]=await Promise.all([api('/api/composition/resolve',{id:ST.id,composition:c}),rxLoadFrame(t)]);
  if(id!==RX.busy||!$('rxCanvas'))return;RX.plan=r.plan;RX.planKey=JSON.stringify(c)+'|'+(RX.t??'');rxDraw($('rxCanvas'),r.plan,img);
  const w=$('rxWarn');if(w)w.innerHTML=r.plan.warnings.map(x=>`<div>⚠ ${esc(x)}</div>`).join('')}
 catch(e){const w=$('rxWarn');if(w)w.textContent=e.message}}
function rxDraw(cv,plan,img){const g=cv.getContext('2d'),s=cv.width/plan.canvas[0],k=img.naturalWidth/plan.source[0];
 g.clearRect(0,0,cv.width,cv.height);
 if(plan.bg.kind==='blur'){g.save();try{g.filter='blur(5px)'}catch(e){}const sc=Math.max(cv.width/img.naturalWidth,cv.height/img.naturalHeight);g.drawImage(img,(cv.width-img.naturalWidth*sc)/2,(cv.height-img.naturalHeight*sc)/2,img.naturalWidth*sc,img.naturalHeight*sc);g.restore()}
 else{g.fillStyle=plan.bg.kind==='color'?plan.bg.color:'#000';g.fillRect(0,0,cv.width,cv.height)}
 for(const L of plan.layers){const [cx,cy,cw,ch]=L.crop,[px,py]=L.pos,[w,h]=L.size;g.drawImage(img,cx*k,cy*k,cw*k,ch*k,px*s,py*s,w*s,h*s);
  if(L.border){g.strokeStyle=L.border_color;g.lineWidth=Math.max(1,L.border*s);g.strokeRect(px*s+g.lineWidth/2,py*s+g.lineWidth/2,w*s-g.lineWidth,h*s-g.lineWidth)}}}

/* ───────── seletor de regiões no quadro original ───────── */
function rxOpenPicker(role,frameT){const c=rxComp();if(!c)return;
 const start=c.regions[role]?{...c.regions[role]}:null;
 RX.picker={role,rect:start,orig:start,undo:[],t:frameT??RX.t??Math.min(dur()*.5,Math.max(0,ST.cursor||0)),drag:null};
 rxRenderPicker()}
function rxClosePicker(){RX.picker=null;const m=$('rxModal');if(m)m.remove();document.removeEventListener('keydown',rxKey,true)}
function rxRenderPicker(){const P=RX.picker;if(!P)return;let m=$('rxModal');
 if(!m){m=document.createElement('div');m.id='rxModal';m.className='rx-modal';m.setAttribute('role','dialog');m.setAttribute('aria-modal','true');document.body.appendChild(m);document.addEventListener('keydown',rxKey,true)}
 const c=rxComp(),roles=rxLayout(c.layout).roles,idx=roles.indexOf(P.role)+1;
 m.innerHTML=`<div class="rx-card"><div class="row"><b class="grow">Selecionar ${RX_ROLE[P.role]} <span class="muted small">(${idx} de ${roles.length})</span></b><button class="small quiet" data-rxp="cancel" aria-label="Cancelar">✕</button></div>
  <p class="help">${P.role==='conteudo'?'Arraste sobre a parte do vídeo que mostra o conteúdo reagido.':'Arraste sobre o rosto/câmera da pessoa. Pode mover e redimensionar depois.'} Este é o vídeo ORIGINAL, sem o corte vertical.</p>
  <div class="rx-stage" id="rxStage"><img id="rxImg" alt="Quadro do vídeo original" draggable="false"><div id="rxLayer"></div><div class="rx-loading" id="rxLoad">Carregando o quadro…</div></div>
  <div class="fld"><label>Quadro do vídeo: <span id="rxTt">${P.t.toFixed(1)}</span> s</label><input type="range" id="rxT" min="0" max="${Math.max(.1,dur()).toFixed(2)}" step=".1" value="${P.t}"></div>
  <div class="row"><button class="small" data-rxp="reset">Redefinir</button><button class="small" data-rxp="undo">Desfazer</button><span class="grow"></span><button class="small" data-rxp="cancel">Cancelar</button><button class="small primary" data-rxp="ok" id="rxOk">Confirmar</button></div></div>`;
 const img=$('rxImg');img.onload=()=>{$('rxLoad').classList.add('hide');rxPaintRects()};img.onerror=()=>{$('rxLoad').textContent='Não consegui carregar o quadro do vídeo original (o arquivo ainda existe?).'};img.src=rxFrameUrl(P.t)}
function rxPaintRects(){const P=RX.picker,layer=$('rxLayer');if(!P||!layer)return;const c=rxComp();let h='';
 for(const [role,r] of Object.entries(c.regions)){if(role===P.role)continue;h+=`<div class="rx-rect other" style="${rxStyle(r)};border-color:${RX_COLORS[role]}"><span style="background:${RX_COLORS[role]}">${RX_ROLE[role]}</span></div>`}
 if(P.rect){h+=`<div class="rx-rect cur" style="${rxStyle(P.rect)};border-color:${RX_COLORS[P.role]}"><span style="background:${RX_COLORS[P.role]}">${RX_ROLE[P.role]}</span>${['nw','ne','sw','se'].map(k=>`<i class="rx-h ${k}" data-h="${k}"></i>`).join('')}</div>`}
 layer.innerHTML=h;const ok=$('rxOk');if(ok)ok.disabled=!P.rect}
const rxStyle=r=>`left:${r.x*100}%;top:${r.y*100}%;width:${r.w*100}%;height:${r.h*100}%`;
function rxPoint(e){const b=$('rxImg').getBoundingClientRect();return{x:Math.min(1,Math.max(0,(e.clientX-b.left)/b.width)),y:Math.min(1,Math.max(0,(e.clientY-b.top)/b.height))}}
function rxPush(){const P=RX.picker;P.undo.push(P.rect?{...P.rect}:null);if(P.undo.length>50)P.undo.shift()}
function rxNorm(a,b){const x0=Math.min(a.x,b.x),y0=Math.min(a.y,b.y),x1=Math.max(a.x,b.x),y1=Math.max(a.y,b.y);return{x:x0,y:y0,w:x1-x0,h:y1-y0}}
function rxDown(e){const P=RX.picker;if(!P||e.target.closest('input,button'))return;const stage=e.target.closest('#rxStage');if(!stage)return;e.preventDefault();
 const pt=rxPoint(e),hd=e.target.closest('[data-h]');rxPush();
 if(hd&&P.rect){const r=P.rect,k=hd.dataset.h;P.drag={kind:'size',anchor:{x:k.includes('w')?r.x+r.w:r.x,y:k.includes('n')?r.y+r.h:r.y}}}
 else if(P.rect&&pt.x>=P.rect.x&&pt.x<=P.rect.x+P.rect.w&&pt.y>=P.rect.y&&pt.y<=P.rect.y+P.rect.h)P.drag={kind:'move',off:{x:pt.x-P.rect.x,y:pt.y-P.rect.y},w:P.rect.w,h:P.rect.h};
 else P.drag={kind:'new',a:pt};
 stage.setPointerCapture?.(e.pointerId)}
function rxMove(e){const P=RX.picker;if(!P||!P.drag)return;const pt=rxPoint(e),d=P.drag;
 if(d.kind==='new')P.rect=rxNorm(d.a,pt);else if(d.kind==='size')P.rect=rxNorm(d.anchor,pt);
 else P.rect={x:Math.min(1-d.w,Math.max(0,pt.x-d.off.x)),y:Math.min(1-d.h,Math.max(0,pt.y-d.off.y)),w:d.w,h:d.h};
 rxPaintRects()}
function rxUp(){const P=RX.picker;if(!P||!P.drag)return;P.drag=null;if(P.rect&&(P.rect.w<.02||P.rect.h<.02)){P.rect=P.undo.pop()||null}rxPaintRects()}
function rxKey(e){const P=RX.picker;if(!P)return;
 if(e.key==='Escape'){e.preventDefault();e.stopPropagation();rxClosePicker()}
 else if(e.key==='Enter'&&!e.target.closest?.('button')){e.preventDefault();e.stopPropagation();rxConfirm()}
 else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.stopPropagation();rxUndoRect()}
 else if(!['Tab','Shift'].includes(e.key))e.stopPropagation()}   // atalhos do Estúdio (C, P, espaço…) ficam parados enquanto o seletor está aberto
function rxUndoRect(){const P=RX.picker;if(!P||!P.undo.length)return;P.rect=P.undo.pop();rxPaintRects()}
function rxConfirm(){const P=RX.picker;if(!P||!P.rect)return toast('Desenhe um retângulo sobre a região.',true);
 const r={x:+P.rect.x.toFixed(5),y:+P.rect.y.toFixed(5),w:+P.rect.w.toFixed(5),h:+P.rect.h.toFixed(5)};if(r.w<.02||r.h<.02)return toast('Região pequena demais. Desenhe um retângulo maior.',true);
 const role=P.role;RX.t=P.t;rxClosePicker();
 mutate(()=>{ST.proj.composition.regions[role]=r});
 const next=rxMissing(rxComp())[0];if(next)setTimeout(()=>rxOpenPicker(next),50)}
document.addEventListener('pointerdown',e=>{if(RX.picker)rxDown(e)},true);
document.addEventListener('pointermove',e=>{if(RX.picker)rxMove(e)},true);
document.addEventListener('pointerup',e=>{if(RX.picker)rxUp(e)},true);
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-rxp]');if(!b||!RX.picker)return;const k=b.dataset.rxp;
 if(k==='cancel')rxClosePicker();else if(k==='ok')rxConfirm();else if(k==='undo')rxUndoRect();
 else if(k==='reset'){rxPush();RX.picker.rect=RX.picker.orig?{...RX.picker.orig}:null;rxPaintRects()}});
document.addEventListener('input',e=>{if(e.target.id==='rxT'&&RX.picker){RX.picker.t=+e.target.value;$('rxTt').textContent=RX.picker.t.toFixed(1)}});
document.addEventListener('change',e=>{if(e.target.id==='rxT'&&RX.picker){$('rxLoad').classList.remove('hide');$('rxLoad').textContent='Carregando o quadro…';$('rxImg').src=rxFrameUrl(RX.picker.t)}});

/* ───────── ações do painel ───────── */
function rxSetParam(key,v){mutate(()=>{const c=ST.proj.composition;c.params=c.params||{};c.params[key]=v})}
$('stRight').addEventListener('click',e=>{const t=e.target;
 const dl=t.closest('[data-del^="scene:"]');if(dl){e.stopImmediatePropagation();const id=dl.dataset.del.slice(6);mutate(()=>{const c=ST.proj.composition;if(c)c.scenes=(c.scenes||[]).filter(z=>z.id!==id);ST.item=null});return}
 const l=t.closest('[data-rxl]');if(l){const id=l.dataset.rxl;mutate(()=>{const old=ST.proj.composition;ST.proj.composition={version:1,layout:id,regions:old?old.regions:{},params:{}}});const next=rxMissing(rxComp())[0];if(next)setTimeout(()=>rxOpenPicker(next),50);return}
 const a=t.closest('[data-rx]');if(a){const k=a.dataset.rx;
  if(k==='more'){RX.more=!RX.more;drawRight()}
  else if(k==='remove')mutate(()=>{ST.proj.composition=null});
  else if(k.startsWith('pick:'))rxOpenPicker(k.slice(5))
  else if(k==='preset-apply'){const p=(RX.presets||[]).find(x=>x.id===RX.presetSel);if(!p)return;
   mutate(()=>{const old=ST.proj.composition,keep=p.has_regions&&p.compatible?p.regions:(old?old.regions:{});ST.proj.composition={version:1,layout:p.layout,regions:keep||{},params:Object.assign({},p.params)}});
   if(p.has_regions&&!p.compatible)toast('Este layout foi salvo com regiões de um vídeo de outra proporção: só o modelo e os ajustes foram aplicados. Marque as regiões.',false);
   const next=rxMissing(rxComp())[0];if(next)setTimeout(()=>rxOpenPicker(next),50)}
  else if(k==='scene-add')rxNewScene(rxPickSceneLayout(),{})
  else if(k==='scene-paste'&&RX.sceneClip)rxNewScene(RX.sceneClip.layout,RX.sceneClip.params)
  else if(k.startsWith('scene-copy:')){const o=getItem({kind:'scene',id:k.slice(11)});if(o){RX.sceneClip={layout:o.layout,params:Object.assign({},o.params)};toast('Cena copiada. Selecione outro trecho e use “Colar na seleção”.');drawRight()}}
  else if(k.startsWith('scene-params:')){const id=k.slice(13);mutate(()=>{const c=ST.proj.composition,o=c.scenes.find(z=>z.id===id);if(o&&o.layout===c.layout)o.params=Object.assign({},c.params||{});else toast('Só vale quando a cena usa o mesmo layout do principal.',true)})}
  else if(k==='preset-save'){const n=$('rxPresetName').value;rxPresetCall({action:'save',name:n,composition:ST.proj.composition,with_regions:$('rxPresetRegions').checked}).then(ok=>{if(ok)toast('Layout salvo.')})}
  else if(k==='preset-rename'){const n=($('rxPresetName')&&$('rxPresetName').value)||'';if(!n)return toast('Digite o novo nome no campo “Nome do layout”.',true);rxPresetCall({action:'rename',preset:RX.presetSel,name:n})}
  else if(k==='preset-dup')rxPresetCall({action:'duplicate',preset:RX.presetSel})
  else if(k==='preset-del'){if(confirm('Excluir este layout salvo? As composições já aplicadas nos cortes não mudam.'))rxPresetCall({action:'delete',preset:RX.presetSel}).then(()=>{RX.presetSel=''})}
  else if(k==='apply-toggle'){RX.applyOpen=!RX.applyOpen;drawRight()}
  else if(k==='apply-sel'||k==='apply-all'){const me=state.candidates.find(x=>x.id===ST.id);const ids=k==='apply-all'?'session':Object.keys(RX.applyPick).filter(i=>RX.applyPick[i]);if(k==='apply-sel'&&!ids.length)return toast('Marque os cortes.',true);
   (async()=>{try{if(ST.dirty)await persist({learn:false,preview:false,force:true});const r=await api('/api/composition/apply',{id:ST.id,composition:ST.proj.composition,targets:ids});await refresh(true);
    toast(`Aplicado em ${r.applied.length} corte${r.applied.length===1?'':'s'}.`+(r.skipped.length?` ${r.skipped.length} pulado${r.skipped.length===1?'':'s'}: ${r.skipped[0].reason}.`:''),!r.applied.length)}catch(e){toast(e.message,true)}})()}}
 const f=t.closest('[data-rxfit]');if(f){const [pre,fit]=f.dataset.rxfit.split(':');rxSetParam(pre+'_fit',fit)}},true);
$('stRight').addEventListener('change',e=>{const t=e.target;
 if(t.id==='rxPreset'){RX.presetSel=t.value;e.stopImmediatePropagation();drawRight();return}
 if(t.dataset.f&&/^composition\.scenes\.\d+\.layout$/.test(t.dataset.f)){e.stopImmediatePropagation();const i=+t.dataset.f.split('.')[2],v=t.value;mutate(()=>{const o=ST.proj.composition.scenes[i];o.layout=v;o.params={}});return}
 if(t.dataset.rxa!==undefined){RX.applyPick[t.dataset.rxa]=t.checked;e.stopImmediatePropagation();return}
 const k=t.dataset.rxf;if(!k)return;e.stopImmediatePropagation();
 let v=t.type==='checkbox'?t.checked:t.value;if(t.dataset.t==='num')v=+v;if(k==='gap'||k==='pip_border')v=Math.round(v);
 const c=ST.proj.composition;if(c&&c.params&&c.params[k]===v)return;rxSetParam(k,v)},true);
$('stRight').addEventListener('input',e=>{const k=e.target.dataset.rxf;if(!k||e.target.type!=='range')return;const o=$('stRight').querySelector(`[data-out="rx.${k}"]`);
 if(o){const v=+e.target.value;o.textContent=k==='gap'||k==='pip_border'?v+' px':k.endsWith('_zoom')?v.toFixed(2)+'×':Math.round(v*100)+'%'}},true);
const rxDrawRight=drawRight;drawRight=function(){rxDrawRight();rxAfterDraw();if(RX.presetsFor!==ST.id){RX.presets=null;RX.presetsFor=ST.id;RX.presetSel=''}if(RX.presets===null&&ST.open&&ST.secs.has('frame')){RX.presets=[];rxLoadPresets()}};
