# Layout de reação (composição) — sem IA

Branch: `feature/layout-reacoes` (a partir do pacote Windows 0.20.0-beta.1; o pacote entregue não foi alterado).
Objetivo: transformar um vídeo horizontal de reação em vertical sem perder a webcam do streamer. O usuário marca as regiões
no quadro ORIGINAL; um único motor monta o quadro final tanto na prévia quanto na exportação.

## Arquitetura (um motor, vários layouts)
`FONTE → REGIÕES → TRANSFORMAÇÕES → LAYOUT → QUADRO FINAL`

| Peça | Onde | Observação |
|---|---|---|
| Modelo, validação, geometria, filtergraph | `liveclips/composition.py` | módulo puro (sem FFmpeg dentro); `resolve()` é a **única** conta de coordenadas |
| Esquema no projeto | `project['composition']` (`project.clean`, `rebase`) | campo opcional; projeto antigo abre igual (`None`) |
| Render/prévia | `media.final_video` → `composition.video_graph` | a prévia em vídeo (rascunho) usa o mesmo caminho da exportação |
| Prévia imediata (canvas) | `ui/reacao.js` ← `/api/composition/resolve` | desenha com as camadas devolvidas pelo servidor; não recalcula geometria |
| Quadro original para marcar regiões | `/media/srcframe?id=…&t=…` | quadro do arquivo de origem, sem o corte 9:16 (rotação e proporção de pixel aplicadas) |
| Presets | `layouts_reacao.json` na pasta de dados, `/api/composition/presets` | local, gravação atômica |
| Aplicar a vários cortes | `/api/composition/apply` | não toca cortes já exportados |
| Sugestões determinísticas | `liveclips/reaction_signals.py`, `/api/composition/suggest` | só diferença de quadros |

### Coordenadas (transformação explícita)
Regiões = frações 0–1 do quadro de **exibição** da fonte (depois de rotação e proporção de pixel), origem no canto superior esquerdo.
Cadeia: ponteiro (px da tela) → retângulo da `<img>` (`getBoundingClientRect`, sem letterbox) → fração 0–1 (salva) →
`crop` em pixels pares da fonte (servidor) → `crop=` do FFmpeg → posição/tamanho no 1080×1920. Independente da resolução do arquivo.
`probe()` agora devolve `rotation`, `sar`, `display_width/height`; fontes com SAR≠1 são normalizadas antes do recorte.

### Oito layouts (um preset parametrizado cada; não há oito pipelines)
Principais: Webcam compacta (split .30), Webcam ampliada (.45), Webcam flutuante. Em "Mais layouts": Webcam embaixo (.62), Foco na reação,
Dueto, Duas webcams + conteúdo (.34), Cinema (.28, conteúdo "Mostrar inteiro", fundo desfocado). Os números são só valores iniciais, todos ajustáveis.
Enquadramento por região: **Preencher** (recorta, sem distorcer), **Mostrar inteiro** (pode sobrar fundo), **Personalizado** (zoom 1–4× + foco).
Fundo: preto, cor ou desfocado (convencional). Janela flutuante: 4 cantos ou posição livre, tamanho, borda; mantém a proporção da webcam.

### Cenas de reação (layout por intervalo)
`composition.scenes=[{id,start,end,layout,params,fade}]` em segundos do CLIPE (como cortes/zooms). No render viram trechos no tempo FINAL
(`composition.segments` + `media.composition_pieces`): acompanham cortes, velocidade, congelamentos, replays e abertura. Cada quadro é
composto uma vez (`trim` + `concat` sobre um único `split`); só a transição suave (0,3 ou 0,6 s) compõe as duas cenas e mistura com peso
linear no tempo (`blend`), determinística. Cena que usa uma região não marcada é ignorada (e avisada).

### Ocultar parte do vídeo (manual)
`composition.masks` (≤6): desfocar ou cobrir com cor uma área da FONTE antes de qualquer recorte (vale para todas as cenas). Nada é
detectado nem reconstruído; a prévia imediata mostra o efeito.

### Sugestões (Fase E)
Movimento médio por região a 5 amostras/s (72 px, cinza). Sugere trechos com conteúdo parado ≥ 2 s e webcam em movimento. Limiares
configuráveis, trechos distantes ≥ 3 s, até 8; cada sugestão traz a regra e "confiança" heurística (forte/média/fraca). **Não sabe se o
vídeo foi pausado** nem o que o streamer faz. Aprovar cria a cena; Ignorar esconde; desfazer = Ctrl+Z.

### Áudio
A composição só mexe no vídeo: uma única trilha de áudio original (testado: 1 stream de áudio na exportação). Nada é duplicado.

## Limitações conhecidas (não implementado / não validado)
- Webcam em **arquivo separado** (segunda fonte) e escolha/deslocamento de áudio: **não implementado**.
- Cantos arredondados e posição livre por arrasto direto na prévia: não implementados (posição livre por sliders).
- Zoom automático/punch é desligado enquanto há composição (cortaria a webcam). Variantes 1:1/4:5/16:9 não usam a composição (só 9:16).
- O método antigo ("legacy", plano B) não monta a composição: o manifesto registra `composition_skipped`.
- Cena que depende de região ausente (ex.: Dueto sem Webcam 2) é ignorada com aviso.
- "Webcam ausente em certos momentos": não há detecção; o usuário usa cena com outro layout (ex.: Cinema) ou oculta o conteúdo no Foco.
- Rotação/SAR: coberto por teste (ver abaixo) apenas em Linux com mídia sintética.
- **Nada disto foi validado no Windows, com GPU, nem com o vídeo real Coringa/Caiox.** Ver `docs/WINDOWS_TESTE/ROTEIRO_LAYOUT_REACAO.md`.

## Fidelidade prévia × exportação
- Geometria: `resolve()` único; teste de pixel (FFmpeg × plano) nos 8 layouts × fit/fill, zoom/foco, gap, fundo, borda, máscaras:
  tolerância ±14 níveis por canal (yuv420 + escala), pontos de amostra a >5 px de bordas de bloco.
- Prévia imediata (canvas) usa as mesmas camadas, mas a escala do navegador não é a lanczos do FFmpeg: serve para posicionar, não para nitidez.
- Prévia em vídeo (rascunho) = mesmo filtergraph em 1080×1920 reduzido a 540×960.
- Não declarar "fidelidade perfeita": o SSIM global não foi usado como critério; a comparação é por região.

## Testes
`tests/test_composicao.py` (validação, geometria, pixels, máscaras, webcam viva com conteúdo parado, exportação real + legenda + áudio),
`tests/test_composicao_cenas.py` (mapa de tempo, quadros exatos, rampa da transição), `tests/test_composicao_presets.py`,
`tests/test_reacao_sugestoes.py`, e2e `ui/e2e_reacao.py` (Playwright: escolher layout → marcar regiões no quadro original → prévia →
ajustes → presets → máscara → cenas → sugestões → persistir/reabrir), benchmark `validacao/bench_composicao.py`.
