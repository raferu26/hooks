/* ───── prévia ao vivo: legenda e título desenhados sobre o vídeo, no relógio do clipe ───── */
const LIVE={on:true};
function liveCaptionLook(){const P=ST.proj,d=ST.data,pf=d.profile;let style=P.captions.style||pf.caption_style||'dynamic';if(style==='auto')style='dynamic';
 return{style,size:P.captions.size??pf.font_size??46,margin:P.captions.margin??pf.caption_margin??340,color:P.captions.color||(pf.caption_color?rgb(pf.caption_color):'#ffd400'),font:pf.brand_font||''}}
function liveLine(t){for(const l of ST.lines){if(t>=l.start-.02&&t<=l.end+.05)return l}return null}
function drawLive(){const host=$('live');if(!host||!ST.open)return;
 if(!LIVE.on||!ST.data.preview.available){host.innerHTML='';return}
 const v=$('stVideo'),t=isNaN(v.currentTime)?0:finalToClip(v.currentTime),look=liveCaptionLook(),P=ST.proj;let html='';
 // títulos (1280 de altura = 100cqh)
 for(const ti of P.titles){if(t<ti.start||t>ti.end)continue;const st=ti.style||'big',pos=ti.position||'top',size=st==='top'?52:st==='bar'?58:84;
  const y=pos==='top'?'top:12cqh':pos==='center'?'top:50cqh;transform:translateY(-50%)':'bottom:26cqh';
  html+=`<div class="ttl ${st}" style="${y};font-size:${size/12.8}cqh;--tc:${esc(ti.color||'#fff')}">${esc(ti.text)}</div>`}
 if(P.captions.enabled){const l=liveLine(t);if(l){const words=l.words&&l.words.length?l.words:null;
  const inner=words?words.map(w=>`<span class="w${t>=w.start&&t<=w.end+.02?' on':''}">${esc(w.word)}</span>`).join(' '):esc(l.text);
  html+=`<div class="cap s-${look.style}" style="bottom:${look.margin/12.8}cqh;font-size:${look.size/12.8}cqh;--cap-color:${esc(look.color)};${look.font?`font-family:'${esc(look.font)}',sans-serif;`:''}"><span class="in">${inner}</span></div>`}}
 if(host.innerHTML!==html)host.innerHTML=html}
$('liveToggle').onchange=()=>{LIVE.on=$('liveToggle').checked;drawLive()};
