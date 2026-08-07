"""Drives Ghostty over AppleScript. The constraints encoded here were measured
on 2026-08-01 — see docs/specs §10.2 before changing any of them."""
import subprocess

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

def build_spawn_script(cwd, command, initial_input, env, window) -> str:
    env_list = ", ".join(f'"{_esc(e)}"' for e in env)
    cfg = (f'{{initial working directory:"{_esc(cwd)}", '
           f'command:"{_esc(command)}", '
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
    ok, _ = _osascript(build_spawn_script(cwd, "claude", briefing, env, window))
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
