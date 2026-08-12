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

COMMS_ALIAS=front comms close >/dev/null
WHO_AFTER=$(comms who) || fail "comms who falhou depois do close"
echo "$WHO_AFTER" | grep -q front && fail "front continuou no who após close"
echo "E2E OK"
