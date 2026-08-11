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
import json, os
from comms import paths


def sessions() -> dict:
    """sessionId -> registry record, for every live session.

    Returns {} both when the registry cannot be read at all AND when any one
    file in it fails to parse as JSON — callers must read either as "unknown",
    never as "nobody is alive". The second case matters if Claude Code's
    write of <pid>.json is not known to be atomic: a `comms who` landing
    mid-write would otherwise see a half-written file, skip only THAT record,
    and report every other session with full confidence — including treating
    the mid-write session itself as gone, since its absence from an otherwise
    "readable" registry would look like proof. One bad file has to cost the
    whole answer, not just its own row."""
    out = {}
    try:
        names = os.listdir(paths.sessions_dir())
    except OSError:
        return out
    degraded = False
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(paths.sessions_dir(), name)
        try:
            with open(path) as fh:
                rec = json.load(fh)
        except OSError:
            continue                  # vanished between listdir and open — not corruption
        except json.JSONDecodeError:
            degraded = True
            continue
        if not isinstance(rec, dict):
            continue
        sid = rec.get("sessionId")
        if sid:
            out[sid] = rec
    return {} if degraded else out


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


def liveness(pid):
    """Tri-state: True/False when `pid` is real, None when there is nothing to ask.

    A registry record missing `pid`, or holding something that is not one, is
    not evidence of death — it is a record with a gap in it, and the session
    it names may well still be there. Only a real pid that fails the kill(0)
    probe counts as dead; presence.read_all() must see that difference rather
    than have pid_alive's own `except TypeError/ValueError: False` blur it
    into "gone"."""
    try:
        int(pid)
    except (TypeError, ValueError):
        return None
    return pid_alive(pid)
