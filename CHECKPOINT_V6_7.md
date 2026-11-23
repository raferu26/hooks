# Checkpoint V6.7 — 0.8.7-beta.1

- Branch isolada: `v6.7`; a branch e a tag da V6.6 permanecem intactas.
- Exportação entre segmentos usa seek preciso depois da entrada e foi repetida com os arquivos reais que apresentavam a falha.
- Resultado real: fonte montada 50,21 s; entrega 1080×1920 com 50,17 s e primeiro quadro em 0,000 s.
- 95 testes automáticos aprovados; proteção de origem falsa repetida 30 vezes sem falha.
- Backups automáticos e manuais protegem banco/perfis. A restauração valida integridade e cria uma cópia do estado anterior.
- Prioridade, formato e estilo reclassificam sugestões automáticas sem refazer a transcrição.
- Sessões podem tentar novamente, religar originais idênticos por SHA-256, arquivar e reativar.
- O instalador verifica dependências e tenta instalar FFmpeg/ffprobe gratuitamente pelo Windows Package Manager.

Limite preservado: backups do programa não copiam gravações pesadas. Para proteção completa, a pasta de mídia também deve ser copiada para outro disco.
