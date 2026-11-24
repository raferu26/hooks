# CLAUDE.md — Hook's (pacote interno `liveclips`)

Instruções permanentes e curtas. Detalhes: `docs/`. Versão de referência: **0.19.0-beta.1** (marco git `baseline-0.19.0-beta.1`).
Dono: Rafael ("Rafa"). Responder em PT-BR, direto, resposta primeiro.

## O que é
Editor desktop **local-first** de vídeos/lives: sugere cortes verticais 9:16, edição no Estúdio, exporta. Assinatura planejada; **todo processamento de vídeo no PC do cliente**.

## Decisões aprovadas (não reverter sem pedir)
1. **100% SEM IA — decisão arquitetural inegociável e permanente (23/11/2026).** A versão comercial final não usa APIs de IA, LLM, serviços de inferência **nem modelos pré-treinados, mesmo offline** (inclui Whisper, MediaPipe, RNNoise neural, Ollama e, por interpretação estrita a confirmar, cascatas Haar). Proibido: nova dependência de IA, download silencioso de modelo, afirmar equivalência que algoritmo convencional não tem. Permitido e preferido: DSP/FFmpeg, visão clássica sem treino (diferença de quadros, fluxo óptico, bordas), heurísticas configuráveis, interação manual inteligente. **Migração progressiva em fases com aprovação** (`docs/SEM_IA_MIGRACAO.md`); nada é removido antes de substituto aprovado; versão atual recuperável. `tests/test_sem_ia_guard.py` impede novos usos de ML; `test_noai_mode` exige `ai_mode='sem_ia'` funcional.
2. **Nada de vídeo vai para servidor.** `hooks_cloud` = conta, plano, licença, cobrança, uso.
3. **Menos é mais ≠ menos capacidade.** Inspetor contextual (seleção manda), 3 pistas (Vídeo, Legendas, Áudio) + extras sob demanda, 3 níveis (essencial / contextual / avançado).
4. **Humano decide.** Nada publica sozinho; heurísticas rotuladas.
5. **Não remover função em silêncio.**
6. **Qualidade:** 4 modos reais (Rápido/Equilibrado/Qualidade/Entrega); Entrega sempre CPU/x264; não presumir equivalência CRF × NVENC/QSV/AMF.
7. **Perguntar antes de:** custo recorrente, hospedagem/serviço externo, mudança de arquitetura, formato de projeto incompatível, remover recurso/dependência, ação destrutiva. Não perguntar detalhes triviais.
8. Sem infraestrutura SaaS nova durante a refatoração do editor, salvo necessidade aprovada.

## Tecnologia real (verificada no código)
Python 3.11 alvo (dev 3.13) · `ThreadingHTTPServer` stdlib em 127.0.0.1 (token + checagem de Host/Origin) · SQLite · FFmpeg/ffprobe · Streamlink · yt-dlp · UI = **um HTML gerado** de `ui/` · janela Edge/Chrome em modo app (`desktop.py`). Não é Tauri/Electron.

## Mapa
`liveclips/`: `app.py` rotas `/api/*` · `studio_api.py` · `engine.py` pistas de trabalho · `store.py` banco/perfis/`save_project`/`review` · `media.py` render FFmpeg · `editing.py` (`timing_for` = **única fonte do mapa de tempo**) · `project.py` · `plan.py` · `hardware.py`/`telemetry.py` encoders e modos · `qc*.py`.
`ui/`: fontes da interface. **Edite `ui/*.js|body.html|style.css` e rode `bash ui/build.sh`**; nunca edite `liveclips/static/index.html` à mão (build reproduz o arquivo byte a byte).
Dados do usuário (`C:\LiveClips` / `~/LiveClips`): nunca tocar. Testes usam `--root` temporário.

## Comandos (a partir da raiz do repositório)
```bash
bash ui/build.sh                                   # gera static/index.html, valida JS (BUILD_OK)
python3 -m pyflakes liveclips hooks_cloud          # nomes indefinidos
PYTHONPATH=. python3 -W ignore -m unittest tests.test_salvar_previa tests.test_modos_qualidade tests.test_noai_mode   # ~1 min
PYTHONPATH=. python3 -W ignore -m unittest discover -s tests -t .      # suíte completa, ~40 min: rodar em segundo plano
python3 -m liveclips --root /tmp/hk --port 8765 --no-browser
bash ui/fresh.sh 8790 && PORT=8790 python3 ui/e2e10.py   # e2e (Playwright + /usr/bin/google-chrome)
python3 validacao/medir_modos.py                   # SSIM/PSNR/tempo por modo
```

## Contra regressão
- Antes de mexer: testes do módulo. Depois: de novo + e2e se tocou a UI. Corrigir regressão antes de avançar.
- Mudanças pequenas, um problema por commit, com teste proporcional ao risco e rollback (git).
- Projeto/perfil/banco antigos devem abrir; campos novos opcionais; migrações idempotentes.
- Prévia e exportação concordam (`timing_for`); mudança no render exige `test_ligacao_modulos` e `test_corpus_cortes`.
- Opção visível na tela tem que **mudar o resultado** (teste opção → comando FFmpeg → arquivo).
- Não sobrescrever módulos nem usar nome sem importar (pyflakes).
- Recalibrar limite de teste só com justificativa escrita em `docs/CHANGELOG.md`.
- Autosave não ensina a memória (`save_project(learn=False)`).

## Verdade
Distinguir verificado · testado · hipótese. Não escrever "funciona" sem executar. Declarar o que não foi validado (Windows, GPU, live real, YouTube real, pessoas). Sem nota "10/10". Ganhos só com medição antes/depois reproduzível.
Cada melhoria grande: ANTES → PROBLEMA → ALTERAÇÃO → TESTE → RESULTADO em `docs/CHANGELOG.md`.

## Documentos
`docs/ARCHITECTURE.md` · `docs/ROADMAP.md` · `docs/CHANGELOG.md` · `docs/KNOWN_ISSUES.md` · `docs/UX_MATRIX.md` · `docs/SEM_IA_MIGRACAO.md` · `docs/BASELINE.md` (medições iniciais) · `docs/handoff/` (pacote histórico recebido: dossiê, inventário, decisões, perguntas em aberto).

## Git e checkpoints (política permanente)
- Remoto oficial: GitHub **privado** `raferu26/hooks` (`origin`). Nunca tornar público, nunca force push, nunca reescrever histórico (correção = commit novo). Não subir vídeos, bancos, perfis, `.env`, chaves ou tokens.
- **Nada importante fica só no ambiente temporário:** envie checkpoints testados com frequência para a branch da funcionalidade (`git push -u origin feature/<nome>`).
- Uma funcionalidade = uma branch (`feature/...`); commits pequenos com teste proporcional. `main` só recebe por Pull Request depois de testes relacionados e revisão do diff; não dar push direto de trabalho incompleto na `main`.
- Antes de fechar uma versão beta: suíte completa registrada em `docs/BASELINE.md`/`CHANGELOG.md` (falhas incluídas) e novo bundle de backup: `git bundle create hooks-backup-AAAA-MM-DD.bundle --all` (+ `git bundle verify`).
- Tags: a sessão em nuvem não consegue enviar tags (proxy 403); criar `baseline-0.19.0-beta.1` (commit `dc8e371`) fora da sessão.
- Antes de `git commit` encadeado a scripts, confira que o passo anterior terminou bem (um commit já subiu com resultados vazios por isso).
