"""Drives Ghostty over AppleScript. The constraints encoded here were measured
on 2026-08-01 — see docs/specs §10.2 before changing any of them."""
import json, os, subprocess, tempfile

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
                set out to out & (id of w) & tab & (id of t) & tab & ¬
                    (working directory of t) & tab & sel & tab & fw & linefeed
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
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        out.append({"window": parts[0], "terminal": parts[1], "cwd": parts[2],
                    "selected": parts[3] == "1", "front_window": parts[4]})
    return out

def window_for_cwd(cwd: str, rows: list = None):
    """Match by working directory. Never by index — window order follows focus."""
    rows = list_terminals() if rows is None else rows
    for row in rows:
        if row["cwd"] == cwd:
            return row["window"]
    return None

def shell_quote(s: str) -> str:
    """Wrap for a POSIX shell single-quoted argument."""
    return "'" + s.replace("'", "'\\''") + "'"

def _briefing_launch(briefing: str) -> str:
    """Write the briefing to a UTF-8 file and return a pure-ASCII shell line
    that reads it, deletes it, and launches claude with it. Ghostty mangles
    non-ASCII in `initial input`; only ASCII may cross that boundary."""
    fd, path = tempfile.mkstemp(prefix="comms-brief-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(briefing)
    q = shell_quote(path)
    return f'B=$(cat {q}); rm -f {q}; claude "$B"'

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
    launch = _briefing_launch(briefing)
    ok, _ = _osascript(build_spawn_script(cwd, None, launch, env, window))
    if window and prev_terminal and front:
        # Separate invocation on purpose: `select tab` issued right after
        # `new tab` in the same script is silently ignored, even with a
        # delay, because Ghostty selects the new tab asynchronously and
        # overrides anything in the same pass. Do not merge these calls.
        # Best-effort: a failed focus restore does not change whether the
        # spawn itself succeeded, and must not be allowed to flip `ok` to
        # True either — its result is intentionally discarded.
        _osascript(build_restore_script(window, prev_terminal, front))
    return ok
