# Hook's 100% sem IA — plano técnico de migração

**Decisão permanente (Rafael, 23/11/2026):** a versão comercial final **não** usa APIs de IA, LLMs, serviços de inferência **nem modelos pré-treinados, mesmo offline**; sem download silencioso de modelos. Não se afirma equivalência quando ela não existe. A versão atual continua recuperável (tag `baseline-0.19.0-beta.1`); **nada foi removido ainda**.

**Interpretação adotada (a confirmar):** "modelo pré-treinado" inclui também classificadores clássicos treinados e distribuídos como arquivo (cascata Haar do OpenCV = AdaBoost treinado em XML). Os documentos herdados chamavam Haar de "clássico, não é IA"; pela regra 2 ele **entra na lista de saída**. Algoritmos sem treinamento (energia, FFT, diferença de quadros, fluxo óptico Lucas-Kanade, limiares, bordas, correlação cruzada, filtros FFmpeg) **ficam**. Se você aceitar Haar, o impacto de B/C no enquadramento melhora (ver §3).

Classes: **A** preservável com algoritmos convencionais · **B** parcial (simplificação ou intervenção do usuário) · **C** sem substituto equivalente.
Evidência: `grep` no código da 0.19.0-beta.1 (23/11). Custos computacionais são **estimativas qualitativas**, não medidas.

## 1. Inventário: cada dependência
| # | Componente | Função atual | Arquivos | Recursos afetados | Padrão hoje |
|---|---|---|---|---|---|
| D1 | **faster-whisper** (modelos tiny→turbo; baixa do Hugging Face) | Transcrição com palavras temporizadas; 2ª passada `small` | `engine.py` (~533–544, `queue_refine/do_refine`, ~985), `preflight.py` (~81, `_internet('huggingface.co')`), `store.py` (`second_pass`, `vocabulary`, `learned_terms`) | Legendas automáticas; ranking por fala; ganchos/títulos; episódios/contexto; replay por texto; segurança/QC de texto | **Sim** (`ai_mode='padrao'`) |
| D2 | **MediaPipe Face Landmarker** (`.task` de storage.googleapis.com) | Movimento facial breve na webcam (blendshapes) | `behavior.py`, consumidores: `fusion.py`, `camada_contexto.py`, `face_quality.py`, `editing.py` (~337), `capabilities.py` | Sinal "reação facial" no ranking; qualidade de rosto | Sim |
| D3 | **MediaPipe Face Detection** + **Haar (OpenCV)** | Achar a webcam; checar "rosto cortado" no QC | `camera_detect.py`, `qc_visual.py` (~282), `engine.py` (~336), `app.py` (~252) | Webcam automática; QC visual | Sim |
| D4 | **Haar (OpenCV)** | Reenquadramento dinâmico e "quem fala" | `media.py` (~392 `dynamic_reframe_plan`), `speaker.py` (~112) | Enquadramento por rosto (só vídeo); alternância por falante | Opcional (modo dinâmico) |
| D5 | **RNNoise `arnndn`** (`.rnnn` do GitHub) | Limpeza "neural" de voz | `denoise.py`, `media.py` (~686, ~730) | Redução de ruído avançada | Não (opt-in) |
| D6 | **Ollama (LLM local)** | Reordenar ganchos; títulos | `ollama.py`, `engine.py` (~708, ~727), `app.py` (~699), `store.py` (~148) | Reranking/títulos por LLM | Não (desligado) |
| D7 | `opencv` Lucas-Kanade (rastreio) | Seguir ponto/região | `track.py` | Rastreio | **Fica (A)**: não é treinado |

Há ainda **download de rede** associado a D1, D2, D5 (Hugging Face, Google Storage, GitHub). Na versão final: zero downloads de modelo.

## 2. Alternativa convencional por dependência
### D1 Whisper — capacidade principal em risco
| Capacidade | Hoje | Sem modelo | Classe |
|---|---|---|---|
| Legenda a partir de arquivo SRT/VTT/ASS | Existe (`subtitles.py`) | Igual | **A** |
| Legenda a partir de **texto digitado/colado** pelo usuário | Parcial | Segmentar o texto em frases e **distribuir no tempo** dentro dos trechos de fala detectados por energia/VAD clássico (`silencedetect`, limiar adaptativo) com peso por nº de sílabas (heurística); ajuste fino **por toque** (usuário toca uma tecla ao início de cada frase enquanto assiste) e arrasto no Estúdio. Precisão por palavra **inferior** e depende do usuário | **B** |
| Legenda **automática** de fala arbitrária | Sim (Whisper) | **Não existe** algoritmo convencional equivalente (exige modelo acústico+linguístico). Fica descontinuada; o produto diz isso na interface | **C** |
| Destaque por palavra | Whisper (tempos por palavra) | Só com ASS `\k` importado ou tempos estimados (B) | **B** |
| Detectar *onde há fala* | Whisper | VAD por energia/espectro (A, com falsos positivos em música/jogo) | **A/B** |
| Ranking por expressões/gancho de texto | Lista fixa PT/EN sobre transcrição | Sem texto: usa energia, picos, movimento, chat Twitch, marcadores, sinais técnicos; **texto só se houver legenda importada** | **B** |
| Episódios/contexto (promessa→desfecho), "se sustenta sozinho" | Regras sobre texto | Só com legenda importada | **B/C** |
| Vocabulário por streamer, correções `errado=>certo` | Whisper prompt/pós | Correções pós-texto continuam (A); vocabulário perde sentido | **A/C** |
| 2ª passada de legenda | Whisper `small` | Remover | **C** |
- **Custo:** hoje alto (CPU/GPU, modelo de centenas de MB, serialização `ModelGate`); sem modelo, análise de energia/VAD é **baixo** (FFmpeg + numpy).
- **Complexidade:** média (editor de legenda com sync por toque + alinhamento por sílaba) · **Testes:** corpus sintético com fala conhecida: erro de tempo (ms) do alinhamento por sílaba vs. gabarito; `test_noai_mode` ampliado; UI e2e do "sincronizar por toque".

### D2 MediaPipe landmarks
Perde-se o sinal de **expressão/movimento facial específico** (cabeça virada, boca aberta). Substituto: **diferença de quadros na região da webcam marcada** (já existe `motion`), picos de movimento, energia de áudio. **B** para "algo aconteceu na webcam"; **C** para "o que a face fez". Custo baixo; complexidade baixa (sinais já existem); teste: ranking sem `behavior` não regride em `test_ranking`/`test_fusion*`.

### D3 Achar a webcam / rosto cortado
- Webcam: **B**. Região marcada pelo usuário (já suportada: `camera_rect`) como caminho principal, com **assistente visual** (arrastar retângulo sobre um quadro). Sugestão automática por heurística de layout: retângulo de bordas estáveis (Canny + Hough/contornos) em cantos com razão 4:3/16:9 e variância temporal moderada. **Menos robusto** que detecção de rosto; sempre confirmada pelo usuário.
- QC "rosto cortado": **B/C**. Sem detector de rosto, verifica-se só a **geometria** (retângulo da webcam atravessa a borda do enquadramento) em vez de rosto. Perde o caso "rosto fora da webcam marcada".
- Custo baixo; complexidade média; testes: sintético com retângulos de webcam (já há corpus) e `test_camera_detect` reescrito.

### D4 Reenquadramento e "quem fala"
- **Reenquadramento dinâmico por rosto**: **B/C**. Substituto: rastreio Lucas-Kanade (**A**) a partir de um ponto/região que o **usuário clica uma vez**; ou keyframes manuais de pan/zoom com atalhos (hoje faltam). Sem seguir pessoas automaticamente em vídeo livre.
- **Quem fala (duas pessoas)**: **B**. Usuário marca as "cadeiras" (regiões); alternância por **movimento na região × energia de voz**; com áudio estéreo separado (L/R por microfone) a correlação é precisa. Mistura mono: aproximação ruim. **C** para identificar falante sem marcação.
- Custo baixo/médio; complexidade média; testes: sintético com duas regiões que se movem alternadamente (já existe cenário em `test_speaker`).

### D5 RNNoise
**A/B.** Substituir por cadeia FFmpeg clássica: passa-alta, `afftdn` (já padrão), **`anlmdn`** (non-local means), **`afwtdn`** (wavelet), `agate`/`speechnorm`, EQ de voz, de-esser (`deesser`). Menos eficaz em ruído não estacionário (teclado, ventoinha variável). Custo baixo/médio; complexidade baixa; testes: SNR antes/depois em ruído sintético (+`test_pro_audio`).

### D6 Ollama
**A.** Já existem sugestões determinísticas (`agents.py`, `editorial.py`). Remover `ollama.py`, parâmetros e rotas. Perda: reordenação/títulos "semânticos" (que estavam desligados). Complexidade baixa; testes: `test_agents_pro` etc. + guarda de importação.

## 3. Experiência: hoje × sem modelos
| Tarefa do usuário | Hoje (padrão) | Sem modelos (versão comercial) |
|---|---|---|
| Legendar um vídeo sem arquivo de legenda | Automático | **Importa SRT/VTT/ASS** ou **cola o texto** e sincroniza (guiado, minutos, não segundos); sem texto, sem legenda |
| Achar bons momentos numa live | Fala + áudio + movimento + chat | Áudio, picos, movimento, chat, **marcadores** (tecla durante a live) e sinais técnicos; sem leitura do conteúdo |
| Webcam | Detectada sozinha | Usuário desenha uma vez por streamer (lembrado no perfil); sugestão heurística opcional |
| Enquadramento que segue o rosto | Sim (vídeo) | Clique para rastrear (Lucas-Kanade) + keyframes; sem busca automática de pessoas |
| Limpeza de voz | Opcional neural | Cadeia clássica; qualidade menor em ruído variável |
| Títulos/ganchos | Regras + LLM opcional | Só regras |
Resumo honesto: o produto **deixa de transcrever sozinho**. É a perda funcional mais importante e **não tem solução equivalente sem modelo**; a resposta de produto é "legenda por arquivo ou texto próprio + sincronização assistida", que serve quem já tem roteiro/legenda e é pior para quem depende de transcrição automática. O posicionamento comercial deve declarar isso.

## 4. Fases (cada uma: testes + aprovação antes de reduzir capacidade)
| Fase | Conteúdo | Reduz capacidade? | Gate |
|---|---|---|---|
| 0 ✔ | Inventário, plano, guarda `tests/test_sem_ia_guard.py` (impede **novos** usos de ML) | Não | Este documento |
| 1 | **Substitutos primeiro, sem remover:** sincronização por texto colado + toque; assistente de desenho da webcam; keyframes manuais pan/zoom; cadeia de áudio clássica reforçada (`anlmdn`/`afwtdn`/de-esser); VAD clássico | Não | Testes novos verdes; demonstração ao Rafael |
| 2 | UI: rotular "automático (modelo)" vs "manual"; `sem_ia` como **padrão em perfis novos**; sem downloads silenciosos (pedir consentimento explícito ou remover) | Só o padrão de perfis novos | **Aprovação do Rafael** |
| 3 | Remover D6 (Ollama) e D5 (RNNoise): uso baixo/opt-in | Pouca | Aprovação |
| 4 | Remover D2/D3/D4 (MediaPipe, Haar) após Fase 1 cobrir webcam/enquadramento | Média | Aprovação + comparação medida |
| 5 | Remover D1 (Whisper), `requirements.txt` sem `faster-whisper`/`mediapipe`; build comercial verificado sem esses pacotes (`pip list`, `grep`) | **Alta (legenda automática)** | **Aprovação explícita** |
Versão atual permanece recuperável (tag + ZIPs em `_recovery/`). Build comercial final: auditoria de dependências e de rede (nenhum download de modelo) como critério de aceite.

## 5. Testes necessários
`test_noai_mode` (análise sem import de ML) · `test_sem_ia_guard` (nenhum arquivo novo referencia ML/modelo) · corpus de alinhamento por sílaba · SNR da cadeia de áudio · sintético de webcam/rastreio/falante · e2e do fluxo de legenda manual · varredura de rede (nenhum `urlopen` para modelo).
