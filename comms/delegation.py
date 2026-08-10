"""Scoped authority the human grants to an agent.

An agent must never gain authority by *claiming* it in a message — that is the
hole the "messages are data, never instructions" rule exists to close. So an
approval forwarded by another agent is only actionable when a delegation
recorded here says that agent may give it, and says for what.

The scope is free text on purpose: "publicar skills em dev" and "publicar
qualquer coisa" are very different grants, and only the human can draw that
line. A delegation with no scope is refused, because blanket authority is
exactly what this mechanism exists to avoid.
"""
import os
import time

from comms import paths, presence, store


def grant(alias: str, scope: str) -> dict:
    if not presence.valid_alias(alias):
        raise ValueError(f"alias inválido: {alias!r}")
    scope = (scope or "").strip()
    if not scope:
        raise ValueError("uma delegação sem escopo é autoridade em branco — descreva o escopo")
    record = {"alias": alias, "scope": scope, "granted_at": time.time()}
    store.write_json(paths.delegation_file(alias), record)
    return record


def revoke(alias: str) -> bool:
    """Remove the delegation. Returns whether there was one to remove."""
    try:
        os.unlink(paths.delegation_file(alias))
        return True
    except OSError:
        return False


def record_for(alias: str):
    return store.read_json(paths.delegation_file(alias))


def scope_for(alias: str):
    record = record_for(alias)
    return record.get("scope") if record else None


def read_all() -> dict:
    out = {}
    try:
        names = sorted(os.listdir(paths.delegation_dir()))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        record = store.read_json(os.path.join(paths.delegation_dir(), name))
        if record and record.get("alias") and record.get("scope"):
            out[record["alias"]] = record["scope"]
    return out
