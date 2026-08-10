#!/usr/bin/env bash
set -euo pipefail
export COMMS_ROOT="$(mktemp -d)"
trap 'rm -rf "$COMMS_ROOT"' EXIT
fail() { echo "FALHOU: $1"; exit 1; }

comms open orch --note "coordenando" >/dev/null
comms open front --note "disponível" >/dev/null
WHO=$(comms who) || fail "comms who falhou após open"
echo "$WHO" | grep -q orch  || fail "orch não apareceu no who"
echo "$WHO" | grep -q front || fail "front não apareceu no who"

COMMS_ALIAS=front comms wait --interval 0.2 --max-seconds 10 > "$COMMS_ROOT/bell.txt" &
BELL=$!
sleep 0.5
COMMS_ALIAS=orch comms post --to front "implementa a fase 1" >/dev/null
wait $BELL || true
grep -q "DOORBELL: mail" "$COMMS_ROOT/bell.txt" || fail "campainha não tocou"

COMMS_ALIAS=front comms inbox | grep -q "implementa a fase 1" || fail "mensagem não chegou"
COMMS_ALIAS=front comms inbox | grep -q "sem mensagens"      || fail "inbox não consumiu"
COMMS_ALIAS=front comms log   | grep -q "implementa a fase 1" || fail "log não guardou"

COMMS_ALIAS=front comms close >/dev/null
WHO_AFTER=$(comms who) || fail "comms who falhou depois do close"
echo "$WHO_AFTER" | grep -q front && fail "front continuou no who após close"
echo "E2E OK"
