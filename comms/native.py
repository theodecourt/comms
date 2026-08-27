"""Claude Code's own session registry, read as an outside observer.

Claude Code writes one file per live session under ~/.claude/sessions/, named
after the pid and holding `sessionId`, `status`, `name` and `cwd`, and removes
it when the session exits. `presence.open()` already records
CLAUDE_CODE_SESSION_ID, so the two sides join on `sessionId` with no new
plumbing — measured 2026-08-11 against the three real sessions on this machine.

Why this exists: comms used to infer liveness from its own heartbeat, written
by a background `comms wait` loop. An agent that was alive and working but had
not re-armed that loop looked exactly like an agent that had died (observed
twice in one session on 2026-08-11). The registry answers the question directly
— is the process there — which is also what let that loop be deleted outright
rather than repaired.

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


def named_by_a_human(session_id: str) -> bool:
    """Whether this session's name was CHOSEN rather than derived.

    Claude Code gives every session a name. Left alone it derives one from the
    directory — `comms-16`, `segura-intelligence-cc` — which carries no
    intent and should not be built on. A name set by `claude -n` at launch or
    by `/rename` mid-session is a decision, and writes a `custom-title` record
    into the session's transcript. Measured 2026-08-12: 10 such records in a
    session spawned with `-n`, 9 in one the user renamed, 0 in a derived one.

    Reading the transcript rather than pattern-matching the name is the point —
    a derived name that happens to look chosen, or the reverse, would fool any
    heuristic, and this question decides what a spawned session is called.
    """
    if not session_id:
        return False
    import glob
    for path in glob.glob(os.path.join(paths.projects_dir(), "*",
                                       f"{session_id}.jsonl")):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"custom-title"' in line or '"customTitle"' in line:
                        return True
        except OSError:
            continue
    return False


def session_name(alias: str, parent_name: str = None,
                 parent_alias: str = None, parent_role: str = None) -> str:
    """What to call a session spawned as `alias` by a session named
    `parent_name`.

    A spawned session inherits its parent's name with the role marker swapped:
    `PROJETO-KB-ORCHESTRATOR` spawning `api` becomes `PROJETO-KB-api`. The
    project is the part worth carrying; the role is the part that changed.

    Only a marker we can PROVE belongs to the parent is stripped — its own
    alias or its own role, matched case-insensitively at the end. Guessing at a
    vocabulary of role-looking words would eventually eat a real project name:
    nothing distinguishes `-ORCHESTRATOR` from `-AUTOMATICO` except knowing
    that the first one is this session's own.

    With no parent name — the parent was never named, so its name carries no
    intent — the alias stands alone, which is what it did before.
    """
    if not parent_name:
        return alias
    base = parent_name
    for marker in (parent_alias, parent_role):
        if not marker:
            continue
        low, mark = base.lower(), marker.lower()
        if low == mark:
            # The parent's whole name is its own role — every session spawned
            # before names carried a project looks like this. There is nothing
            # to pass on, and `api-front` would be one role glued to another.
            base = ""
            break
        if low.endswith("-" + mark):
            base = base[: -(len(marker) + 1)]
            break
    return f"{base}-{alias}" if base else alias


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
