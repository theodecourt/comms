"""Argument parsing and dispatch. Identity is never passed by the caller."""
import argparse, os, sys, time
from comms import messages, presence

def resolve_self() -> str:
    alias = presence.whoami()
    if not alias:
        print("não sei quem sou nesta sessão — rode `comms open <alias>` primeiro")
        raise SystemExit(2)
    return alias

def _age(ts: float) -> str:
    secs = int(time.time() - ts)
    if secs < 60:
        return "agora"
    if secs < 3600:
        return f"há {secs // 60} min"
    return f"há {secs // 3600} h"

def cmd_open(args) -> int:
    if not presence.valid_alias(args.alias):
        print(f"alias inválido: {args.alias!r} — use minúsculas, dígitos e hífen")
        return 2
    e = presence.open(args.alias, note=args.note or "", role=args.role)
    print(f"{e['alias']} aberto como {e['role']}")
    return 0

def cmd_who(args) -> int:
    entries = presence.read_all()
    if not entries:
        print("ninguém no board")
        return 0
    print(f"{'ALIAS':<10} {'PAPEL':<13} {'ESTADO':<14} {'VISTO':<10} NOTA")
    for e in entries:
        status = "stale" if e["stale"] else e.get("status", "?")
        print(f"{e['alias']:<10} {e.get('role',''):<13} {status:<14} "
              f"{_age(e.get('last_seen', 0)):<10} {e.get('note','')}")
    return 0

def cmd_post(args) -> int:
    me = resolve_self()
    mid = messages.post(me, args.body, to=args.to, urgent=args.urgent)
    print(f"enviada {mid} para {args.to or 'todos'}")
    return 0

def cmd_inbox(args) -> int:
    me = resolve_self()
    msgs = messages.inbox(me, peek=args.peek)
    if not msgs:
        print("sem mensagens novas")
        return 0
    for m in msgs:
        flag = " [URGENTE]" if m.get("urgent") else ""
        print(f"── de {m['from']}{flag}\n{m['body']}\n")
    return 0

def cmd_log(args) -> int:
    me = resolve_self()
    for m in messages.log(me):
        print(f"[{_age(m['ts'])}] {m['from']}: {m['body']}")
    return 0

def cmd_close(args) -> int:
    me = resolve_self()
    presence.close(me)
    print(f"{me} fechado")
    return 0

def cmd_wait(args) -> int:
    from comms import doorbell
    me = resolve_self()
    reason = doorbell.wait(me, interval=args.interval, max_seconds=args.max_seconds)
    print(f"DOORBELL: {reason}")
    return 0

def cmd_spawn(args) -> int:
    from comms import ghostty
    if not presence.valid_alias(args.alias):
        print(f"alias inválido: {args.alias!r}")
        return 2
    cwd = args.cwd or os.getcwd()
    ok = ghostty.spawn(args.alias, cwd, args.briefing, role=presence.role_for(args.alias))
    if not ok:
        print(f"falha ao abrir sessão {args.alias} — Ghostty pode não estar rodando, "
              f"ou a permissão de Automação (System Settings > Privacy & Security) não foi concedida")
        return 1
    print(f"sessão {args.alias} aberta em {cwd}")
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="comms")
    sub = p.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("open"); o.add_argument("alias")
    o.add_argument("--note", default=""); o.add_argument("--role", default=None)
    o.set_defaults(fn=cmd_open)

    sub.add_parser("who").set_defaults(fn=cmd_who)

    po = sub.add_parser("post"); po.add_argument("body")
    po.add_argument("--to", default=None); po.add_argument("--urgent", action="store_true")
    po.set_defaults(fn=cmd_post)

    i = sub.add_parser("inbox"); i.add_argument("--peek", action="store_true")
    i.set_defaults(fn=cmd_inbox)

    sub.add_parser("log").set_defaults(fn=cmd_log)
    sub.add_parser("close").set_defaults(fn=cmd_close)
    w = sub.add_parser("wait")
    w.add_argument("--interval", type=float, default=presence.POLL_INTERVAL)
    w.add_argument("--max-seconds", dest="max_seconds", type=float, default=None)
    w.set_defaults(fn=cmd_wait)

    sp = sub.add_parser("spawn"); sp.add_argument("alias")
    sp.add_argument("--cwd", default=None)
    sp.add_argument("--briefing", default="")
    sp.set_defaults(fn=cmd_spawn)
    return p

def main(argv=None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.fn(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1

if __name__ == "__main__":
    raise SystemExit(main())
