#!/usr/bin/env python3
"""Claude Code hook → comms presence. Never blocks, never fails: any error
exits 0 silently, because a raising hook would break the user's session."""
import json, os, sys

STATUS_BY_EVENT = {
    "UserPromptSubmit": "working",
    "Stop": "idle",
    "Notification": "waiting-human",
}

# Byte thresholds on the transcript, a proxy for context usage. Calibrate
# against real sessions — compaction and tool results distort the ratio.
# Transcript size as a proxy for context usage, because the model cannot read
# its own percentage. Calibrated 2026-08-10 against one real measurement: a
# 6.26 MB transcript sat at 56% context (`/context`), giving ~11.2 MB per 100%.
# The original 1.6/1.4 MB guesses were ~4x too low and fired on every turn of
# any long session — an alarm that always rings is an alarm nobody reads.
#
# One data point is a weak basis and the relationship is not truly linear
# (compaction and dropped tool results distort it). Re-measure when a session
# next reaches a known percentage, and prefer erring early over erring late.
BYTES_PER_PERCENT = 6_260_000 / 56
WARN_BYTES = {
    "orchestrator": int(BYTES_PER_PERCENT * 80),   # ~8.9 MB
    "builder": int(BYTES_PER_PERCENT * 70),        # ~7.8 MB
}

def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    if name in ("UserPromptSubmit", "SessionStart"):
        # Mail on the comms path — a broadcast, or a fallback from a failed
        # native send — used to be announced by the doorbell: a background
        # process whose exit woke the session. That cost a wake-up every time
        # its bound elapsed, whether or not anything had arrived, and it was
        # reaped without warning besides. Anything urgent now travels by
        # native SendMessage, which wakes a peer with no background process at
        # all, so the comms path no longer needs one either: it can wait for
        # the agent's next turn, which is exactly when this hook runs.
        from comms import messages
        # peek: counting must not consume. The agent still has to run
        # `comms inbox` to read, and that is what marks the mail as seen.
        waiting = messages.inbox(alias, peek=True)
        if waiting:
            senders = ", ".join(sorted({m["from"] for m in waiting}))
            plural = "ns" if len(waiting) != 1 else "m"
            print(f"✉ {len(waiting)} mensage{plural} no comms, de {senders} "
                  f"— rode `comms inbox`")

    if name == "UserPromptSubmit":
        # Claude Code only forwards a hook's stdout into the model's context
        # on UserPromptSubmit (and SessionStart) — printing this on Stop
        # would be silently dropped, so the warning has to fire here, at the
        # start of the turn it should affect.
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
