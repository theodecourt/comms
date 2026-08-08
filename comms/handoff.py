"""Replace a session that is running out of context, keeping its alias."""
import os
from comms import messages, presence

def doc_path(cwd: str, alias: str, stamp: str) -> str:
    return os.path.join(cwd, "scratchpad", f"{stamp}-handoff-{alias}.md")

def write_doc(path: str, alias: str, note: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(f"# Handoff — {alias}\n\n")
        fh.write(f"**Nota da sessão anterior:** {note}\n\n")
        fh.write("## Estado\n\n")
        fh.write(body.rstrip() + "\n")

def run(alias: str, body: str, stamp: str, spawn_fn=None) -> str:
    entry = next((e for e in presence.read_all() if e["alias"] == alias), None)
    if entry is None:
        print(f"{alias} não está no board")
        raise SystemExit(2)
    cwd = entry.get("cwd") or os.getcwd()
    path = doc_path(cwd, alias, stamp)
    write_doc(path, alias, entry.get("note", ""), body)

    briefing = (f"Você é o novo `{alias}`, substituindo a sessão anterior por handoff "
                f"de contexto. Leia {path}, depois rode `comms open {alias}` e arme a "
                f"campainha com `comms wait` em background.")
    if spawn_fn is None:
        from comms import ghostty
        spawn_fn = ghostty.spawn
    spawned = spawn_fn(alias=alias, cwd=cwd, briefing=briefing,
                        role=presence.role_for(alias))
    # spawn_fn may be a test stub that returns None (does not report) — only
    # an explicit False means the spawn is known to have failed. Losing the
    # successor here would leave the board with no orchestrator at all, so
    # the old presence entry must survive and no swap must be announced.
    if spawned is False:
        print(
            f"não foi possível abrir a sessão sucessora de {alias} — a sessão "
            f"antiga continua no board; corrija o problema (Ghostty rodando? "
            f"permissão de Automação concedida?) e rode `comms handoff` novamente"
        )
        raise SystemExit(1)

    # Broadcast before closing: if post() ever raised, the old presence entry
    # would still be there and the board would reflect reality. Closing first
    # would risk announcing nothing (or a swap that failed midway) while
    # already having removed the only session actually on the alias.
    messages.post(alias, f"handoff: {alias} foi substituído por uma sessão nova. "
                         f"Estado em {path}.")
    presence.close(alias)
    return path
