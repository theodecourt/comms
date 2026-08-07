#!/usr/bin/env python3
# hooks/install_hooks.py — adds the comms hook alongside existing hooks
import json, os, shutil, sys

SETTINGS = os.path.expanduser("~/.claude/settings.json")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comms-hook.py")
EVENTS = ["UserPromptSubmit", "Stop", "Notification", "SessionEnd"]

def main() -> int:
    shutil.copy(SETTINGS, SETTINGS + ".bak-comms")
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
    with open(SETTINGS, "w") as fh:
        json.dump(cfg, fh, indent=2)
    print(f"backup: {SETTINGS}.bak-comms")
    print(f"adicionados: {added or 'nada — já estavam lá'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
