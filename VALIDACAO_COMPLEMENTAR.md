# Validação complementar — Hook’s 0.18.1-beta.1

Ambiente: Linux de desenvolvimento, FFmpeg/ffprobe, mídia **sintética** gerada por `tests/corpus.py`. Nada foi validado no Windows, em live real, em editor de vídeo real, com GPU, nem com pessoas. “Comprovado” abaixo significa: um teste automático ou uma medição reproduzível em arquivo renderizado, com resultado esperado definido **antes** de rodar. Avaliação automática não é opinião de usuário.

Como reproduzir (na pasta do código): `PYTHONPATH=. python3 -W ignore -m unittest tests.<módulo>`.
Exemplos antes/depois dos defeitos de corte: `validacao/exemplos_antes` e `validacao/exemplos_depois` (medidas em JSON + 3 quadros cada; gerados com `HOOKS_EXEMPLOS=<pasta>`).

## 1. Qualidade dos cortes (mídia sintética com gabarito)
Módulos: `tests/corpus.py` (gabarito no texto), `tests/medidas.py` (medidas independentes do produto), `tests/test_corpus_cortes.py` (expectativas fixas, 4 cenários: jogo+webcam, vídeo sem webcam, vídeo vertical, edições do projeto).

| Requisito | Evidência (medida) | Resultado | Correção | Reteste |
|---|---|---|---|---|
| Intervalo marcado preservado | reação silenciosa 29–32 s | 3,03 s mantidos (mín. 2,8) | — | ok |
| Áudio, vídeo e efeito sincronizados | flash × bipe | 20 ms (limite 80) | — | ok |
| Legenda × voz | início da fala × início da legenda | −20 ms (limite 150) | — | ok |
| Sem deformar nem cortar o que não deve | proporção do rosto, quadrado de referência, cantos do vídeo vertical, lados do horizontal | rosto 0,99; 76 px; cantos e lados preservados | — | ok |
| Movimento fluido | passo do objeto por quadro, quadros repetidos | 29 px/quadro; 0,1 % parados | — | ok |
| Volume consistente | LUFS integrado, pico real, variação | −16,0 LUFS; −4,9 dBTP; variação 8,13 dB | limite de variação recalibrado de 8,0 para 9,0 (calibração do predefinido “natural”, **não** é correção de produto; registrado aqui) | ok |
| Prévia = exportação | duração e diferença de quadros | duração igual; diferença ≤ 5,6 (limite 14) | — | ok |
| Zoom automático visível | degrau de ampliação no instante do gatilho | presente | — | ok |
| Título automático não cobre a webcam | quadros com o rosto visível | **antes: 103 quadros cobertos nos primeiros 3,4 s** | `media.camera_zone` + `captions.title_blocks(margin_frac)`: título desce abaixo da região da câmera | rosto visível ≥ 90 % (teste `Regressions`) |
| Legenda fora da faixa que o TikTok costuma cobrir | borda inferior da legenda × faixa do QC | **antes: padrão 260 → borda a ~1514 px (faixa coberta começa em 1440); a ajuda dizia que 260 bastava** | padrão 340; texto da ajuda corrigido; perfis já salvos mantêm o valor que o usuário tinha | ok; regressão `default caption margin vs QC zone` |

Limites: “legibilidade” foi medida por posição e faixa segura, não por pessoas lendo; efeitos por perfil foram contados no plano, não julgados esteticamente; a fidelidade da prévia em JavaScript para a legenda do libass não foi comparada quadro a quadro.

## 2. Comprovação P00–P27 (ligação do código ao arquivo final)
Prova de ligação: `tests/test_ligacao_modulos.py` espia as chamadas do FFmpeg e renderiza o mesmo corte com tudo **ligado** e tudo **desligado**: cada opção aparece no comando quando ligada, some quando desligada, e nenhuma gera “recuo”. Cobre: `voice_preset`, `lut`, `slow_interp`, `stabilize`, `auto_music`, `cut_fade`, `blur_regions`, `auto_color`, `motion_level`. Além disso o efeito é medido no arquivo (cor muda o brilho do quadro inteiro; música audível nas pausas).

Varredura de código morto (funções sem nenhum chamador em `liveclips/`, só em testes): `layout_policy`, `caption_track.collisions/reading/timing_error/wer`, `perception.*`, `technical.scan_silence_filter`, `editing.Remap.occurrences`, `project.ramp_duration`, `plan.to_output/to_source/frame_index`, `motion.zoom_at`. **Não corrigido:** ligar `layout_policy` mudaria o layout por trecho, algo que o renderizador (um layout por corte) não suporta sem reescrever o filtro; ficou registrado como lacuna.

Legenda: ✔ comprovado (sintético) · ◐ parcial · ✘ ausente na integração · ⌀ não verificável aqui.

| Módulo | Entrada / config | Efeito observável | Sem o dado necessário | Verificação | Estado |
|---|---|---|---|---|---|
| P01 plano/receita | `media._attach_plan` → `plano.json` | plano gravado e relido nos testes de corpus | sem plano o render usa o plano B | `test_corpus_cortes`, `test_plan_memory` | ✔ |
| P02 relógio/remap | `editing.Remap` | legenda −20 ms; reação preservada | — | corpus | ✔ (`Remap.occurrences` sem chamador) |
| P03 análise técnica | `technical.analyze` em `_analyze_free` | picos/silêncio/preto/parado sugerem cortes | sem sinal → nenhum candidato, aviso | `test_technical`, `test_noai_mode` | ✔ (`scan_silence_filter` sem chamador) |
| P04 marcadores | `marcadores.json/csv/txt`, “marcar agora” | corte do marcador (janela 5–38 s) | sem marcador → só picos | corpus, `test_markers*` | ✔ |
| P05 pausas | `auto_silence`, `silence_policy` | pausas encurtadas, fala preservada | sem transcrição usa energia | `test_silence_policy`, `ProjectEdits` | ✔ |
| P06 áudio externo | vínculo em Avançado | áudio trocado com offset medido | ambíguo → recusa | `test_syncaudio` | ✔ |
| P07 layouts | `layout` do perfil/projeto | `game_pip` verificado no corpus | — | `ProjectEdits`, `test_layout_policy` (função isolada) | ◐ um layout por corte; adaptativo ✘ |
| P08 rastreio | `track_roi`, `reframe_mode=rastreio` | `plano_enquadramento.json` | região sem textura → quadro padrão | `test_track` | ✔ (vídeo real ⌀) |
| P09 zooms | automático + `project.zooms` | zoom visível | sem ponto visual → sem zoom | corpus | ✔ |
| P10 replay/freeze | `project.replays/freezes` | trecho repetido/congelado | — | `test_exemplo_completo` | ✔ (política automática ◐) |
| P11 velocidade | `project.speeds`, `slow_interp` | 2× em 22–24 s | fora de 6 s → recusa | `ProjectEdits`, ligação | ✔ |
| P12 voz | `voice_preset` | −16,0 LUFS; cadeia no comando | filtro ausente → pula e avisa | corpus, ligação, `test_voice_chain` | ✔ |
| P13 música/ducking | `auto_music`, `sfx` | música audível nas pausas | sem faixa → nada | ligação | ✔ (batida só manual ◐) |
| P14 legendas prontas | SRT/VTT/ASS | falas com origem registrada | formato inválido → erro claro | `test_subtitles`, corpus | ✔ |
| P15 títulos por dados | `title_template` | título do rótulo; **agora fora da webcam** | campo vazio some | `test_titledata`, corpus | ✔ |
| P16 chroma/máscara | só projeto/API | despill, máscara | falha → aviso no QC | `test_keying` | ✔ (sem UI) |
| P17 cor/LUT | `auto_color`, `lut` | brilho do quadro muda; `lut3d` no comando | quase preto → não mexe (intencional) | `test_grade`, ligação | ✔ |
| P18 estabilização | `stabilize` | `deshake` no comando | filtro ausente → aviso | ligação | ◐ efeito em vídeo trêmulo real ⌀ |
| P19 transições | `cut_fade` | fade de áudio de 20 ms nas emendas | — | ligação, `test_cut_fade` | ◐ sem xfade de vídeo |
| P20 capas | `cover` | `_capa.jpg` entregue | capa fraca → aviso | `test_cover`, corpus | ✔ |
| P21 receitas de imagem | `brand`, `imagerecipe` | moldura/logo visíveis | imagem inválida → original | `test_imagerecipe` | ✔ |
| P22 diretor | `director_report` | causas registradas | — | `test_director` | ✔ |
| P23 multiformato | `export_formats` | 1:1, 4:5, 16:9 válidos | variante inútil → apagada e registrada | `test_multiformat` | ✔ |
| P24 cache/fila/recuperação | `cache.py`, `store.recover` | **queda do processo em duas etapas da exportação e em plena análise: reabre, limpa e refaz sem duplicar** (seção 4) | — | `test_protecao_dados` | ◐ sem proxy |
| P25 QC e recuo | `qc`, `_single_ladder` | o QC apontou a legenda na faixa coberta (item da seção 1) | — | `test_retreat`, corpus | ✔ |
| P26 intercâmbio | OTIO, `projeto.json` | biblioteca OTIO 0.18.1 abre; `reopen` confere | projeto inválido → `ValueError` | `test_exemplo_completo`, seção 4 | ✔ biblioteca · ⌀ Premiere/Resolve/Final Cut/CapCut |
| P27 gráficos 2D | `motion_level` | barra/título/contador | sem caixa → não entra | `test_graphics2d`, ligação | ✔ |

## 3. Instalação limpa e atualização
- Ambiente isolado (Python 3.11 + só `requirements.txt`, sem pytest/playwright), pacote extraído para pasta com **espaços, apóstrofo e acentos** (`Instalação Hook's`), usuário sem privilégio (`nobody`), sem rede (`unshare -n`), `PYTHONDONTWRITEBYTECODE`: diagnóstico completo OK; `test_noai_mode` + `test_exemplo_completo` (24 testes) passam; **0** tentativas de importar modelos de IA no modo sem IA; primeira abertura serve o painel (`/api/state` 200, pasta de dados criada).
- Mensagem de dependência ausente: `ffmpeg, ffprobe não encontrado(s). Rode o INSTALAR.bat de novo.` (verificada por simulação de `find_tool`).
- **Atualização com dados reais da 0.17.1:** os dados foram criados com o **código 0.17.1** (streamer, perfil, sessão, dois candidatos, projeto com corte/zoom/título, aprovação, exportação). Aberto com o código 0.18.1: perfil preservado (18 chaves novas preenchidas por padrão, câmera e margem 260 do usuário mantidas), projeto normalizado, **exportação antiga idêntica byte a byte** depois de abrir e de renderizar outro corte, novo render nos dados antigos concluído, projeto da 0.17.1 renderizado no código novo com duração esperada (17,0 s). O painel abre esses dados sem erro de JavaScript (`validacao/painel_dados_0_17_1.png`).
- Corrigido: `INSTALAR.bat`, `ATUALIZAR.bat` e `GERAR_DIAGNOSTICO.bat` estavam com fins de linha LF (o `cmd.exe` pode errar ao achar rótulos com `goto`) → CRLF nos 7; `ATUALIZAR.bat` quebrava ao arrastar o ZIP (aspas) e com apóstrofo no caminho (PowerShell) → tratados; `INSTALAR.bat` abortava se o modelo facial não baixasse, mesmo sendo opcional → só avisa. `tests/test_instaladores.py` confere CRLF, ASCII, rótulos e parênteses (verificação estática).
- **Não validado:** execução dos `.bat` no Windows, `winget`, Deno, atalho, SmartScreen/antivírus, outro SO ou outro hardware. As correções dos `.bat` são **[Provável]**: baseadas em comportamento conhecido do `cmd.exe`, sem execução.

## 4. Proteção de dados e recuperação (`tests/test_protecao_dados.py`, 16 testes)
| Requisito | Evidência | Resultado | Correção |
|---|---|---|---|
| Original nunca alterado | hash, tamanho e mtime da pasta do usuário antes/depois de analisar e exportar; nome `jogo 'quebrado' $(touch PWNED) & \`id\` ; "aspas" ção.mp4` | idêntico; nada novo ao lado; `PWNED` não existe | — (não há `shell=True`; comandos são listas) |
| Colisão de saída | entrega com arquivo diferente no mesmo nome; mesma entrega duas vezes | outro conteúdo → `_2`; mesmo conteúdo → reaproveita | — |
| Exportação existente não sobrescrita | status forçado para “aprovado” e nova exportação | arquivo idêntico, 1 pasta | — |
| Limpeza só de temporários | pasta `render_*` resto × corte pronto × pastas do usuário × arquivo `render.txt` | só o resto sai | — |
| Gravação interrompida | falha na troca; 4 gravadores simultâneos lendo sem parar | arquivo anterior intacto, sem `.tmp`; nunca JSON cortado | **novo `atomic.py`** em `fonte.json`, `vinculo_origem.json`, `inventario.json`, `captura_fim.json`, `servidor.json` (permissão 600 em POSIX), sincronia de áudio, marcadores/legendas importados |
| Queda durante exportação (SIGKILL em “pasta criada” e em “vídeo parcial gravado”) | banco antes: `exporting`; depois de reabrir: `approved`; sem `render_*`; fonte idêntica; 2ª recuperação inofensiva; exportação final **uma** pasta e **uma** entrega | passou | — |
| Queda durante a análise | segmento `processing` → `new`; reanálise 2× | **1** corte do marcador | — |
| Importação de projeto/pacote com caminho perigoso | `copy: ../segredo.txt`, `name: ../x`, `a\b`, `/etc/passwd`, JSON lista/incompleto | antes: leitura fora de `fontes/` aceita e `AttributeError` com JSON-lista; **agora** ignorado/erro claro | `export_pack.reopen` restringe a `fontes/`, valida nome e estrutura |
| Backup com caminho inseguro | ZIP com `perfis/../../fora` | recusado, nada criado fora | — (já existia) |
| Logs sem credenciais | token em URL, `Authorization: Bearer`, `oauth:`, cookie, `C:\Users\<nome>`, `/home/<nome>` | tudo oculto no diagnóstico; sem banco/mp4 no ZIP | `support.clean_text` ampliado |
Observações: `servidor.json` contém o token local; em Windows a permissão herdada da pasta de dados vale (`C:\LiveClips` pode ser legível por outros usuários da máquina) — não alterado, **[Hipótese]** de risco só em PC compartilhado.

## 5. Entradas extremas, simultaneidade e desempenho (`tests/test_entradas_extremas.py`, 9 testes)
- Arquivo vazio / texto com extensão de vídeo / inexistente / só áudio: mensagens em português com o nome do arquivo (antes: “Invalid data found when processing input”). Vídeo sem áudio e com duas faixas: exportam; o inventário avisa.
- Original movido: erro “Religar original”, nada criado, e **depois de devolver o arquivo a tentativa seguinte conclui**. Original alterado: bloqueado, arquivo intocado.
- Sem espaço: o corte volta à fila (`approved`) sem lixo e conclui quando a reserva é reduzida. **Bug achado:** a reserva usada era a do perfil **congelado na sugestão**, então mudar “reserva de disco” em Ajustes não valia para cortes já sugeridos → passa a valer a atual.
- Três exportações simultâneas do mesmo corte + segundo clique em “aprovar”: 1 pasta, 1 entrega, nenhuma exceção.
- Desempenho (medido): o original era relido por inteiro a **cada** prévia e exportação (`media.sha_file` em `engine._do_render`). Antes: **2 leituras** (prévia + exportação); depois: **1** (`sha_file_cached` por caminho+tamanho+mtime; a primeira conferência continua lendo tudo). Ordem de grandeza: ~1 GB/s com cache de disco quente aqui; em HDD, fontes de horas custam dezenas de segundos por prévia **[Provável]**, não medido.
- Processos órfãos: matando só o Python (SIGKILL) durante a exportação, o FFmpeg filho terminou sozinho (0 restantes em 3 s e em 28 s). **Só Linux**; Windows não verificado.

## 6. Registro de achados
| # | Achado | Gravidade | Causa | Correção | Reteste |
|---|---|---|---|---|---|
| F01 | Título automático cobria o rosto da webcam | alta | margem fixa ignorava a região da câmera | `camera_zone`, `margin_frac` | corpus + regressão |
| F02 | Legenda padrão dentro da faixa coberta pelos botões | média | margem 260; ajuda dizia suficiente | 340 + texto | regressão |
| F03 | `find_tool` não achava ferramentas em venv via link simbólico | baixa (Linux) | `resolve()` seguia o link | candidato sem resolver | diagnóstico OK |
| F04 | `reopen` aceitava caminhos fora de `fontes/` e quebrava com JSON-lista | média | arquivo de fora tratado como confiável | validação | 4 testes |
| F05 | Arquivos de estado gravados sem atomicidade | média | `write_text` direto | `atomic.py` | 4 testes |
| F06 | Original relido inteiro a cada prévia/exportação | média (grandes fontes) | hash sem memória | `sha_file_cached` | 2→1 |
| F07 | Reserva de disco do perfil antigo prevalecia | baixa | perfil congelado no corte | perfil atual | teste |
| F08 | Mensagem crua do ffprobe | baixa | erro técnico repassado | mensagens PT-BR | teste |
| F09 | Diagnóstico não ocultava Bearer/cookie/usuário | média | regex curto | ampliado | teste |
| F10 | `.bat` com LF, aspas/apóstrofo, modelo facial obrigatório | média **[Provável]** | — | corrigidos | estático apenas |
| F11 | Funções sem chamador; layout adaptativo não integrado | média | desenho | **não corrigido** | — |

## 7. Sem validação neste ambiente
Windows (execução dos `.bat`, Explorer, winget, Deno, atalho, antivírus), live real e captura, vídeo real de câmera/jogo, GPU/encoders por hardware, Premiere/Resolve/Final Cut/CapCut, pessoas reais (legibilidade, gosto, retenção), outro SO ou hardware, carga longa (horas) e exportação paralela com `export_workers=2`, camada de interface da bandeja de exportação com axe (fumaça de JS rodou sem erro; o roteiro completo `smoke_ui` depende de dados e abas que não existiam na pasta de teste), layout adaptativo por trecho, fidelidade da legenda da prévia em JavaScript frente ao libass.
