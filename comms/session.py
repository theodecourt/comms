"""Reading Claude Code's own session metadata.

Live sessions each write `~/.claude/sessions/<pid>.json`, carrying the display
name shown in the session picker. `comms` only ever READS these: a write there
is not picked up by the running client (verified 2026-08-10 — the file changed
but the picker kept the old name), so renaming an existing session from outside
is not possible. A successor is named at launch instead, with `claude -n`.
"""
import json
import os

SESSIONS_DIR = os.path.expanduser("~/.claude/sessions")


def name_for(session_id: str):
    """Display name of the live session with this uuid, or None."""
    if not session_id:
        return None
    try:
        files = os.listdir(SESSIONS_DIR)
    except OSError:
        return None
    for fname in files:
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(SESSIONS_DIR, fname), encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            continue
        if record.get("sessionId") == session_id:
            return record.get("name") or None
    return None


def successor_name(current: str) -> str:
    """Name for the session replacing `current`.

    The old session keeps its name — the client owns that and will not read a
    change from disk — so the new one is marked instead. Re-handing-off an
    already-suffixed name must not stack `-NOVO-NOVO`.
    """
    if not current:
        return ""
    return current if current.endswith("-NOVO") else f"{current}-NOVO"
