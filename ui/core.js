const token=__BOOT_TOKEN__,$=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state=null,view='clips',streamerId=localStorage.getItem('lc-streamer')||'',sessionId=localStorage.getItem('lc-session')||'',filter='review',pollBusy=false,selected=new Set(),batchMode='',batchReport=[],camRect=null,trackRoi=null,blurRegions=[],markMode='cam',dragNow=null,camImage=null,sourceMeta={},profileStyle='clean',keys={};
const statusNames={pending:'Para revisar',approved:'Na fila',exporting:'Exportando',done:'Pronto',rejected:'Rejeitado',duplicate:'Repetido',error:'Falhou',replaced:'Substituído'};
const styleInfo={
 clean:['Limpo','Opiniões e assuntos sérios. Pouco efeito, muita legibilidade.'],gameplay:['Gameplay','Jogadas e falhas. Pausas curtas, zoom em picos.'],
 reaction:['Reação','Sustos e risadas com a webcam em evidência.'],podcast:['Podcast','Conversas longas, planos alternados por frase.'],
 interview:['Entrevista','Pergunta e resposta preservadas, zoom discreto.'],hype:['Hype','Clímax e energia alta, cortes apertados.'],
 creative:['Criativo','Humor com recursos visuais, tudo desligável.'],storytelling:['História','Preparação, clímax e desfecho protegidos.'],
 educational:['Educacional','Explicações e listas; termos na tela.'],commentary:['Comentário','Opinião sem mudar o sentido.'],
 meme:['Meme','Timing apertado, zoom e recursos de humor.'],cinematic:['Cinemático','Respira mais, cor contida, sem zoom automático.'],funny:['Engraçado','Compatível com perfis antigos de humor.']};
const rgb=b=>'#'+b.slice(4,6)+b.slice(2,4)+b.slice(0,2),bgr=c=>{c=c.slice(1);return c.slice(4,6)+c.slice(2,4)+c.slice(0,2)};
const clock=(s,d=0)=>{s=Math.max(0,s);const m=Math.floor(s/60),x=(s%60).toFixed(d).padStart(d?4:2,'0');return m+':'+x};
function toast(m,error=false){const t=$('toast');t.textContent=m;t.className='toast'+(error?' error':'');clearTimeout(toast.t);toast.t=setTimeout(()=>t.classList.add('hide'),6500)}
let stateTag='';
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:{'X-LiveClips-Token':token,...(path==='/api/state'&&stateTag?{'X-State-Tag':stateTag}:{}),...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});let v={};try{v=await r.json()}catch(e){}if(!r.ok)throw Error(v.error||'Não foi possível concluir.');if(path==='/api/state')stateTag=r.headers.get('X-State-Tag')||v.tag||stateTag;return v}
async function upload(kind,file){const r=await fetch('/api/upload?kind='+kind+'&name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-LiveClips-Token':token},body:file});const v=await r.json();if(!r.ok)throw Error(v.error||'Envio falhou.');return v.item}
async function act(path,data,message){try{const v=await api(path,data);if(message)toast(message);await refresh(true);return v}catch(e){toast(e.message,true);throw e}}
const streamer=()=>state?.streamers.find(s=>s.id===streamerId),session=()=>state?.sessions.find(s=>s.id===sessionId);
const sessionsOf=()=>state.sessions.filter(s=>s.streamer===streamerId&&s.status!=='archived'||s.id===sessionId&&s.streamer===streamerId);
const clipsOf=()=>state.candidates.filter(c=>c.session===sessionId&&c.status!=='replaced');
function clipTitle(c){const p=c.data.project;const t=p&&p.titles&&p.titles[0]&&p.titles[0].text;if(t)return t;const h=c.data.hook&&c.data.hook.opening;if(h)return h;return c.data.moment_label||c.data.transcript?.slice(0,70)||'Corte '+c.id.slice(0,4)}
async function refresh(force=false){if(pollBusy){if(!force)return;await new Promise(r=>setTimeout(r,200))}pollBusy=true;try{const next=await api('/api/state');if(!next.unchanged){state=next;render()}else if(force)render();if(window.studioTick)studioTick()}catch(e){if(!state&&$('loading')){$('loadingText').textContent='Não consegui falar com o Hook’s. Confira se a janela do programa continua aberta.';$('loadingRetry').classList.remove('hide');$('loading').querySelector('.spin').classList.add('stopped')}$('workerTitle').textContent='Sem conexão com o Hook’s';$('workerDetail').textContent='Mantenha a janela do programa aberta e atualize a página.'}finally{pollBusy=false}}

/* ───── navegação ───── */
function go(v){view=v;if(v==='add')setTimeout(()=>loadPreflight(true),0);localStorage.setItem('lc-view',v);for(const id of ['onboarding','clips','add','music','settings','account'])$('v-'+id).classList.toggle('hide',id!==v);document.querySelectorAll('[data-nav]').forEach(b=>b.setAttribute('aria-current',b.dataset.nav===v?'page':'false'));if(v==='settings')fillProfile();if(v==='account')setTimeout(renderAccount,0);if(v==='music')renderMusicPage();render()}
document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>go(b.dataset.nav));
document.querySelectorAll('dialog [data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());

function render(){
 if(!state)return;
 const LD=$('loading');if(LD)LD.remove();
 licenseTick();
 if(!state.streamers.some(s=>s.id===streamerId)){streamerId=state.streamers[0]?.id||''}
 if(!streamerId){const only=view==='account'?'account':'onboarding';for(const id of ['onboarding','clips','add','music','settings','account'])$('v-'+id).classList.toggle('hide',id!==only);$('streamerSelect').innerHTML='';renderStatus();if(only==='account')renderAccount();return}
 if(view==='onboarding')view='clips';
 for(const id of ['onboarding','clips','add','music','settings','account'])$('v-'+id).classList.toggle('hide',id!==view);
 document.querySelectorAll('[data-nav]').forEach(b=>b.setAttribute('aria-current',b.dataset.nav===view?'page':'false'));
 const key=JSON.stringify(state.streamers.map(s=>[s.id,s.name])+streamerId);if(key!==keys.streamers){keys.streamers=key;$('streamerSelect').innerHTML=state.streamers.map(s=>`<option value="${s.id}" ${s.id===streamerId?'selected':''}>${esc(s.name)}</option>`).join('')}
 const ss=sessionsOf();if(!ss.some(s=>s.id===sessionId))sessionId=ss[0]?.id||'';
 renderStatus();renderAlerts();renderCaptures();renderPerf();if(view==='account')renderAccount();
 if(view==='clips')renderClips();
 const pending=sessionsOf().length?state.candidates.filter(c=>c.streamer===streamerId&&c.status==='pending').length:0;$('navCount').textContent=pending;$('navCount').classList.toggle('hide',!pending);
}
function renderStatus(){const w=state.worker;$('workerTitle').textContent=w.stage;$('workerDetail').textContent=w.detail+(w.busy&&w.elapsed_s>120?` · há ${Math.round(w.elapsed_s/60)} min nesta etapa${w.elapsed_s>600?'. Está demorando: se não houver % andando, pause esta sessão em Gerenciar ou rode o GERAR_DIAGNOSTICO.bat':''}`:'');$('workerDot').className='dot '+(w.busy?'busy':state.paused?'':'on');$('disk').textContent=state.free_gb.toFixed(1)+' GB livres';$('pauseBtn').textContent=state.paused?'Iniciar análise':'Pausar análise';
 const busyLanes=(w.lanes||[]).filter(l=>l.busy);
 $('workerLanes').innerHTML=!(w.lanes||[]).length?'':!busyLanes.length?'<div class="lane muted"><span class="dot"></span><span>Nada em andamento</span></div>':busyLanes.map(l=>`<div class="lane"><span class="dot ${l.busy?'busy':''}"></span><span><b>${esc(l.label)}</b> ${l.busy?esc((l.stage||'')+(l.percent!=null?' '+l.percent+'%':'')):'<span class="muted">livre</span>'}</span></div>`).join('');
 const has=w.percent!=null&&w.busy;$('workerProg').classList.toggle('hide',!has);if(has){$('workerBar').style.width=w.percent+'%';$('workerPct').textContent=w.percent+'%';$('workerEta').textContent=w.eta_text?'faltam '+w.eta_text:'calculando…'}}
function liveBar(s){
 const hhmm=iso=>{try{return new Date(iso).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}catch(e){return ''}};
 const retry=s.source_url?`<button class="small primary" data-do="resumecap" data-url="${esc(s.source_url)}" data-streamer="${esc(s.streamer)}">Retomar gravação</button>`:'';
 if(!s.closed&&s.capture_running){const age=s.last_file_age_s,stale=age!=null&&age>150,lag=Math.max(0,(s.files||0)-1-(s.analyzed||0));
  return `<div class="banner ${stale?'error':'rec'}" style="align-items:flex-start"><span class="dot ${stale?'':'on'}" style="margin-top:6px"></span><span class="grow"><b>${stale?'Gravando, mas sem pedaço novo':'Gravando agora'}</b> · ${s.files} pedaço${s.files===1?'':'s'} de 1 min gravado${s.files===1?'':'s'} · ${s.analyzed} de ${s.registered} analisado${s.analyzed===1?'':'s'}${age!=null?` · último pedaço há ${age<90?Math.round(age)+' s':Math.round(age/60)+' min'}`:''}${lag>=3?` · <b>análise ${lag} min atrás da live</b>`:''}<br><span class="small muted">${stale?'A live pode ter caído. Se continuar assim, pare e retome a gravação.':'Os primeiros cortes aparecem depois de 2 a 3 pedaços analisados, e os próximos chegam sozinhos enquanto você edita.'}</span></span><button class="small danger" data-do="stopcap" data-session="${esc(s.id)}">Parar gravação</button></div>`}
 if(!s.closed&&!s.capture_running)return `<div class="banner error"><span><b>Esta sessão está marcada como ao vivo, mas nenhuma gravação está rodando.</b></span>${retry}</div>`;
 const e=s.capture_end;
 if(e&&e.by==='automatico')return `<div class="banner error" style="align-items:flex-start"><span class="grow"><b>A gravação parou sozinha${e.at?' às '+hhmm(e.at):''}.</b> ${esc(e.reason||'')}<br><span class="small muted">Isso costuma ser a live acabando, ou a conexão caindo. O que já foi gravado (${s.registered} pedaço${s.registered===1?'':'s'}) continua sendo analisado.</span></span>${retry}</div>`;
 return ''}
function renderAlerts(){const a=licenseBanners();const miss=Object.entries(state.tools).filter(([k,v])=>!v).map(([k])=>k);if(miss.length)a.push(`<div class="banner error"><span>Ferramentas não encontradas: <b>${esc(miss.join(', '))}</b>. Rode o INSTALAR.bat de novo.</span><button class="small" id="toolsCheck">Verificar</button></div>`);
 const rg=state.regeneration?.[streamerId];if(rg)a.push(`<div class="banner"><span>Refazendo as sugestões automáticas com o perfil atual. Cortes revisados e exportados foram preservados.</span></div>`);
 if(state.paused&&state.sessions.some(s=>s.streamer===streamerId&&s.enabled&&(s.analyzed<s.registered||!s.closed)))a.push(`<div class="banner"><span>A análise está pausada.</span><button class="small primary" data-do="resume">Iniciar análise</button></div>`);
 const sd=state.streamers.find(x=>x.id===streamerId);
 if(sd&&sd.profile&&(sd.profile.content_mode||'live')==='live'&&!sd.profile.camera_rect&&state.sessions.some(x=>x.streamer===streamerId&&x.enabled)){const sg=(state.camera_suggestions||{})[streamerId];
  if(sg)a.push(`<div class="banner"><span><b>Achei a webcam sozinho (confiança ${esc(sg.level)}).</b> ${esc(sg.reason)} Aplicar faz o programa reanalisar o que já foi gravado.</span><span class="row"><button class="small primary" data-do="camaccept" data-streamer="${esc(streamerId)}">Usar esta webcam</button><button class="small" data-gopane="cam">Ver e ajustar</button><button class="small quiet" data-do="camdismiss" data-streamer="${esc(streamerId)}">Dispensar</button></span></div>`);
  else a.push(`<div class="banner"><span><b>A webcam deste streamer não está marcada.</b> O Hook’s tenta achar sozinho quando chegam os primeiros pedaços da live. Sem ela, a prévia e a exportação das lives falham e os cortes saem sem a leitura do rosto.</span><button class="small primary" data-gopane="cam">Marcar a webcam</button></div>`)}
 const cap=state.worker.capacity;
 if(cap&&cap.ok===false&&cap.lives>=2)a.push(`<div class="banner" style="align-items:flex-start"><span class="grow"><b>Seu computador não acompanha ${cap.lives} lives ao mesmo tempo.</b> Cada minuto de live leva cerca de ${Math.round(cap.rtf*60)} s para ser transcrito; com ${cap.lives} lives seriam ${Math.round(cap.needed*60)} s por minuto. A análise vai ficando para trás (os cortes demoram mais a chegar; nada se perde).<br><span class="small muted">O que ajuda: modelo de voz menor no perfil (tiny ou base) antes de começar a live, ou menos lives ao mesmo tempo. Estimativa baseada nas últimas ${cap.samples} transcrições.</span></span></div>`);
 const ls=session();if(ls&&ls.streamer===streamerId)a.push(liveBar(ls));
 const k=JSON.stringify(a);if(k!==keys.alerts){keys.alerts=k;$('alerts').innerHTML=a.join('')}}
document.addEventListener('click',e=>{if(e.target.id==='preRefresh')loadPreflight(true);const gp=e.target.closest?.('[data-gopane]');if(gp){go('settings');showPane(gp.dataset.gopane)}if(e.target.id==='toolsCheck'||e.target.id==='toolsBtn')act('/api/tools/check',{},'Ferramentas verificadas.').catch(()=>{});if(e.target.dataset?.do==='resume')act('/api/pause',{paused:false}).catch(()=>{});
 const d=e.target.closest('[data-do]');if(!d)return;
 if(d.dataset.do==='camaccept'){act('/api/camera/accept',{streamer:d.dataset.streamer},'Webcam aplicada.').catch(()=>{})}
 if(d.dataset.do==='camdismiss'){act('/api/camera/dismiss',{streamer:d.dataset.streamer},'Sugestão dispensada.').catch(()=>{})}
 if(d.dataset.do==='stopcap'){if(!confirm('Parar a gravação desta live? O que já foi gravado continua sendo analisado.'))return;d.disabled=true;act('/api/capture/stop',{session:d.dataset.session},'Gravação encerrada.').catch(()=>{d.disabled=false})}
 if(d.dataset.do==='resumecap'){d.disabled=true;act('/api/capture/start',{streamer:d.dataset.streamer,url:d.dataset.url},'Gravação retomada em uma nova sessão.').catch(()=>{d.disabled=false})}});

/* ───── cortes ───── */
function renderClips(){
 const s=session(),ss=sessionsOf(),name=streamer()?.name||'';$('pageTitle').textContent=name?name+' · cortes':'Cortes';
 const sk=JSON.stringify(ss.map(x=>[x.id,x.name,x.status,x.closed]));if(sk!==keys.sessions||$('sessionSelect').value!==sessionId){keys.sessions=sk;$('sessionSelect').innerHTML=ss.map(x=>`<option value="${x.id}" ${x.id===sessionId?'selected':''}>${esc(x.name)}${x.closed?'':' · ao vivo'}${x.status==='archived'?' · arquivada':''}</option>`).join('')||'<option value="">Nenhum conteúdo ainda</option>'}
 const none=!s;$('manualBtn').disabled=none;$('openFolder').disabled=none;$('sessionSelect').disabled=none;
 const clips=s?clipsOf():[],pend=clips.filter(c=>c.status==='pending').length,exp=clips.filter(c=>c.status==='done').length,q=clips.filter(c=>['approved','exporting'].includes(c.status)).length;
 const step=(id,state_,txt)=>{$(id).className=state_;$(id+'Txt').textContent=txt};
 if(!s){$('subtitle').textContent='Adicione um vídeo, podcast ou live para começar.';for(const id of ['stepSource','stepAnalyze','stepReview','stepExport'])step(id,'','');$('stepSource').className='active';$('sessionMeta').classList.add('hide');$('filters').innerHTML='';$('cards').innerHTML=`<div class="empty" style="grid-column:1/-1"><h2>Nada por aqui ainda</h2><p>Cole o link de um vídeo ou de uma live para o Hook’s procurar os melhores momentos.</p><p style="margin-top:16px"><button class="primary" data-nav-go="add">Adicionar conteúdo</button></p></div>`;return}
 const done=s.registered>0&&s.analyzed===s.registered&&s.closed;
 const rv=s.review||{},decided=(rv.accepted||0)+(rv.rejected||0),rateText=decided?` · ${Math.round(rv.rate*100)}% aceitos (${rv.accepted} de ${decided} decididos)`:'';
 $('subtitle').textContent=s.completed?`${clips.length} ${clips.length===1?'corte encontrado':'cortes encontrados'} em ${Math.round(s.duration/60)} min${rateText}`:s.registered?`Analisando… ${Math.round(s.analyzed_until/60)} de ${Math.round(s.duration/60)} min`:'Preparando o conteúdo…';
 step('stepSource','done',s.closed?'pronto':'gravando');step('stepAnalyze',done?'done':'active',`${s.analyzed}/${s.registered} partes`);step('stepReview',pend?'active':clips.length?'done':'',pend?pend+' para revisar':clips.length?'tudo revisado':'aguardando');step('stepExport',q?'active':exp?'done':'',q?q+' na fila':exp?exp+' prontos':'—');
 const meta=[];if(s.status==='error')meta.push(`<b>Erro:</b> ${esc(s.error)} <button class="small" data-do="retry">Tentar novamente</button>`);if(s.camera_upscale)meta.push('A webcam desta origem tem resolução baixa e será ampliada.');if(!s.source_available)meta.push('O arquivo original não foi encontrado. Use Gerenciar → Localizar original.');
 $('sessionMeta').classList.toggle('hide',!meta.length);$('sessionMeta').innerHTML=meta.join(' · ');
 $('sessionToggle').textContent=s.status==='archived'?'Reativar sessão':s.enabled?'Pausar esta sessão':'Retomar esta sessão';
 const f=[['review','Para revisar',c=>c.status==='pending'],['queue','Na fila',c=>['approved','exporting'].includes(c.status)],['done','Prontos',c=>c.status==='done'],['check','Conferir',c=>c.status==='done'&&c.data.qc&&c.data.qc.level&&c.data.qc.level!=='ok'],['rejected','Rejeitados',c=>['rejected','duplicate'].includes(c.status)],['error','Com erro',c=>c.status==='error'],['all','Todos',c=>true]];
 $('filters').innerHTML=f.filter(([id,,fn])=>id==='review'||id==='all'||clips.some(fn)).map(([id,l,fn])=>`<button aria-pressed="${filter===id}" data-filter="${id}">${l} <span class="muted">${clips.filter(fn).length}</span></button>`).join('');
 const sel=f.find(x=>x[0]===filter)||f[0];const list=clips.filter(sel[2]).sort((a,b)=>b.score-a.score);for(const id of [...selected])if(!clips.some(x=>x.id===id&&x.status==='pending'))selected.delete(id);
 const ck=JSON.stringify([filter,list.map(c=>[c.id,c.version,c.status,c.preview_status,c.has_preview,c.score,clipTitle(c),c.data.confidence?.tier,c.data.qc?.level,!!c.data.ab,!!c.data.series,c.reason])]);
 if(ck!==keys.cards){keys.cards=ck;$('cards').innerHTML=list.length?list.map(clipCard).join(''):`<div class="empty" style="grid-column:1/-1"><h2>${clips.length?'Nenhum corte neste filtro':s.completed?'Nenhum momento forte encontrado':'Procurando os melhores momentos…'}</h2><p>${clips.length?'Troque o filtro acima.':(!s.closed&&s.capture_running?'Gravando. Cada pedaço tem 1 min; os primeiros cortes aparecem depois de 2 a 3 pedaços analisados.':'As sugestões aparecem aqui assim que as primeiras partes forem analisadas.')}</p></div>`}
 drawBatch()
}
function clipFlags(c){const f=[],cf=c.data.confidence,q=c.data.qc;
 if(cf&&['pending'].includes(c.status))f.push(cf.tier==='baixa'?'<span class="conf baixa" title="'+esc((cf.reasons||[]).join(' '))+'">revisar com atenção</span>':`<span class="conf ${cf.tier}" title="${esc((cf.reasons||[]).join(' '))}">confiança ${cf.tier}</span>`);
 if(['pending'].includes(c.status)&&c.data.estado_contexto){const ec={aguardando_contexto:['média','aguardando contexto','Falta contexto anterior ou o desfecho do trecho. Abra o estúdio → Por quê.'],exploratorio:['média','exploratório','Reação sem fala; é uma hipótese para você conferir, não um momento confirmado.'],revisao_necessaria:['média','revisão necessária','Os sinais deste trecho conflitam entre si.']}[c.data.estado_contexto];if(ec)f.push(`<span class="conf ${ec[0]}" title="${esc(ec[2])}">${ec[1]}</span>`)}
 if(q&&q.level&&q.level!=='ok'){const n=(q.items||[]).filter(i=>i.status!=='ok').length;f.push(`<span class="conf ${q.level==='erro'?'baixa':'média'}" title="${esc(q.summary||'')}">revisar${n?' · '+n:''}</span>`)}
 if(c.status==='rejected'&&c.reason)f.push(`<span class="chip reason">${esc((state.reject_reasons||{})[c.reason]||c.reason)}</span>`);
 if(c.data.ab)f.push(`<span class="chip aqua">Teste A/B · ${esc(c.data.ab.label)}</span>`);if(c.data.series)f.push(`<span class="chip aqua">Parte ${c.data.series.part}/${c.data.series.of}</span>`);
 return f.length?`<div class="flags">${f.join('')}</div>`:''}
function clipCard(c){const dur=c.end-c.start,hook=c.data.hook?.score;const st=c.status==='pending'?'':`<span class="chip ${c.status==='done'?'good':c.status==='error'?'bad':'info'} state">${statusNames[c.status]}</span>`;
 const vid=c.has_preview?`<video muted preload="metadata" src="/media/preview?id=${c.id}#t=0.4"></video>`:'';
 const card=`<button class="clip" data-clip="${c.id}"><div class="thumb">${vid}<div class="shade"></div><span class="score">${c.score.toFixed?c.score.toFixed(1):c.score}</span>${st}<div class="stack"><div class="title">${esc(clipTitle(c))}</div>${clipFlags(c)}</div></div><div class="foot"><span>${clock(dur)} · ${c.data.project?'editado':'automático'}</span><span>${hook!=null?'gancho '+hook.toFixed(0):''}</span></div></button>`;
 if(c.status!=='pending')return card;const on=selected.has(c.id);
 return `<div class="cardwrap${on?' sel':''}" data-wrap="${c.id}">${card}<label class="pick" title="Selecionar (tecla X)"><input type="checkbox" data-pick="${c.id}" ${on?'checked':''} aria-label="Selecionar: ${esc(clipTitle(c))}"></label></div>`}
/* ---------- revisão em lote e por teclado ---------- */
const pendingNow=()=>clipsOf().filter(c=>c.status==='pending'&&!(ST.decided&&ST.decided.has(c.id))).sort((a,b)=>b.score-a.score);
const titleOf=id=>{const c=clipsOf().find(x=>x.id===id);return c?clipTitle(c):id};
function drawBatch(){const bar=$('batchBar');if(!bar)return;const n=selected.size,pend=pendingNow().length;
 if(!n&&!batchReport.length){bar.classList.add('hide');bar.innerHTML='';batchMode='';return}
 bar.classList.remove('hide');let h='';
 if(batchMode==='approve')h=`<span><b>Aprovar ${n} ${n===1?'corte':'cortes'}</b> e mandar para a fila de exportação?</span><button class="primary small" id="batchYes">Sim, aprovar</button><button class="small" id="batchNo">Cancelar</button>`;
 else if(batchMode==='reject')h=`<span><b>Motivo da rejeição</b> (${n}) — tecla 1 a 9:</span>`+Object.entries(state.reject_reasons||{}).map(([k,v],i)=>`<button class="small" data-breason="${esc(k)}">${i+1} · ${esc(v)}</button>`).join('')+`<button class="small quiet" data-breason="">Sem motivo</button><button class="small quiet" id="batchNo">Cancelar</button>`;
 else if(n)h=`<span><b>${n}</b> ${n===1?'selecionado':'selecionados'}</span><button class="primary small" id="batchApprove">Aprovar…</button><button class="small" id="batchReject">Rejeitar…</button>${n<pend?`<button class="small quiet" id="batchAll">Selecionar os ${pend} para revisar</button>`:''}<button class="small quiet" id="batchClear">Limpar</button>`;
 if(batchReport.length)h+=`<div class="batch-report" role="status"><b>${batchReport.length} ${batchReport.length===1?'corte não pôde':'cortes não puderam'} ser decididos em lote:</b><ul>${batchReport.map(r=>`<li><b>${esc(titleOf(r.id))}</b> — ${esc(r.error)}</li>`).join('')}</ul><button class="small quiet" id="batchDismiss">Entendi</button></div>`;
 const was=bar.dataset.h;if(was===h)return;bar.dataset.h=h;bar.innerHTML=h;const f=bar.querySelector('#batchYes,[data-breason]');if(f&&batchMode)f.focus()}
function setSelected(id,on){if(on)selected.add(id);else selected.delete(id);const w=document.querySelector(`[data-wrap="${id}"]`);if(w){w.classList.toggle('sel',on);const i=w.querySelector('input');if(i)i.checked=on}if(!selected.size)batchMode='';drawBatch()}
async function runBatch(action,reason){const ids=[...selected];batchMode='';try{const r=await api('/api/review/batch',{ids,action,reason:reason||''});
 const failed=r.results.filter(x=>!x.ok);selected.clear();failed.forEach(x=>{if(!/já foi decidido|não encontrado/.test(x.error))selected.add(x.id)});batchReport=failed;
 toast(`${r.done} ${action==='approve'?(r.done===1?'aprovado':'aprovados'):(r.done===1?'rejeitado':'rejeitados')}${failed.length?` · ${failed.length} para ver abaixo`:''}.`,!!failed.length&&!r.done);keys.cards='';await refresh(true)}catch(e){toast(e.message,true)}drawBatch()}
document.addEventListener('change',e=>{const p=e.target.closest?.('[data-pick]');if(p)setSelected(p.dataset.pick,p.checked)});
document.addEventListener('click',e=>{const b=e.target.closest('#batchBar button');if(!b)return;
 if(b.id==='batchApprove'){batchMode='approve';drawBatch()}else if(b.id==='batchReject'){batchMode='reject';drawBatch()}
 else if(b.id==='batchNo'){batchMode='';drawBatch()}else if(b.id==='batchYes')runBatch('approve');
 else if(b.id==='batchClear'){selected.clear();batchMode='';keys.cards='';renderClips()}
 else if(b.id==='batchAll'){pendingNow().forEach(c=>selected.add(c.id));keys.cards='';renderClips()}
 else if(b.id==='batchDismiss'){batchReport=[];drawBatch()}
 else if('breason' in b.dataset)runBatch('reject',b.dataset.breason)});
function focusedClip(){const el=document.activeElement?.closest?.('[data-clip],[data-wrap]');if(!el)return null;return el.dataset.clip||el.dataset.wrap}
document.addEventListener('keydown',e=>{if(ST.open||view!=='clips'||e.ctrlKey||e.metaKey||e.altKey)return;
 if(document.querySelector('dialog[open]'))return;const t=e.target.tagName||'';if(['INPUT','TEXTAREA','SELECT'].includes(t)&&e.target.type!=='checkbox')return;
 const k=e.key.toLowerCase();
 if(batchMode==='reject'&&/^[1-9]$/.test(k)){const r=Object.keys(state.reject_reasons||{})[+k-1];if(r){e.preventDefault();runBatch('reject',r)}return}
 if(k==='escape'){if(batchMode){batchMode='';drawBatch()}else if(selected.size){selected.clear();keys.cards='';renderClips()}return}
 const cards=[...document.querySelectorAll('#cards .clip')];
 if(['arrowright','arrowleft','arrowdown','arrowup','j','k'].includes(k)&&cards.length){
  const cur=cards.indexOf(document.activeElement?.closest?.('.clip')||document.activeElement);const top=cards[0].offsetTop,cols=Math.max(1,cards.filter(x=>x.offsetTop===top).length);
  const step={arrowright:1,j:1,arrowleft:-1,k:-1,arrowdown:cols,arrowup:-cols}[k];const next=cur<0?0:Math.max(0,Math.min(cards.length-1,cur+step));e.preventDefault();cards[next].focus();cards[next].scrollIntoView({block:'nearest'});return}
 const id=focusedClip();const pending=pendingNow().some(c=>c.id===id);
 if(k==='x'&&id&&pending){e.preventDefault();setSelected(id,!selected.has(id));return}
 if((k==='a'||k==='r')&&(selected.size||(id&&pending))){e.preventDefault();if(!selected.size)setSelected(id,true);batchMode=k==='a'?'approve':'reject';drawBatch()}});
document.addEventListener('click',e=>{const f=e.target.closest('[data-filter]');if(f){filter=f.dataset.filter;keys.cards='';renderClips()}const c=e.target.closest('[data-clip]');if(c)openStudio(c.dataset.clip);const g=e.target.closest('[data-nav-go]');if(g)go(g.dataset.navGo);if(e.target.dataset?.do==='retry')act('/api/session/retry',{session:sessionId},'Sessão enviada de novo para a fila.').catch(()=>{})});
$('sessionSelect').onchange=()=>{sessionId=$('sessionSelect').value;localStorage.setItem('lc-session',sessionId);keys.cards='';renderClips()};
$('streamerSelect').onchange=()=>{streamerId=$('streamerSelect').value;localStorage.setItem('lc-streamer',streamerId);sessionId='';keys={};render()};
$('pauseBtn').onclick=()=>act('/api/pause',{paused:!state.paused},state.paused?'Análise iniciada.':'Análise pausada depois da tarefa atual.').catch(()=>{});
$('quitApp').onclick=async()=>{const a=state?.activity||{},p=[];if(a.capturas)p.push(`gravando ${a.capturas} live(s)`);if(a.analisando)p.push('analisando');if(a.exportando)p.push(`exportando ${a.exportando} clipe(s)`);
 const msg=p.length?`O Hook’s está ${p.join(' e ')}. Se encerrar agora, as gravações são finalizadas e o resto fica para a próxima vez. Encerrar mesmo assim?`:'Encerrar o Hook’s?';
 if(!confirm(msg))return;try{await api('/api/app/quit',{});pollBusy=true;document.body.innerHTML='<div style="display:grid;place-items:center;height:100vh;font:16px system-ui;text-align:center;padding:24px"><div><h2>Hook’s encerrado</h2><p>Gravações finalizadas e dados salvos. Pode fechar esta janela.</p></div></div>'}catch(e){toast(e.message,true)}};
$('backupBtn').onclick=()=>act('/api/backup/create',{},'Backup criado na pasta de dados.').catch(()=>{});
$('reclassifyBtn').onclick=()=>{if(confirm('Refazer as sugestões automáticas pendentes com o perfil e o aprendizado atuais? Cortes revisados e exportados são preservados.'))act('/api/regenerate',{streamer:streamerId},'Reclassificação iniciada.').catch(()=>{})};
$('sessionToggle').onclick=()=>{const s=session();if(s?.status==='archived')act('/api/session/archive',{session:sessionId,archived:false},'Sessão reativada.').catch(()=>{});else act('/api/session',{session:sessionId,enabled:!s.enabled},'Sessão atualizada.').catch(()=>{})};
$('sessionRetry').onclick=()=>act('/api/session/retry',{session:sessionId},'Sessão enviada de novo para a fila.').catch(()=>{});
$('relinkSource').onclick=()=>{const p=prompt('Cole o caminho completo do arquivo ou da pasta original:');if(p)act('/api/session/relink',{session:sessionId,path:p},'Original religado e verificado.').catch(()=>{})};
$('archiveSession').onclick=()=>{const s=session(),arch=s?.status!=='archived';if(!arch||confirm('Arquivar esta sessão? Originais, análises e cortes continuam preservados.'))act('/api/session/archive',{session:sessionId,archived:arch},arch?'Sessão arquivada.':'Sessão reativada.').catch(()=>{})};
$('closeSession').onclick=()=>act('/api/session',{session:sessionId,closed:true},'Gravação marcada como encerrada.').catch(()=>{});
$('openFolder').onclick=()=>act('/api/open-folder',{session:sessionId}).catch(()=>{});

/* ───── adicionar ───── */
function renderCaptures(){$('captureCount').textContent=`Lives em captura · ${state.captures.length}/${state.capture_limit}`;if(document.activeElement!==$('captureLimit'))$('captureLimit').value=state.capture_limit;$('stopAll').classList.toggle('hide',!state.captures.length);
 const k=JSON.stringify([state.captures,state.streamers.map(s=>s.name)]);if(k!==keys.caps){keys.caps=k;$('activeCaptures').innerHTML=state.captures.map(c=>`<div class="row" style="padding:8px 0"><span class="dot on"></span><strong>${esc(state.streamers.find(s=>s.id===c.streamer)?.name||'Streamer')}</strong><span class="muted small">Chat: ${esc(c.chat||'não conectado')}</span><span class="grow"></span><button class="small" data-capture-open="${c.streamer}" data-session="${c.session}">Ver cortes</button><button class="small danger" data-capture-stop="${c.session}">Encerrar</button></div>`).join('')||'<p class="help">Nenhuma live em captura.</p>'}}
let pre={at:0,streamer:null,busy:false};
function loadPreflight(force){if(!streamerId||pre.busy)return;if(!force&&pre.streamer===streamerId&&Date.now()-pre.at<20000)return;pre.busy=true;
 api('/api/preflight',{streamer:streamerId}).then(r=>{pre={at:Date.now(),streamer:streamerId,busy:false};renderPreflight(r)}).catch(()=>{pre.busy=false})}
function renderPreflight(r){const icon={ok:'✓',aviso:'!',erro:'✕'};
 $('preflight').innerHTML=`<div class="row" style="justify-content:space-between"><strong>Antes de gravar: ${r.level==='ok'?'tudo certo':r.level==='aviso'?'há avisos':'há um problema que impede'}</strong><button class="small quiet" id="preRefresh">Verificar de novo</button></div>`+
  r.checks.map(x=>`<div class="pre ${x.level}"><span class="pi">${icon[x.level]}</span><span class="grow"><b>${esc(x.title)}</b><br><span class="small muted">${esc(x.detail)}</span></span>${x.action&&x.action.startsWith('settings:')?`<button class="small" data-gopane="${esc(x.action.slice(9))}">Abrir ajustes</button>`:''}</div>`).join('')}
function renderPerf(){if(document.activeElement!==$('perfMode'))$('perfMode').value=state.engine_mode||'pistas';if(document.activeElement!==$('perfExports'))$('perfExports').value=String(state.export_workers||1)}
function savePerf(){act('/api/engine/mode',{lanes:$('perfMode').value,export_workers:Number($('perfExports').value)},'Desempenho atualizado.').catch(()=>{})}
$('perfMode').onchange=savePerf;$('perfExports').onchange=savePerf;
$('captureLimit').onchange=()=>act('/api/capture/limit',{limit:Number($('captureLimit').value)},'Limite atualizado.').catch(()=>{$('captureLimit').value=state.capture_limit});
$('stopAll').onclick=()=>act('/api/capture/stop-all',{},'Todas as capturas foram encerradas.').catch(()=>{});
$('activeCaptures').onclick=e=>{const o=e.target.closest('[data-capture-open]'),s=e.target.closest('[data-capture-stop]');if(o){streamerId=o.dataset.captureOpen;sessionId=o.dataset.session;keys={};go('clips')}if(s){s.disabled=true;act('/api/capture/stop',{session:s.dataset.captureStop},'Captura encerrada.').catch(()=>{s.disabled=false})}};
$('videoBtn').onclick=()=>{$('videoForm').reset();sourceMeta={};$('videoTestResult').textContent='';$('videoDialog').showModal();$('videoUrl').focus()};
$('fileBtn').onclick=()=>{$('fileForm').reset();$('fileDialog').showModal();$('videoPath').focus()};
$('liveBtn').onclick=()=>{$('captureForm').reset();sourceMeta={};$('captureTestResult').textContent='';$('capturePath').textContent=state.root+'\\'+streamer().name+'\\sessoes\\…';$('captureDialog').showModal();$('captureUrl').focus()};
$('videoTest').onclick=async()=>{const b=$('videoTest'),o=$('videoTestResult');b.disabled=true;o.textContent='Testando…';try{sourceMeta=await api('/api/capture/test',{streamer:streamerId,url:$('videoUrl').value});o.textContent=`${sourceMeta.plugin} · ${sourceMeta.author||'canal'} · ${sourceMeta.title||'vídeo'} · ${sourceMeta.selected}`}catch(e){sourceMeta={};o.textContent=e.message}finally{b.disabled=false}};
$('captureTest').onclick=async()=>{const b=$('captureTest'),o=$('captureTestResult');b.disabled=true;o.textContent='Testando…';try{const r=await api('/api/capture/test',{streamer:streamerId,url:$('captureUrl').value});sourceMeta=r;o.textContent=`${r.plugin} · ${r.author||'canal'} · ${r.selected}${r.warnings.length?' · '+r.warnings.join(' '):''}`}catch(e){sourceMeta={};o.textContent=e.message}finally{b.disabled=false}};
$('videoForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/video/url',{streamer:streamerId,url:$('videoUrl').value,reframe_mode:$('videoFraming').value});$('videoDialog').close();if(r.download){go('clips');pollRenders();toast('Baixando o vídeo do YouTube. Acompanhe na bandeja; quando terminar, a análise começa sozinha.');return}sessionId=r.id;keys={};await refresh(true);go('clips');toast('O Hook’s está assistindo e analisando o vídeo.')}catch(err){toast(err.message,true)}};
$('fileForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/video/import',{streamer:streamerId,path:$('videoPath').value,name:$('videoName').value,title:$('videoTitle').value,reframe_mode:$('fileFraming').value});$('fileDialog').close();sessionId=r.id;keys={};await refresh(true);go('clips');toast((r.riscos&&r.riscos.length)?'Arquivo vinculado. Atenção: '+r.riscos.map(x=>x.message).join(' '):'Arquivo vinculado e enviado para análise.')}catch(err){toast(err.message,true)}};
$('captureForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/capture/start',{streamer:streamerId,url:$('captureUrl').value,analyze:$('captureAnalyze').checked,title:sourceMeta.title||'',author:sourceMeta.author||'',plugin:sourceMeta.plugin||'',category:sourceMeta.category||''});$('captureDialog').close();sessionId=r.id;keys={};await refresh(true);go('clips');toast('Captura iniciada.')}catch(err){toast(err.message,true)}};
$('startDemo').onclick=async()=>{const b=$('startDemo');b.disabled=true;b.textContent='Preparando o exemplo…';try{const r=await api('/api/demo',{});streamerId=r.streamer;localStorage.setItem('lc-streamer',r.streamer);sessionId=r.session||'';keys={};await refresh(true);go('clips');toast('Exemplo pronto. Abra o corte para ver o Estúdio.')}catch(e){toast(e.message,true)}finally{b.disabled=false;b.textContent='Ver com um vídeo de exemplo'}};
$('loadingRetry').onclick=()=>{$('loadingText').textContent='Abrindo o Hook’s…';$('loadingRetry').classList.add('hide');$('loading').querySelector('.spin').classList.remove('stopped');refresh(true)};
$('newStreamer').onclick=$('firstStreamer').onclick=()=>{$('streamerForm').reset();$('streamerDialog').showModal();$('streamerName').focus()};
$('streamerForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/streamer',{name:$('streamerName').value});$('streamerDialog').close();streamerId=r.id;localStorage.setItem('lc-streamer',r.id);sessionId='';keys={};await refresh(true);go('add')}catch(err){toast(err.message,true)}};
$('importBtn').onclick=()=>{$('legacySelect').innerHTML=state.legacy.map(x=>`<option>${esc(x.name)}</option>`).join('')||'<option value="">Nenhuma gravação antiga encontrada</option>';$('importDialog').showModal()};
$('importForm').onsubmit=async e=>{e.preventDefault();if(!$('legacySelect').value)return;try{const r=await api('/api/import',{streamer:streamerId,name:$('legacySelect').value,closed:$('legacyClosed').checked});$('importDialog').close();sessionId=r.id;keys={};await refresh(true)}catch(err){toast(err.message,true)}};
$('manualBtn').onclick=()=>{const s=session();$('manualForm').reset();$('manualLimit').textContent=`Duração entre 1 e 90 s. Conteúdo analisado até ${clock(s.analyzed_until)}.`;$('manualDialog').showModal()};
$('manualForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/manual',{session:sessionId,start:Number($('manualStart').value),end:Number($('manualEnd').value)});$('manualDialog').close();await refresh(true);openStudio(r.id)}catch(err){toast(err.message,true)}};

/* ───── ajustes ───── */
function fillProfile(){const s=streamer();if(!s)return;const p=s.profile;profileStyle=p.editorial_style||'clean';$('profileTitle').textContent=s.name+' · ajustes';
 for(const [id,key,def] of [['autoZoom','auto_zoom',true],['autoCadence','auto_cadence',true],['autoSilence','auto_silence',true],['autoRepetition','auto_repetition',false],['autoGrade','auto_grade',true],['autoReframe','auto_reframe',true]])$(id).checked=p[key]??def;
 for(const [id,key] of [['clipFormat','clip_format'],['captionStyle','caption_style'],['behaviorSensitivity','behavior_sensitivity'],['permissionPolicy','permission_policy'],['speakerMode','speaker_mode'],['priority','priority'],['model','model'],['quality','capture_quality'],['whisperDevice','whisper_device'],['videoEncoder','video_encoder']])$(id).value=p[key]??(key==='whisper_device'?'auto':'cpu');
 $('hashtags').value=p.hashtags||'';$('deliveryFolder').value=p.delivery_folder||'';drawDeliverInfo();$('ollamaOn').checked=!!p.ollama;$('ollamaModel').value=p.ollama_model||'';drawLearning();fillAgents(p);fillAgents(p);
 $('aiMode').value=p.ai_mode||'padrao';$('coverOn').checked=p.cover??true;$('cutFade').value=p.cut_fade||'off';$('slowInterp').value=p.slow_interp||'off';$('stabilize').value=p.stabilize||'off';$('titleTemplate').value=p.title_template||'';$('autoColor').value=p.auto_color||'off';fillLuts(p.lut||'');$('lutStrength').value=p.lut_strength??1;$('lutStrengthOut').textContent=Math.round(($('lutStrength').value)*100)+'%';$('voicePreset').value=p.voice_preset||'off';$('coverTemplate').value=p.cover_template||'destaque';for(const f of ['1x1','4x5','16x9'])$('fmt'+f).checked=(p.export_formats||[]).includes(f);$('exportSrt').checked=!!p.export_srt;$('motionLevel').value=p.motion_level||'off';$('autoReplay').value=p.auto_replay||'off';$('silencePolicy').value=p.silence_policy||'pausas_longas';$('freeHeuristic').checked=p.free_heuristic??true;drawMarkers();$('language').value=p.language||'';$('threads').value=p.threads;$('reserve').value=p.min_free_gb;$('fontSize').value=p.font_size;$('margin').value=p.caption_margin;$('captionColor').value=rgb(p.caption_color);$('vocabulary').value=p.vocabulary||'';$('corrections').value=p.corrections||'';$('creditNote').value=p.credit_note||'';
 camRect=p.camera_rect?Array.from(p.camera_rect):null;trackRoi=p.track_roi?Array.from(p.track_roi):null;blurRegions=(p.blur_regions||[]).map(r=>({...r}));drawBlurList();camImage=null;$('cameraCanvas').dataset.session='';drawStyleGrid();drawCamera();updateCamera();
 const rp=state.root.split(/[\\/]/).filter(Boolean);$('rootPath').textContent='Dados em …\\'+rp.slice(-2).join('\\');$('toolsInfo').textContent=Object.entries(state.tools).map(([k,v])=>(v?'✓ ':'✕ ')+k).join('  ');$('events').innerHTML=state.events.map(x=>`<div>${esc(x.kind)}: ${esc(x.message)}</div>`).join('')}
function drawLearning(){const L=(state.learning||{})[streamerId];$('learnBox').textContent=!L?'':L.used>=4?`Aprendendo com ${L.used} clipes que você registrou.${L.up.length?' Mais peso a: '+L.up.join(', ')+'.':''}${L.down.length?' Menos peso a: '+L.down.join(', ')+'.':''}`:`Registre os números dos posts (visualizações, curtidas, salvamentos) no botão Publicar de cada clipe exportado. Faltam ${L.needed} clipe${L.needed===1?'':'s'} com 100+ visualizações para o sistema começar a aprender.`}
$('systemCheck').onclick=async()=>{const b=$('systemCheck'),o=$('systemInfo');b.disabled=true;o.textContent='Testando placa de vídeo e Ollama… pode levar alguns segundos.';try{const r=await api('/api/system/check',{});if(r.error){o.textContent=r.error;return}const enc=r.encoders.available.length?r.encoders.available.map(e=>e.label).join(', '):'nenhuma placa de vídeo passou no teste (o vídeo usa o processador)';o.innerHTML=`<div>Exportação por placa de vídeo: ${esc(enc)}.</div><div>Transcrição: ${r.cuda>0?r.cuda+' placa(s) NVIDIA com CUDA encontrada(s)':'sem CUDA (usa o processador)'}.</div><div>Ollama: ${r.ollama.running?'rodando · modelos: '+esc(r.ollama.models.join(', ')):'não encontrado neste computador'}.</div>`}catch(e){o.textContent=e.message}finally{b.disabled=false}};
function drawStyleGrid(){$('styleGrid').innerHTML=Object.entries(styleInfo).filter(([k])=>k!=='funny'||profileStyle==='funny').map(([k,[n]])=>`<button type="button" class="style-opt" aria-pressed="${k===profileStyle}" data-style="${k}"><b>${n}</b></button>`).join('');$('styleDetail').textContent=(styleInfo[profileStyle]||styleInfo.clean)[1]}
$('styleGrid').onclick=e=>{const b=e.target.closest('[data-style]');if(b){profileStyle=b.dataset.style;drawStyleGrid()}};
function updateCamera(){const s=session();$('camStatus').textContent=!s?'Adicione um conteúdo para preparar a imagem.':s.frame_status==='queued'?'Preparando imagem…':s.frame_status==='error'?s.frame_error:camRect?'Webcam marcada. Confira se corresponde ao streamer.':'Prepare a imagem e marque a webcam antes da primeira exportação de live.';if(s?.frame_status==='ready'&&$('cameraCanvas').dataset.session!==s.id){$('cameraCanvas').dataset.session=s.id;const img=new Image();img.onload=()=>{camImage=img;$('cameraCanvas').width=img.naturalWidth;$('cameraCanvas').height=img.naturalHeight;drawCamera()};img.src='/media/frame?id='+s.id}}
function drawCamera(){const c=$('cameraCanvas'),x=c.getContext('2d');x.fillStyle='#050b14';x.fillRect(0,0,c.width,c.height);if(camImage)x.drawImage(camImage,0,0,c.width,c.height);else{x.fillStyle='#8fa1b8';x.font='20px Segoe UI';x.fillText('Prepare a imagem da sessão para marcar a webcam.',32,c.height/2)}blurRegions.forEach((r,i)=>{const X=r.x*c.width,Y=r.y*c.height,W=r.w*c.width,H=r.h*c.height;x.fillStyle='rgba(255,80,110,.28)';x.fillRect(X,Y,W,H);x.setLineDash([10,6]);x.strokeStyle='#ff506e';x.lineWidth=3;x.strokeRect(X,Y,W,H);x.setLineDash([]);x.fillStyle='#ff506e';x.font='bold 22px Segoe UI';x.fillText(String(i+1),X+8,Y+26)});
if(camRect){x.strokeStyle='#ffb938';x.lineWidth=4;x.strokeRect(camRect[0]*c.width,camRect[1]*c.height,camRect[2]*c.width,camRect[3]*c.height)}
if(trackRoi){x.setLineDash([2,6]);x.strokeStyle='#38d6ff';x.lineWidth=4;x.strokeRect(trackRoi[0]*c.width,trackRoi[1]*c.height,trackRoi[2]*c.width,trackRoi[3]*c.height);x.setLineDash([])}
if(drag0&&dragNow&&markMode==='blur'){x.setLineDash([6,6]);x.strokeStyle='#ff506e';x.lineWidth=2;x.strokeRect(dragNow[0]*c.width,dragNow[1]*c.height,dragNow[2]*c.width,dragNow[3]*c.height);x.setLineDash([])}}
function blurOverlapsCam(){return !!camRect&&blurRegions.some(r=>r.x<camRect[0]+camRect[2]&&r.x+r.w>camRect[0]&&r.y<camRect[1]+camRect[3]&&r.y+r.h>camRect[1])}
function drawBlurList(){const box=$('blurList');if(!box)return;box.innerHTML=blurRegions.length?blurRegions.map((r,i)=>`<div class="row" style="align-items:center;margin-bottom:6px"><span class="chip">${i+1}</span><input class="grow" data-blur-label="${i}" maxlength="40" placeholder="Nome (ex.: chat, doação)" value="${esc(r.label||'')}" aria-label="Nome da área ${i+1}"><span class="muted small">${Math.round(r.w*100)}% × ${Math.round(r.h*100)}%</span><button type="button" class="small" data-blur-del="${i}">Remover</button></div>`).join('')+(blurOverlapsCam()?'<p class="help" style="color:var(--warn,#ffb938)">Uma área a borrar cobre parte da webcam.</p>':''):'<p class="help">Nenhuma área marcada. Escolha “Marcar área a borrar” e arraste sobre a imagem.</p>';
 box.querySelectorAll('[data-blur-del]').forEach(b=>b.onclick=()=>{blurRegions.splice(+b.dataset.blurDel,1);drawBlurList();drawCamera()});
 box.querySelectorAll('[data-blur-label]').forEach(i=>i.oninput=()=>{blurRegions[+i.dataset.blurLabel].label=i.value})}
let drag0=null;const cpt=e=>{const r=$('cameraCanvas').getBoundingClientRect();return[Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]};
$('camAuto').onclick=async()=>{const s=session();if(!s){toast('Escolha uma sessão com vídeo gravado.');return}
 $('camAuto').disabled=true;$('camAuto').textContent='Procurando…';
 try{const r=await api('/api/camera/detect',{session:s.id});
  if(r.found){camRect=r.rect;drawCamera();updateCamera();toast(`Achei (${r.level}). ${r.reason} Confira o retângulo e clique em Salvar.`)}
  else toast(r.reason||'Não encontrei a webcam. Marque à mão.')}
 catch(e){toast(e.message||'Falha ao localizar a webcam.')}
 finally{$('camAuto').disabled=false;$('camAuto').textContent='Localizar a webcam automaticamente'}};

async function drawMarkers(){const box=$('markInfo');if(!box)return;const s=session();if(!s){box.textContent='Escolha uma sessão para marcar momentos.';return}
 try{const r=await api('/api/session/markers',{session:s.id});const n=r.markers.length;const sub=r.subtitles.count;
  const ex=r.external_audio;$('extInfo').textContent=ex?(ex.ok?'Áudio externo sincronizado (deslocamento '+ex.offset+' s). Entra no lugar do áudio do vídeo.':'Áudio externo recusado: '+(ex.reason||'sem motivo')):'Nenhum áudio externo vinculado.';
  box.textContent=(n?n+' marcador(es) nesta sessão'+(r.markers.some(m=>m.approx)?' (alguns estimados pelo relógio)':'')+'. ':'Nenhum marcador nesta sessão. ')+(sub?sub+' fala(s) de legenda importada.':'Nenhuma legenda importada.')+(r.warnings.length?' Avisos: '+r.warnings.join(' · '):'')}
 catch(e){box.textContent=e.message||'Não consegui ler os marcadores.'}}
async function markAct(path,data,ok){const s=session();if(!s){toast('Escolha uma sessão primeiro.',true);return}
 try{const r=await api(path,{session:s.id,...data});toast(typeof ok==='function'?ok(r):ok);drawMarkers()}catch(e){toast(e.message,true)}}
$('markNow').onclick=()=>markAct('/api/session/marker',{label:$('markLabel').value,epoch:Date.now()/1000},r=>r.approx?'Momento marcado (estimado: ainda está no pedaço que está sendo gravado).':'Momento marcado.');
$('markPick').onclick=()=>$('markFile').click();$('subPick').onclick=()=>$('subFile').click();
$('markFile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;if(f.size>900000){toast('Arquivo grande demais.',true);return}markAct('/api/session/markers/import',{name:f.name,content:await f.text()},r=>r.imported+' marcador(es) importado(s). Os cortes serão refeitos.')};
$('subFile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;if(f.size>900000){toast('Arquivo grande demais.',true);return}markAct('/api/session/subtitles/import',{name:f.name,content:await f.text()},r=>r.imported+' fala(s) importada(s). Elas só viram texto de legenda.')};
$('markClear').onclick=()=>markAct('/api/session/markers/clear',{},'Marcadores apagados.');
$('subClear').onclick=()=>markAct('/api/session/subtitles/clear',{},'Legendas importadas apagadas.');

function fillLuts(current){const sel=$('lutSelect');const list=state?.luts||[];sel.innerHTML='<option value="">Nenhuma</option>'+list.map(l=>`<option value="${esc(l.file)}">${esc(l.file)}</option>`).join('');sel.value=list.some(l=>l.file===current)?current:''}
$('lutUpload').onclick=()=>$('lutFile').click();
$('lutFile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;try{const it=await upload('lut',f);await refresh(true);fillLuts(it.file);toast('LUT “'+it.file+'” instalada. Salve os ajustes para usar.')}catch(err){toast(err.message,true)}};
$('lutStrength').oninput=()=>{$('lutStrengthOut').textContent=Math.round($('lutStrength').value*100)+'%'};

$('extLink').onclick=()=>{const v=$('extPath').value.trim();if(!v){toast('Cole o caminho completo do arquivo de áudio.',true);return}markAct('/api/session/external-audio',{path:v},r=>r.linked.ok?'Áudio sincronizado ('+r.linked.offset+' s).':'Não sincronizei: '+r.linked.reason)};
$('extClear').onclick=()=>markAct('/api/session/external-audio/clear',{},'Áudio externo desvinculado.');
$('cameraCanvas').onpointerdown=e=>{if(!camImage)return;drag0=cpt(e);dragNow=null;e.target.setPointerCapture(e.pointerId)};
$('cameraCanvas').onpointermove=e=>{if(!drag0)return;const p=cpt(e),r=[Math.min(p[0],drag0[0]),Math.min(p[1],drag0[1]),Math.abs(p[0]-drag0[0]),Math.abs(p[1]-drag0[1])];if(markMode==='blur')dragNow=r;else if(markMode==='track')trackRoi=r;else camRect=r;drawCamera()};
$('cameraCanvas').onpointerup=()=>{if(markMode==='blur'&&dragNow){if(dragNow[2]>=.02&&dragNow[3]>=.02){if(blurRegions.length>=6)toast('Use no máximo 6 áreas a borrar.',true);else blurRegions.push({x:dragNow[0],y:dragNow[1],w:dragNow[2],h:dragNow[3],label:''})}drawBlurList()}drag0=null;dragNow=null;drawCamera()};
function setMark(m){markMode=m;$('markCam').setAttribute('aria-pressed',m==='cam');$('markBlur').setAttribute('aria-pressed',m==='blur');$('markTrack').setAttribute('aria-pressed',m==='track');$('cameraCanvas').style.cursor='crosshair'}
$('markCam').onclick=()=>setMark('cam');$('markBlur').onclick=()=>setMark('blur');$('markTrack').onclick=()=>setMark('track');$('clearTrack').onclick=()=>{trackRoi=null;drawCamera()};
$('getFrame').onclick=()=>{if(!sessionId){toast('Adicione ou selecione um conteúdo primeiro.',true);return}act('/api/frame',{session:sessionId},'Imagem na fila.').catch(()=>{})};
$('profileForm').onsubmit=async e=>{e.preventDefault();const p={...streamer().profile,delivery_folder:$('deliveryFolder').value.trim(),camera_rect:camRect,track_roi:trackRoi,blur_regions:blurRegions.map(r=>({x:r.x,y:r.y,w:r.w,h:r.h,label:r.label||''})),editorial_style:profileStyle,clip_format:$('clipFormat').value,quality_mode:$('qualityMode').value,auto_zoom:$('autoZoom').checked,auto_cadence:$('autoCadence').checked,auto_grade:$('autoGrade').checked,auto_silence:$('autoSilence').checked,auto_repetition:$('autoRepetition').checked,auto_reframe:$('autoReframe').checked,caption_style:$('captionStyle').value,behavior_sensitivity:$('behaviorSensitivity').value,vocabulary:$('vocabulary').value,corrections:$('corrections').value,permission_policy:$('permissionPolicy').value,speaker_mode:$('speakerMode').value,credit_note:$('creditNote').value,language:$('language').value||null,model:$('model').value,priority:$('priority').value,capture_quality:$('quality').value,threads:Number($('threads').value),min_free_gb:Number($('reserve').value),font_size:Number($('fontSize').value),caption_margin:Number($('margin').value),caption_color:bgr($('captionColor').value),whisper_device:$('whisperDevice').value,video_encoder:$('videoEncoder').value,hashtags:$('hashtags').value,ollama:$('ollamaOn').checked,ollama_model:$('ollamaModel').value,second_pass:$('secondPass').value,ai_mode:$('aiMode').value,cover:$('coverOn').checked,cut_fade:$('cutFade').value,slow_interp:$('slowInterp').value,stabilize:$('stabilize').value,title_template:$('titleTemplate').value.trim(),auto_color:$('autoColor').value,lut:$('lutSelect').value,lut_strength:Number($('lutStrength').value),voice_preset:$('voicePreset').value,cover_template:$('coverTemplate').value,export_formats:['1x1','4x5','16x9'].filter(f=>$('fmt'+f).checked),export_srt:$('exportSrt').checked,motion_level:$('motionLevel').value,auto_replay:$('autoReplay').value,silence_policy:$('silencePolicy').value,free_heuristic:$('freeHeuristic').checked,brand:collectBrand()};try{await api('/api/profile',{streamer:streamerId,profile:p});await refresh(true);toast(state.regeneration?.[streamerId]?'Ajustes salvos. As sugestões automáticas estão sendo refeitas.':'Ajustes salvos.')}catch(err){toast(err.message,true)}};

function deliverStats(){const rows=state.candidates.filter(c=>c.streamer===streamerId&&c.status==='done');const by=s=>rows.filter(c=>(c.data.delivery||{}).status===s).length;return {done:rows.length,ok:by('ok'),pend:by('pendente'),err:by('erro')}}
function drawDeliverInfo(){const el=$('deliverInfo');if(!el)return;const p=streamer()?.profile||{};if(!p.delivery_folder){el.textContent='Sem pasta de entrega definida.';return}const d=deliverStats();el.textContent=`${d.ok} de ${d.done} prontos já copiados${d.pend?` · ${d.pend} esperando a pasta aparecer`:''}${d.err?` · ${d.err} com erro (veja no corte)`:''}.`}
$('deliverReady').onclick=async()=>{try{await api('/api/delivery/ready',{streamer:streamerId});toast('Copiando os cortes prontos para a pasta de entrega…');setTimeout(()=>refresh(true).then(drawDeliverInfo),2500)}catch(e){toast(e.message,true)}};

/* Painel de progresso real dos cortes (vem do FFmpeg; sem temporizador). Cada tarefa tem um id: dados de execução antiga não entram. */
const renderState={tasks:[],seen:{},timer:null,key:''};
const RSTATE={na_fila:['Na fila',''],preparando:['Preparando','warn'],processando:['Processando','warn'],finalizando:['Finalizando','warn'],concluido:['✓ Concluído','ok'],cancelado:['Cancelado','bad'],falhou:['✕ Falhou','bad']};
function mmss(s){s=Math.max(0,Math.round(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
function drawRenders(){
 const tray=$('renderTray');if(!tray)return;
 const list=renderState.tasks.filter(t=>!renderState.seen[t.task]||renderState.seen[t.task]!=='hidden');
 const key=JSON.stringify(list.map(t=>[t.task,t.state,t.stage,t.percent,t.elapsed_s,t.eta_s]));
 if(key===renderState.key)return;renderState.key=key;
 tray.innerHTML=list.map(t=>{const [name,cls]=RSTATE[t.state]||[t.state,''],active=t.can_cancel,det=t.determinate||t.state==='concluido';
  const pct=Math.round(t.percent),dl=t.kind==='download',lbl=`${dl?'Download':t.kind==='previa'?'Prévia':'Exportação'}: ${t.label}`;
  const bar=`<div class="rbar${det||t.percent>0&&!active?'':' indet'}" ${det?`role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="${esc(lbl)}"`:`role="progressbar" aria-label="${esc(lbl)} (sem medida de progresso nesta etapa)"`}><i style="width:${det||!active?pct:Math.max(pct,0)}%"></i></div>`;
  const meta=[det||t.percent>0?pct+'%':'',t.elapsed_s?mmss(t.elapsed_s)+' decorridos':'',t.eta_s!=null?'restam cerca de '+mmss(t.eta_s):''].filter(Boolean).join(' · ');
  const err=t.state==='falhou'||t.state==='cancelado'?`<div class="rmeta">${esc(t.error||(dl?'Cole o link de novo para tentar outra vez.':'As escolhas do corte foram mantidas.'))}</div>`:'';
  const acts=active?`<div class="ract"><button class="small" data-rcancel="${esc(t.candidate)}">Cancelar</button></div>`:`<div class="ract">${dl?'':`<button class="small" data-ropen="${esc(t.candidate)}">${t.state==='concluido'?'Abrir o corte':'Ver o corte e tentar de novo'}</button>`}<button class="small" data-rhide="${esc(t.task)}" aria-label="Dispensar aviso">Dispensar</button></div>`;
  return `<div class="rtask" data-task="${esc(t.task)}"><div class="rtitle"><b title="${esc(lbl)}">${esc(t.label)}</b><span class="rstate ${cls}">${name}</span></div><div class="rstage">${esc(t.state==='concluido'?(dl?'Vídeo baixado. A análise começou.':t.kind==='previa'?'A prévia está pronta.':'O corte está pronto e entregue.'):t.stage)}</div>${bar}<div class="rmeta">${meta}</div>${err}${acts}</div>`}).join('');
}
async function pollRenders(){
 try{const r=await api('/api/renders');const before=renderState.tasks.map(t=>t.task+t.state).join();renderState.tasks=r.renders||[];
  const after=renderState.tasks.map(t=>t.task+t.state).join();drawRenders();
  if(before!==after&&renderState.tasks.some(t=>!t.can_cancel&&t.state!=='na_fila'))refresh(true)}catch(e){}
 const active=renderState.tasks.some(t=>t.can_cancel||t.state==='na_fila');
 clearTimeout(renderState.timer);renderState.timer=setTimeout(pollRenders,document.hidden?5000:active?800:3500);
}
document.addEventListener('click',async e=>{
 const c=e.target.closest('[data-rcancel]'),o=e.target.closest('[data-ropen]'),h=e.target.closest('[data-rhide]');
 if(c){c.disabled=true;try{const r=await api('/api/render/cancel',{candidate:c.dataset.rcancel});toast(r.result==='cancelando'?'Cancelando… os arquivos temporários deste corte serão removidos.':'Corte removido da fila.');pollRenders();refresh(true)}catch(err){toast(err.message,true);c.disabled=false}}
 else if(o){openStudio(o.dataset.ropen)}
 else if(h){renderState.seen[h.dataset.rhide]='hidden';renderState.key='';drawRenders()}
});
pollRenders();
