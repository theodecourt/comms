"""Claude Code's own session registry, read as an outside observer.

Claude Code writes one file per live session under ~/.claude/sessions/, named
after the pid and holding `sessionId`, `status`, `name` and `cwd`, and removes
it when the session exits. `presence.open()` already records
CLAUDE_CODE_SESSION_ID, so the two sides join on `sessionId` with no new
plumbing — measured 2026-08-11 against the three real sessions on this machine.

Why this exists: comms used to infer liveness from its own heartbeat, which
only the doorbell writes. An agent that was alive and working but had not
re-armed `comms wait` looked exactly like an agent that had died (observed
twice in one session on 2026-08-11). The registry answers the two questions
separately — is the process there, and what does the harness say it is doing.

Everything here is read-only and optional. Every function degrades to "unknown"
rather than raising, so comms keeps working unchanged where the registry is
absent: another terminal, a future layout, a machine without it.
"""
import os
from comms import paths, store


def sessions() -> dict:
    """sessionId -> registry record, for every live session.

    Returns {} when the registry cannot be read at all, which callers must read
    as "unknown", never as "nobody is alive"."""
    out = {}
    try:
        names = os.listdir(paths.sessions_dir())
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        rec = store.read_json(os.path.join(paths.sessions_dir(), name))
        if not isinstance(rec, dict):
            continue
        sid = rec.get("sessionId")
        if sid:
            out[sid] = rec
    return out


def pid_alive(pid) -> bool:
    """Signal 0 probes for existence without touching the process.

    A process that exists but belongs to another user raises PermissionError —
    that is still a live process, so it counts as alive."""
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False
    return True
