"""Conhecimento editorial durável (fundamentos K01–K16 do dossiê) e competências do currículo (P18).

São regras com contraexemplo, não frases genéricas. Entram na memória como `semente`: repertório declarado, não aprendizado."""

FUNDAMENTALS = [
    dict(id='K01', concept='Contexto e resolução', rule='Preservar a informação necessária para entender a ação e sua resposta', contraexemplo='Começar no grito sem mostrar o motivo', competencia='corte_fidelidade', tarefas=['corte', 'narrativa']),
    dict(id='K02', concept='Integridade temporal', rule='Manter causa e efeito e distinguir replay de evento novo', contraexemplo='Atribuir uma risada de outro instante à jogada', competencia='corte_fidelidade', tarefas=['corte', 'replay', 'narrativa']),
    dict(id='K03', concept='Ritmo semântico', rule='Cortar por sentido e intenção, não apenas por silêncio ou intervalo fixo', contraexemplo='Remover a pausa que constrói a piada', competencia='ritmo_continuidade', tarefas=['corte', 'pausas']),
    dict(id='K04', concept='Hierarquia visual', rule='O elemento principal depende do que a cena precisa explicar naquele instante', contraexemplo='Ampliar o rosto enquanto o jogo mostra a ação decisiva', competencia='composicao', tarefas=['layout', 'zoom']),
    dict(id='K05', concept='Legibilidade', rule='Agrupar legenda por sentido e proteger áreas relevantes', contraexemplo='Texto sobre mira e alvo ou palavra destacada fora do tempo', competencia='legenda', tarefas=['legenda']),
    dict(id='K06', concept='Áudio prioritário', rule='Voz e sons causais têm prioridade sobre música e efeitos adicionais', contraexemplo='SFX cobrindo a frase ou o som que explica o susto', competencia='audio', tarefas=['audio', 'sfx', 'musica']),
    dict(id='K07', concept='Efeito motivado', rule='Aplicar a intervenção quando sua função for clara; permitir nenhuma intervenção', contraexemplo='Zoom a cada dois segundos independentemente da cena', competencia='efeitos', tarefas=['zoom', 'sfx', 'efeitos']),
    dict(id='K08', concept='Observação facial', rule='Descrever movimentos com contexto e confiança, sem afirmar emoção interna como fato', contraexemplo='Usar boca aberta como certeza de surpresa', competencia='revisao', tarefas=['percepcao']),
    dict(id='K09', concept='Diarização', rule='Rótulo de falante não equivale a identidade pessoal comprovada', contraexemplo='Trocar speaker_1 por um nome sem mapeamento', competencia='legenda', tarefas=['legenda', 'percepcao']),
    dict(id='K10', concept='Tempo', rule='Separar PTS, time base e posição na timeline e remapear todas as camadas', contraexemplo='Subtrair o início do clipe e ignorar replay e velocidade', competencia='ritmo_continuidade', tarefas=['corte', 'velocidade', 'replay']),
    dict(id='K11', concept='Intercâmbio', rule='OTIO transporta informação editorial e referências; compatibilidade de efeitos depende do adaptador', contraexemplo='Prometer round-trip universal ou render direto pelo OTIO', competencia='revisao', tarefas=['exportacao']),
    dict(id='K12', concept='Evidência de qualidade', rule='Avaliar vídeo renderizado e comparar com baseline e avaliação humana', contraexemplo='Chamar de profissional porque o processo retornou sucesso', competencia='revisao', tarefas=['revisao', 'avaliacao']),
    dict(id='K13', concept='Tendências', rule='Registrar data, região, nicho e origem e expirar combinações temporárias', contraexemplo='Tratar uma música como permanentemente em alta', competencia='personalizacao', tarefas=['tendencias']),
    dict(id='K14', concept='Métricas', rule='Separar qualidade editorial, codificação e desempenho publicado', contraexemplo='Usar VMAF como medida de humor ou edição', competencia='revisao', tarefas=['avaliacao']),
    dict(id='K15', concept='Memória com escopo', rule='Uma correção local não se transforma automaticamente em regra global', contraexemplo='Remover todos os zooms de todos os criadores após uma rejeição', competencia='personalizacao', tarefas=['memoria']),
    dict(id='K16', concept='Originalidade e destino', rule='Verificar origem e regras de cada destino sem supor que legenda torna conteúdo original', contraexemplo='Prometer monetização por adicionar borda e mudar velocidade', competencia='personalizacao', tarefas=['exportacao', 'ativos']),
]

COMPETENCIES = {
    'corte_fidelidade': 'Corte e fidelidade',
    'ritmo_continuidade': 'Ritmo e continuidade',
    'composicao': 'Composição',
    'legenda': 'Legenda',
    'audio': 'Áudio',
    'efeitos': 'Efeitos',
    'personalizacao': 'Personalização',
    'revisao': 'Revisão',
    'especializada': 'Composição especializada',
}

# Defeito da taxonomia -> competência que ele mede.
DEFECT_SKILL = dict(contexto_insuficiente='corte_fidelidade', payoff_cortado='corte_fidelidade', causalidade_alterada='corte_fidelidade',
                    fala_truncada='corte_fidelidade', crop_incorreto='composicao', rosto_truncado='composicao', alvo_oculto='composicao',
                    hud_necessario_oculto='composicao', texto_ilegivel='legenda', palavra_incorreta='legenda',
                    legenda_dessincronizada='legenda', voz_mascarada='audio', clipping_introduzido='audio',
                    mascara_instavel='especializada', identidade_trocada='especializada', replay_confuso='efeitos',
                    cor_inconsistente='efeitos', duracao_incorreta='ritmo_continuidade', render_incompleto='revisao')
