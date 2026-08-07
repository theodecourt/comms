"""Presence has two owners: the agent supplies alias/note, hooks and the
doorbell supply status/last_seen. Staleness is computed, never stored."""
import os, re, time
from comms import paths, store

POLL_INTERVAL = 2
TTL = 3 * POLL_INTERVAL
VALID_STATUSES = ("working", "idle", "waiting-human")
_ALIAS_RE = re.compile(r"^[a-z0-9-]+$")

def valid_alias(alias: str) -> bool:
    return bool(alias) and bool(_ALIAS_RE.match(alias))

def role_for(alias: str) -> str:
    return "orchestrator" if alias == "orch" else "builder"

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
    out = []
    try:
        names = sorted(os.listdir(paths.presence_dir()))
    except OSError:
        return out
    now = time.time()
    for name in names:
        if not name.endswith(".json"):
            continue
        entry = store.read_json(os.path.join(paths.presence_dir(), name))
        if entry is None:
            continue
        entry["stale"] = (now - entry.get("last_seen", 0)) > TTL
        out.append(entry)
    return out

def whoami():
    alias = os.environ.get("COMMS_ALIAS")
    if alias:
        return alias
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session:
        return None
    for entry in read_all():
        if entry.get("session") == session:
            return entry["alias"]
    return None
