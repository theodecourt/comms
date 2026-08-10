"""Every filesystem location lives here. Nothing else knows the layout."""
import os

def root() -> str:
    return os.environ.get("COMMS_ROOT") or os.path.expanduser("~/.claude/comms")

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
