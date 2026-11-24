/* Quebra da legenda em blocos, IDÊNTICA à da exportação (captions.smart_groups / CAPTION_STYLES). Funções puras: valem no navegador e no node.
   A paridade com o Python é garantida por tests/test_legenda_previa.py (mesmas entradas, mesmos blocos). Não edite sem rodar o teste. */
const CAP_WEAK=new Set(['a','o','as','os','um','uma','de','do','da','dos','das','em','no','na','nos','nas','por','para','pra','com','que','e','ou','se','mas','ao','the','of','to','and','in','on']);
const CAP_CHUNK={impact:[3,18],box:[4,24]};   /* [max_words, max_chars] por estilo; os demais usam 4/26 (CAPTION_STYLES) */
function capPlain(v){return String(v).toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/g,'')}
function capLen(s){return Array.from(s).length}
function capSmartGroups(words,maxWords,maxChars){
 const out=[];let g=[];
 for(const w of words){
  if(g.length){
   const gap=w.start-g[g.length-1].end,last=g[g.length-1].text;
   const hard=/[.!?\u2026]$/.test(last.replace(/["\u201d\u2019)\u00bb]+$/,''));
   const soft=g.length>=2&&/[,;:]$/.test(last);
   const full=g.length>=maxWords||capLen(g.map(x=>x.text).concat([w.text]).join(' '))>maxChars;
   if(hard||soft||gap>.35||full){
    if(full&&!(hard||soft)&&gap<=.35&&g.length>1&&CAP_WEAK.has(capPlain(last))){const carry=g.pop();out.push(g);g=[carry]}
    else{out.push(g);g=[]}
   }
  }
  g.push(w);
 }
 if(g.length)out.push(g);
 return out}
function capChunkFor(style){return CAP_CHUNK[style]||[4,26]}
/* palavras de todas as linhas do Estúdio, na ordem, no formato do exportador {start,end,text} */
function capWordsOf(lines){const ws=[];for(const l of lines)for(const w of(l.words||[]))ws.push({start:w.start,end:w.end,text:w.word});return ws}
/* bloco visível no instante t (o exportador mostra cada bloco de início da 1ª palavra até o fim da última) */
function capGroupAt(groups,t){for(const g of groups){if(t>=g[0].start-.02&&t<=g[g.length-1].end+.02)return g}return null}
/* Títulos: as MESMAS quebras de linha do exportador (textwrap.wrap(width)[:3]); tamanhos/margens/estilos = captions.title_blocks */
const TITLE_SPEC={big:{size:66,wrap:16,upper:true},top:{size:36,wrap:30,upper:false},bar:{size:50,wrap:22,upper:false}};
const TITLE_MARGIN={top:170,center:0,bottom:430};   /* unidades de 1280 de altura (MarginV do ASS) */
function capWrap(text,width,maxLines){
 /* mesmo algoritmo do textwrap.wrap do Python (sem quebra em hífen): palavra maior que a linha ocupa o espaço que sobra na linha atual */
 const words=String(text).split(/\s+/).filter(Boolean),lines=[];let cur='';
 for(let w of words){
  while(capLen(w)>width){
   if(cur){const used=capLen(cur)+1;if(used<=width){const space=width-used,A=Array.from(w);lines.push((cur+' '+A.slice(0,space).join('')).trim());w=A.slice(space).join('')}else{lines.push(cur)}cur=''}
   else{const A=Array.from(w);lines.push(A.slice(0,width).join(''));w=A.slice(width).join('')}
  }
  if(!w)continue;
  if(!cur)cur=w;else if(capLen(cur)+1+capLen(w)<=width)cur+=' '+w;else{lines.push(cur);cur=w}
 }
 if(cur)lines.push(cur);
 return lines.slice(0,maxLines||3)}
if(typeof module!=='undefined')module.exports={capSmartGroups,capChunkFor,capWordsOf,capGroupAt,capPlain,capWrap,TITLE_SPEC,TITLE_MARGIN};
