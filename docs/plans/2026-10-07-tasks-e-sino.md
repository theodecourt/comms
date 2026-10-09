# Plano — tasks compartilhadas e sino confiável

Spec: `docs/specs/2026-10-07-tasks-e-sino-design.md`. Aprovado pelo Theo em
2026-10-07 com estas decisões sobre as perguntas em aberto:

- Raiz das tasks: `~/obsidian-segura/tasks/` (sobrescrita por `COMMS_TASKS_DIR`;
  com `COMMS_ROOT` definido e sem `COMMS_TASKS_DIR`, cai em `$COMMS_ROOT/tasks`).
- `reachable` é tri-state: `True`/`False`/`None`, como `live`. Um booleano leria
  "registry ilegível" — que acontece sempre que um arquivo dele está no meio de
  uma escrita — como "inalcançável", e o sino piscaria.
- `SessionStart` entra no `EVENTS` do `install_hooks.py` (o Theo roda o
  instalador; `settings.json` não é tocado daqui).
- `assign` aceita `--resumo` opcional, que nomeia o arquivo da subtarefa.
- Sessão que entrou à mão (sem `COMMS_ALIAS`) é religada pelo pid do Claude,
  gravado no presence no `open`.
- Poda: 24 h (`presence.PRUNE_AFTER_SECONDS`).

## Medição (passo 0)

`/clear` troca o id da sessão — medido em 2026-10-07 numa sessão real: o mesmo
pid passou de um transcript `SessionStart:startup` para um novo, aberto por
`SessionStart:clear`; o registry (`~/.claude/sessions/<pid>.json`) foi
reescrito no lugar com o id novo, e `CLAUDE_CODE_SESSION_ID` nos processos
filhos também. `--resume` não foi medido.

## Tarefas (um commit cada)

0. Spec e este plano.
1. Hook: fallback por `COMMS_ALIAS` e por pid, religando `presence.session`,
   em todo evento. Não religa se a sessão antiga está comprovadamente viva.
2. `reachable` em `presence.read_all()`.
3. Poda de fantasmas em `comms who` e no `SessionStart`; `SessionStart` no
   instalador.
4. `comms who --json`.
5. `comms/tasks.py`, templates, `comms task new|assign|status`.
6. `comms task close`, reaproveitando a nota de vault do handoff.
7. Linha `📋` no hook.
8. SKILL.md, README, e2e.

Fora de escopo: bloqueio em `PreToolUse`, mudanças no agent-monitor, qualquer
processo que lance agentes ou crie worktrees.
