# Hook's — beta para Windows (procedimento)

> **Estado honesto:** o pacote é gerado e **verificado em Linux** (integridade, hashes, `.bat` com CRLF, sem segredos). **Nada foi executado em Windows.** Este documento é o roteiro para o **primeiro teste físico**; só depois dele se pode dizer "validado no Windows".

## 1. Arquitetura que será entregue (a atual, sem mudanças)
ZIP → pasta no PC → `INSTALAR.bat` cria `.venv` (Python 3.11) e instala `requirements.txt`, instala FFmpeg (winget `Gyan.FFmpeg`) e Deno (winget, só para YouTube) → atalho **Hook's** abre o servidor local (127.0.0.1) numa janela Edge/Chrome em modo app. Dados em `C:\LiveClips`. Não é um instalador `.exe` (decisão de instalador/Tauri/Electron segue em aberto: F01).
Mudança nesta beta: o instalador **não baixa mais nenhum modelo** (antes baixava o modelo facial do MediaPipe). Whisper baixa o modelo de fala **só no primeiro uso do modo com IA**; no modo sem IA nada é baixado.

## 2. Gerar o pacote (no repositório, árvore limpa)
```bash
python3 tools/empacotar_release.py --saida ../release
```
Produz `Hooks-<versão>.zip`, `Hooks-<versão>.zip.sha256` e imprime as verificações (zip íntegro, manifesto, `.bat` CRLF, `chcp 65001`, sem segredos/vídeos/banco/venv, arquivos exigidos). O ZIP sai do que está **no git**, nunca de uma pasta suja.

## 3. Instalar no Windows (primeiro teste físico)
Requisitos: Windows 10/11, **Python 3.11** (python.org), internet para `pip`/winget, ~3 GB livres.
1. Confira o SHA-256 do ZIP (`certutil -hashfile Hooks-<versão>.zip SHA256`) contra o arquivo `.sha256`.
2. Extraia em uma pasta **sem espaços** (ex.: `C:\Hooks`). Não extraia dentro de "Downloads" protegido.
3. Duplo clique em `INSTALAR.bat`. Se pedir, aceite o winget. Guarde `instalacao.log`.
4. Abra o atalho **Hook's** (ou `ABRIR_LIVECLIPS.bat`). O painel abre em janela própria.
5. Atualizar depois: `ATUALIZAR.bat` (guarda `liveclips_anterior` para voltar). Backup: `RESTAURAR_BACKUP.bat`. Diagnóstico: `GERAR_DIAGNOSTICO.bat`.

## 4. Roteiro do teste físico (marque cada item; **nenhum foi feito**)
| # | Teste | Aceite | Resultado |
|---|---|---|---|
| W01 | `INSTALAR.bat` do zero | termina sem erro; `.venv` criado; FFmpeg/ffprobe achados | ☐ |
| W02 | Atalho abre a janela sem console | janela do app; sem janela preta | ☐ |
| W03 | Banner "Recurso indisponível" | **não** aparece (OpenCV, numpy, yt-dlp instalados) | ☐ |
| W04 | Importar um vídeo local (MP4) | análise termina; cortes sugeridos | ☐ |
| W05 | Estúdio: editar, prévia, desfazer, Ctrl+K, tecla F | sem travar; prévia gerada | ☐ |
| W06 | Exportar nos 4 modos (CPU) | arquivos 1080×1920 abrem; áudio sincronizado | ☐ |
| W07 | Exportar com GPU (se houver): informar a placa | recua para CPU se o driver recusa | ☐ |
| W08 | Legenda em fonte do Windows | fonte e posição iguais às da prévia (V04) | ☐ |
| W09 | "Encerrar Hook's" e fechar a janela | processos terminam; `servidor.json` removido | ☐ |
| W10 | `ATUALIZAR.bat` sobre uma instalação existente | dados em `C:\LiveClips` intactos; rollback funciona | ☐ |
Envie: `instalacao.log`, `hooks_servidor.log` (em `C:\LiveClips`), o modelo da CPU/GPU e uma captura de tela de qualquer erro.

## 5. Riscos conhecidos (não resolvidos)
Antivírus pode bloquear `.bat`/venv; caminho com espaços/acentos; `winget` ausente (Windows 10 antigo); FFmpeg do winget sem o filtro `afwtdn` (há fallback `afftdn`); encoders GPU não validados; i7-3770 com várias pistas disputando núcleos; instalador exige Python 3.11 instalado pelo usuário.
