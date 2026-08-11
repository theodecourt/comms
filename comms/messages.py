"""One message is one file. Delivery is a write into the recipient's inbox;
reading moves it to the log. Nothing is ever deleted."""
import itertools, json, os, time, uuid
from comms import paths, store

_seq = itertools.count()

def _deliver(alias: str, msg: dict) -> None:
    store.ensure_dirs(alias)
    name = f"{msg['ts']:.6f}-{next(_seq):06d}-{msg['id']}.json"
    store.write_json(os.path.join(paths.inbox_dir(alias), name), msg)

def _append_log(alias: str, msg: dict) -> None:
    path = paths.log_file(alias)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(msg) + "\n")

def post(sender: str, body: str, to: str = None, urgent: bool = False) -> str:
    msg = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "from": sender,
        "to": to,
        "body": body,
        "urgent": urgent,
    }
    if to:
        targets = [to]
    else:
        from comms import presence
        targets = [e["alias"] for e in presence.read_all() if e["alias"] != sender]
    for target in targets:
        _deliver(target, msg)
    return msg["id"]

def inbox(alias: str, peek: bool = False) -> list:
    d = paths.inbox_dir(alias)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    out = []
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        msg = store.read_json(path)
        if msg is None:
            continue
        out.append(msg)
        if not peek:
            _append_log(alias, msg)
            try:
                os.unlink(path)
            except OSError:
                pass
    return out

def log(alias: str) -> list:
    try:
        with open(paths.log_file(alias)) as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except OSError:
        return []

def record_native(sender: str, to_name: str, alias: str = None,
                  delivered: bool = True, msg_id: str = "") -> dict:
    """Registra que uma mensagem foi pelo transporte nativo.

    Guarda o fato, nunca o corpo: o texto trafega pelo nativo e o board é
    testemunha, não transporte. Escreve nos DOIS lados porque "quem falou com
    quem" só é auditável se o remetente também puder ver o que mandou.

    `delivered=False` é gravado de propósito. O fallback para `comms post` é
    responsabilidade do agente, e um fallback esquecido precisa deixar rastro.
    """
    rec = {
        "id": msg_id or uuid.uuid4().hex[:12],
        "ts": time.time(),
        "from": sender,
        "to": alias or to_name,
        "kind": "native",
        "delivered": bool(delivered),
        "off_board": alias is None,
    }
    _append_log(sender, rec)
    if alias and alias != sender:
        _append_log(alias, rec)
    return rec
