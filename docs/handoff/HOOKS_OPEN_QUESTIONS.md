# HOOKS — Perguntas em aberto e lacunas de histórico

Parte do pacote `HOOKS_MASTER_HANDOFF`. Cada item: pergunta, por que importa, evidência disponível, como resolver. Estas são coisas que **não consegui recuperar ou validar**; nenhuma foi preenchida por suposição.

## A. Lacunas de histórico (fontes inacessíveis)

| # | Pergunta | Por que importa | Evidência disponível | Como resolver |
|---|---|---|---|---|
| H01 | O que foi discutido e decidido na conversa de origem (outro assistente; pasta `referenced-chatgpt-conversation-this-is-an`) antes da V6/0.8.0? | Ideia original, requisitos iniciais (4 lives simultâneas, webcam em cima, edição durante a live) e decisões iniciais vêm dali | Nome da pasta, `work/source/liveclips-v6-main`, `work/incoming/liveclips-home-0.8.1`, `CHECKPOINT_V6…V6_9` e a memória do assistente ("projeto nasceu como agente clipador/LiveClips") | Rafael exportar essa conversa ou colar o início; ou aceitar a lacuna |
| H02 | Quando e por que o nome mudou de LiveClips para Hook's? | Identidade; nomes internos continuam `liveclips` | Memória: decidido em 19/11/2026, só nome/logo mudam; o ZIP 0.12 ainda chama LiveClips e o 0.13 já Hooks | Confirmar com o Rafael; o código mantém `liveclips` de propósito |
| H03 | Qual o conteúdo e a data do **relatório de auditoria de arquitetura** (pedido de redefinição Desktop SaaS Local-First, 23/11)? | Contém a avaliação de stack (Tauri/Electron/nativo) e o plano de otimização | Só o prompt (`a8c8724a`) e a decisão resumida em memória; o link do relatório no Docs não foi preservado no contexto disponível | Rafael indicar o link do documento ou pedir nova auditoria |
| H04 | Houve auditoria de desempenho e de QA multi-perfil entregue? | Os prompts de 23/11 pedem investigação, medição e correção; os resultados deveriam aparecer em `NOVIDADES_0_18`/`0_17` | Há medições na 0.17 (painel 0,57→0,07 s etc.) e testes de entradas extremas (~14.500 requisições); o relatório consolidado dos prompts `aea368ce`/`c61c4d1a` não foi localizado | Conferir com o Rafael se existe documento separado |
| H05 | Qual é o número exato de versão da "V7.1"? | A tabela de versões tem um buraco entre 0.9.0 e 0.10.0 | `CHECKPOINT_V7_1.md` cita "tag v0.9.0-beta.1 (V7)" como rollback; não há ZIP próprio | Recuperar tags do repositório git original, se existir |
| H06 | Quem produziu os kits de prompts P01–P18 (18/11), A01–A16 (19/11) e P00–P27 (22/11)? | Distinguir especificação (proposta) de código | Os arquivos dizem "preparado em…"; o texto fala em "assistente que programa" | Confirmar autoria; irrelevante para o código, relevante para o histórico |
| H07 | Existe histórico de commits do repositório original (`liveclips-v6-main`, branches `v6.x`)? | Rollback fino e arqueologia | `.gitignore`/`.gitattributes` e menções a branches/tags nos checkpoints; o repo não está nos uploads (só `liveclips-v6-main` como pasta e o ZIP CapCut de referência) | Rafael localizar o `.git` na pasta Codex |
| H08 | Capturas de tela "antes/depois" do redesign (`/tmp/shots*`) ainda existem? | Evidência visual do P01/P02 | Foram geradas em ambiente temporário (`/tmp`) e entregues na conversa; não estão no pacote | Regenerar com `ui10/fresh.sh` + `shot*.py` |

## B. Perguntas de produto/negócio ainda sem resposta

| # | Pergunta | Por que importa | Evidência | Como resolver |
|---|---|---|---|---|
| B01 | Tornar o modo Sem IA o padrão e retirar faster-whisper/mediapipe da instalação? | Define a promessa comercial "sem IA" × legenda automática | `NOVIDADES_0_19` §5 | Decisão do Rafael (ver roadmap A01) |
| B02 | Tipo de cliente-alvo (streamer, agência, clipador), preços, limites por plano | Planos do servidor vêm inativos com preço 0 e números ilustrativos | `SAAS_0_16.md`; memória: "ainda não definiu tipo de cliente, PC vs nuvem, CNPJ nem preços" (22/11) | Rafael definir |
| B03 | CNPJ, razão social, meio de cobrança (Pix manual × Asaas) | Jurídico e fiscal | `SAAS_0_16`, `PENDENCIAS_0_17_1` | Rafael + contador/advogado |
| B04 | Stack final do instalador (servidor local + janela Edge/Chrome, Tauri, Electron, outro) | Define esforço, tamanho, segurança, atualização automática | `desktop.py` é a solução atual; avaliação pedida em 23/11 sem relatório localizável | Retomar a avaliação (roadmap F01) |
| B05 | Política de proteção do código e licença offline | Distribuição hoje é ZIP com Python legível | Licença Ed25519 válida 72 h existe; anti-engenharia-reversa não | Decisão + pesquisa |
| B06 | Direitos autorais e termos das plataformas para gravar lives de terceiros | Risco jurídico | `PENDENCIAS_0_17_1` item A.4 | Advogado |
| B07 | O produto se destina a quais plataformas de saída (TikTok, Reels, Shorts)? Margens de legenda foram conferidas contra a interface real? | A margem 340 px vem de uma faixa de QC, não de prints reais | `EDITOR_PRO_V8`, `VALIDACAO_COMPLEMENTAR` | Prints reais das plataformas |

## C. Pendências de validação técnica

| # | Pergunta | Evidência atual | Como resolver |
|---|---|---|---|
| V01 | O Hook's abre e funciona no Windows 10/11 real? (atalho, ícone, janela sem console, Encerrar) | Nunca testado | Rafael rodar o roteiro; enviar `hooks_servidor.log` |
| V02 | NVENC/QSV/AMF aceitam os ajustes novos dos modos Qualidade/Rápido? | Sem GPU no ambiente; GPU do Rafael **não informada** | Informar a placa; C02 do roadmap |
| V03 | O tempo dos modos em vídeo real | Sintético: 7,4/9,2/90,9/168 s para 4 s | Enviar 2–3 clipes |
| V04 | A prévia de legenda em HTML é igual à legenda renderizada (libass)? | Hipótese; nunca comparada quadro a quadro | Teste visual lado a lado |
| V05 | O YouTube real baixa com o yt-dlp do PC? | Só HTTP local simulado | Teste no PC |
| V06 | A captura de 2–4 lives simultâneas aguenta no i7-3770? | Só `.ts` simulados; capacidade medida só com modelo falso | Teste com lives |
| V07 | O arquivo OTIO abre em Premiere/Resolve/Final Cut/CapCut? | Só lido pela biblioteca OpenTimelineIO | Abrir nos editores |
| V08 | A taxa de acerto dos cortes sugeridos | Não existe | Gabarito do Rafael (`bench.py`) |
| V09 | O custo de redesenho (N5) em clipe de 90 s com muitas palavras | Não medido | Medir com Playwright |
| V10 | O Estúdio novo é realmente mais fácil para iniciantes? | Só medidas mecânicas (cliques/tempo por e2e) | Teste com pessoas |
| V11 | Os limiares de QC (congelamento 2 s etc.) são adequados | "Valores iniciais" | Dados reais |

## D. Inconsistências conhecidas na documentação

- `NOVIDADES_0_19.md` chama de "E3" o que inclui o inspetor (que na auditoria era E4) e as 3 pistas; este pacote registra as duas numerações (ver roadmap).
- `capabilities.py` descreve o estado de cada receita "na 0.13"; não confirmei se todas foram atualizadas depois dos módulos P00–P27 [NÃO VERIFICADO].
- O docstring de `liveclips/__init__.py` ainda diz "Hook's 0.13" apesar de `__version__ = '0.19.0-beta.1'`.
- Documentos de estado antigos (por exemplo `PENDENCIAS_0_16.md`) permanecem no pacote e citam números de testes (~800) que não valem mais.
