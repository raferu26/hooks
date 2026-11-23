#!/bin/bash
# uso: ui/fresh.sh PORT  -> reinicia servidor de teste com dados novos em /tmp/uiroot10
HERE="$(cd "$(dirname "$0")" && pwd)"
pkill -f "run.py /tmp/uiroot10" 2>/dev/null; sleep 3
rm -rf /tmp/uiroot10
python3 "$HERE/seed.py" /tmp/uiroot10 2>&1 | tail -2
setsid nohup python3 "$HERE/run.py" /tmp/uiroot10 ${1:-8780} >/tmp/ui_server.log 2>&1 &
for i in $(seq 1 20); do grep -q serving /tmp/ui_server.log 2>/dev/null && break; sleep 1; done
tail -1 /tmp/ui_server.log
