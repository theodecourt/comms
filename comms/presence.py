"""Presence has two owners: the agent supplies alias/note, hooks supply
status/last_seen."""
import os, re, time
from comms import paths, store

VALID_STATUSES = ("working", "idle", "waiting-human")
_ALIAS_RE = re.compile(r"^[a-z0-9-]+$")

def valid_alias(alias: str) -> bool:
    return bool(alias) and bool(_ALIAS_RE.match(alias))

def role_for(alias: str) -> str:
    """`orch`, or any `orch-<something>`, orchestrates. Everyone else builds.

    An alias says the role and nothing else — `orch`, `builder-1`, `builder-2`.
    What a builder is working on goes in its `--note`, and which repo it sits
    in is already visible everywhere the alias is shown. A board can hold more
    than one orchestrator, which is why the prefixed form exists.

    The role is not decoration: the context-limit hook warns an orchestrator at
    80% and a builder at 70%, on the reasoning that an orchestrator's context is
    the scarce thing. An `orch-front` classified as a builder would be pushed
    into a handoff earlier than it should be.

    The hyphen carries the rule — without it `orchid` would orchestrate."""
    return "orchestrator" if alias == "orch" or alias.startswith("orch-") \
        else "builder"

def open(alias, note="", role=None, session=None, cwd=None, terminal=None) -> dict:
    store.ensure_dirs(alias)
    entry = {
        "alias": alias,
        "role": role or role_for(alias),
        "note": note,
        "cwd": cwd or os.getcwd(),
        "session": session or os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
        "terminal": terminal or "",
        "status": "idle",
        "last_seen": time.time(),
    }
    store.write_json(paths.presence_file(alias), entry)
    return entry

def touch(alias: str, status: str = None) -> None:
    """Silent when the alias is unknown — hooks fire for sessions that never
    joined the board, and a hook must never fail."""
    entry = store.read_json(paths.presence_file(alias))
    if entry is None:
        return
    if status in VALID_STATUSES:
        entry["status"] = status
    entry["last_seen"] = time.time()
    store.write_json(paths.presence_file(alias), entry)

def close(alias: str) -> None:
    try:
        os.unlink(paths.presence_file(alias))
    except OSError:
        pass

def read_all() -> list:
    """Every board entry, enriched with whether its process is still there.

    `live` comes from Claude Code's own session registry, not from a heartbeat
    of ours. There is no staleness any more: it used to mean "the doorbell is
    not running", and with the doorbell gone it would have meant nothing while
    still looking like a verdict.

    `live` is None whenever it genuinely cannot be known, and no caller may
    read None as False — guessing "dead" would evict a healthy agent."""
    out = []
    try:
        names = sorted(os.listdir(paths.presence_dir()))
    except OSError:
        return out
    from comms import native
    registry = native.sessions()
    for name in names:
        if not name.endswith(".json"):
            continue
        entry = store.read_json(os.path.join(paths.presence_dir(), name))
        if entry is None:
            continue
        session = entry.get("session")
        record = registry.get(session) if session else None
        if record is not None:
            entry["live"] = native.liveness(record.get("pid"))
            entry["native_status"] = record.get("status")
            entry["native_name"] = record.get("name") or None
        else:
            # Absent registry, or an agent that joined without
            # CLAUDE_CODE_SESSION_ID: unknown, not dead. Only a readable
            # registry that does not list a known session proves it is gone.
            entry["live"] = False if (registry and session) else None
            entry["native_status"] = None
            entry["native_name"] = None
        out.append(entry)
    return out

def whoami():
    """This session's alias, or None.

    COMMS_ALIAS is trusted only while it still names a row on the board. The
    variable is frozen at spawn time and cannot be updated from outside the
    process, so after a rename — or a close — it names an identity that no
    longer exists, and a session that believed it would post as a ghost. The
    session id survives both, so it is what the fallback matches on."""
    alias = os.environ.get("COMMS_ALIAS")
    if alias and os.path.exists(paths.presence_file(alias)):
        return alias
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session:
        return None
    for entry in read_all():
        if entry.get("session") == session:
            return entry["alias"]
    return None
