# HOOKS — Histórico de versões e registro de decisões

Parte do pacote `HOOKS_MASTER_HANDOFF`. Este arquivo é a **cronologia** (o que cada versão trouxe) e o **registro de decisões** (por que). A narrativa completa e as auditorias estão em `HOOKS_MASTER_DOSSIER.md`; o estado operacional atual em `HOOKS_TECHNICAL_HANDOFF.md`.

Legenda de confiança: **[HISTÓRICO CONFIRMADO]** mensagem/arquivo acessível · **[VERIFICADO NO CÓDIGO]** lido/medido no código ou nos ZIPs · **[TESTADO]** executado · **[DECISÃO APROVADA]** autorizada pelo Rafael · **[PLANEJADO]** · **[IMPLEMENTAÇÃO PARCIAL]** · **[OBSOLETO]** · **[INFERÊNCIA]** · **[NÃO VERIFICADO]**.

Fontes desta análise (ver lacunas no dossiê): ZIPs de 0.9.0 a 0.19.0 (abertos e medidos), documentos `CHECKPOINT_V6…V8`, `ESTUDIO_0_11…0_13`, `CHECKUP_0_14`, `INTELIGENCIA_0_14`, `PISTAS_0_15`, `APLICATIVO_0_16`, `SAAS_0_16`, `PENDENCIAS_0_16/0_17_1`, `REFINAMENTO_0_17/0_17_1`, `PROGRESSO_P00_P27`, `VALIDACAO_COMPLEMENTAR`, `CORRECOES_0_18_2`, `NOVIDADES_0_18/0_19`, os kits de prompts enviados por você, a auditoria de UX salva no Docs e a memória do assistente.

---

## 1. Linha do tempo das versões

Datas = data de modificação do arquivo no ambiente de trabalho (aproximadas; fuso Brasília). LOC = linhas de Python em `liveclips/*.py`. "Defs de teste" = contagem estática de `def test_` (não é o número de execuções; a suíte da 0.19 executa 1212 casos por causa de subtestes).

| Versão | Data aprox. | LOC / módulos / defs de teste | O que trouxe (resumo) | Problemas que ficaram | Evidência |
|---|---|---|---|---|---|
| 0.8.0-beta.1 (V6) | 16/11 | — / — / 65 (relato) | Primeiro checkpoint recebido: captura por Streamlink, transcrição, ranking por fala/áudio/movimento, prévia horizontal, exportação TikTok 1080×1920 (webcam em cima, jogo embaixo, legenda). Teste manual: 12 sugestões, exportação vertical confirmada pelo usuário | Captura de 2+ lives em paralelo sem validação; ranking não interpreta semântica | `CHECKPOINT_V6.md` [HISTÓRICO CONFIRMADO] |
| 0.8.1-beta.1 (V6.1) | 16–17/11 | — / 72 | Captura até 1440p, 1080×1920 Lanczos, H.264 CRF 18, 60 fps preservado, deduplicação | FFmpeg ausente no ambiente de desenvolvimento: render 1440p não testado | `CHECKPOINT_V6_1.md` |
| 0.8.2-beta.3 (V6.2) | 17/11 | — / 77 | Teste de link, Twitch com chat, picos de chat, movimentos faciais por regiões, fusão multimodal, aprendizado por streamer, QC editorial | Nada validado em live real | `CHECKPOINT_V6_2.md` |
| 0.8.3 (V6.3) | 17/11 | — | Modos independentes Live × Vídeo/Podcast (arquivo local vinculado) | — | `CHECKPOINT_V6_3.md` |
| 0.8.4 (V6.4) | 17/11 | — | Vídeo por link público pelo mesmo pipe resiliente | Limite físico: o vídeo precisa chegar à máquina | `CHECKPOINT_V6_4.md` |
| 0.8.5 (V6.5) | 17/11 | — | Dois enquadramentos (conservador/dinâmico) com OpenCV | — | `CHECKPOINT_V6_5.md` |
| 0.8.6 (V6.6) | 17/11 | — | Análise progressiva de vídeo por link; **Corte manual** | — | `CHECKPOINT_V6_6.md` |
| 0.8.7 (V6.7) | 17/11 | — / 95 | Seek preciso na exportação entre segmentos (50,17 s reais), backups com restauração validada, reclassificação, instalador com FFmpeg via winget | Backups não incluem gravações pesadas | `CHECKPOINT_V6_7.md` |
| 0.8.8 (V6.8) | 17/11 | — | Taxonomia de 9 momentos, notas narrativas, MediaPipe Face Landmarker local e opcional, vocabulário por streamer | O agente observa movimento, não emoção | `CHECKPOINT_V6_8.md` |
| 0.8.9 (V6.9) | 17–18/11 | — | Reformulação visual (azul-escuro), fluxo de 4 etapas | — | `CHECKPOINT_V6_9.md` |
| 0.9.0-beta.1 (V7) | 18/11 | 3 542 / 18 / 117 | Editor profissional: 13 estilos, plano por corte, pausa segura, imagem/SFX/música, comparação original×editado, manifesto. V7.1: história completa (preparação/clímax/encerramento, alternativas 30/45/60 s; 119 testes) | Teste real de codificação dependia de FFmpeg no PC | `CHECKPOINT_V7.md`, `CHECKPOINT_V7_1.md`, ZIP 0.9.0 [VERIFICADO NO CÓDIGO]. O número de versão exato da V7.1 não aparece nos arquivos: [NÃO VERIFICADO] |
| 0.10.0-beta.1 (V8) | 18/11 | 4 093 / 20 / 150 | Looks por estilo, curvas de zoom, supersample, legendas sem piscar, render em **uma** codificação com recuo ao método V7, loudness medido; créditos ReaCut (MIT) | — | `CHECKPOINT_V8.md`, `EDITOR_PRO_V8.md` |
| 0.11.0-estudio-beta.1 | 18/11 21:51 | 6 339 / 29 / 239 | **Estúdio de edição** (fala + prévia + ferramentas + trilhas), layouts, velocidade, congelar, SFX, imagens, música por link, formatos 1:1/4:5/16:9, pacote de publicação, Ollama opcional, GPU automática | Música por link/GPU/Ollama sem teste real; aba de ferramentas quebrava em 3 linhas | `ESTUDIO_0_11.md`, ZIP |
| 0.12.0-beta.1 | 18/11 23:26 | 8 863 / 41 / 348 | Pipeline de agentes (ranking→juiz→Ollama→contexto→plano), segunda passada de legenda, QC na exportação, prévia ao vivo de legenda/título, kit de marca, reenquadramento por quem fala, RNNoise, A/B de gancho, `ATUALIZAR.bat`, diagnóstico | ATUALIZAR.bat não testado no Windows; RNNoise sem fala real | `ESTUDIO_0_12.md` |
| 0.13.0-beta.1 (já "Hook's") | 19/11 08:54 | 12 003 / 60 / 513 | Plano versionado (`plan.py`), replay/rampa/congelar, registro de capacidades, memória editorial, habilidade narrativa, revisão ciente do plano, pacote com OTIO, edição por conversa, trilha de legenda, percepção, telemetria | Nenhum item validado com conteúdo real | `ESTUDIO_0_13.md` |
| 0.14.0-beta.1 | 19/11 10:34 | 13 781 / 73 / 625 | **Checkup após incidente real** (live gravando sem cortes chegarem): falha de análise não derruba mais o cadastro de pedaços, fallback CUDA, aviso de fim de captura, barra da live em Cortes; camada de inteligência N01–N32 (1 disponível, 21 parciais, 2 laboratório, 8 ausentes) | `time` sem import em `app.py` quase foi ao pacote (pego por pyflakes); `intelligence.py` sobrescrito por engano e restaurado | `CHECKUP_0_14.md`, `INTELIGENCIA_0_14.md` |
| 0.15.0-beta.3 | 19/11 13:13 | 14 333 / 75 / 667 | **Pistas de trabalho** (um trabalhador por tipo), capacidade medida, pré-checagem, webcam automática (beta.3) | Nada validado com 4 lives, GPU ou Windows | `PISTAS_0_15.md` |
| 0.16.0-beta.1 / beta.2 | 22/11 19:59 / 20:43 | 15 133 / 77 / 780–783 | **Base SaaS** (`hooks_cloud`: contas, planos, licença Ed25519, cobrança Pix/Asaas, admin, LGPD), `licensing.py`, atalho/janela de aplicativo (`desktop.py`) | Windows/Edge/Asaas/SMTP/HTTPS/jurídico não validados; ~14.500 requisições inválidas acharam 4 rotas 500 e 10 ações quebradas (corrigidas) | `SAAS_0_16.md`, `APLICATIVO_0_16.md`, `PENDENCIAS_0_16.md` |
| 0.17.0-beta.1 | 22/11 21:59 | 15 822 / 78 / 840 | Velocidade (painel 0,57→0,07 s, abertura do banco 2,2→0,04 s), rejeição em 1 clique com motivo, taxa de aceitação por live, 2ª passada de legenda padrão, QC visual (rosto cortado, quadro congelado, estouro…) | Motivo de rejeição ainda não realimenta o agente | `REFINAMENTO_0_17.md` |
| 0.17.1-beta.1 | 22/11 23:18 | 16 231 / 80 / 891 | Teclado e lote na biblioteca, pasta de entrega (Drive via app desktop), limpeza de renders incompletos, backup verificado, pré-voo com estimativa | Integração direta Drive API não feita | `REFINAMENTO_0_17_1.md`, `PENDENCIAS_0_17_1.md` |
| 0.18.0-beta.1 | 23/11 02:14 | 19 724 / 93 / 1091 | **Módulos P00–P27** (marcadores, silêncio/preto/parado, sincronismo por áudio, legendas SRT/VTT/ASS importadas, cor/LUT, chave de cor, estabilização, capas, receitas de imagem, multiformato, cache, OTIO, gráficos 2D) e **modo Sem IA** (`ai_mode='sem_ia'`) | Tudo sintético; recursos novos nascem desligados | `NOVIDADES_0_18.md`, `PROGRESSO_P00_P27.md` |
| 0.18.1-beta.1 | 23/11 12:52 | 20 191 / 95 / 1165 | Validação complementar com corpus sintético e gabarito; título deixava de cobrir a webcam (103 quadros cobertos → ≥90% visível); margem de legenda 260→340 | Limite de variação de loudness recalibrado 8→9 dB (registrado como calibração, não correção) | `VALIDACAO_COMPLEMENTAR.md` |
| 0.18.2-beta.1 | 23/11 14:10 | 20 364 / 96 / 1174 | **Correção do YouTube** (vídeo comum ia ao streamlink e gravava 0 bytes → agora `videodl.py` com yt-dlp), SaaS visível (`SAAS_LOCAL.bat`, aba Assinatura) | YouTube real não testado; Windows/Asaas/SMTP não testados | `CORRECOES_0_18_2.md` |
| **0.19.0-beta.1** (atual) | 23/11 16:17 | 20 480 / 96 / 1192 (1212 execuções) | Estúdio com inspetor contextual, 3 pistas, "Sugestões", autosave, prévia anterior preservada, 4 modos de qualidade reais, atalhos novos | Ver estado atual no handoff e `HOOKS_ROADMAP.md` | `NOVIDADES_0_19.md` [TESTADO em Linux, mídia sintética] |

Observações sobre a evolução [VERIFICADO NO CÓDIGO nos ZIPs]:
- Crescimento: 3,5 mil → 20,5 mil linhas de Python em ~5 dias de calendário (18→23/11) e de 117 → 1 192 definições de teste. O HTML único passou de 74 KB para 289 KB.
- Marcos: V7/V8 (editor), 0.11 (Estúdio), 0.13 (plano versionado), 0.14 (checkup/incidente real), 0.15 (pistas), 0.16 (SaaS), 0.18 (P00–P27 + Sem IA), 0.19 (redesign).
- Versões que introduziram problemas conhecidos depois corrigidos: 0.8.x–0.18.2 já nasciam com **modos de qualidade sem efeito** (P10, corrigido só na 0.19); 0.14 quase publicou erro de import; 0.18.0 deixou título cobrindo webcam e legenda baixa demais (corrigidos na 0.18.1); 0.18.2 corrigiu o YouTube (`videodl.py`).
- Funcionalidades reconstruídas: render (3 codificações na V7 → 1 na V8 com recuo), prévia (rascunho sem texto gravado na 0.12; prévia anterior preservada na 0.19), fila (trabalhador único → pistas na 0.15).
- Funcionalidade removida explicitamente: campo `reframe` (morto) na V8. Nenhuma outra remoção documentada [HISTÓRICO CONFIRMADO].
- Número de versão ≠ implementação: os kits de prompt P01–P18 (18/11), A01–A16 (19/11) e P00–P27 (22/11) são **especificações propostas**, não código. Só o que aparece nos ZIPs e nos documentos de estado conta como implementado.

---

## 2. Fases (resumo; narrativa em `HOOKS_MASTER_DOSSIER.md` §Parte I)

1. **Origem (anterior a 16/11)** — o código nasceu numa conversa de outro assistente (a pasta local do projeto se chama `referenced-chatgpt-conversation-this-is-an`, com `work/source/liveclips-v6-main` e `work/incoming/liveclips-home-0.8.1`) [HISTÓRICO CONFIRMADO: nomes de pasta nos uploads e na memória]. O conteúdo dessa conversa **não está acessível**: lacuna.
2. **Agente clipador (V6.x, 0.8.x)** — foco em captura de lives, transcrição, ranking e exportação vertical.
3. **Editor profissional (V7–V8, 0.9–0.10)** — a ênfase passa de "achar o momento" para "editar bem".
4. **Estúdio (0.11–0.13)** — interface de edição com trilhas, plano versionado, memória editorial.
5. **Operação real (0.14–0.15)** — incidente com live real (CORINGA / DAVA JONAS) vira checkup; pistas para 4 lives.
6. **Produto comercial (0.16–0.17.1)** — SaaS de contas/licença, app com atalho, velocidade, robustez.
7. **Edição sem IA (0.18.x)** — módulos P00–P27 e modo Sem IA; correção do YouTube.
8. **Redesign (0.19)** — auditoria de UX, aprovação, implementação de E0–E3(+E4 parcial).

---

## 3. Registro de decisões (ADR resumido)

Formato: problema → alternativas → decisão → justificativa → consequências/riscos → estado → ainda válida?

### D01 — Processamento local (nada de vídeo em servidor) [DECISÃO APROVADA 23/11; já adotada como suposição em 22/11]
- **Problema:** como vender uma ferramenta de vídeo pesada por assinatura.
- **Alternativas:** (a) SaaS web com processamento em nuvem; (b) desktop local-first com servidor mínimo; (c) híbrido.
- **Decisão:** (b). O Hook's roda no PC do cliente; o servidor `hooks_cloud` cuida só de conta, plano, licença, cobrança e contagem de uso.
- **Justificativa (sua, 23/11 + `SAAS_0_16.md`):** custo de nuvem para vídeo, privacidade, aproveitar hardware do cliente, sem custo recorrente de inferência.
- **Consequências:** suporte a hardware heterogêneo (CPU/GPU/Windows), instalação, atualização e proteção de código passam a ser problema do produto.
- **Estado:** app local implementado [VERIFICADO]; servidor existe e foi testado só em Linux [TESTADO]; hospedagem, pagamento real, jurídico: [PLANEJADO].
- **Válida:** sim.

### D02 — Arquitetura da aplicação: servidor HTTP local (stdlib) + interface HTML + janela Edge/Chrome em modo app [VERIFICADO NO CÓDIGO]
- **Problema:** parecer um aplicativo sem reescrever tudo.
- **Alternativas consideradas por você em 23/11:** Tauri, Electron, nativo, backend compilado (a avaliação pedida no prompt de redefinição arquitetural; **o relatório dessa avaliação não está acessível**: lacuna).
- **Decisão efetiva até hoje:** nenhuma troca. `desktop.py` abre `http://127.0.0.1:<porta>` em janela própria do Edge/Chrome (perfil separado). Servidor `ThreadingHTTPServer`, token por sessão, SQLite.
- **Estado:** funciona em Linux [TESTADO]; janela/ícone/atalho no Windows real **não** validados [NÃO VERIFICADO].
- **Válida:** em aberto: a escolha Tauri/Electron/instalador `.exe` é decisão pendente (ver roadmap R-F01).

### D03 — Uma única codificação no render, com recuo automático [HISTÓRICO CONFIRMADO V8]
- Problema: 2–3 recodificações perdiam qualidade e tempo. Decisão: filtergraph único; se falhar, volta ao método V7 e registra o motivo. Em 0.18 ampliou-se o recuo (sem módulos opcionais). Válida.

### D04 — Qualidade: 4 modos reais, Entrega sempre na CPU [DECISÃO APROVADA 23/11; implementada na 0.19]
- Problema (P10): os 4 modos eram idênticos no caminho principal.
- Decisão: `telemetry.MODES` + `hardware.GPU_MODES`; Entrega usa x264 `slower` CRF 15 sempre na CPU, porque as escalas NVENC/QSV/AMF **não** são equivalentes ao CRF (você pediu para não presumir equivalência).
- Risco: ajustes p7/hq/veryslow/QP17-19 podem ser recusados por drivers; recuo para CPU existe. Nada testado em GPU real.
- Medido (sintético, 4 s 1080×1920): SSIM 0,854 / 0,964 / 0,975 / 0,981 e 7,4 / 9,2 / 90,9 / 168 s.

### D05 — Pistas de trabalho (0.15) [VERIFICADO NO CÓDIGO]
- Problema: um trabalhador para tudo; exportar travava análise de live. Decisão: `LANES=('analise','edicao','exportacao','exportacao2','refino')`, modelo de voz único com `ModelGate`, modo `lanes=unico` preservado. Gargalo conhecido: transcrição.

### D06 — Heurística explicável, nunca "probabilidade de viralizar" [HISTÓRICO CONFIRMADO]
- Notas marcadas `heuristico_nao_calibrado`; calibrador só liga com ≥30 casos reservados; chat/rosto só pontuam com confirmação de outra pista. Válida.

### D07 — Humano decide: nada publica sozinho [HISTÓRICO CONFIRMADO]
- `publish.py` entrega pacote; estados de entrega com aprovação por hash. Pasta de entrega copia, não envia. Válida.

### D08 — Redesign: inspetor contextual no lugar de 8 abas; 3 pistas; "Sugestões"; ordem E0→E1→E2→resto [DECISÃO APROVADA 23/11 15:04]
- Alternativas da auditoria: manter abas por categoria; dividir em Editar/Aparência/Exportar (sugerido no prompt). Rejeitadas pela auditoria porque recriam o problema; adotada seleção-manda.
- Estado: ver `HOOKS_MASTER_DOSSIER.md` §Parte VII (tabela E0–E10).

### D09 — Salvar ≠ renderizar; autosave que não ensina a memória [DECISÃO APROVADA; implementada 0.19]
- P04/N4: `save_project(learn=False)` no autosave; aprendizado único com o diff inteiro ao salvar de propósito, sair, trocar de corte ou exportar. Prévia antiga preservada e marcada "Prévia anterior".

### D10 — **IA: de "capacidade desejada" para "editor sem dependência de IA"** (capítulo próprio)
Evolução [HISTÓRICO CONFIRMADO]:
1. **0.8–0.17:** o agente usava faster-whisper (transcrição), MediaPipe (rosto/webcam), RNNoise opcional e Ollama opcional; os kits de 18–19/11 pediam "compreender contexto, reações, microexpressões" (A01–A16) e um "segundo avaliador que leia a transcrição" foi discutido como próximo salto.
2. **22/11:** kit "edição automática offline e sem IA" (P00–P27) define Sem IA como requisito transversal; 0.18.0 implementa `ai_mode='sem_ia'`.
3. **23/11:** direção comercial: app desktop sem serviços de IA na nuvem; o diferencial é não depender de IA. Requisito "SEM IA": auditar Whisper, MediaPipe, RNNoise, Ollama; não introduzir novas dependências; alternativas convencionais com limites; sem remoção silenciosa.

Realidade atual [VERIFICADO NO CÓDIGO e TESTADO]:
- Modo **Sem IA** existe e funciona (teste `tests/test_noai_mode.py` bloqueia faster_whisper, mediapipe, torch, onnxruntime, tensorflow durante a análise).
- Perfil novo ainda nasce em `ai_mode='padrao'` e `requirements.txt` instala `faster-whisper==1.2.1` e `mediapipe==0.10.21`.
- Funções que **não** são IA: sugestões (`agents.py`), conversa de edição (`converse.py`, regras e regex), "Por quê", QC, silêncio/preto/parado, histogramas, loudness, cortes, zoom, velocidade.
- Haar (OpenCV) é classificador clássico treinado, não rede neural; "rastreio" é fluxo óptico Lucas-Kanade.
- Capacidades que **não existem sem modelo**: reconhecer fala arbitrária, reconhecer expressão/emoção, achar o momento "mais engraçado" semanticamente, remover fundo por significado. Alternativas: importar SRT/VTT/ASS, marcadores manuais, região marcada à mão, picos de energia (rotulados heurística).
- **Pendente de aprovação sua:** tornar Sem IA o padrão e remover faster-whisper/mediapipe de `requirements.txt` (perde legenda automática para quem não tem arquivo de legenda). Não foi feito.
- Contradição histórica a manter visível: os documentos 0.11–0.17 descrevem o produto como "agente" com IA local opcional; a 0.19 renomeou "Agente"→"Sugestões" sem mudar o código determinístico.

### D11 — SaaS (contas/licença) como base separada, modo livre por padrão [VERIFICADO]
- `cloud_config.json` com `enforce:true`, `server_url`, `public_keys` liga o login; sem ele, o app roda sem limites (0.15 idêntico). Licença Ed25519 válida 72 h, funcionamento offline até vencer. Suposições (Pix manual no beta, sem CNPJ, textos legais em rascunho) vêm de `SAAS_0_16.md` e **você não as confirmou explicitamente** [NÃO VERIFICADO].

### D12 — Compatibilidade de projetos [VERIFICADO/TESTADO]
- Campos novos opcionais; projeto 0.18.2 abre na 0.19; voltar à 0.18.2 mostra a prévia de corte editado na 0.19 como "Sem prévia". Perfis antigos mantêm a chave de memória (`store.py` linha com `ai_mode`).

### D13 — Atualização por `ATUALIZAR.bat` com rollback (`liveclips_anterior`) [HISTÓRICO CONFIRMADO]
- Dados em `C:\LiveClips` nunca são tocados. Não testado no Windows real.

### D14 — Proteção de código, licenciamento anti-pirataria, instalador `.exe`, assinatura digital [PLANEJADO / NÃO DECIDIDO]
- Mencionados como riscos em `APLICATIVO_0_16.md` e no prompt de 23/11; nada implementado. Distribuição atual: ZIP com código Python legível.
