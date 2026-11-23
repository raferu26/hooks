# HOOKS — Roadmap de continuidade

Parte do pacote `HOOKS_MASTER_HANDOFF`. Base: estado real da **0.19.0-beta.1** (23/11/2026). Nada aqui é compromisso já implementado; **Estado** diz o que existe hoje. Decisões já aprovadas pelo Rafael não foram reordenadas: a ordem aprovada é E0 → E1 → E2 → demais etapas (redesign, interatividade, qualidade, otimização). Onde a ordem abaixo difere do roteiro E0–E10 da auditoria, a justificativa está no item.

Princípios que valem para todos os itens: preservar a 0.18.2/0.19 como rollback; mudar em passos pequenos; rodar a suíte antes e depois; sem nova dependência de IA; sem remover função em silêncio; "concluído" só com teste ou medição.

## Estado das etapas aprovadas (E0–E10)

| Etapa | Estado | Evidência / o que falta |
|---|---|---|
| E0 Linha de base | **CONCLUÍDA** | Medidas "antes" (vídeo ~7%, 8 abas, 8 pistas) e baseline da suíte; capturas de tela em ambiente temporário (não preservadas no pacote) |
| E1 Salvar × prévia | **CONCLUÍDA** [TESTADO] | `test_salvar_previa` (9), e2e; N4 (autosave não ensina) resolvido |
| E2 Qualidade de exportação | **CONCLUÍDA em CPU** [TESTADO]; **GPU NÃO VALIDADA** | `test_modos_qualidade` (9), `validacao/medir_modos.py` |
| E3 Timeline | **PARCIAL** | 3 pistas + extras sob demanda + desenho só do visível feitos. Faltam snap magnético, ripple/split de primeira classe, arrasto sem redesenho total, medição N5 com 200 itens e clipes de 90 s |
| E4 Inspetor contextual | **CONCLUÍDA** [TESTADO e2e] (implementada junto com E3 nesta versão; o NOVIDADES a rotula "E3") | 8 abas → inspetor + seções recolhíveis; "Sugestões" |
| E5 Layout | **PARCIAL** | Vídeo 17,2% da tela (1440×900), barra em 1 linha (1440/1280/1024), um só transporte. Faltam painéis redimensionáveis lembrados, gaveta <1100 px verificada, transcrição sob demanda (T) |
| E6 Atalhos | **PARCIAL** | Feitos: ?, ← →, +/−, P, Ctrl+S só salva, Ctrl+Enter duplo, guarda de campo de texto em Ctrl+Z/Y. Faltam Ctrl+K (busca), mapa único pesquisável |
| E7 Design system | **PENDENTE** | Tokens de tipografia/espaçamento/áreas clicáveis; varredura de contraste AA não feita |
| E8 Prévia em camadas | **PENDENTE** | Hoje: prévia = render do clipe inteiro a 540×960 (~9–10 s para 14 s) |
| E9 Recursos de edição | **PENDENTE** | Ver M01–M08 |
| E10 Validação | **PARCIAL** | e2e e roteiro prontos; testes com pessoas reais, Windows e GPU não feitos |

---

## Prioridade crítica

### C01 — Validar a 0.19 no Windows real
- **Descrição:** instalar/atualizar (`ATUALIZAR.bat`), abrir pelo atalho, janela Edge/Chrome em modo app, Estúdio, exportação nos 4 modos, rollback `liveclips_anterior`.
- **Justificativa:** nada do Windows foi exercitado desde a 0.12; o PC alvo é i7-3770, 16 GB, GPU não informada.
- **Dependências:** acesso do Rafael ao PC (o assistente não alcança o Windows sem a ponte).
- **Componentes:** `desktop.py`, `.bat`, `hardware.py`, `media.py`.
- **Riscos:** janela preta ao chamar ffmpeg; Edge não encerrar; antivírus.
- **Aceite:** checklist de `ROTEIRO_TESTE_USUARIOS_0_19.md` + log `hooks_servidor.log` sem erro; 1 corte exportado em cada modo.
- **Testes:** manual guiado + `tests/smoke_ui.py`. **Estado:** não iniciado.

### C02 — Medir modos de qualidade com clipes reais e GPU
- **Descrição:** 2–3 clipes reais + modelo da placa; medir tempo, tamanho, SSIM/PSNR (`validacao/medir_modos.py`); confirmar se NVENC p7/hq, QSV veryslow, AMF QP17/19 são aceitos; ajustar tabela.
- **Justificativa:** os números atuais vêm de fonte sintética com ruído por quadro; Qualidade/Entrega levaram 91/168 s para 4 s.
- **Dependências:** clipes do Rafael; C01. **Riscos:** tempo de Entrega pode ser inaceitável no i7-3770.
- **Aceite:** tabela real por modo/encoder; recuo para CPU comprovado quando o driver recusa.
- **Estado:** não iniciado; hipótese: diferença menor em vídeo real [HIPÓTESE].

### C03 — Preservar as fontes da interface e do empacotamento
- **Descrição:** `ui10/` (core.js, studio.js, agents.js, live.js, account.js, music.js, body.html, style.css, assets, build.sh, seed.py, run.py, e2e) **não está no ZIP** da 0.19; só `static/index.html` gerado. Incorporar ao repositório.
- **Justificativa:** editar o HTML gerado à mão contradiz a regra "nunca edite index.html"; sem as fontes, o redesign não continua. `pack10.sh` mora em `/tmp` (efêmero).
- **Aceite:** repositório contém as fontes e um `build` reproduzível que gera byte a byte o `index.html` atual. **Estado:** o pacote de fontes `HOOKS_UI_SOURCES_0.19.zip` acompanha esta documentação; falta mover para o repo.

### C04 — Iniciar controle de versão (git) para o código atual
- **Justificativa:** a árvore de trabalho não é um repositório; o histórico original tinha branches/tags (`v6.1…v0.9.0-beta.1`, `.gitignore`/`.gitattributes` aparecem nos uploads). Hoje o rollback é por cópia de pasta/ZIP.
- **Aceite:** `git init` com commit-base = 0.19.0-beta.1; tag; `.gitignore` sem vídeos, banco, venv, perfis. **Estado:** não feito.

### C05 — Validar a escolha de momentos com live real
- **Justificativa:** `PENDENCIAS_0_17_1`: é o ponto de maior risco do produto; não existe taxa de acerto.
- **Descrição:** gabarito de ≥20 momentos bons por streamer (`bench.py`), medir acerto; ligar o motivo de rejeição aos pesos só depois de 2–3 lives.
- **Dependências:** lives reais (CORINGA, DAVA JONAS). **Estado:** estrutura pronta, sem dados.

### C06 — Testar vídeo do YouTube real e a atualização do yt-dlp
- **Justificativa:** correção da 0.18.2 só testada com servidor HTTP simulado. **Aceite:** baixar um vídeo comum e uma live no PC do Rafael e analisar. **Estado:** não validado.

---

## Prioridade alta

### A01 — Decidir "Sem IA como padrão" (DECISÃO DO RAFAEL)
- **Opções:** (1) manter padrão com IA, Sem IA opcional (hoje); (2) Sem IA padrão, Whisper/MediaPipe opcionais e fora do `requirements.txt` base (instalação "completa" separada); (3) Sem IA padrão e remover.
- **Impacto:** quem não tem legenda pronta perde legenda automática. Não implementar antes da decisão.
- **Aceite:** instalação limpa sem pacotes de IA roda análise, edição e exportação (já provado por `test_noai_mode` para a análise).

### A02 — Prévia em camadas (E8)
- **Descrição:** L1 imediata (HTML), L2 trecho afetado com cache por hash, L3 fiel.
- **Riscos:** alto — cortes/rampas deslocam a linha do tempo depois do ponto editado; `timing_for` (fonte única do mapa de tempo) e `preview_timing` já existem e devem ser a base. Fazer protótipo antes.
- **Aceite:** mudança simples visível <1 s; trecho em poucos segundos; prévia sempre rotulada como aproximada/fiel; teste de regressão prévia×exportação (diferença ≤ limite de `test_corpus_cortes`).

### A03 — Terminar a timeline (E3)
- **Itens:** snap configurável (cortes, playhead, palavras), split/remover com fechamento do vazio, arrasto sem redesenho total, medição com 200 blocos e clipe de 90 s (N5), limite do histórico de desfazer (hoje 80 snapshots JSON completos).
- **Aceite:** quadro <16 ms no arrasto com 200 blocos (medido no Chrome headless); sem regressão em `test_studio*`/e2e.

### A04 — Atalhos e busca (E6 restante)
- Ctrl+K, mapa único pesquisável, conflito com atalhos do navegador. **Aceite:** teste automatizado digitando em cada campo + Ctrl+Z.

### A05 — Design system (E7)
- Escala tipográfica (12/14/16/20/28), grade de 4 px, áreas clicáveis ≥32/40 px, foco visível, contraste AA por script; rosa só na ação primária. **Risco baixo (CSS).**

### A06 — Reorganizar os 11 Ajustes
- Só o Estúdio foi reorganizado. Seguir o mesmo princípio (mapa de migração, nada some, busca). **Estado:** pendente.

### A07 — Testes de usabilidade com pessoas
- Roteiro `ROTEIRO_TESTE_USUARIOS_0_19.md`; 10 tarefas × perfis; registrar tempo/cliques/erros/satisfação. **Não bloqueia o desenvolvimento** (decisão do Rafael).

### A08 — Realimentar o ranking com o motivo de rejeição
- Depende de C05 (dados). Risco: ruído com poucos exemplos.

### A09 — Fila e gargalo da transcrição com várias lives
- N05/N06 (filas com orçamento, idempotência de jobs) estão ausentes/parciais; um modelo de voz único serializa a transcrição. Medir em PC real antes de mexer.

---

## Prioridade média

| ID | Descrição | Notas |
|---|---|---|
| M01 | Miniaturas na pista Vídeo | Geração em segundo plano com cache por conteúdo (`cache.py`) |
| M02 | Transições (xfade) e J/L cut | Hoje só fade de áudio; R04/R27 ausentes. Cuidado com o `plan.py`/`Remap` |
| M03 | Reposicionar webcam arrastando no preview | Depende de L1 (A02) |
| M04 | EQ/compressor/de-esser clássicos de voz | Filtros FFmpeg; testar em fala real |
| M05 | Reenquadramento que segue a pessoa na live | Só dá para validar com 2–3 trechos reais do Rafael |
| M06 | Desfoque rastreado de dado sensível (doações/usuários no chat) | Também risco de privacidade |
| M07 | Layout por trecho | A política existe, o render por trecho não |
| M08 | Estabilização de duas passadas (vidstab) | Dependência extra do FFmpeg |
| M09 | Calibrar limites do QC (2 s congelado etc.) com dados reais | |
| M10 | Dicionário por streamer (nomes, jogos, bordões) para legenda | Parcial: correções fixas existem |

## Prioridade futura (comercial e infraestrutura)

| ID | Descrição | Dependências / riscos |
|---|---|---|
| F01 | Decidir stack do instalador (manter servidor local + janela Edge/Chrome, ou Tauri/Electron) e gerar instalador `.exe` com desinstalador e atualização | Decisão arquitetural **ainda aberta**; precisa de máquina Windows; tamanho do pacote (FFmpeg, Python) |
| F02 | Proteção do código (hoje ZIP com Python legível), licenciamento resistente a engenharia reversa | Aceitar que desktop Python é difícil de proteger; avaliar compilação/ofuscação sem prometer segurança total |
| F03 | Hospedar `hooks_cloud` (domínio, HTTPS, e-mail SMTP, backup) | **Gera custo: aprovação do Rafael**; CNPJ/razão social indefinidos |
| F04 | Pagamento: testar Pix manual com valor baixo e Asaas sandbox | URL de produção, link de pagamento e cancelamento sem confirmação |
| F05 | Jurídico: termos, privacidade, DPA (`DPA_RASCUNHO.md`), gravação de lives de terceiros | Advogado |
| F06 | Atualização automática do app | Depende de F01 |
| F07 | Integração direta Google Drive (Caminho B) | Escopos restritos exigem verificação; manter Caminho A (pasta sincronizada) |
| F08 | Publicação/agendamento nas plataformas | Depende de aprovação das plataformas; hoje só pacote de texto |
| F09 | Aprender com métricas pós-publicação (CSV TikTok já importável) | `analytics.py`/`learning.py` existem; falta ciclo validado |

## Fora do escopo (a menos que o Rafael aprove)

Qualquer nova dependência de IA (modelos, APIs de IA, LLM em nuvem); processamento de vídeo em servidor; remoção silenciosa de funções.
