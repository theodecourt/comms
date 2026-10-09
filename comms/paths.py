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

def projects_dir() -> str:
    """Where Claude Code keeps one transcript per session — read, never written.

    Bound to COMMS_ROOT for the same reason sessions_dir() is: a test that read
    the real transcripts would depend on which sessions this machine happens to
    have."""
    explicit = os.environ.get("COMMS_PROJECTS_DIR")
    if explicit:
        return explicit
    if os.environ.get("COMMS_ROOT"):
        return os.path.join(os.environ["COMMS_ROOT"], "projects")
    return os.path.expanduser("~/.claude/projects")

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

def assignments_dir() -> str:
    """Kept apart from presence on purpose: SessionEnd deletes the presence
    row, and an assignment has to outlive the session that received it."""
    return os.path.join(root(), "assignments")

def assignment_file(alias: str) -> str:
    return os.path.join(assignments_dir(), f"{alias}.json")

def tasks_root() -> str:
    """One folder per task, in the Obsidian vault so a human reads them where
    the rest of the notes are.

    COMMS_ROOT drags this with it, as it does sessions_dir(): a test that set
    up a fake board and forgot COMMS_TASKS_DIR must land in its tmpdir, never
    in the real vault — which is a git repo that gets pushed."""
    explicit = os.environ.get("COMMS_TASKS_DIR")
    if explicit:
        return explicit
    if os.environ.get("COMMS_ROOT"):
        return os.path.join(os.environ["COMMS_ROOT"], "tasks")
    return os.path.expanduser("~/obsidian-segura/tasks")

def templates_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "templates")
