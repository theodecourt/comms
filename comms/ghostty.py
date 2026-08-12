"""Drives Ghostty over AppleScript. The constraints encoded here were measured
on 2026-08-01 — see docs/specs §10.2 before changing any of them."""
import json, os, subprocess, tempfile, time

# Fields are separated by "|:|", not by `tab`. Inside `tell application
# "Ghostty"` the word `tab` resolves to Ghostty's own tab CLASS, not to the
# AppleScript tab character, so the script emitted the literal text "tab" and
# every row failed to parse — list_terminals() returned empty, which silently
# made every spawn open a new window and skipped focus restore entirely.
# Measured 2026-08-10. Do not reintroduce a bare `tab` here.
LIST_SCRIPT = """
tell application "Ghostty"
    if it is not running then return ""
    set out to ""
    set fw to id of front window
    repeat with w in windows
        repeat with tb in tabs of w
            try
                set t to focused terminal of tb
                set sel to "0"
                if selected of tb then set sel to "1"
                set out to out & (id of w) & "|:|" & (id of t) & "|:|" & ¬
                    (working directory of t) & "|:|" & sel & "|:|" & fw & linefeed
            end try
        end repeat
    end repeat
    return out
end tell
"""

def _osascript(script: str) -> tuple:
    """Run an AppleScript and report whether it actually worked.

    Returns (ok, output). `ok` is False when the process could not even be
    started (osascript missing, etc.) or when it exited non-zero — a
    malformed script, Ghostty not running, or Automation permission denied
    all surface as a non-zero exit here. The *exception* is still swallowed
    (this module never raises), but the *fact* of failure is not: callers
    such as spawn() need it to avoid reporting success for a tab that was
    never opened.
    """
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if r.returncode != 0:
        return False, ""
    return True, r.stdout.strip()

def _esc(s: str) -> str:
    # Backslashes MUST be escaped before quotes. Doing it the other way
    # round would re-escape the backslash just introduced for the quote,
    # corrupting the AppleScript string literal.
    return s.replace("\\", "\\\\").replace('"', '\\"')

def list_terminals() -> list:
    ok, output = _osascript(LIST_SCRIPT)
    if not ok:
        return []
    out = []
    for line in output.splitlines():
        parts = line.split("|:|")
        if len(parts) < 5:
            continue
        out.append({"window": parts[0], "terminal": parts[1], "cwd": parts[2],
                    "selected": parts[3] == "1", "front_window": parts[4]})
    return out

def window_for_cwd(cwd: str, rows: list = None):
    """Window to open the new tab in, matched by working directory.

    Never by index — window order follows focus and shifts between calls.

    An exact match is preferred, then the nearest ancestor: a session working
    in `<repo>/scratchpad/foo` belongs in the window already open on `<repo>`,
    which is what "one window per repo" means in practice. Without the
    ancestor fallback every session running below the repo root got its own
    window (observed 2026-08-10 with the `ai` session). Only when no window
    sits on the directory or above it is a new window the right answer.
    """
    rows = list_terminals() if rows is None else rows
    target = os.path.realpath(cwd)
    best, best_len = None, -1
    for row in rows:
        row_dir = os.path.realpath(row["cwd"]) if row["cwd"] else ""
        if not row_dir:
            continue
        if row_dir == target:
            return row["window"]
        # os.path.commonpath would match siblings sharing a prefix string;
        # the separator check keeps this to genuine ancestors.
        if target.startswith(row_dir.rstrip(os.sep) + os.sep) and len(row_dir) > best_len:
            best, best_len = row["window"], len(row_dir)
    return best

def shell_quote(s: str) -> str:
    """Wrap for a POSIX shell single-quoted argument."""
    return "'" + s.replace("'", "'\\''") + "'"

def _briefing_launch(briefing: str, name: str = None) -> str:
    """Write the briefing to a UTF-8 file and return a shell line that reads
    it, deletes it, and launches claude with it. The BRIEFING must not travel
    inline — Ghostty mangles non-ASCII in `initial input` — which is why it
    goes through a file and only the launch line crosses that boundary.

    `claude -n <name>` names the native session. Without it Claude Code derives
    a name from the directory (`comms-9d`), so `ListAgents` and `comms who`
    disagreed about what to call the same agent and no peer could address it by
    the name the board shows. `name` may carry the parent's project prefix, so
    it is not ASCII by construction the way a bare alias is — the shell quoting
    is what makes that safe."""
    fd, path = tempfile.mkstemp(prefix="comms-brief-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(briefing)
    q = shell_quote(path)
    flag = f"-n {shell_quote(name)} " if name else ""
    return f'B=$(cat {q}); rm -f {q}; claude {flag}"$B"'

def parent_naming() -> tuple:
    """(name, alias, role) of the session running this spawn.

    Returns (None, None, None) when that session's own name was never chosen —
    a derived name carries no project to pass on, so the child should just be
    its alias."""
    from comms import native, presence
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not session or not native.named_by_a_human(session):
        return None, None, None
    record = native.sessions().get(session) or {}
    alias = os.environ.get("COMMS_ALIAS") or None
    role = None
    for entry in presence.read_all():
        if entry.get("session") == session:
            alias = alias or entry["alias"]
            role = entry.get("role")
            break
    return record.get("name") or None, alias, role

def build_spawn_script(cwd, command, initial_input, env, window) -> str:
    env_list = ", ".join(f'"{_esc(e)}"' for e in env)
    # `command` is deliberately omitted when falsy. Ghostty runs a configured
    # `command` through `/usr/bin/login -flp <user> /bin/bash --noprofile
    # --norc -c exec -l <command>` — measured 2026-08-10 from a failed spawn.
    # `--noprofile --norc` means the process gets no shell profile, so PATH
    # lacks ~/.local/bin: `claude` is not found, AND a session launched that
    # way could not run `comms` either. Omitting `command` gets Ghostty's
    # default shell, which IS a login shell (measured: `$0` == `-/bin/zsh`),
    # so the launch belongs in `initial input` instead.
    command_field = f'command:"{_esc(command)}", ' if command else ""
    cfg = (f'{{initial working directory:"{_esc(cwd)}", '
           f'{command_field}'
           f'environment variables:{{{env_list}}}, '
           f'initial input:"{_esc(initial_input)}" & linefeed}}')
    # Target the window by its stable `id`, never by index — window order
    # follows focus and shifts between calls. If there is no matching
    # window, open a brand-new one instead of guessing a tab target.
    target = (f'new tab in (first window whose id is "{_esc(window)}") '
              f'with configuration {cfg}') if window else \
             f'new window with configuration {cfg}'
    return f'tell application "Ghostty"\n    {target}\nend tell'

def build_restore_script(target_window, prev_terminal, front_window) -> str:
    """Tab first, window second: `select tab` raises its own window, so
    restoring the target window's previous tab before re-activating the
    front window is the only order that leaves focus where it started."""
    return f'''tell application "Ghostty"
    repeat with w in windows
        if (id of w) is "{_esc(target_window)}" then
            repeat with tb in tabs of w
                try
                    if (id of (focused terminal of tb)) is "{_esc(prev_terminal)}" then select tab tb
                end try
            end repeat
        end if
    end repeat
    activate window (first window whose id is "{_esc(front_window)}")
end tell'''

def is_trusted_dir(cwd: str) -> bool:
    """Whether Claude Code has already been opened in `cwd`.

    A session started in a directory Claude Code has never seen blocks on its
    "do you trust the files in this folder?" prompt, waiting for a keypress.
    A spawned builder would sit there forever while the board shows nothing —
    observed 2026-08-10. Directories that have been opened appear as keys in
    ~/.claude.json; the dialog is Claude Code's own safety gate, so `comms`
    checks it and refuses rather than trying to pre-approve anything."""
    try:
        with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as fh:
            projects = json.load(fh).get("projects", {})
    except (OSError, ValueError):
        return True     # cannot tell — do not block the spawn on a guess
    return os.path.realpath(cwd) in {os.path.realpath(k) for k in projects}

def wait_for_session(cwd: str, before: set, timeout: float = 30.0,
                     settle: float = 2.0) -> bool:
    """Hold the new tab in focus until its SessionStart hook has run.

    Restoring focus immediately corrupts session→terminal mapping downstream.
    The agent-monitor hook records which Ghostty tab owns a session by asking
    which tab is focused at SessionStart, guarded only by working directory —
    and window_for_cwd deliberately opens the new tab in the window ALREADY on
    that repo, so the tab we restore focus to has the same cwd and sails past
    that guard. The new session then records the SPAWNING tab's id, two
    sessions claim one terminal, and agent-monitor evicts them from one another
    on every pass, painting titles onto the wrong tabs. Observed 2026-08-11:
    `builder` and `orch` both reported terminal A9B83B31.

    It was intermittent because Ghostty selects the new tab asynchronously, so
    the restore sometimes landed before that and sometimes after — the same
    race already documented in spawn(). Waiting removes the race instead of
    hoping to win it.

    Measured 2026-08-11: the session registry appears ~1.5s after spawn and
    SessionStart fires ~0.33s after that, so the registry alone is too early —
    hence `settle`. Returns False on timeout, and the caller restores focus
    anyway: a slow session must not strand the user's focus forever.
    """
    from comms import native
    target = os.path.realpath(cwd)
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sid, rec in native.sessions().items():
            if sid in before:
                continue
            # A record with no cwd must never match: os.path.realpath("")
            # resolves to the CURRENT directory, which equals `target`
            # whenever spawning into this process's own cwd — the common
            # case — and would satisfy the wait on any unrelated new session.
            rec_cwd = rec.get("cwd")
            if rec_cwd and os.path.realpath(rec_cwd) == target:
                time.sleep(settle)
                return True
        time.sleep(0.1)
    return False

def spawn(alias: str, cwd: str, briefing: str, role: str = None) -> bool:
    """Open a Ghostty session for `alias`. Returns True only when the spawn
    invocation itself succeeded — the caller (cmd_spawn) uses this to avoid
    reporting a session as open when no tab was actually created."""
    rows = list_terminals()
    front = rows[0]["front_window"] if rows else None
    window = window_for_cwd(cwd, rows)
    prev_terminal = next((r["terminal"] for r in rows
                          if r["window"] == window and r["selected"]), None)
    env = [f"COMMS_ALIAS={alias}"]
    if role:
        env.append(f"COMMS_ROLE={role}")
    # No `command` — the login shell launches claude from `initial input`, so
    # the session inherits a real PATH (see build_spawn_script for why).
    #
    # The briefing goes through a file rather than inline, because Ghostty's
    # `initial input` re-encodes what it types: UTF-8 bytes are read as
    # Latin-1 and encoded again, so "ê" (c3 aa) arrives as c3 83 c2 aa.
    # Measured 2026-08-10 against a real spawn. Keeping the launch line pure
    # ASCII sidesteps it — Python writes the file as UTF-8 and the shell
    # reads it back intact.
    from comms import native
    # The child inherits the parent's project name with the role marker
    # swapped, so a tree of sessions reads as one piece of work rather than as
    # a pile of bare roles: PROJETO-KB-ORCHESTRATOR spawning `api` becomes
    # PROJETO-KB-api. A parent that was never named has no project to pass on,
    # and the child is just its alias.
    launch = _briefing_launch(briefing,
                              native.session_name(alias, *parent_naming()))
    before = set(native.sessions())
    ok, _ = _osascript(build_spawn_script(cwd, None, launch, env, window))
    # A spawn that already failed — Ghostty not running, Automation
    # permission denied — has no tab to wait for. Waiting anyway would hold
    # the caller for the full timeout before it could even report the error.
    if ok and window and prev_terminal and front:
        # Never restore focus before the new session has recorded its own tab —
        # see wait_for_session for what breaks when we do.
        wait_for_session(cwd, before)
        # Separate invocation on purpose: `select tab` issued right after
        # `new tab` in the same script is silently ignored, even with a
        # delay, because Ghostty selects the new tab asynchronously and
        # overrides anything in the same pass. Do not merge these calls.
        # Best-effort: a failed focus restore does not change whether the
        # spawn itself succeeded, and must not be allowed to flip `ok` to
        # True either — its result is intentionally discarded.
        _osascript(build_restore_script(window, prev_terminal, front))
    return ok
