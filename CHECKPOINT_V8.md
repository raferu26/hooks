# Checkpoint V8 — editor profissional

- Curvas de zoom por punch, avanço lento e supersample (`liveclips/motion.py`).
- Look por estilo (curva, cor, legenda) e margem de respiro real; campo `reframe` removido.
- Legendas sem piscar; estilos `impact`, `pop`, `box` e modo Automática; ênfase no pico.
- Render em uma passada com retorno automático ao método V7; vídeos longos com busca grossa.
- Loudness medido com ganho linear somente quando o pico permite.
- 150 testes aprovados; créditos do ReaCut (MIT) em THIRD_PARTY_NOTICES.md.

Rollback: tag `v0.9.0-beta.1` (V7) ou o ZIP 0.9.0.
