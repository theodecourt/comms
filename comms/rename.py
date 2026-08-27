"""Changing an alias means moving everything keyed by it, atomically enough
that a half-done rename cannot strand a session between two identities."""
import os
from comms import paths, presence, store


class RenameRefused(Exception):
    """Carries the reason, which the CLI prints verbatim."""


def _orphan_delegation(alias: str) -> bool:
    """A grant left behind by an alias that is no longer on the board.

    Renaming into one would hand this session authority granted to somebody
    else — the only way an agent could widen its own scope without a human,
    which is the thing the delegation block exists to prevent."""
    return (os.path.exists(paths.delegation_file(alias))
            and not os.path.exists(paths.presence_file(alias)))


def _move(src: str, dst: str) -> None:
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)


def run(old: str, new: str) -> str:
    """Move `old` to `new` and return `new`. Raises RenameRefused, having
    changed nothing, when the move would be unsafe."""
    if not presence.valid_alias(new):
        raise RenameRefused(
            f"alias inválido: {new!r} — use minúsculas, dígitos e hífen")
    if new == old:
        raise RenameRefused(f"{old} já é o alias desta sessão")
    if not os.path.exists(paths.presence_file(old)):
        raise RenameRefused(f"{old} não está no board")
    if os.path.exists(paths.presence_file(new)):
        raise RenameRefused(
            f"{new} já está no board — o alias é a identidade, e duas sessões "
            f"não podem dividir uma")
    if _orphan_delegation(new):
        raise RenameRefused(
            f"{new} tem uma delegação deixada por uma sessão que fechou. "
            f"Renomear para lá herdaria autoridade concedida a outro agente — "
            f"peça ao Theo `comms revoke {new}` se ela não vale mais")

    # Presence last: while it is still under the old name the session is
    # findable, and every guard above has already passed. A crash between the
    # moves leaves mail and history under the new name and the entry under the
    # old, which `comms open <new>` repairs — the reverse would leave a session
    # on the board with its inbox somewhere else.
    _move(paths.inbox_dir(old), paths.inbox_dir(new))
    _move(paths.log_file(old), paths.log_file(new))

    # The grant names its holder inside the record, not only in the filename —
    # `delegation.read_all()` keys on the field. Moving the file alone would
    # leave the board advertising authority for an alias nobody holds, and the
    # renamed session unable to use the grant that followed it.
    grant = store.read_json(paths.delegation_file(old))
    if grant is not None:
        grant["alias"] = new
        store.write_json(paths.delegation_file(new), grant)
        os.unlink(paths.delegation_file(old))

    entry = store.read_json(paths.presence_file(old)) or {}
    entry["alias"] = new
    entry["role"] = presence.role_for(new)
    store.write_json(paths.presence_file(new), entry)
    os.unlink(paths.presence_file(old))
    return new
