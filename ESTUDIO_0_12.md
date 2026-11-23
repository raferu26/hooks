# LiveClips 0.12 — o que mudou, o que foi testado e o que só você valida

## Agentes
- Pipeline de escolha: sugestão → ranking → curadoria (judge) → reavaliação opcional pelo Ollama → ampliação de contexto → plano de edição. Há uma segunda passada para legendas, aprendizado dos seus hábitos (aprovar/rejeitar/editar), níveis de confiança com calibração, e controle de qualidade (qc.py) na exportação.
- **Benchmark**: você marca no mínimo 20 momentos bons de conteúdo real (gabarito) e o programa mede quantos o agente achou. Sem o seu gabarito não existe número; os testes daqui usam dados sintéticos e só provam que a conta funciona.

## Estúdio
- **Prévia ao vivo**: legenda e título aparecem na hora, desenhados pelo navegador. A prévia de rascunho (540×960) **não grava mais texto no vídeo**. Zoom, cortes, velocidade, cor e layout continuam gravados no rascunho e exigem **Atualizar prévia**. A posição ao vivo é aproximada; a exportação final é a referência.
- **Kit de marca por streamer** (no perfil): logo (canto, tamanho, opacidade), imagem de abertura e de encerramento (quadro inteiro nos primeiros/últimos segundos, sem aumentar a duração; use 1080×1920), fonte de legenda, cor e posição do título. Fontes ficam na pasta `fontes` (.ttf/.otf). O logo respeita as margens seguras da interface do TikTok. Cor e posição só se aplicam a títulos que você não personalizou.
- **Reenquadramento seguindo quem fala**, **áudio profissional** (redução de ruído neural opcional via RNNoise, baixado uma vez), **eventos visuais** (heurística).
- **Publicação**: importação de CSV de desempenho (mostra uma prévia e pede confirmação), teste A/B de gancho (variações do mesmo momento) e série Parte 1/2.
- **Controle de qualidade na exportação**: confere duração, áudio, zona segura do texto e outros itens antes de marcar como pronto.

## Suporte
- Log rotativo em `logs/liveclips.log`; `python -m liveclips diag` ou **GERAR_DIAGNOSTICO.bat** cria um ZIP em `diagnosticos/` sem vídeos, banco ou perfis, com tokens e caminho do usuário ocultados.
- Progresso com tempo restante (aparece só depois de 5 s e 3% de avanço, para não mostrar estimativa instável).
- **ATUALIZAR.bat**: pede o ZIP novo, mantém a versão anterior em `liveclips_anterior` e volta atrás se a instalação falhar.

## Interface
Paleta grafite neutra (rosa = ação principal, água = referência/seleção, âmbar = cursor e atenção), barra lateral de navegação, abas do estúdio com ícones (Estilo, Legendas, Títulos, Música, Efeitos, Quadro, Agente, Publicar). Verificada por capturas de tela e fluxos automatizados em Chrome neste ambiente.

## Limites (honestidade)
- **Não testado no Windows**: ATUALIZAR.bat e as mudanças no INSTALAR.bat. Não foi possível gerar um instalador .exe aqui.
- Redução de ruído neural: verificada tecnicamente, **sem fala real**; ouça antes de usar em tudo. O download do modelo precisa de internet no seu PC.
- Reenquadramento: validado só com rostos sintéticos e **sem separação de falantes por áudio**.
- Eventos visuais: heurística, sujeita a erro.
- Zonas do controle de qualidade: números aproximados da interface do TikTok. A margem padrão de legenda (260) fica dentro da zona conservadora; ajuste se quiser mais folga.
- Formato do CSV de desempenho não é documentado pelas plataformas: por isso há prévia e confirmação.
- Não medido aqui: música por YouTube, codificadores de GPU, qualidade do Ollama, acerto dos agentes em conteúdo real.
- Fontes e músicas: a licença é responsabilidade sua.

## O que fazer primeiro
1. Rode o TESTE_GUIADO.md com 2 lives reais.
2. Monte o gabarito (≥20 momentos) e rode o benchmark.
3. Ouça a redução de ruído em fala real e confira o QC em um clipe já postado.
