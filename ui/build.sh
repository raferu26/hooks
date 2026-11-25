#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${HOOKS_UI_OUT:-$HERE/../liveclips/static/index.html}"
export OUT
cd "$HERE" && python3 - <<'PY'
import os
c=open('style.css',encoding='utf-8').read()
head='<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Hook’s</title><link rel="icon" type="image/png" href="data:image/png;base64,'+open('assets/favicon.b64').read().strip()+'">\n<style>\n'+c+'\n</style></head>\n'
body=open('body.html',encoding='utf-8').read().replace('__LOGO_SIDE__',open('assets/logo_side.b64').read().strip())
js=open('core.js',encoding='utf-8').read()+'\n'+open('music.js',encoding='utf-8').read()+'\n'+open('studio.js',encoding='utf-8').read()+'\n'+open('reacao.js',encoding='utf-8').read()+'\n'+open('capgroups.js',encoding='utf-8').read()+'\n'+open('textcaps.js',encoding='utf-8').read()+'\n'+open('agents.js',encoding='utf-8').read()+'\n'+open('live.js',encoding='utf-8').read()+'\n'+open('account.js',encoding='utf-8').read()+'\nrefresh(true).then(()=>{const v=localStorage.getItem("lc-view");go(["clips","add","music","settings","account"].includes(v)?v:"clips")});setInterval(()=>{if(!document.hidden)refresh()},2500);\n'
import hashlib
html=head+body+'<script>\n'+js+'</script>\n</body></html>\n'
tag='<meta name="ui-build" content="%s">'
html=html.replace('<head>','<head>'+(tag%''),1)
ident=hashlib.sha256(html.encode('utf-8')).hexdigest()[:12]
html=html.replace(tag%'',tag%ident,1)
open(os.environ['OUT'],'w',encoding='utf-8',newline='').write(html)
PY
TMPJS="$(mktemp --suffix=.js)"; export TMPJS
node -e "const fs=require('fs');const h=fs.readFileSync(process.env.OUT,'utf8');const m=h.match(/<script>([\s\S]*)<\/script>/);fs.writeFileSync(process.env.TMPJS,m[1].replace('__BOOT_TOKEN__','\"x\"'))" && node --check "$TMPJS" && echo BUILD_OK; rm -f "$TMPJS"
