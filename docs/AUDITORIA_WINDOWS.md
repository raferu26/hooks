# Operação Windows First — auditoria de integração (24–25/11/2026)

## Relato
Com a 0.20.0-beta.2 (commit `b8e9921b34`) instalada no Windows, o usuário não via as opções de webcam / Layout de reação que a entrega dizia estar prontas.

## O que foi verificado (e descartado)
| Hipótese | Evidência | Resultado |
|---|---|---|
| ZIP gerado da branch/commit errado | `BUILD_INFO.json` do ZIP = `b8e9921b34…`; 123 arquivos de código do ZIP comparados byte a byte com o commit: **0 diferenças** | descartada |
| Interface não reconstruída | `liveclips/static/index.html` do ZIP contém `rxCanvas`, `data-rxl`, "Layout de reação" (11 ocorrências) e o build das fontes de `ui/` reproduz o arquivo byte a byte | descartada |
| Backend sem rotas | `app.py` do ZIP registra `/api/composition/*` e `srcframe` | descartada |
| Erro JS silencioso | e2e Playwright **rodado sobre o ZIP extraído** (28+ verificações, 0 erro de console) | descartada (no Linux) |
| Flag oculta / só Linux | a seção "Layout de reação" aparece sempre na aba "Layout e imagens"; nenhum `os.name` no caminho | descartada |
| **Atalho/instalação antiga: o lançador abre o servidor de OUTRA instalação** | ver abaixo | **CAUSA-RAIZ COMPROVADA POR REPRODUÇÃO** |

## Causa-raiz
`liveclips/desktop.py::launch()` decidia "já tem servidor rodando?" olhando só `servidor.json` na **pasta de dados** (`C:\LiveClips`, compartilhada por todas as instalações) e `alive(info)`. Qualquer servidor vivo ali era reaproveitado — sem checar versão, commit nem pasta de instalação. O programa também **deixa o servidor rodando em segundo plano** quando a janela fecha cedo ou há atividade (`desktop.py`, mensagens "deixei o Hook's rodando"). Resultado: com a beta.1 ainda rodando, o atalho da beta.2 abria uma janela **na beta.1** (que não tem o Layout de reação), sem nenhum aviso. A tela não mostrava qual build era.

**Reprodução (24/11):** servidor do commit `385948571a` (beta.1) subido sobre uma pasta de dados; `desktop.launch()` do código da beta.2 apontou a janela para ele e `/api/state` respondeu `version: 0.20.0-beta.1`. Foi o comportamento observado, sem erro algum.
**Limite honesto:** não temos acesso ao PC do usuário; a reprodução prova que o defeito existe e produz exatamente o sintoma relatado, não que foi isso que aconteceu lá. O diagnóstico novo (`DIAGNOSTICO_WINDOWS.bat`) responde isso no PC dele (linha "Servidor… É OUTRA INSTALAÇÃO").

## Por que os testes não pegaram
Todos os testes anteriores subiam o app a partir da **árvore de desenvolvimento** com pasta de dados nova; nenhum testava (a) o ZIP extraído, (b) o atalho/lançador com outra versão viva, (c) se a versão exibida bate com o pacote, (d) se os recursos declarados estão no produto instalado.

## Correções (branch `fix/windows-layouts-integration`)
1. **Lançador:** `servidor.json` agora grava versão, commit e pasta de instalação; `launch()` só reaproveita servidor da MESMA instalação. Outra instalação: se ociosa, **pergunta** (Sim/Não) antes de encerrá-la; se ocupada (gravando/analisando/exportando) **não encerra** e explica; nunca abre a janela na versão errada. Testes em `tests/test_desktop.py::OtherInstallTests`.
2. **Rastreabilidade:** rodapé mostra versão · commit · id da tela (`<meta name="ui-build">` gerado no build); clique abre o **diagnóstico** (`/api/diagnostico`, sem tokens); a tela avisa se a página carregada é de outra versão (Ctrl+F5).
3. **Integridade funcional:** `liveclips/funcionalidades.py` — recursos declarados em `BUILD_INFO.json` (`funcionalidades_esperadas`) são verificados no produto instalado (catálogo = 8 layouts/3 principais, controles no HTML distribuído, rotas, render dos 8 layouts no FFmpeg local). Entra no **autoteste** como passo crítico.
4. **Bloqueio de release:** `tools/empacotar_release.py` aborta se a interface distribuída ≠ build de `ui/`, se o id da tela não confere ou se qualquer recurso declarado falha. Gera `ESTADO_DO_RELEASE.json` separando: build produzido / testes Linux / Windows automatizado / Windows físico / aprovada (os três últimos sempre `false` até haver evidência).
5. **Testes do produto distribuído:** `tools/testar_pacote.py` extrai o ZIP numa pasta limpa, semeia dados com o código do pacote, sobe o servidor com `python -I`, roda o e2e de interface (inclui os 8 layouts), prévia que muda, exportação (1080×1920, 1 áudio, webcam animada com conteúdo parado, cena na exportação), reinício do servidor (persistência).
6. **Instalador:** `winget` só depois de pergunta Sim/Não (Python e FFmpeg), dizendo o que instala, que usa internet e que altera o Windows; recusa não instala nada.
7. **`DIAGNOSTICO_WINDOWS.bat`:** versão, pasta, commit, Python, FFmpeg, integridade pelo manifesto, filtros, GPU real, 8 layouts, servidor/porta/processos, erros recentes — local, revisável, nada enviado.
8. **CI Windows sob demanda** (`.github/workflows/windows.yml`, só `workflow_dispatch`): **não executado**; custo: minutos Windows contam em dobro em repositório privado.

## Como impedir que volte
Gate de empacotamento + testes do produto distribuído + autoteste crítico + identidade no servidor/rodapé. Regra: nada é "pronto" sem passar por `tools/testar_pacote.py` sobre o ZIP.

## Pendente / não validado
Windows físico e automatizado, GPU, vídeo real. A reprodução do defeito foi em Linux (comportamento do lançador é independente de SO; a caixa Sim/Não usa `MessageBoxW`, que não foi exercitada fora do Windows).
