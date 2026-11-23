# Dependências com modelo de aprendizado de máquina — auditoria (sem remoção)

Estado: **inventário e plano**. Nada foi removido. Qualquer remoção exige aprovação do Rafael (CLAUDE.md §7).
Evidência = `grep` no código da 0.19.0-beta.1 (linhas podem mudar; reconfira antes de agir).

| Componente | Onde é usado | Ativo por padrão? | O que depende dele | Sem ele (`sem_ia`) | Alternativa sem IA | Perda inevitável |
|---|---|---|---|---|---|---|
| **faster-whisper** (transcrição) | `engine.py` ~533–544 (carrega `WhisperModel`), `preflight.py` ~81 (download do modelo) | **Sim**: perfil novo nasce `ai_mode='padrao'`; `requirements.txt` instala `faster-whisper==1.2.1` | Legendas automáticas, 2ª passada de legenda, ranking por fala/expressões, ganchos/títulos sugeridos, contexto/episódios (texto) | `_analyze_free` roda sem transcrição | Importar SRT/VTT/ASS (`subtitles.py`); marcadores manuais; picos de energia/movimento/silêncio | **Legenda automática** e tudo que lê texto, para quem não tem arquivo de legenda |
| **MediaPipe** Face Landmarker | `behavior.py` (~219, baixa modelo de `storage.googleapis.com`), `camera_detect.py` (~39–74) | Sim no modo padrão | Movimento facial breve (rotulado, não é emoção); localização automática da webcam | `camera_detect` recua para Haar (OpenCV, clássico); `behavior` desligado | Haar/OpenCV; região da webcam marcada à mão (já existe) | Sinal de movimento facial; detecção automática mais frágil |
| **RNNoise** (`arnndn`) | `denoise.py` (baixa `.rnnn` de GitHub), `media.py` ~686/730 (`voice_clean=='neural'`) | Não (opcional; `afftdn` é o padrão) | Só a limpeza "neural" de voz | `media.py` ~681/438 já ignora no `sem_ia` | `afftdn`, passa-alta, gate/EQ (FFmpeg) | Redução de ruído mais fraca em ruído não estacionário |
| **Ollama** (LLM local) | `ollama.py`; `engine.py` ~708 (`rerank`), ~727 (`titles`); `app.py` ~699 (lista modelos); `store.py` ~148 | **Não** (desligado por padrão) | Avaliador de ganchos, títulos por LLM | Sem efeito | `agents.py`/`editorial.py` (regras, determinístico) já cobrem sugestões | Reordenação/títulos semânticos |

**Já clássico (não é IA):** Haar e Lucas-Kanade (OpenCV), `agents.py`, `converse.py` (regex/regras), QC, `signals.py`, `technical.py`, `visual.py`, loudnorm.

**Efeitos colaterais de rede a decidir junto:** o app baixa arquivos de modelo de `storage.googleapis.com` (MediaPipe), `raw.githubusercontent.com` (RNNoise) e do Hugging Face (Whisper, via biblioteca). Não envia vídeo; mesmo assim é tráfego externo que o produto "sem IA" deve declarar ou eliminar.

## Plano de substituição proposto (precisa de aprovação, ver A01/B01)
1. **Fase 0 (sem risco):** documentar e rotular na UI o que cada modo faz. Nenhuma remoção.
2. **Fase 1:** tornar `sem_ia` o padrão para perfis **novos** (perfis existentes mantêm a chave); `requirements.txt` base sem Whisper/MediaPipe; `requirements-ia.txt` opcional. Teste: instalação limpa roda análise+edição+exportação.
3. **Fase 2:** reforçar caminho sem texto: importação de legenda como fluxo de primeira classe, marcadores com 1 tecla, editor de legenda manual (temporizar a partir de arquivo/texto colado).
4. **Fase 3 (só se aprovado):** retirar o código das 4 integrações. Perda funcional declarada ao cliente.
Não afirmar paridade: nenhum algoritmo clássico reconhece fala arbitrária nem expressão.
