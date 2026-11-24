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

## 6. O que foi verificado em Linux para esta beta (sem executar no Windows)
| Verificação | Resultado | Como reproduzir |
|---|---|---|
| **Wheels para Windows** (cp311, win_amd64) de **todas** as dependências do `requirements.txt` | resolvem: 69 arquivos, **345 MB** de wheels; numpy fica em **1.26.4** (imposto pelo `mediapipe`) | `pip download --platform win_amd64 --python-version 3.11 --implementation cp --abi cp311 --only-binary=:all: -r requirements.txt` |
| Peso da pilha de IA | ≈ **255 MB (74%)** dos wheels vêm de `mediapipe` (jax/jaxlib/scipy/matplotlib…) e `faster-whisper` (ctranslate2/av/onnxruntime/tokenizers); o núcleo (numpy, OpenCV, streamlink, yt-dlp, cryptography) ≈ 69 MB + dependências leves — estimativa por nome de pacote | idem, agrupando por pacote |
| Janela de console piscando | todas as chamadas `subprocess` passam `creationflags` (**1 faltava**, em `music.py`, corrigida) | `tests/test_windows_static.py` |
| Código só de Linux | `fcntl` protegido por `os.name`; sem caminhos Unix fixos no produto | idem |
| `.bat` | CRLF e `chcp 65001` | idem |
| **Downloads de modelos** | o instalador não baixa nada; a rede só é usada em módulos listados (ação do usuário/configuração); o **modo sem IA não abre conexão externa** durante análise, sugestão e render | `tests/test_sem_downloads.py`; `tests/test_noai_mode.py::test_no_outbound_network_in_no_ai_mode` |
| Pacote | ZIP com manifesto, 7 verificações | `tools/empacotar_release.py` |
**Limites desta verificação:** os testes rodaram com **numpy 2.5.5** (Linux, Python 3.13); no Windows a instalação usa numpy 1.26.4 e Python 3.11 — combinação **não testada**. Existir wheel não prova que a biblioteca funciona no PC do cliente (drivers, antivírus, VC++ runtime). Uso de CPU/GPU, tempo de exportação e inicialização só se medem no Windows (roteiro W01–W10).
