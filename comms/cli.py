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
    alias = presence.resolve_alias(
        args.alias, session=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    e = presence.open(alias, note=args.note or "", role=args.role)
    if alias != args.alias:
        print(f"{args.alias} → {alias}")
    print(f"{e['alias']} aberto como {e['role']}")
    return 0

def _state(e) -> str:
    """What the agent is doing — or that it is no longer there.

    `live is False` outranks the agent's own last self-report, which is frozen
    at whatever it wrote before dying."""
    if e.get("live") is False:
        return "foi-embora"
    return e.get("status", "?")

NATIVE_NAME_WIDTH = 34      # fits the names Claude Code derives on its own
ALIAS_WIDTH = 16            # fits `builder-front-2`, the longest the
                            # convention produces before it starts truncating

def _trunc(s: str, width: int) -> str:
    """Cut to `width` from the MIDDLE, keeping both ends.

    This column is an addressing key: the reader matches it against
    `ListAgents` to find a peer. Cutting the tail off broke exactly that —
    `joao-claude-setup-skills-commands` came out as `joao-claude-setup-ski…`
    and an agent had to guess by prefix (reported from a real test,
    2026-08-12). Keeping head and tail leaves enough to recognise the name
    either way."""
    if len(s) <= width:
        return s
    keep = width - 1
    head = (keep + 1) // 2
    return s[:head] + "…" + s[len(s) - (keep - head):]

def cmd_who(args) -> int:
    from comms import delegation
    pruned = presence.prune_ghosts()
    entries = presence.read_all()
    if args.json:
        # For readers that are not agents — agent-monitor paints the 🔔 from
        # `reachable` — so they never have to parse the table.
        import json
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
    grants = delegation.read_all()
    if not entries and not grants:
        print("ninguém no board")
        return 0
    if pruned:
        print(f"removidos do board (sessão encerrada há mais de "
              f"{presence.PRUNE_AFTER_SECONDS // 3600} h): {', '.join(pruned)}")
    # No bell column. It reported whether a `comms wait` was armed, which
    # mattered while the doorbell was how mail arrived. Native SendMessage
    # reaches a session with no background process, and comms-path mail now
    # surfaces through the hook at the agent's next turn, so nothing depends on
    # anyone holding a doorbell open — the column would read `surda` for
    # everyone, always, and mean nothing.
    print(f"{'ALIAS':<{ALIAS_WIDTH}} {'PAPEL':<13} {'ESTADO':<14} "
          f"{'NOME NATIVO':<{NATIVE_NAME_WIDTH}} {'VISTO':<10} NOTA")
    for e in entries:
        alias = _trunc(e["alias"], ALIAS_WIDTH)
        name = _trunc(e.get("native_name") or "—", NATIVE_NAME_WIDTH)
        print(f"{alias:<{ALIAS_WIDTH}} {e.get('role',''):<13} {_state(e):<14} "
              f"{name:<{NATIVE_NAME_WIDTH}} "
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
        if m.get("kind") == "native":
            mark = "" if m.get("delivered") else "  ⚠ NÃO ENTREGUE"
            print(f"[{_age(m['ts'])}] {m['from']} → {m['to']}: via nativo{mark}")
        else:
            print(f"[{_age(m['ts'])}] {m['from']}: {m['body']}")
    return 0

def cmd_rename(args) -> int:
    from comms import rename
    me = resolve_self()
    try:
        novo = rename.run(me, args.alias)
    except rename.RenameRefused as e:
        print(str(e))
        return 2
    print(f"{me} agora é {novo} — mensagens, histórico e delegação vieram junto")
    print(f"o nome nativo da sessão não muda: use /rename {novo} se quiser os "
          f"dois iguais")
    return 0

def cmd_close(args) -> int:
    me = resolve_self()
    presence.close(me)
    print(f"{me} fechado")
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
    # Resolved against the TARGET repo, not this one: the child's layer comes
    # from where it will live. Doing it here also means COMMS_ALIAS reaches the
    # child already final, so its auto-join has nothing left to decide.
    if args.model and not ghostty.valid_model(args.model):
        print(f"modelo desconhecido: {args.model!r} — use um alias "
              f"({', '.join(ghostty.MODEL_ALIASES)}), opcionalmente com [1m], "
              f"ou o id completo do modelo. Claude Code não recusa um nome que "
              f"não conhece: ele abre a sessão mesmo assim, degradada, e o board "
              f"mostraria um builder que nunca funciona.")
        return 2
    alias = presence.resolve_alias(args.alias, cwd=cwd)
    if alias != args.alias:
        print(f"{args.alias} → {alias}")
    role = presence.role_for(alias)
    # Resolved here rather than left to spawn() so the success line can name the
    # model that actually launched — the default is a decision comms made on the
    # caller's behalf, and one it should say out loud.
    model = args.model or ghostty.model_for_role(role)
    ok = ghostty.spawn(alias, cwd, args.briefing, role=role, model=model)
    if not ok:
        print(f"falha ao abrir sessão {alias} — Ghostty pode não estar rodando, "
              f"ou a permissão de Automação (System Settings > Privacy & Security) não foi concedida")
        return 1
    print(f"sessão {alias} aberta em {cwd} com {model or 'o modelo padrão'}")
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

def cmd_task_new(args) -> int:
    from comms import tasks
    try:
        task = tasks.new(args.nome)
    except tasks.TaskError as e:
        print(str(e))
        return 2
    print(f"task criada em {task}")
    print(f"preencha objetivo e critérios em {tasks.task_file(task)}")
    return 0

def cmd_task_assign(args) -> int:
    from comms import tasks
    try:
        rec = tasks.assign(args.alias, args.task, args.subtask, resumo=args.resumo)
    except tasks.TaskError as e:
        print(str(e))
        return 2
    prev = rec["previous"]
    if prev and (prev.get("task"), prev.get("subtask")) != (rec["task"], rec["subtask"]):
        print(f"{args.alias} deixa {os.path.basename(str(prev.get('task')))} "
              f"· subtarefa {prev.get('subtask')}")
    print(f"{args.alias} → {os.path.basename(rec['task'])} · subtarefa "
          f"{rec['subtask']} ({rec['file']})")
    return 0

def _print_task(task: str) -> None:
    from comms import tasks
    state = "fechada" if tasks.is_closed(task) else "aberta"
    print(f"{os.path.basename(task)} ({state})")
    rows = tasks.status(task)
    if not rows:
        print("  sem subtarefas")
        return
    print(f"  {'ID':<5} {'ESTADO':<8} {'DONO':<16} {'BRANCH':<32} {'SHA':<10} ARQUIVO")
    for r in rows:
        print(f"  {r['id']:<5} {r['status']:<8} {r['owner'] or '—':<16} "
              f"{r['branch'] or '—':<32} {r['sha'][:10] or '—':<10} {r['file']}")

def cmd_task_status(args) -> int:
    from comms import tasks
    if args.task:
        try:
            targets = [tasks.resolve(args.task)]
        except tasks.TaskError as e:
            print(str(e))
            return 2
    else:
        targets = [t for t in tasks.all_tasks() if not tasks.is_closed(t)]
        if not targets:
            print("nenhuma task aberta")
            return 0
    for i, task in enumerate(targets):
        if i:
            print()
        _print_task(task)
    return 0

def cmd_task_close(args) -> int:
    from comms import tasks
    try:
        rec = tasks.close(args.task)
    except tasks.TaskError as e:
        print(str(e))
        return 2
    print(f"{os.path.basename(rec['task'])} fechada")
    if rec["freed"]:
        print(f"atribuições apagadas: {', '.join(rec['freed'])}")
    print(rec["archived"])
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="comms")
    sub = p.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("open"); o.add_argument("alias")
    o.add_argument("--note", default=""); o.add_argument("--role", default=None)
    o.set_defaults(fn=cmd_open)

    w = sub.add_parser("who"); w.add_argument("--json", action="store_true")
    w.set_defaults(fn=cmd_who)

    po = sub.add_parser("post"); po.add_argument("body")
    po.add_argument("--to", default=None); po.add_argument("--urgent", action="store_true")
    po.set_defaults(fn=cmd_post)

    i = sub.add_parser("inbox"); i.add_argument("--peek", action="store_true")
    i.set_defaults(fn=cmd_inbox)

    sub.add_parser("log").set_defaults(fn=cmd_log)

    rn = sub.add_parser("rename"); rn.add_argument("alias")
    rn.set_defaults(fn=cmd_rename)

    sub.add_parser("close").set_defaults(fn=cmd_close)
    # No `wait`. It backgrounded a polling loop whose exit woke an idle
    # session; native SendMessage wakes a peer with no process at all, and
    # comms-path mail is announced by the hook at the agent's next turn. What
    # was left was a subscription to being interrupted every time its bound
    # elapsed, for nothing.

    sp = sub.add_parser("spawn"); sp.add_argument("alias")
    sp.add_argument("--cwd", default=None)
    sp.add_argument("--briefing", default="")
    sp.add_argument("--model", default=None,
                    help="modelo da sessão filha; sem isso, o papel decide "
                         "(orquestrador opus[1m], builder sonnet[1m])")
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

    t = sub.add_parser("task").add_subparsers(dest="task_cmd", required=True)
    tn = t.add_parser("new"); tn.add_argument("nome")
    tn.set_defaults(fn=cmd_task_new)
    ta = t.add_parser("assign"); ta.add_argument("alias"); ta.add_argument("task")
    ta.add_argument("--subtask", required=True)
    ta.add_argument("--resumo", default=None,
                    help="o que a subtarefa entrega; nomeia o arquivo dela")
    ta.set_defaults(fn=cmd_task_assign)
    ts = t.add_parser("status"); ts.add_argument("task", nargs="?")
    ts.set_defaults(fn=cmd_task_status)
    tc = t.add_parser("close"); tc.add_argument("task")
    tc.set_defaults(fn=cmd_task_close)

    return p

def main(argv=None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.fn(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1

if __name__ == "__main__":
    raise SystemExit(main())
