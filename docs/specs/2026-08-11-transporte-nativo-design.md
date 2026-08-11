# Design — transporte nativo cross-session

**Data:** 2026-08-11 · **Status:** aguardando revisão do Theo antes do plano.

## Objetivo

Passar o envio de mensagens entre agentes para o `SendMessage` nativo do Claude
Code (v2.1.224), mantendo o board do comms como dono da identidade, da política
e do registro.

## Por que agora

O doorbell existe por um motivo só: acordar um peer ocioso. Ele é um processo de
fundo de vida longa, e em 2026-08-11 três sessões independentes — `ai`, `setup`,
`builder` — o viram ser ceifado, sempre com saída vazia. O `ai` leu o silêncio
como "pare" e ficou horas surdo enquanto o board ainda o listava como
disponível.

O transporte nativo acorda um peer **sem processo de fundo nenhum**. A classe
inteira de falha desaparece por construção, em vez de ganhar mais uma regra
para sobreviver a ela.

## Fatos medidos (não suposições)

Tudo abaixo foi verificado nesta máquina em 2026-08-11.

| Fato | Como foi verificado |
|---|---|
| `SendMessage` acorda sessão ociosa sem input humano | duas vezes, com sessão descartável |
| Sessão morta → erro honesto, sem falso sucesso | envio para sessão encerrada |
| Endereçar exige `[ref]` de um `ListAgents` fresco | nome puro foi recusado |
| Não há fila: destino fora do ar é recusado, não enfileirado | mesmo teste acima |
| `PostToolUse` dispara para `SendMessage` | sessão headless com `--settings` próprio |
| Payload traz `tool_input{to,summary,message}`, `session_id`, `cwd`, `tool_response{success,msg_id}` | idem |
| O hook dispara também na tentativa que FALHA | a 1ª tentativa usou nome puro e falhou; a 2ª, com ref, funcionou |

## Decisões (Theo, 2026-08-11)

1. **O registro guarda o fato, não o corpo** — para mensagem que foi pelo
   nativo. `comms log` mostra "orch → builder, 14:32, via nativo"; o texto
   trafega só pelo nativo. Mensagem que cai no fallback é um `comms post`
   comum e continua carregando o corpo, como sempre: ali o board é o
   transporte, não a testemunha.
2. **Quem grava é um hook**, não o agente. Registro que depende de disciplina
   falha justamente nos dias corridos.
3. **Roteamento: nativo sempre; comms quando o nativo falhar.** Regra única e
   autoverificável — o próprio `tool_response` diz quando caiu.
4. **O fallback é do agente**, que lê o erro e roda `comms post`.

Sobre a 4: recomendei que o hook fizesse o fallback sozinho e o Theo preferiu
manter no agente. Mitigação que não contraria a escolha: **o hook registra
também a tentativa falha, marcada como não entregue** — se o agente esquecer o
fallback, o esquecimento fica visível no log em vez de sumir.

## Arquitetura

O nativo vira transporte. O comms vira identidade, política e registro.

```
orch                                        builder
 │                                             │
 ├── SendMessage(to: "builder [ref]") ────────►│   (acorda, sem processo de fundo)
 │        │
 │        └── PostToolUse ──► hook ──► log do board (fato, sem corpo)
 │
 └── se success:false ──► comms post ──► inbox do alias (corpo, durável)
                                             │
                                             └── doorbell acorda (caminho de reserva)
```

## Componentes

### 1. Hook `PostToolUse` com matcher `SendMessage`

**Faz:** lê o payload no stdin, resolve remetente e destinatário, grava uma linha
de fato. Nunca falha de forma barulhenta — um hook que quebra atrapalha o turno
do agente.

- **Remetente:** `COMMS_ALIAS`, ou `session_id` → entrada de presence.
- **Destinatário:** `tool_input.to` é **nome nativo**, não alias, e pode vir com
  sufixo `" [ref]"` — precisa ser removido antes de casar. O mapeamento nome
  nativo → alias sai do join `presence.session` ↔ `sessionId` do registro de
  sessões, que já existe desde 2026-08-11.
- **Destinatário fora do board:** não existe alias nem log do outro lado, então
  o fato é gravado **só no log do remetente**, com o nome nativo como veio e
  marcado como fora do board. O log continua honesto em vez de omitir.
- **Entregue ou não:** `tool_response.success` decide. Ambos são gravados; só o
  entregue conta como comunicação de fato.

**Formato:** mesma `log/<alias>.jsonl` de hoje, com `kind: "native"`, sem `body`,
e com `delivered: true|false` e `msg_id`. Escreve no log dos **dois** lados —
sem isso o remetente não consegue auditar o que mandou, que é metade da pergunta
"quem falou com quem".

### 2. `comms who` mostra o nome nativo

É o que fecha o caminho alias → `SendMessage`. Custo zero de plumbing: o join já
existe e o registro nativo já carrega `name`. Para sessão spawnada, alias e nome
nativo já são idênticos por causa do `claude -n`.

O agente ainda precisa de um `ListAgents` fresco para obter o `[ref]`. O board
diz *quem* endereçar; o `ListAgents` diz *como*. Nenhum endereço é persistido.

### 3. Doorbell rebaixado, não removido

Continua servindo o que o nativo não faz: fallbacks, broadcast, e posts vindos
de script ou hook. Deixa de ser crítico — um agente surdo continua recebendo
mensagem nativa. É isso que torna o incidente do `ai` irrepetível.

### 4. A skill muda em três pontos

- Regra de transporte: nativo sempre, `comms post` quando `success:false`.
- `CAMPAINHA surda` deixa de significar "não recebe" e passa a significar "não é
  acordada pelo caminho do comms". Sem essa correção a skill passa a mentir.
- Como endereçar: `comms who` para escolher, `ListAgents` para obter o ref.

## Casos de borda

- **Janela de handoff.** O alias sobrevive, a sessão não. O nativo falha
  (sessão velha morreu, nova ainda não subiu) → o agente cai para o `comms
  post` → o sucessor lê a inbox. O fallback cobre exatamente o pior momento.
- **Duas tentativas, um envio.** O hook dispara nas duas; filtrar por `success`
  evita mensagem fantasma no log.
- **Peer fora do comms.** `SendMessage` funciona; o board registra o fato com o
  nome nativo e sem alias.
- **Hook ausente.** Sem o hook o transporte continua funcionando e só o registro
  se perde. Degradação aceitável: mensagem entregue vale mais que log completo.

## Verificação

- Testes de unidade do hook: resolução de remetente e destinatário, remoção do
  sufixo `[ref]`, filtro por `success`, destinatário fora do board, payload
  malformado (não pode levantar exceção).
- Teste de integração: alimentar o hook com o payload **real** capturado hoje,
  em vez de um payload inventado.
- Manual, uma vez: `orch` manda para `builder` pelo nativo e o fato aparece no
  `comms log` dos dois lados.

Isolamento obrigatório: `COMMS_ROOT` em tmpdir com `tearDown`, como toda a
suíte. O `COMMS_ROOT` já arrasta o diretório de sessões junto.

## Fora de escopo

- Broadcast pelo nativo (não existe lá; continua no comms).
- Mapa alias→endereço persistido — o `[ref]` é efêmero por natureza.
- Remover o doorbell.
- Ownership de working copy — item separado do feedback do Theo, e a chave certa
  ali é repo + branch, não diretório.

## Risco aberto

A causa da ceifa do doorbell continua sem diagnóstico, e são **pelo menos duas**:
uma capturável (SIGTERM/SIGHUP, agora tratada e visível) e a do exit 144, que não
passa pelo handler. Este desenho não a resolve — ele torna o doorbell não
crítico, que é o que importa na prática. Registro em
`scratchpad/2026-08-11-doorbell-morte-silenciosa.md`.
