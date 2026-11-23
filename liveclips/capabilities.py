"""Registro de capacidades e receitas de edição (F15, F27) e matriz de estado do dossiê (F01–F28, R01–R36).

Regra do dossiê: estar no catálogo editorial não é estar implementado. Cada receita diz o que o código FAZ hoje,
com o arquivo que prova e o plano B. O planejador só pode propor o que está `disponivel` ou `parcial`; pedir uma
receita ausente é recusado com mensagem, nunca descartado em silêncio. "Não aplicar nada" é uma escolha válida.
"""
from . import motion

DISPONIVEL, PARCIAL, AUSENTE, LAB = 'disponivel', 'parcial', 'ausente', 'laboratorio'
STATES = (DISPONIVEL, PARCIAL, AUSENTE, LAB)
USABLE = (DISPONIVEL, PARCIAL)
NO_EFFECT = 'nenhum'            # escolha explícita de não intervir

HEX16 = '^[a-f0-9]{16}$'


def _recipe(id_, nome, status, evidencia, fallback='', nota='', params=None, version=1, custo='não medido', nivel='intermediario'):
    return dict(id=id_, version=version, nome=nome, status=status, evidencia=evidencia, fallback=fallback, nota=nota,
                params=params or {}, custo=custo, nivel=nivel)


# Receitas R01–R36 do dossiê, com o estado real no código da 0.13.
RECIPES = {
    'R01': _recipe('R01', 'Corte limpo e ajuste de entrada/saída', PARCIAL, 'agents.tighten_bounds, timeline.expand_context, editor manual',
                   'Ajuste manual no Estúdio', 'Bordas seguem frases; alças vêm do contexto anterior/posterior.', nivel='essencial'),
    'R02': _recipe('R02', 'Pausas e repetições', PARCIAL, 'editing._safe_silences/_safe_repetitions, safety.py, narrative_skill.protected_pauses',
                   'Não cortar', 'Classifica por duração e vizinhança; pausas perto do clímax ficam protegidas.', nivel='essencial'),
    'R03': _recipe('R03', 'Jump cut motivado', PARCIAL, 'editing.cuts_for', 'Manter o trecho', 'Sem checagem de continuidade corporal.'),
    'R04': _recipe('R04', 'J cut e L cut', AUSENTE, '', 'Corte seco', 'Imagem e áudio compartilham os mesmos pontos de corte (media.build_source).'),
    'R05': _recipe('R05', 'Abertura por antecipação curta', DISPONIVEL, 'project.teaser, agents.suggest_teaser, media.plan_pieces', 'Cronologia integral'),
    'R06': _recipe('R06', 'Preparação e payoff', PARCIAL, 'narrative.story_plan, narrative_skill.function_map', 'Corte cronológico'),
    'R07': _recipe('R07', 'Pausa e silêncio intencionais', PARCIAL, 'narrative_skill.protected_pauses', 'Manter pausa original',
                   'Protege pausas; não cria silêncio artificial.'),
    'R08': _recipe('R08', 'Corte por correspondência visual', AUSENTE, '', 'Corte seco', nivel='avancado'),
    'R09': _recipe('R09', 'Layout vertical webcam + gameplay', DISPONIVEL, 'media.live_filters, media.resolve_layout', 'Layout "Ajustar"',
                   'Câmera em cima, tela dividida, jogo com câmera no canto e só câmera.', nivel='essencial'),
    'R10': _recipe('R10', 'Punch in sobre reação', DISPONIVEL, 'motion.py, editing.plan_edits, project.zooms', 'Sem zoom',
                   params=dict(zoom=(1.02, motion.MAX_ZOOM), curve=tuple(motion.PUNCH_CURVES)), custo='baixo'),
    'R11': _recipe('R11', 'Reenquadramento rastreado', PARCIAL, 'speaker.py, media.dynamic_reframe_plan', 'Enquadramento fixo do perfil',
                   'Só no modo vídeo; no modo live o recorte da câmera é fixo.', nivel='avancado'),
    'R12': _recipe('R12', 'Troca motivada entre layouts', PARCIAL, 'layout_policy.py (política e plano); render troca layout por clipe, não por trecho',
                   'Layout fixo do perfil', 'A política decide trechos com histerese; o render por trecho ainda não existe.', nivel='avancado'),
    'R13': _recipe('R13', 'Congelamento e anotação', PARCIAL, 'media.build_source (hold), project.freezes', 'Sem congelar',
                   'Congela; anotação desenhada sobre o quadro não existe.', params=dict(duration=(0.3, 3.0))),
    'R14': _recipe('R14', 'Replay explicativo', DISPONIVEL, 'editing.Remap (replays), project.replays', 'Sem replay',
                   'Legenda e áudio seguem o mesmo remapeamento; replay lento sai mudo por padrão.',
                   params=dict(rate=(0.25, 2.0)), custo='baixo'),
    'R15': _recipe('R15', 'Legenda limpa por blocos', DISPONIVEL, 'captions.py', 'Legenda por bloco de frase', nivel='essencial'),
    'R16': _recipe('R16', 'Destaque sincronizado de palavras', DISPONIVEL, 'captions.keyword_indexes, make_ass', 'Legenda sem destaque'),
    'R17': _recipe('R17', 'Tipografia cinética', PARCIAL, 'captions.CAPTION_STYLES (estilos animados)', 'Legenda estática', nivel='avancado'),
    'R18': _recipe('R18', 'Título de contexto', DISPONIVEL, 'captions.title_blocks, project.titles', 'Sem título'),
    'R19': _recipe('R19', 'B-roll e imagem de apoio', PARCIAL, 'assets.py, project.overlays', 'Sem imagem',
                   'Insere imagens da biblioteca; não busca por significado nem confere licença por destino automaticamente.', nivel='avancado'),
    'R20': _recipe('R20', 'Setas e anotações rastreadas', AUSENTE, '', 'Sem anotação', nivel='avancado'),
    'R21': _recipe('R21', 'Corte sincronizado à música', PARCIAL, 'music.beat_times, agents.snap_to_beats', 'Cortes sem grade musical',
                   'Acentos de zoom seguem as batidas; cortes de montagem não.'),
    'R22': _recipe('R22', 'Rampa de velocidade (velocity)', PARCIAL, 'project.ramp_steps, editing.Remap', 'Velocidade constante',
                   'Rampa em degraus constantes; sem interpolação de quadros.', params=dict(rate=(0.25, 4.0)), nivel='avancado'),
    'R23': _recipe('R23', 'Câmera lenta seletiva', PARCIAL, 'project.speeds', 'Velocidade normal', 'Repete quadros; não inventa detalhe.',
                   params=dict(rate=(0.25, 4.0))),
    'R24': _recipe('R24', 'Ducking de música sob voz', DISPONIVEL, 'media.audio_chain (sidechaincompress)', 'Música em volume baixo fixo'),
    'R25': _recipe('R25', 'Efeito sonoro por função', DISPONIVEL, 'sfx.py (catálogo sintetizado, com função e intensidade)', 'Sem efeito'),
    'R26': _recipe('R26', 'Acabamento de voz', DISPONIVEL, 'media.audio_chain, denoise.py, loudnorm em dois passes', 'Áudio original normalizado'),
    'R27': _recipe('R27', 'Transição por movimento', AUSENTE, '', 'Corte seco', nivel='avancado'),
    'R28': _recipe('R28', 'Shake localizado', AUSENTE, '', 'Sem shake'),
    'R29': _recipe('R29', 'Máscara de pessoa', AUSENTE, '', 'Layout comum', 'Sem segmentação temporal instalada.', nivel='avancado'),
    'R30': _recipe('R30', 'Texto atrás do sujeito', AUSENTE, '', 'Texto na frente', 'Depende de R29.', nivel='avancado'),
    'R31': _recipe('R31', 'Desfoque rastreado de informação', AUSENTE, '', 'Cobertura fixa manual', nivel='avancado'),
    'R32': _recipe('R32', 'Colagem e paralaxe 2.5D', LAB, '', 'Sem efeito', nivel='especializado'),
    'R33': _recipe('R33', 'Composição e câmera 3D', LAB, '', 'Sem efeito', nivel='especializado'),
    'R34': _recipe('R34', 'Correção de cor', PARCIAL, 'editing.grade_filters, LOOKS', 'Sem correção',
                   'Contraste, saturação e brilho globais; sem correção por região nem tratamento HDR.'),
    'R35': _recipe('R35', 'Estabilização e ruído visual', AUSENTE, '', 'Sem tratamento', nivel='avancado'),
    'R36': _recipe('R36', 'Loop editorial e final', AUSENTE, '', 'Final simples'),
}

# Receitas executáveis do plano (nomes usados em plan.effects_of) -> receita do dossiê e limites tipados.
PLAN_RECIPES = {
    'punch_in': dict(recipe='R10', params=dict(zoom=('num', 1.02, motion.MAX_ZOOM), curve=('enum', tuple(motion.PUNCH_CURVES)))),
    'titulo_contexto': dict(recipe='R18', params=dict(style=('enum', ('big', 'bar', 'top')), position=('enum', ('top', 'center', 'bottom')))),
    'sfx_funcao': dict(recipe='R25', params=dict(kind=('str',), volume=('num', .05, 1.0))),
    'congelar': dict(recipe='R13', params={}),
    'replay': dict(recipe='R14', params=dict(rate=('num', .25, 2.0), mute=('bool',))),
    'velocidade': dict(recipe='R23', params=dict(rate=('num', .25, 4.0))),
    'velocidade_rampa': dict(recipe='R22', params=dict(rate=('num', .25, 4.0))),
    'musica_ducking': dict(recipe='R24', params=dict(asset=('str',), duck=('bool',))),
    'imagem_apoio': dict(recipe='R19', params=dict(asset=('str',))),
    NO_EFFECT: dict(recipe=None, params={}),
}


def status_of(recipe_id):
    return RECIPES[recipe_id]['status']


def usable(recipe_id):
    return RECIPES[recipe_id]['status'] in USABLE


def check_use(name, params):
    """Mensagens de problema para o uso de uma receita do plano. Lista vazia = pode usar."""
    spec = PLAN_RECIPES.get(name)
    if spec is None:
        return [f'A receita "{name}" não existe no registro de capacidades.']
    if spec['recipe'] and not usable(spec['recipe']):
        return [f'A receita {spec["recipe"]} ({RECIPES[spec["recipe"]]["nome"]}) não está disponível nesta versão.']
    messages = []
    for key, rule in spec['params'].items():
        if key not in params:
            continue
        value = params[key]
        kind = rule[0]
        if kind == 'num':
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not rule[1] <= value <= rule[2]:
                messages.append(f'{name}.{key}={value!r} fora do limite {rule[1]} a {rule[2]}.')
        elif kind == 'enum':
            if value not in rule[1]:
                messages.append(f'{name}.{key}={value!r} não é um valor permitido.')
        elif kind == 'bool':
            if not isinstance(value, bool):
                messages.append(f'{name}.{key} precisa ser verdadeiro ou falso.')
        elif kind == 'str':
            if not isinstance(value, str) or len(value) > 80:
                messages.append(f'{name}.{key} precisa ser um texto curto.')
    extra = set(params) - set(spec['params'])
    if extra:
        messages.append(f'{name}: parâmetros desconhecidos {sorted(extra)}.')
    return messages


def fallback(name):
    spec = PLAN_RECIPES.get(name)
    if not spec or not spec['recipe']:
        return ''
    return RECIPES[spec['recipe']]['fallback']


def request(recipe_id):
    """Pedido de uma receita pelo planejador: devolve (aceito, mensagem, plano B)."""
    item = RECIPES.get(recipe_id)
    if item is None:
        return False, f'{recipe_id} não existe no registro.', ''
    if item['status'] in USABLE:
        return True, '', item['fallback']
    return False, f'{recipe_id} ({item["nome"]}) está {item["status"]} nesta versão; usando o plano B.', item['fallback']


def summary():
    counts = {state: 0 for state in STATES}
    for item in RECIPES.values():
        counts[item['status']] += 1
    return counts


def as_rows():
    return [RECIPES[key] for key in sorted(RECIPES)]


# Itens N01–N32 do dossiê de inteligência/contexto/operação (0.14). Mesma regra: catálogo não é implementação.
# `parcial` = existe e é testado com dados sintéticos; NENHUM item foi validado em conteúdo real de lives.
INTELLIGENCE = {
    'N01': ('Fechamento explícito de segmentos', AUSENTE, '', 'Segue valendo a regra antiga (arquivo estável > 25 s, último só com sessão encerrada).'),
    'N02': ('Reconexão com épocas de captura', AUSENTE, '', ''),
    'N03': ('Referências e retenção do buffer', PARCIAL, 'retention.plan', 'Só simula a limpeza e protege mídia de cortes ativos; não apaga nada e não considera editor/revisões.'),
    'N04': ('Mapa de relógios', PARCIAL, 'clockmap.py, chat.py', 'Declara a incerteza do chat (padrão 5 s ou latência do provedor). Deslocamento só com chat_clock.json; não alinha sozinho.'),
    'N05': ('Filas separadas com orçamento', PARCIAL, 'engine.waiting_note', 'Só informa que a live espera a vez; continua um único trabalhador, sem fila separada.'),
    'N06': ('Identidade e retomada de jobs', AUSENTE, '', 'Sem lease/idempotência nova.'),
    'N07': ('Estado semântico da sessão', PARCIAL, 'context_store.py, studio_api.context_action', 'Fatos/hipóteses com proveniência e escopo; participantes e tópicos NÃO são extraídos sozinhos.'),
    'N08': ('Episódios abertos e desfecho', PARCIAL, 'episodes.py, dimensions.py, handoff.py', 'Regras de texto em português; o corte espera se há promessa sem desfecho. Não validado em conteúdo real.'),
    'N09': ('Relações entre acontecimentos', PARCIAL, 'episodes.py, fusion.associate', 'Relação temporal nunca é causa; alternativas ficam listadas.'),
    'N10': ('Recuperação de contexto distante', PARCIAL, 'context_search.py', 'Busca textual/estruturada até 15 min antes; referência ambígua vai para decisão humana.'),
    'N11': ('Percepção do gameplay ou vídeo', AUSENTE, '', 'Sem modelo de visão: o jogo só entra como flashes/rajadas de pixel.'),
    'N12': ('Candidatos silenciosos', LAB, 'silent_path.py', 'Até 2 por contexto, sempre rotulados como exploratórios; bocejo, movimento global e pista isolada fraca são descartados com motivo.'),
    'N13': ('Refinamento de limites', PARCIAL, 'timeline.expand_context, context_search.required_context', 'Os limites principais não mudaram; o contexto exigido é listado e bloqueia o estado "pronto".'),
    'N14': ('Ranking por dimensões', PARCIAL, 'dimensions.py', 'As dimensões são calculadas e mostradas, mas a ordem dos cortes continua pelo escore antigo.'),
    'N15': ('Diversidade semântica', PARCIAL, 'dimensions.novelty', 'Medida de novidade por sobreposição de tempo/texto; deduplicação antiga mantida.'),
    'N16': ('Qualidade da face', PARCIAL, 'face_quality.py', 'Cobertura, tamanho do rosto e amostragem. Desfoque e oclusão NÃO são medidos.'),
    'N17': ('Rastreamento e baseline por atividade', PARCIAL, 'behavior.py', 'Baseline separado falando/ouvindo (≥ 8 amostras) e pose reiniciada após perda do rosto. Sem identidade entre pessoas.'),
    'N18': ('Buffer facial e análise densa', LAB, 'signals.refine_dense', 'Função existe (4–30 fps, só no trecho); não é chamada automaticamente e o ganho de recall não foi medido.'),
    'N19': ('Início, ápice e retorno', PARCIAL, 'behavior.py', 'Eventos têm onset/apex/offset e incerteza igual ao passo de amostragem (0,25 s a 4 fps).'),
    'N20': ('Eventos de áudio e prosódia', AUSENTE, '', 'Só energia de som; não distingue risada de som do jogo.'),
    'N21': ('Fusão com origem e dependência', PARCIAL, 'fusion.py', 'Movimento, rosto e comportamento da webcam contam como UMA fonte. Atribuição ao streamer fica "não verificada".'),
    'N22': ('Raciocinador contextual local', AUSENTE, '', 'O Ollama segue só no rerank/títulos de antes.'),
    'N23': ('Calibração e abstenção', PARCIAL, 'calibration.py, fusion.py', 'Estados de abstenção existem. Notas = "heurístico_nao_calibrado"; calibrar exige ≥ 30 casos reservados.'),
    'N24': ('Memória episódica com proveniência', DISPONIVEL, 'context_store.py', 'Fato exige evidência; correção versiona, lista dependentes e permite reverter.'),
    'N25': ('Casos de erro e momentos perdidos', PARCIAL, 'context_store.add_case, app.record_case, studio.js', 'Aprovar/rejeitar e "momento perdido" viram casos; ninguém os usa para ajustar nada automaticamente.'),
    'N26': ('Avaliação causal por replay', PARCIAL, 'replay.py', 'Verificador de "olhar o futuro" pronto; não foi rodado com gravações reais.'),
    'N27': ('Comparação humana e ablação', PARCIAL, 'replay.ablate/evaluate', 'Mede cobertura contra casos humanos; sem casos, não calcula número.'),
    'N28': ('Observabilidade por evento', PARCIAL, 'context_store.trace, camada_contexto.py', 'Registra a etapa de sugestão por corte; não acompanha render/entrega.'),
    'N29': ('Painel de contexto e revisão', PARCIAL, 'studio.js (aba "Por quê")', 'Mostra dimensões, abstenções, episódios, contexto exigido e correção; sem exibir evidência bruta quadro a quadro.'),
    'N30': ('Distribuição opcional por conectores', AUSENTE, '', 'Pacote manual mantido.'),
    'N31': ('Métricas com definição e escopo', AUSENTE, '', ''),
    'N32': ('Recuperação verificável do ambiente e da mídia', PARCIAL, 'recovery.verify_restore', 'Verifica um backup em pasta isolada e lista mídia ausente; ainda não há botão na interface.'),
}


def intelligence_rows():
    return [dict(id=k, nome=v[0], status=v[1], evidencia=v[2], nota=v[3]) for k, v in sorted(INTELLIGENCE.items())]


def intelligence_summary():
    counts = {state: 0 for state in STATES}
    for v in INTELLIGENCE.values():
        counts[v[1]] += 1
    return counts
