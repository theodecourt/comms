#!/usr/bin/env python3
# hooks/install_hooks.py — adds the comms hook alongside existing hooks
import json, os, shutil, sys, time

SETTINGS = os.environ.get("COMMS_SETTINGS") or os.path.expanduser("~/.claude/settings.json")
HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "comms-hook.py")
SEND_HOOK = os.path.join(HERE, "comms-sendmessage-hook.py")
EVENTS = ["UserPromptSubmit", "Stop", "Notification", "SessionEnd"]
# PostToolUse precisa de matcher: sem ele o hook rodaria em toda ferramenta.
MATCHED = [("PostToolUse", "SendMessage", SEND_HOOK)]

def backup_path() -> str:
    # Timestamped so re-runs never clobber an earlier backup — the first
    # backup taken is the only copy of the pre-comms settings and has to
    # survive every later run of this script.
    stamp = time.strftime("%Y%m%dT%H%M%S")
    candidate = f"{SETTINGS}.bak-comms-{stamp}"
    suffix = 0
    while os.path.exists(candidate):
        suffix += 1
        candidate = f"{SETTINGS}.bak-comms-{stamp}-{suffix}"
    return candidate

def main() -> int:
    backup = backup_path()
    shutil.copy(SETTINGS, backup)
    with open(SETTINGS) as fh:
        cfg = json.load(fh)
    hooks = cfg.setdefault("hooks", {})
    entry = {"type": "command", "command": HOOK}
    added = []
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        existing = [h.get("command") for g in groups for h in g.get("hooks", [])]
        if HOOK in existing:
            continue
        groups.append({"hooks": [entry]})
        added.append(event)
    for event, matcher, script in MATCHED:
        groups = hooks.setdefault(event, [])
        existing = [h.get("command") for g in groups for h in g.get("hooks", [])]
        if script in existing:
            continue
        groups.append({"matcher": matcher,
                       "hooks": [{"type": "command", "command": script}]})
        added.append(f"{event}({matcher})")
    with open(SETTINGS, "w") as fh:
        json.dump(cfg, fh, indent=2)
    print(f"backup: {backup}")
    print(f"adicionados: {added or 'nada — já estavam lá'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
