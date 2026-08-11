"""Every filesystem location lives here. Nothing else knows the layout."""
import os

def root() -> str:
    return os.environ.get("COMMS_ROOT") or os.path.expanduser("~/.claude/comms")

def sessions_dir() -> str:
    """Claude Code's own live-session registry — read, never written.

    A relocated board is a test or a sandbox, never the real machine layout, so
    COMMS_ROOT drags this path with it: pairing a fake board with the REAL
    registry would make results depend on which sessions happen to be open at
    the time. Binding it here rather than asking every setUp to remember a
    second variable is deliberate — the protection cannot be forgotten if
    there is nothing to remember. COMMS_SESSIONS_DIR still overrides both, for
    tests that need to populate a registry of their own."""
    explicit = os.environ.get("COMMS_SESSIONS_DIR")
    if explicit:
        return explicit
    if os.environ.get("COMMS_ROOT"):
        return os.path.join(os.environ["COMMS_ROOT"], "sessions")
    return os.path.expanduser("~/.claude/sessions")

def presence_dir() -> str:
    return os.path.join(root(), "presence")

def presence_file(alias: str) -> str:
    return os.path.join(presence_dir(), f"{alias}.json")

def inbox_dir(alias: str) -> str:
    return os.path.join(root(), "inbox", alias)

def log_file(alias: str) -> str:
    return os.path.join(root(), "log", f"{alias}.jsonl")

def delegation_dir() -> str:
    return os.path.join(root(), "delegations")

def delegation_file(alias: str) -> str:
    return os.path.join(delegation_dir(), f"{alias}.json")
