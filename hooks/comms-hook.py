#!/usr/bin/env python3
"""Claude Code hook → comms presence. Never blocks, never fails: any error
exits 0 silently, because a raising hook would break the user's session."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATUS_BY_EVENT = {
    "UserPromptSubmit": "working",
    "Stop": "idle",
    "Notification": "waiting-human",
}

# Byte thresholds on the transcript, a proxy for context usage. Calibrate
# against real sessions — compaction and tool results distort the ratio.
WARN_BYTES = {"orchestrator": 1_600_000, "builder": 1_400_000}

def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    name = event.get("hook_event_name") or ""
    session = event.get("session_id") or ""
    if not name or not session:
        return 0

    from comms import presence

    alias = None
    for entry in presence.read_all():
        if entry.get("session") == session:
            alias = entry["alias"]
            break
    if alias is None:
        return 0        # session never joined the board

    if name == "SessionEnd":
        presence.close(alias)
        return 0

    status = STATUS_BY_EVENT.get(name)
    presence.touch(alias, status=status)

    if name == "Stop":
        transcript = event.get("transcript_path") or ""
        role = presence.role_for(alias)
        limit = WARN_BYTES.get(role, WARN_BYTES["builder"])
        try:
            if transcript and os.path.getsize(transcript) > limit:
                if role == "orchestrator":
                    print("⚠ contexto alto — avise o Theo e proponha `comms handoff`")
                else:
                    print("⚠ contexto alto — termine a tarefa atual e não aceite nova")
        except OSError:
            pass
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:
        sys.exit(0)
