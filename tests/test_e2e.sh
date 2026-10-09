#!/usr/bin/env bash
set -euo pipefail
export COMMS_ROOT="$(mktemp -d)"
trap 'rm -rf "$COMMS_ROOT"' EXIT
fail() { echo "FALHOU: $1"; exit 1; }

FRONT_SESSION="sess-e2e-front"
comms open orch --note "coordenando" >/dev/null
CLAUDE_CODE_SESSION_ID="$FRONT_SESSION" comms open front --note "disponível" >/dev/null
WHO=$(comms who) || fail "comms who falhou após open"
echo "$WHO" | grep -q orch  || fail "orch não apareceu no who"
echo "$WHO" | grep -q front || fail "front não apareceu no who"

COMMS_ALIAS=orch comms post --to front "implementa a fase 1" >/dev/null

# O aviso substituiu a campainha. Não há processo de fundo para esperar: o hook
# anuncia a inbox no turno seguinte, e é a única via pela qual o Claude Code
# injeta saída de hook no modelo.
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/comms-hook.py"
NOTICE=$(printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","cwd":"/tmp","transcript_path":""}' \
         "$FRONT_SESSION" | python3 "$HOOK")
echo "$NOTICE" | grep -q "comms inbox" || fail "hook não anunciou a mensagem pendente"
echo "$NOTICE" | grep -q "orch"        || fail "aviso não disse de quem era"

# anunciar não pode consumir: quem consome é o `comms inbox` do agente
COMMS_ALIAS=front comms inbox --peek | grep -q "implementa a fase 1" \
  || fail "o aviso consumiu a mensagem"

COMMS_ALIAS=front comms inbox | grep -q "implementa a fase 1" || fail "mensagem não chegou"
COMMS_ALIAS=front comms inbox | grep -q "sem mensagens"      || fail "inbox não consumiu"
COMMS_ALIAS=front comms log   | grep -q "implementa a fase 1" || fail "log não guardou"

# Tarefa: atribuída ao alias, anunciada pelo hook, liberada no close.
export COMMS_TASKS_DIR="$COMMS_ROOT/tasks" COMMS_VAULT="$COMMS_ROOT/vault"
comms task new "Funil de vendas" >/dev/null || fail "task new falhou"
comms task assign front funil-de-vendas --subtask 01 --resumo "endpoint" >/dev/null \
  || fail "task assign falhou"
TASK_NOTICE=$(printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","cwd":"/tmp","transcript_path":""}' \
         "$FRONT_SESSION" | python3 "$HOOK")
echo "$TASK_NOTICE" | grep -q "📋 .*subtarefa 01" || fail "hook não anunciou a tarefa"
comms task status funil-de-vendas | grep -q "front" || fail "status não mostrou o dono"
comms task close funil-de-vendas >/dev/null || fail "task close falhou"
ls "$COMMS_VAULT" | grep -q "Task" || fail "close não escreveu a nota"
[ -z "$(ls "$COMMS_ROOT/assignments")" ] || fail "close não apagou a atribuição"
comms who --json | python3 -c 'import json,sys; assert all("reachable" in r for r in json.load(sys.stdin))' \
  || fail "who --json sem reachable"

COMMS_ALIAS=front comms close >/dev/null
WHO_AFTER=$(comms who) || fail "comms who falhou depois do close"
echo "$WHO_AFTER" | grep -q front && fail "front continuou no who após close"
echo "E2E OK"
