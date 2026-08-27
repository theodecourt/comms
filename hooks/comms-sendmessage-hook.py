#!/usr/bin/env python3
"""PostToolUse(SendMessage) → registro no board.

Grava o FATO de um envio nativo, nunca o corpo: o texto trafega pelo
transporte nativo e o board é testemunha. Sai 0 em qualquer erro, porque um
hook que levanta exceção estraga o turno do usuário.
"""
import json, os, re, sys

REF = re.compile(r"\s*\[[0-9a-fA-F]+\]\s*$")

def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name") != "SendMessage":
        return 0

    to_raw = (event.get("tool_input") or {}).get("to") or ""
    # O ref é efêmero e não faz parte da identidade — sem removê-lo nenhum
    # destinatário casaria e todo envio viraria "fora do board".
    to_name = REF.sub("", to_raw).strip()
    if not to_name:
        return 0

    response = event.get("tool_response") or {}
    delivered = bool(response.get("success"))
    msg_id = response.get("msg_id") or ""

    from comms import messages, presence
    entries = presence.read_all()

    session = event.get("session_id") or ""
    sender = os.environ.get("COMMS_ALIAS") or next(
        (e["alias"] for e in entries if e.get("session") == session), None)
    if sender is None:
        return 0        # remetente nunca entrou no board

    alias = next((e["alias"] for e in entries
                  if e.get("native_name") == to_name), None)

    messages.record_native(sender, to_name, alias=alias,
                           delivered=delivered, msg_id=msg_id)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:
        sys.exit(0)
