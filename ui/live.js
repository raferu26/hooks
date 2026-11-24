/* ───── prévia ao vivo: legenda e título desenhados sobre o vídeo, no relógio do clipe ───── */
const LIVE={on:true};
/* libass mede Fontsize pela altura da célula da linha (ascendente+descendente), o CSS pela altura do em: mesma fonte e mesmo número saem ~10% menores no vídeo final.
   Fator medido com a mesma fonte (validacao/legenda_fidelidade.py): largura ASS/HTML = 0,899. */
const CAP_SCALE=.9;
/* [deslocamento de tamanho, teto] por estilo = CAPTION_STYLES de captions.py (tests/test_legenda_previa.py garante que não divergem) */
const CAP_SIZE={dynamic:[0,0],clean:[-3,0],bold:[5,68],minimal:[-6,0],impact:[8,70],pop:[2,0],box:[-2,0]};
function capSize(style,base){const [off,cap]=CAP_SIZE[style]||[0,0];return style==='dynamic'?base:Math.min(cap||1e9,Math.max(24,base+off))}
function liveCaptionLook(){const P=ST.proj,d=ST.data,pf=d.profile;let style=P.captions.style||pf.caption_style||'dynamic';if(style==='auto')style='dynamic';
 return{style,size:capSize(style,P.captions.size??pf.font_size??46),margin:P.captions.margin??pf.caption_margin??340,color:P.captions.color||(pf.caption_color?rgb(pf.caption_color):'#ffd400'),font:pf.brand_font||''}}
function liveLine(t){for(const l of ST.lines){if(t>=l.start-.02&&t<=l.end+.05)return l}return null}
let CAPG={key:'',groups:[]};
function capGroupsNow(style){const key=style+'|'+ST.id+'|'+ST.rev+'|'+ST.lines.length;if(CAPG.key!==key){const [mw,mc]=capChunkFor(style);CAPG={key,groups:capSmartGroups(capWordsOf(ST.lines),mw,mc)}}return CAPG.groups}
function drawLive(){const host=$('live');if(!host||!ST.open)return;
 if(!LIVE.on||!ST.data.preview.available){host.innerHTML='';return}
 const v=$('stVideo'),t=isNaN(v.currentTime)?0:finalToClip(v.currentTime),look=liveCaptionLook(),P=ST.proj;let html='';
 // títulos (1280 de altura = 100cqh)
 for(const ti of P.titles){if(t<ti.start||t>ti.end)continue;const st=TITLE_SPEC[ti.style||'big']?(ti.style||'big'):'big',pos=ti.position||'top',sp=TITLE_SPEC[st];
  /* tamanho, margens, caixa alta e quebras = captions.title_blocks (tests/test_legenda_previa.py); a barra e o título de topo têm caixa atrás, como no ASS (BorderStyle 3) */
  const hex=/^#[0-9a-f]{6}$/i.test(ti.color||'')?ti.color:'#ffffff',lum=(.299*parseInt(hex.slice(1,3),16)+.587*parseInt(hex.slice(3,5),16)+.114*parseInt(hex.slice(5,7),16))/255;
  const mv=pos==='top'&&ti.margin_frac!=null?Math.max(0,Math.min(900,Math.round(+ti.margin_frac*1280))):(TITLE_MARGIN[pos]??170);
  const y=pos==='center'?'top:50cqh;transform:translateY(-50%)':pos==='bottom'?`bottom:${mv/12.8}cqh`:`top:${mv/12.8}cqh`;
  const txt=capWrap(sp.upper?String(ti.text).toUpperCase():String(ti.text),sp.wrap,3).map(esc).join('<br>');
  const ink=st==='bar'?(lum>.55?'#101010':'#fff'):hex;
  html+=`<div class="ttl t-${st}" style="${y};font-size:${sp.size/12.8*CAP_SCALE}cqh;--tc:${esc(hex)};--ink:${ink}"><span class="in">${txt}</span></div>`}
 if(P.captions.enabled){const l=liveLine(t);
  /* Sem edição de texto, a exportação quebra a fala em blocos pelo estilo (captions.smart_groups); com texto editado, cada linha é um bloco.
     A prévia faz o mesmo: mostra o bloco que a exportação mostraria neste instante (paridade: tests/test_legenda_previa.py). */
  let words=l&&l.words&&l.words.length?l.words:null,shown=l;
  if(l&&words&&!ST.linesEdited){const gr=capGroupsNow(look.style),g=capGroupAt(gr,t);if(g){words=g.map(w=>({start:w.start,end:w.end,word:w.text}));shown=l}else shown=null}
  if(shown){
  const inner=words?words.map(w=>`<span class="w${t>=w.start&&t<=w.end+.02?' on':''}">${esc(w.word)}</span>`).join(' '):esc(l.text);
  html+=`<div class="cap s-${look.style}" style="bottom:${look.margin/12.8}cqh;font-size:${look.size/12.8*CAP_SCALE}cqh;--cap-color:${esc(look.color)};${look.font?`font-family:'${esc(look.font)}',sans-serif;`:''}"><span class="in">${inner}</span></div>`}}
 if(host.innerHTML!==html)host.innerHTML=html}
$('liveToggle').onchange=()=>{LIVE.on=$('liveToggle').checked;drawLive()};
