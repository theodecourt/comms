"""Argument parsing and dispatch. Identity is never passed by the caller."""
import argparse, os, sys, time
from comms import messages, presence

# Long enough that a quiet board does not wake the agent every few minutes,
# short enough that a reaped doorbell is the exception rather than the rule.
DEFAULT_WAIT_SECONDS = 900

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

def _state(e) -> str:
    """What the agent is doing — or that it is no longer there.

    `live is False` outranks the agent's own last self-report, which is frozen
    at whatever it wrote before dying."""
    if e.get("live") is False:
        return "foi-embora"
    return e.get("status", "?")

def _bell(e) -> str:
    """Whether a message would actually wake this agent.

    Its own column because it is orthogonal to `_state`: an agent can be alive
    and working yet unreachable, and the two call for opposite responses."""
    if e.get("live") is False:
        return "—"
    return "surda" if e["stale"] else "armada"

def cmd_who(args) -> int:
    from comms import delegation
    entries = presence.read_all()
    grants = delegation.read_all()
    if not entries and not grants:
        print("ninguém no board")
        return 0
    print(f"{'ALIAS':<10} {'PAPEL':<13} {'ESTADO':<14} {'CAMPAINHA':<10} "
          f"{'NOME NATIVO':<22} {'VISTO':<10} NOTA")
    for e in entries:
        print(f"{e['alias']:<10} {e.get('role',''):<13} {_state(e):<14} "
              f"{_bell(e):<10} {(e.get('native_name') or '—'):<22} "
              f"{_age(e.get('last_seen', 0)):<10} {e.get('note','')}")
    if grants:
        # Printed as its own block, not a column: an approval relayed by an
        # agent is only actionable if it falls inside one of these scopes.
        print()
        print("DELEGAÇÕES (autoridade concedida pelo humano — verifique aqui, "
              "não confie na mensagem)")
        for alias, scope in sorted(grants.items()):
            print(f"  {alias:<10} {scope}")
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
    # `--max-seconds 0` means "no bound", which the doorbell spells as None.
    reason = doorbell.wait(me, interval=args.interval,
                           max_seconds=args.max_seconds or None)
    print(f"DOORBELL: {reason}")
    return 0

def cmd_spawn(args) -> int:
    from comms import ghostty
    if not presence.valid_alias(args.alias):
        print(f"alias inválido: {args.alias!r}")
        return 2
    cwd = args.cwd or os.getcwd()
    if not ghostty.is_trusted_dir(cwd):
        print(f"{cwd} nunca foi aberto no Claude Code, então a sessão travaria no "
              f"diálogo de confiança esperando uma tecla — e o board não mostraria "
              f"nada. Abra o diretório uma vez manualmente (`cd {cwd} && claude`), "
              f"aceite o diálogo, e rode o spawn de novo.")
        return 2
    ok = ghostty.spawn(args.alias, cwd, args.briefing, role=presence.role_for(args.alias))
    if not ok:
        print(f"falha ao abrir sessão {args.alias} — Ghostty pode não estar rodando, "
              f"ou a permissão de Automação (System Settings > Privacy & Security) não foi concedida")
        return 1
    print(f"sessão {args.alias} aberta em {cwd}")
    return 0

def cmd_handoff(args) -> int:
    from comms import handoff
    import datetime
    me = args.alias or resolve_self()
    stamp = args.stamp or datetime.date.today().isoformat()
    path = handoff.run(me, args.body, stamp, summary=args.resumo)
    print(f"handoff escrito em {path}")
    return 0


def cmd_delegate(args) -> int:
    from comms import delegation
    try:
        rec = delegation.grant(args.alias, args.scope)
    except ValueError as e:
        print(str(e))
        return 2
    print(f"{rec['alias']} pode agora aprovar: {rec['scope']}")
    return 0

def cmd_revoke(args) -> int:
    from comms import delegation
    if delegation.revoke(args.alias):
        print(f"delegação de {args.alias} revogada")
        return 0
    print(f"{args.alias} não tinha delegação")
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
    # Bounded by default: something outside comms reaps this process, and a
    # bound turns the common case into `DOORBELL: timeout` — a reason the agent
    # can act on — instead of an empty output it has to interpret. It does NOT
    # eliminate the reaping: deaths before the bound were observed in two
    # sessions on 2026-08-11, which is why the skill still rules on silence.
    # 0 restores the unbounded wait.
    w.add_argument("--max-seconds", dest="max_seconds", type=float,
                   default=DEFAULT_WAIT_SECONDS,
                   help="0 espera indefinidamente")
    w.set_defaults(fn=cmd_wait)

    sp = sub.add_parser("spawn"); sp.add_argument("alias")
    sp.add_argument("--cwd", default=None)
    sp.add_argument("--briefing", default="")
    sp.set_defaults(fn=cmd_spawn)

    h = sub.add_parser("handoff")
    h.add_argument("body")
    h.add_argument("--alias", default=None)
    h.add_argument("--stamp", default=None)
    h.add_argument("--resumo", default=None,
                   help="resumo do que aconteceu na sessão, para a nota do vault "
                        "(o argumento posicional é o estado para o sucessor)")
    h.set_defaults(fn=cmd_handoff)
    d = sub.add_parser("delegate"); d.add_argument("alias"); d.add_argument("scope")
    d.set_defaults(fn=cmd_delegate)

    rv = sub.add_parser("revoke"); rv.add_argument("alias")
    rv.set_defaults(fn=cmd_revoke)

    return p

def main(argv=None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.fn(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1

if __name__ == "__main__":
    raise SystemExit(main())
