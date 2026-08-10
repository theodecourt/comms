"""Replace a session that is running out of context, keeping its alias."""
import os
import subprocess
from comms import messages, presence, session

def vault_root() -> str:
    """Where archive notes land. Overridable with COMMS_VAULT so tests never
    write into — or push to — the real Obsidian vault. Read at call time, for
    the same reason paths.root() is."""
    return os.environ.get("COMMS_VAULT") or os.path.expanduser(
        "~/obsidian-segura/claude-code-session-history")

def doc_path(cwd: str, alias: str, stamp: str) -> str:
    """Never returns a path that already holds a file.

    The name is deterministic from (cwd, alias, stamp), so a second handoff on
    the same day — or any tooling that guesses the same name — would silently
    overwrite the first. That doc is git-excluded, so an overwrite is
    unrecoverable except from the transcript of whoever last read it. Happened
    once, 2026-08-10. A numbered variant costs nothing and loses nothing."""
    base = os.path.join(cwd, "scratchpad", f"{stamp}-handoff-{alias}")
    candidate = f"{base}.md"
    n = 2
    while os.path.exists(candidate):
        candidate = f"{base} ({n}).md"
        n += 1
    return candidate

def vault_path(alias: str, stamp: str, vault: str = None) -> str:
    """Where the archive copy lands, avoiding same-day collisions the way
    /archive-session does — a numbered suffix rather than an overwrite."""
    base = vault or vault_root()
    candidate = os.path.join(base, f"{stamp} Handoff {alias}.md")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(base, f"{stamp} Handoff {alias} ({n}).md")
        n += 1
    return candidate

def write_vault_note(path: str, alias: str, stamp: str, project: str,
                     session_id: str, body: str) -> None:
    """Archive copy for the Obsidian vault, with the frontmatter the
    /archive-session notes use so both kinds of note query alike."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\n")
        fh.write(f"date: {stamp}\n")
        fh.write(f"project: {project}\n")
        fh.write(f"session: {session_id}\n")
        fh.write(f"tags: [claude-session, handoff, {project}]\n")
        fh.write("---\n\n")
        fh.write(f"# Handoff — {alias}\n\n")
        fh.write(body.rstrip() + "\n")

def publish_vault(path: str) -> bool:
    """Commit and push the archive note. The vault exists to be backed up off
    this machine, and `confirm-before-push` carves it out for exactly that.
    A failure here must not fail the handoff — the note is already on disk."""
    repo = os.path.dirname(os.path.dirname(path))
    try:
        subprocess.run(["git", "-C", repo, "add", path],
                       capture_output=True, timeout=30, check=True)
        subprocess.run(["git", "-C", repo, "commit", "-m",
                        f"handoff: {os.path.basename(path)}"],
                       capture_output=True, timeout=30, check=True)
        subprocess.run(["git", "-C", repo, "push", "origin", "main"],
                       capture_output=True, timeout=90, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False

def write_doc(path: str, alias: str, note: str, body: str,
              summary: str = None) -> None:
    """The successor's single source. Carries both texts, so the briefing
    needs one path and the summary does not depend on the vault write, which
    happens after the spawn."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Handoff — {alias}\n\n")
        fh.write(f"**Nota da sessão anterior:** {note}\n\n")
        fh.write("## Estado\n\n")
        fh.write(body.rstrip() + "\n")
        if summary:
            fh.write("\n## O que aconteceu na sessão anterior\n\n")
            fh.write(summary.rstrip() + "\n")

def run(alias: str, body: str, stamp: str, spawn_fn=None, summary: str = None) -> str:
    """`body` is forward-looking: what the successor needs to continue.
    `summary` is backward-looking: what happened this session, for the vault
    archive. They are different documents and one text serves neither well —
    when `summary` is omitted the archive falls back to `body` and says so."""
    entry = next((e for e in presence.read_all() if e["alias"] == alias), None)
    if entry is None:
        print(f"{alias} não está no board")
        raise SystemExit(2)
    cwd = entry.get("cwd") or os.getcwd()
    # Check before writing anything: a successor spawned into a directory
    # Claude Code has never seen would block on the trust dialog, and the
    # handoff would have already closed the only live session on this alias.
    if spawn_fn is None:
        from comms import ghostty
        if not ghostty.is_trusted_dir(cwd):
            print(f"{cwd} nunca foi aberto no Claude Code — a sessão sucessora "
                  f"travaria no diálogo de confiança e você perderia {alias}. "
                  f"Abra o diretório uma vez manualmente e tente de novo.")
            raise SystemExit(2)
    path = doc_path(cwd, alias, stamp)
    write_doc(path, alias, entry.get("note", ""), body, summary=summary)

    briefing = (f"Você é o novo `{alias}`, substituindo a sessão anterior por handoff "
                f"de contexto. Leia {path} — ele traz o estado atual e o que aconteceu "
                f"na sessão anterior. Depois rode `comms open {alias}` e arme a "
                f"campainha com `comms wait` em background.")
    if spawn_fn is None:
        from comms import ghostty
        spawn_fn = ghostty.spawn
    # The old session keeps its name — the client owns that and does not read a
    # change from disk (verified 2026-08-10). The successor is marked instead.
    old_name = session.name_for(entry.get("session", ""))
    spawned = spawn_fn(alias=alias, cwd=cwd, briefing=briefing,
                        role=presence.role_for(alias),
                        name=session.successor_name(old_name or ""))
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

    # Archive to the vault last: it is the one step whose failure should not
    # cost the handoff. Everything above already succeeded, and the state doc
    # is on disk either way.
    try:
        vp = vault_path(alias, stamp)
        archive_body = summary or (
            "_Sem resumo de sessão — o texto abaixo é o estado de handoff, "
            "escrito para o sucessor continuar, não um relato do que aconteceu._\n\n"
            + body)
        write_vault_note(vp, alias, stamp, os.path.basename(cwd),
                         entry.get("session", ""), archive_body)
        if os.environ.get("COMMS_VAULT"):
            print(f"nota escrita em {vp} (COMMS_VAULT definido — sem commit/push)")
        elif publish_vault(vp):
            print(f"arquivado no vault: {os.path.basename(vp)} (commitado e enviado)")
        else:
            print(f"arquivado no vault: {os.path.basename(vp)} "
                  f"(local — o commit/push falhou, verifique o repo do vault)")
    except OSError as e:
        print(f"nota do vault não foi escrita ({e}) — o handoff em si está feito")
    return path
