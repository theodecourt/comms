# Design — tasks compartilhadas e sino confiável

**Data:** 2026-10-07 · **Status:** rascunho, aguardando revisão do Theo antes do plano.

## Objetivo

Duas mudanças que andam juntas porque dependem da mesma coisa — o hook saber,
de forma durável, quem é cada sessão:

1. **Tasks.** Uma pasta por tarefa no vault, com um arquivo de estado dono do
   orch e um arquivo por subtarefa, para que um builder novo (no dia seguinte,
   depois de handoff ou compactação) saiba o que é dele sem ninguém repetir no
   prompt.
2. **Sino confiável.** O 🔔 significa "registrado no comms e alcançável". Hoje o
   registro pode caducar em silêncio e o sino continua aceso.

## Fora de escopo (decidido)

- Nenhum processo Python que lance agentes ou crie worktrees. O Claude já cria
  worktrees sozinho; o orch continua sendo quem decide o que lançar.
- Fila, limite de concorrência e detecção de travamento. Se a necessidade
  aparecer depois de usar tasks por uma semana, vira outro design (e é aí que o
  nome `orchd` faz sentido).
- Fallback automático do `SendMessage` — continua sendo do agente (decisão de
  2026-08-11).

## Parte 1 — Tasks

### Layout

```
~/obsidian-segura/tasks/<AAAA-MM-DD>-<slug>/
  TASK.md                  # só o orch escreve
  subtasks/
    01-<slug>.md           # só o dono da subtarefa escreve
    02-<slug>.md
```

`COMMS_TASKS_DIR` sobrescreve a raiz (testes nunca escrevem no vault real, como
`COMMS_VAULT` já faz). O código fica no vault? **Não**: worktrees ficam fora.

**Um escritor por arquivo.** Vários agentes anexando no mesmo markdown se
sobrescrevem; por isso `TASK.md` é do orch e cada subtarefa é de quem a possui.

O arquivo é nomeado pela **subtarefa**, não pelo agente: um builder que assume
no dia seguinte (mesmo alias ou `builder-back-2`) continua o mesmo arquivo.

### TASK.md

Objetivo e critérios de aceite; tabela de subtarefas (id, repo, resumo,
depende-de, dono, estado, branch, sha); log de decisões; bloqueios.

### Arquivo de subtarefa

Frontmatter com `status: todo|doing|blocked|done`, `branch`, `sha`; corpo livre
com o que foi feito, o que falta e perguntas. É a primeira coisa que o sucessor
lê.

### Atribuição durável

`~/.claude/comms/assignments/<alias>.json`:

```json
{"task": "<caminho da pasta>", "subtask": "01", "assigned_at": 0}
```

Mora **fora** do presence de propósito: o hook `SessionEnd` apaga a linha do
presence, e a atribuição precisa sobreviver a isso. Chave é o alias, não a
sessão, então handoff e retomada mantêm a tarefa.

### Comandos (todos de uma execução, sem processo de fundo)

| Comando | Faz |
|---|---|
| `comms task new "<nome>"` | cria a pasta e o `TASK.md` a partir de um template |
| `comms task assign <alias> <task> --subtask <id>` | grava a atribuição e o dono na tabela |
| `comms task status [<task>]` | imprime a tabela, lendo o frontmatter das subtarefas |
| `comms task close <task>` | escreve a nota de arquivo no vault (mesmo caminho do `--resumo` do handoff), apaga as atribuições, marca a task como fechada |

`status` lê o frontmatter dos arquivos de subtarefa e é a fonte da verdade; o
orch pode reescrever a tabela do `TASK.md` a partir dele.

### Como o agente fica sabendo

O hook (`UserPromptSubmit` e `SessionStart`) imprime uma linha quando o alias
tem atribuição:

`📋 <task> · subtarefa 01 → leia TASK.md e subtasks/01-<slug>.md`

Mesmo canal do `✉` de hoje, e pelo mesmo motivo: só `UserPromptSubmit` e
`SessionStart` chegam ao contexto do modelo. Sobrevive a compactação porque é
reimpresso a cada turno.

`comms spawn --briefing` continua sendo como o orch dá o contexto inicial; a
linha do hook é a rede de segurança. Agente já em execução recebe a tarefa por
`SendMessage` do orch.

### Skill

Um parágrafo novo em `open-comms`: se há linha `📋`, leia o `TASK.md` primeiro;
escreva só no arquivo da sua subtarefa; só o orch edita `TASK.md`; ao terminar,
marque `status: done` com branch e sha e avise o orch.

## Parte 2 — Sino confiável

### O que o sino diz

"Esta sessão está no board **e** o board consegue alcançá-la." Hoje só a
primeira metade é verdadeira de forma durável.

### Causas de sino mentiroso

1. **Hook identifica só por `session_id`.** `comms-hook.py` casa
   `entry.session == session_id` e sai em silêncio se não achar. Sessão
   retomada ou com id novo vira surda: sem `touch`, sem `✉`, estado congelado,
   e a linha continua no board. `whoami()` já tem fallback por `COMMS_ALIAS`; o
   hook não.
2. **Nada expira.** O presence só some no `SessionEnd`; terminal fechado ou
   processo morto deixa linha fantasma, e broadcast entrega na inbox dela.
3. **O sino é desenhado fora deste repo**, pelo agent-monitor (fork
   `theodecourt/agent-monitor`, branch `feat/theo/comms-role-no-titulo`).

### Mudanças neste repo

- **Hook com fallback e religação.** Se o `session_id` não casa, usar
  `COMMS_ALIAS` quando a linha existe e **atualizar `presence.session`** para o
  id novo. Passa a valer para todos os eventos, não só `SessionStart`.
- **Campo `reachable` por linha**, calculado em `presence.read_all()`:
  verdadeiro quando a linha existe, `live is not False` e a sessão atual está
  ligada à linha. `None` continua significando "não dá para saber", nunca
  "morto" — a regra de `native.py` não muda.
- **Poda de fantasmas.** `comms who` e o `SessionStart` removem linhas com
  `live is False` e `last_seen` acima de um limite (proposta: 24 h). A inbox e o
  log **não** são apagados. Linhas com `live is None` nunca são podadas.
- **`comms who --json`**, para o agent-monitor consumir `reachable` sem
  interpretar texto.

### Mudança no agent-monitor (outro repo)

Pintar 🔔 só quando `reachable` for verdadeiro, e apagar o sino quando deixar de
ser. **Antes de desenhar isto é preciso ler o código do agent-monitor**
(`~/segura/agent-monitor`): não está confirmado se ele hoje lê os arquivos de
presence direto ou outra coisa. O desenho acima assume que dá para ele ler
`comms who --json`.

### "Quem não tem sino não deve falar" — decisão aberta

O comms não consegue impedir o `SendMessage` nativo; só registra o fato depois
(`PostToolUse`). Para tornar a regra real seria preciso um hook `PreToolUse` em
`SendMessage` que **bloqueie** o envio quando o remetente não está no board ou
o destinatário está fora dele. Custo: bloqueia também conversa legítima com
sessão fora do comms. **Escolha do Theo:** (a) só avisar, (b) bloquear, (c) não
fazer — o log já marca `off_board`.

## Verificação

- Testes de unidade: hook com `session_id` novo religa pela `COMMS_ALIAS`;
  `reachable` nos três estados (vivo, morto, desconhecido); poda não toca linha
  desconhecida nem apaga inbox; atribuição sobrevive ao `SessionEnd`; `task
  close` apaga atribuições e escreve o arquivo; payload malformado nunca
  levanta.
- Teste de integração do hook com payload real capturado, como no design do
  transporte nativo.
- Manual, uma vez: rodar `/clear` numa sessão registrada e conferir que o `✉`
  e o `📋` continuam aparecendo; matar uma sessão com `kill -9` e conferir que o
  sino some e a linha é podada.
- `COMMS_ROOT` e `COMMS_TASKS_DIR` em tmpdir com `tearDown`.

## Perguntas em aberto

1. Ler o agent-monitor para confirmar de onde o sino tira o estado.
2. `PreToolUse` em `SendMessage`: avisar, bloquear ou nada.
3. Raiz das tasks: `~/obsidian-segura/tasks/` serve? (O arquivo de handoff vai
   para `~/obsidian-segura/claude-code-session-history`.)
4. Limite de poda: 24 h está bom?
5. Confirmar que `/clear` e `--resume` trocam o `session_id` — é a hipótese da
   causa 1 e nunca foi medida aqui.
