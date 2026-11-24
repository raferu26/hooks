# Áudio clássico (sem IA) — comparativo medido

Ferramenta: `python3 validacao/medir_audio.py [saida.json]` (sinais sintéticos com referência limpa; **não é fala real**). Resultados: `validacao/audio_antes_0_19.json` (código 0.19) e `validacao/audio_depois_dsp.json`. Testes de regressão: `tests/test_audio_dsp.py`.
Métricas: **piso de ruído** nas pausas (dBFS, menor = melhor), **SDR** da fala contra a voz limpa (maior = melhor; todos os candidatos ficam ≈12,3 dB porque o passa-alta de 70 Hz comum a todos corta parte do fundamental sintético), **VOL σ** (consistência: desvio do nível entre falas), LUFS e pico verdadeiro (ebur128).

## 1. Redução de ruído (24 s, ruído rosa −42 dBFS + zumbido 60/120 Hz)
| Cadeia | Tempo p/ 24 s | SDR | Piso de ruído | SNR |
|---|---|---|---|---|
| sem tratamento | 0,1 s | 20,3 | −42,2 | 20,6 |
| 0.19: passa-alta + `afftdn` nr12 | 0,20 s | 12,4 | −48,2 | 26,6 |
| `afwtdn` 70% sozinho | 0,19 s | 12,3 | −54,6 | 33,0 |
| `anlmdn` (non-local means) | 1,9 s | 12,5 | −60,7 | 39,1 |
| **app agora: `afftdn` + `afwtdn` 70%** | 0,24 s | 12,4 | **−53,4** | **31,8** |
**Por que híbrido:** o wavelet adaptativo sozinho **piora clipes curtos** (6 s: piso −45,0 contra −48,1 do `afftdn`, pois ainda não aprendeu o ruído). Medido em 6/12/24/60 s: híbrido remove **6,0 / 6,0 / 9,1 / 9,7 dB a mais** que o `afftdn`, com SDR igual (±0,05). `anlmdn` remove mais, mas é ~10× mais lento: **candidato para o modo "Entrega"**, ainda não adotado.
**Limite:** ruído sintético estacionário. Ruído de teclado, ventoinha variável ou sala reverberante não foi testado; wavelet pode soar "debaixo d'água" em voz real. Validar com 2–3 áudios reais antes de chamar de melhoria percebida. Sem `afwtdn` no FFmpeg, o app volta ao `afftdn`.

## 2. Ducking da música sob a voz
| Parâmetros do `sidechaincompress` | Música na fala | Música nas pausas | Queda |
|---|---|---|---|
| 0.19: thr .06, ratio 8, 20/350 ms | −28,4 | −24,4 | **3,9 dB** |
| **agora: thr .03, ratio 10, 15/400 ms** | −32,7 | −25,3 | **7,3 dB** |
Causa da queda fraca: limiar de −24 dBFS ficava acima das falas baixas (−28/−30 dBFS RMS), que então não acionavam o ducking. **Limite:** a fala sintética tem pouco fator de crista; em fala real o ducking aciona mais. Pausas perdem ~1 dB (liberação de 400 ms).

## 3. Consistência de volume (VOL σ, menor = melhor) e níveis finais
| Cadeia | VOL σ | LUFS | Pico |
|---|---|---|---|
| sem nivelar | 4,9 | −21,5 | 0,0 |
| compressor `natural` (preset) | 2,6 | −20,6 | −1,4 |
| compressor `forte` (preset) | 1,7 | −18,1 | 0,0 |
| `dynaudnorm` | 4,0 | −18,6 | −1,0 |
| `speechnorm` | 2,8 | −16,6 | −0,3 |
| **app, limpeza leve, preset off (padrão)** | **2,8** | −20,0 | −1,5 |
| **app, limpeza leve + preset natural** | **1,0** | −19,0 | −1,5 |
Achado: o padrão (`voice_preset='off'`) deixa VOL σ ≈ 2,8 dB; o preset **natural** reduz para ≈1,0 dB. **Decisão pendente:** tornar `natural` o padrão de perfis novos? (muda o som de todos os cortes novos). Pico verdadeiro fica ≤ −1,5 dBTP em todos os casos do app. LUFS final de −19/−20 aqui é de `loudnorm` de 1 passada; a exportação usa 2 passadas (alvo −16 LUFS, medido −16,0 no corpus).

## 4. Pendências
Fala real (limpeza, ducking, preset); ruído não estacionário; `anlmdn` no modo Entrega; EQ/de-esser avaliados só quanto a níveis; Windows/FFmpeg do instalador (a presença de `afwtdn` depende da versão do FFmpeg do cliente — há fallback).

## 5. Comparativo A/B para ouvir (`validacao/ab_audio.py`)
Para decidir se o preset `natural` vira padrão **com áudio real**:
```bash
python3 validacao/ab_audio.py voz_limpa.wav voz_com_ruido.wav gameplay.mp4 --saida ab_saida --segundos 60 --limpeza
```
Gera, por amostra, `1_original`, `2_preset_desligado`, `3_preset_natural` (e com `--limpeza` também `4_desligado_com_limpeza`, `5_natural_com_limpeza`), **todas no mesmo volume (−16 LUFS)**, mais `ouvir.html` (players com **modo cego** sorteado e campo de notas) e `metricas.json` (LUFS, pico, LRA, consistência σ, piso de ruído, % de clip). Use cópias dos arquivos; os originais não são tocados. `--demo` gera 3 amostras sintéticas só para conferir o fluxo.
**Achado já visível no demo sintético:** com ruído de fundo, o preset `natural` **sem** limpeza sobe o piso de ruído (≈ +2,4 dB: −35,9 → −33,4 dBFS) porque o compressor tem ganho de compensação; com a limpeza ligada o piso cai (−48 dBFS). Ouça esse caso com atenção.
O que avaliar de ouvido: clareza · artefatos (som "debaixo d'água", chiado, bombeamento da música) · preservação da voz · consistência de volume.
