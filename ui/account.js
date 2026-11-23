/* ───── assinatura ───── */
let licMode='login',licAsked=false;
const L=()=>state&&state.license||{mode:'livre',ok:true};
const licNum=(n,d=1)=>Number(n||0).toLocaleString('pt-BR',{maximumFractionDigits:d});
const licDate=t=>t?new Date(t*1000).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric'}):'—';
const licWhen=t=>t?new Date(t*1000).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'nunca';
const licPlanName=l=>l.plan_name||'—';

function licenseTick(){const l=L();
 $('navAccount').classList.toggle('hide',l.mode==='livre');
 // abre o login uma vez por sessão do painel, sem prender a tela: o aviso fica fixo em cima
 if(l.needs_login&&!licAsked&&!$('licenseDialog').open){licAsked=true;licOpen('login')}
 if(!l.needs_login)licAsked=false}

function licenseBanners(){const l=L(),a=[];if(l.mode==='livre')return a;
 const btnLogin='<button class="small primary" data-lic="login">Entrar</button>',btnPortal='<button class="small" data-lic="portal">Abrir minha conta</button>',btnSync='<button class="small" data-lic="sync">Tentar agora</button>';
 if(l.state==='sem_login'||l.state==='invalida')a.push(`<div class="banner error"><span><b>Entre com a sua conta para usar o Hook’s.</b> ${esc(l.last_error||'')}</span>${btnLogin}</div>`);
 else if(l.state==='expirada')a.push(`<div class="banner error"><span><b>Sua assinatura venceu.</b> Lives em andamento continuam gravando, mas não dá para iniciar outra, analisar nem aprovar cortes.</span>${btnPortal}</div>`);
 else if(l.state==='suspensa')a.push(`<div class="banner error"><span><b>Assinatura suspensa.</b> ${esc(l.message)}</span>${btnPortal}</div>`);
 else if(l.state==='offline')a.push(`<div class="banner error"><span><b>Falta confirmar a assinatura.</b> ${esc(l.message)}${l.last_error?'<br><span class="small muted">'+esc(l.last_error)+'</span>':''}</span>${btnSync}</div>`);
 else if(l.state==='relogio')a.push(`<div class="banner error"><span><b>Relógio do computador atrasado.</b> ${esc(l.message)}</span>${btnSync}</div>`);
 else if(l.state==='atraso')a.push(`<div class="banner"><span><b>Pagamento em atraso.</b> ${esc(l.message)}</span>${btnPortal}</div>`);
 else if(l.state==='teste'&&l.period){const days=Math.ceil((l.period[1]*1000-Date.now())/864e5);if(days<=3)a.push(`<div class="banner"><span><b>Seu teste termina ${days<=0?'hoje':days===1?'amanhã':'em '+days+' dias'}.</b> Assine para continuar usando.</span>${btnPortal}</div>`)}
 if(l.ok&&l.limits){
  if(l.hours_ratio>=1)a.push(`<div class="banner error"><span><b>As horas de live do plano acabaram.</b> A gravação continua, mas a análise está pausada até o plano renovar ou subir.</span>${btnPortal}</div>`);
  else if(l.hours_ratio>=.8)a.push(`<div class="banner"><span><b>Você usou ${Math.round(l.hours_ratio*100)}% das horas de live do período.</b> ${licNum(l.usage.horas)} de ${licNum(l.limits.horas,0)} h.</span>${btnPortal}</div>`);
  if(l.clips_ratio>=1)a.push(`<div class="banner error"><span><b>Você chegou ao limite de clipes do período.</b> Não dá para aprovar novos cortes até o plano renovar ou subir.</span>${btnPortal}</div>`);
  else if(l.clips_ratio>=.8)a.push(`<div class="banner"><span><b>Você usou ${Math.round(l.clips_ratio*100)}% dos clipes do período.</b> ${licNum(l.usage.clipes,0)} de ${licNum(l.limits.clipes,0)}.</span>${btnPortal}</div>`)}
 return a}

function renderAccount(){const l=L();if(l.mode==='livre'){$('accBody').innerHTML='<div class="sect box"><h3>Modo livre</h3><p class="help">Este programa não exige conta nem tem limites de plano.</p></div>';return}
 $('accSub').textContent=l.email?`Conta ${l.email}`:'Entre para ver o seu plano.';
 if(!l.email){$('accBody').innerHTML=`<div class="sect box"><h3>Você ainda não entrou</h3><p class="help">${esc(l.message)}</p><div class="row" style="margin-top:12px"><button class="primary" data-lic="login">Entrar</button><button data-lic="register">Criar conta</button></div></div>`;return}
 const bar=(used,lim,unit)=>{const p=lim?Math.min(100,Math.round(used/lim*100)):0;return `<div style="margin:14px 0"><div class="row" style="justify-content:space-between"><span>${unit[0]}</span><span class="muted">${licNum(used,unit[2])} de ${licNum(lim,0)} ${unit[1]}</span></div><div class="bar" style="margin-top:6px"><i style="width:${p}%;${p>=100?'background:var(--bad)':p>=80?'background:var(--amber)':''}"></i></div></div>`};
 const chipState={teste:['Teste',''],ativa:['Ativa',''],atraso:['Em atraso',''],cancelada:['Cancelada',''],suspensa:['Suspensa',''],expirada:['Vencida','']}[l.state]||[l.state,''];
 $('accBody').innerHTML=`<div class="settings" style="display:block"><div class="sect box"><div class="row" style="justify-content:space-between"><div><h3 style="margin:0">${esc(licPlanName(l))}</h3><p class="help" style="margin:4px 0 0">${esc(l.message)}</p></div><span class="chip">${esc(chipState[0])}</span></div>
 <p class="help" style="margin-top:10px">Período atual até <b>${licDate(l.period&&l.period[1])}</b>${l.cancel_at_period_end?' · <b>não renova</b>':''}.</p></div>
 <div class="sect box"><h4>Uso neste período</h4>${l.limits?bar(l.usage.horas,l.limits.horas,['Horas de live analisadas','h',1])+bar(l.usage.clipes,l.limits.clipes,['Clipes exportados','',0]):''}
 <p class="help">${l.limits?`Até ${l.limits.lives} live(s) ao mesmo tempo · ${l.limits.canais} canal(is) · ${l.limits.dispositivos} computador(es). `:''}O uso zera quando o período renova. Rever a análise de um trecho já analisado não cobra de novo.</p></div>
 <div class="sect box"><h4>Este computador</h4><p class="help">Última confirmação com o servidor: <b>${licWhen(l.last_sync)}</b>. A licença vale sem internet até <b>${licWhen(l.valid_until)}</b>.${l.pending_events?` ${l.pending_events} registro(s) de uso aguardando envio.`:''}${l.last_error?`<br><span style="color:var(--bad)">${esc(l.last_error)}</span>`:''}</p>
 <div class="row" style="margin-top:10px"><button class="small" data-lic="sync">Sincronizar agora</button><button class="small danger" data-lic="logout">Sair da conta</button></div></div>
 <p class="help">${l.terms_url?`<a href="${esc(l.terms_url)}" target="_blank" rel="noopener">Termos de Uso</a> · <a href="${esc(l.privacy_url)}" target="_blank" rel="noopener">Política de Privacidade</a>`:''}${l.support_url?` · <a href="${esc(l.support_url)}" target="_blank" rel="noopener">Suporte</a>`:''}</p></div>`}

/* login, cadastro e esqueci a senha */
function licOpen(mode){licMode=mode;const l=L(),reg=mode==='register',fg=mode==='forgot';
 $('licTitle').textContent=reg?'Criar conta':fg?'Recuperar senha':'Entrar no Hook’s';
 $('licSub').textContent=reg?'Teste grátis, sem cartão. Você usa o Hook’s neste computador.':fg?'Enviamos um link para criar uma nova senha.':'Use a conta que você criou para assinar.';
 $('licNameBox').classList.toggle('hide',!reg);$('licTermsBox').classList.toggle('hide',!reg);$('licPassBox').classList.toggle('hide',fg);
 $('licPass').required=!fg;$('licName').required=reg;$('licTerms').required=reg;$('licPass').autocomplete=reg?'new-password':'current-password';
 $('licGo').textContent=reg?'Criar conta e começar':fg?'Enviar link':'Entrar';
 $('licSwap').textContent=reg?'Já tenho conta':'Criar conta';$('licForgot').classList.toggle('hide',fg);
 $('licTermsLink').href=l.terms_url||'#';$('licPrivLink').href=l.privacy_url||'#';
 $('licNote').textContent=reg?'A senha precisa ter pelo menos 10 caracteres.':'';
 if(!$('licenseDialog').open)$('licenseDialog').showModal();$('licEmail').focus()}
$('licSwap').onclick=()=>licOpen(licMode==='register'?'login':'register');
$('licForgot').onclick=()=>licOpen('forgot');
$('licenseForm').onsubmit=async e=>{e.preventDefault();const b=$('licGo');b.disabled=true;
 try{const email=$('licEmail').value.trim();
  if(licMode==='forgot'){await act('/api/license/forgot',{email},'Se o e-mail estiver cadastrado, o link chega em instantes.');licOpen('login')}
  else if(licMode==='register'){await act('/api/license/register',{name:$('licName').value,email,password:$('licPass').value,accept_terms:$('licTerms').checked},'Conta criada. Seu teste começou.');$('licenseDialog').close();$('licPass').value=''}
  else{await act('/api/license/login',{email,password:$('licPass').value},'Você entrou.');$('licenseDialog').close();$('licPass').value=''}
 }catch(err){$('licNote').textContent=err.message}finally{b.disabled=false}};

document.addEventListener('click',async e=>{const d=e.target.closest?.('[data-lic]');if(!d)return;const k=d.dataset.lic,l=L();
 if(k==='login')licOpen('login');
 if(k==='register')licOpen('register');
 if(k==='portal'&&l.portal_url)window.open(l.portal_url,'_blank','noopener');
 if(k==='sync')licSync(d);
 if(k==='logout'){if(!confirm('Sair da conta neste computador? Você precisará entrar de novo para analisar e exportar.'))return;act('/api/license/logout',{},'Você saiu da conta.').catch(()=>{})}});
async function licSync(btn){btn.disabled=true;try{const v=await api('/api/license/refresh',{});await refresh(true);toast(v.ok?'Assinatura confirmada.':v.message,!v.ok)}catch(err){toast(err.message,true)}finally{btn.disabled=false}}
$('accSync').onclick=e=>licSync(e.currentTarget);
$('accPortal').onclick=()=>{const l=L();if(l.portal_url)window.open(l.portal_url,'_blank','noopener');else toast('O endereço da sua conta não está configurado.',true)};
