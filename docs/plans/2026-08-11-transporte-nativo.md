# Transporte nativo cross-session — plano de implementação

> **Para trabalhadores agênticos:** SUB-SKILL OBRIGATÓRIA: use
> superpowers:subagent-driven-development (recomendado) ou
> superpowers:executing-plans para implementar tarefa a tarefa. Os passos usam
> checkbox (`- [ ]`) para acompanhamento.

**Goal:** fazer o `SendMessage` nativo carregar as mensagens entre agentes,
com o board do comms registrando o fato de cada envio.

**Architecture:** o nativo vira transporte; o comms vira identidade, política e
registro. Um hook `PostToolUse` com matcher `SendMessage` grava o fato sem corpo
no log dos dois lados. `comms who` passa a mostrar o nome nativo, que é como o
agente sai do alias para o destinatário do `SendMessage`.

**Tech Stack:** Python 3 da stdlib apenas, `unittest`, hooks do Claude Code.

## Global Constraints

- Spec de referência: `docs/specs/2026-08-11-transporte-nativo-design.md`.
- Nenhuma dependência externa. Só stdlib.
- Todo teste que define `COMMS_ROOT` **precisa** de `tearDown` que remova a
  variável e o tmpdir — a suíte roda num processo só e uma variável vazada torna
  as suítes seguintes dependentes de ordem.
- `COMMS_ROOT` já arrasta o diretório de sessões junto (`paths.sessions_dir()`),
  então nenhum teste toca o registro real da máquina.
- Hook nunca levanta exceção e nunca sai diferente de 0. Hook que quebra estraga
  o turno do usuário.
- Mensagens ao usuário em português, como o resto do CLI.

---

### Task 1: `comms who` mostra o nome nativo

Sem isso o agente não sai do alias para o alvo do `SendMessage`.

**Files:**
- Modify: `comms/presence.py` (dentro de `read_all()`)
- Modify: `comms/cli.py` (`cmd_who`)
- Test: `tests/test_presence.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `presence.read_all()` passa a incluir a chave `native_name: str|None`
  em cada entrada. As Tasks 2 e 3 dependem dela.

- [ ] **Step 1: Escreva o teste que falha**

Em `tests/test_presence.py`, dentro de `PresenceTest`:

```python
    def test_read_all_exposes_the_native_session_name(self):
        from comms import presence
        presence.open("infra", session="sess-1")
        self._registry({"sessionId": "sess-1", "pid": os.getpid(),
                        "status": "busy", "name": "infra"})
        self.assertEqual(presence.read_all()[0]["native_name"], "infra")

    def test_native_name_is_none_without_a_registry_match(self):
        from comms import presence
        presence.open("infra", session="sess-1")
        self.assertIsNone(presence.read_all()[0]["native_name"])
```

- [ ] **Step 2: Rode para confirmar que falha**

Run: `python3 -m unittest tests.test_presence -v -k native_name`
Expected: FAIL com `KeyError: 'native_name'`

- [ ] **Step 3: Implemente**

Em `comms/presence.py`, dentro de `read_all()`, no bloco onde `record` existe e
no `else`:

```python
        if record is not None:
            entry["live"] = native.pid_alive(record.get("pid"))
            entry["native_status"] = record.get("status")
            entry["native_name"] = record.get("name") or None
        else:
            entry["live"] = False if (registry and session) else None
            entry["native_status"] = None
            entry["native_name"] = None
```

- [ ] **Step 4: Rode e confirme que passa**

Run: `python3 -m unittest tests.test_presence -v -k native_name`
Expected: PASS

- [ ] **Step 5: Teste do `comms who`**

Em `tests/test_cli.py`, dentro de `CliTest`:

```python
    def test_who_shows_the_native_name_for_addressing(self):
        # É por esse nome que o agente endereça o SendMessage; sem ele o board
        # diz com quem falar e não diz como.
        import os
        from comms import store, paths
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-front"
        run("open", "front")
        store.write_json(os.path.join(paths.sessions_dir(), "1.json"),
                         {"sessionId": "sess-front", "pid": os.getpid(),
                          "status": "busy", "name": "front-tab"})
        _, out = run("who")
        self.assertIn("front-tab", out)
```

- [ ] **Step 6: Rode, confirme que falha, implemente o `cmd_who`**

Run: `python3 -m unittest tests.test_cli -v -k native_name`
Expected: FAIL

Em `comms/cli.py`, substitua o cabeçalho e o laço de `cmd_who`:

```python
    print(f"{'ALIAS':<10} {'PAPEL':<13} {'ESTADO':<14} {'CAMPAINHA':<10} "
          f"{'NOME NATIVO':<22} {'VISTO':<10} NOTA")
    for e in entries:
        print(f"{e['alias']:<10} {e.get('role',''):<13} {_state(e):<14} "
              f"{_bell(e):<10} {(e.get('native_name') or '—'):<22} "
              f"{_age(e.get('last_seen', 0)):<10} {e.get('note','')}")
```

- [ ] **Step 7: Rode a suíte inteira**

Run: `python3 -m unittest discover -s tests -q`
Expected: OK

- [ ] **Step 8: Commit**

```bash
git add comms/presence.py comms/cli.py tests/test_presence.py tests/test_cli.py
git commit -m "feat: board mostra o nome nativo, que é como se endereça um peer"
```

---

### Task 2: registrar o fato de um envio nativo

**Files:**
- Modify: `comms/messages.py`
- Modify: `comms/cli.py` (`cmd_log`)
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: nada da Task 1.
- Produces: `messages.record_native(sender: str, to_name: str, alias: str|None,
  delivered: bool, msg_id: str) -> dict`. A Task 3 chama exatamente esta
  assinatura.

- [ ] **Step 1: Escreva o teste que falha**

Em `tests/test_messages.py`:

```python
    def test_record_native_writes_the_fact_to_both_sides(self):
        from comms import messages
        messages.record_native("orch", "builder", alias="builder",
                               delivered=True, msg_id="abc123")
        for who in ("orch", "builder"):
            rec = messages.log(who)[-1]
            self.assertEqual(rec["kind"], "native")
            self.assertEqual(rec["from"], "orch")
            self.assertEqual(rec["to"], "builder")
            self.assertTrue(rec["delivered"])
            self.assertNotIn("body", rec)

    def test_record_native_off_board_only_touches_the_sender(self):
        # Sem alias não existe log do outro lado; omitir seria perder o fato.
        from comms import messages
        messages.record_native("orch", "alguma-sessao", alias=None,
                               delivered=True, msg_id="x")
        rec = messages.log("orch")[-1]
        self.assertEqual(rec["to"], "alguma-sessao")
        self.assertTrue(rec["off_board"])
        self.assertEqual(messages.log("alguma-sessao"), [])

    def test_a_failed_send_is_recorded_as_not_delivered(self):
        # O agente é quem faz o fallback; se esquecer, o esquecimento fica
        # visível aqui em vez de sumir.
        from comms import messages
        messages.record_native("orch", "builder", alias="builder",
                               delivered=False, msg_id="")
        self.assertFalse(messages.log("orch")[-1]["delivered"])
```

- [ ] **Step 2: Rode para confirmar que falha**

Run: `python3 -m unittest tests.test_messages -v -k record_native`
Expected: FAIL com `AttributeError: module 'comms.messages' has no attribute 'record_native'`

- [ ] **Step 3: Implemente**

Em `comms/messages.py`, no fim do arquivo:

```python
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
```

- [ ] **Step 4: Rode e confirme que passa**

Run: `python3 -m unittest tests.test_messages -v -k record_native`
Expected: PASS

- [ ] **Step 5: Teste do `comms log` (hoje ele quebraria)**

Em `tests/test_cli.py`:

```python
    def test_log_renders_a_native_record_without_a_body(self):
        # cmd_log lê m["body"] direto; um registro nativo não tem corpo e
        # levantaria KeyError.
        import os
        from comms import messages
        os.environ["COMMS_ALIAS"] = "orch"
        run("open", "orch")
        messages.record_native("orch", "builder", alias="builder",
                               delivered=True, msg_id="abc")
        code, out = run("log")
        self.assertEqual(code, 0)
        self.assertIn("via nativo", out)

    def test_log_marks_an_undelivered_native_record(self):
        import os
        from comms import messages
        os.environ["COMMS_ALIAS"] = "orch"
        run("open", "orch")
        messages.record_native("orch", "builder", alias="builder",
                               delivered=False, msg_id="")
        _, out = run("log")
        self.assertIn("NÃO ENTREGUE", out)
```

- [ ] **Step 6: Rode, confirme que falha, implemente**

Run: `python3 -m unittest tests.test_cli -v -k native_record`
Expected: FAIL com `KeyError: 'body'`

Em `comms/cli.py`, substitua o corpo de `cmd_log`:

```python
def cmd_log(args) -> int:
    me = resolve_self()
    for m in messages.log(me):
        if m.get("kind") == "native":
            mark = "" if m.get("delivered") else "  ⚠ NÃO ENTREGUE"
            print(f"[{_age(m['ts'])}] {m['from']} → {m['to']}: via nativo{mark}")
        else:
            print(f"[{_age(m['ts'])}] {m['from']}: {m['body']}")
    return 0
```

- [ ] **Step 7: Rode a suíte inteira**

Run: `python3 -m unittest discover -s tests -q`
Expected: OK

- [ ] **Step 8: Commit**

```bash
git add comms/messages.py comms/cli.py tests/test_messages.py tests/test_cli.py
git commit -m "feat: board registra o fato de um envio nativo, sem o corpo"
```

---

### Task 3: o hook que grava

**Files:**
- Create: `hooks/comms-sendmessage-hook.py`
- Test: `tests/test_sendmessage_hook.py`

**Interfaces:**
- Consumes: `presence.read_all()["native_name"]` (Task 1),
  `messages.record_native(...)` (Task 2).
- Produces: script executável que lê o payload do `PostToolUse` no stdin.

**Payload real capturado em 2026-08-11** — use este, não um inventado:

```json
{"hook_event_name": "PostToolUse", "tool_name": "SendMessage",
 "session_id": "<uuid>", "cwd": "/Users/theo/comms",
 "tool_input": {"to": "builder [24374e]", "summary": "...", "message": "..."},
 "tool_response": {"success": true, "message": "...", "msg_id": "9ee4d0d0-..."}}
```

- [ ] **Step 1: Escreva os testes que falham**

Crie `tests/test_sendmessage_hook.py`:

```python
import json, os, shutil, subprocess, sys, tempfile, unittest

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "hooks", "comms-sendmessage-hook.py")

class SendMessageHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        os.makedirs(os.path.join(self.tmp, "sessions"), exist_ok=True)
        from comms import presence, store, paths
        presence.open("orch", session="sess-orch")
        presence.open("builder", session="sess-builder")
        store.write_json(os.path.join(paths.sessions_dir(), "b.json"),
                         {"sessionId": "sess-builder", "pid": os.getpid(),
                          "status": "idle", "name": "builder"})

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, payload):
        # COMMS_ALIAS é removido de propósito: o hook o prefere sobre a busca
        # por session_id, então uma variável vazada de outra suíte faria o
        # teste do remetente-fora-do-board passar pelo motivo errado.
        env = dict(os.environ, COMMS_ROOT=self.tmp)
        env.pop("COMMS_ALIAS", None)
        p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                           text=True, capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def _payload(self, to, success=True, session="sess-orch"):
        return {"hook_event_name": "PostToolUse", "tool_name": "SendMessage",
                "session_id": session, "cwd": self.tmp,
                "tool_input": {"to": to, "message": "oi"},
                "tool_response": {"success": success, "msg_id": "m1"}}

    def test_records_a_delivered_send_on_both_logs(self):
        from comms import messages
        self._run(self._payload("builder [24374e]"))
        self.assertEqual(messages.log("orch")[-1]["to"], "builder")
        self.assertTrue(messages.log("builder")[-1]["delivered"])

    def test_strips_the_ephemeral_ref_before_matching(self):
        # Sem remover " [ref]" nenhum destinatário casaria e todo envio
        # apareceria como fora do board.
        from comms import messages
        self._run(self._payload("builder [abc999]"))
        self.assertFalse(messages.log("orch")[-1]["off_board"])

    def test_a_failed_send_is_recorded_as_undelivered(self):
        from comms import messages
        self._run(self._payload("builder [24374e]", success=False))
        self.assertFalse(messages.log("orch")[-1]["delivered"])

    def test_a_peer_outside_the_board_is_recorded_on_the_sender_only(self):
        from comms import messages
        self._run(self._payload("alguma-sessao [111111]"))
        rec = messages.log("orch")[-1]
        self.assertTrue(rec["off_board"])
        self.assertEqual(rec["to"], "alguma-sessao")

    def test_a_sender_outside_the_board_records_nothing(self):
        from comms import messages
        self._run(self._payload("builder [24374e]", session="sess-desconhecida"))
        self.assertEqual(messages.log("builder"), [])

    def test_another_tool_is_ignored(self):
        from comms import messages
        p = dict(self._payload("builder [24374e]"), tool_name="Bash")
        self._run(p)
        self.assertEqual(messages.log("orch"), [])

    def test_garbage_on_stdin_exits_zero_and_records_nothing(self):
        # Hook que quebra estraga o turno do usuário.
        env = dict(os.environ, COMMS_ROOT=self.tmp)
        for raw in ("", "   ", "{isto não é json"):
            p = subprocess.run([sys.executable, HOOK], input=raw, text=True,
                               capture_output=True, env=env)
            self.assertEqual(p.returncode, 0, raw)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rode para confirmar que falha**

Run: `python3 -m unittest tests.test_sendmessage_hook -v`
Expected: FAIL — o arquivo do hook não existe

- [ ] **Step 3: Implemente o hook**

Crie `hooks/comms-sendmessage-hook.py`:

```python
#!/usr/bin/env python3
"""PostToolUse(SendMessage) → registro no board.

Grava o FATO de um envio nativo, nunca o corpo: o texto trafega pelo
transporte nativo e o board é testemunha. Sai 0 em qualquer erro, porque um
hook que levanta exceção estraga o turno do usuário.
"""
import json, os, re, sys

REF = re.compile(r"\s*\[[0-9a-fA-F]+\]\s*$")

def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name") != "SendMessage":
        return 0

    to_raw = (event.get("tool_input") or {}).get("to") or ""
    # O ref é efêmero e não faz parte da identidade — sem removê-lo nenhum
    # destinatário casaria e todo envio viraria "fora do board".
    to_name = REF.sub("", to_raw).strip()
    if not to_name:
        return 0

    response = event.get("tool_response") or {}
    delivered = bool(response.get("success"))
    msg_id = response.get("msg_id") or ""

    from comms import messages, presence
    entries = presence.read_all()

    session = event.get("session_id") or ""
    sender = os.environ.get("COMMS_ALIAS") or next(
        (e["alias"] for e in entries if e.get("session") == session), None)
    if sender is None:
        return 0        # remetente nunca entrou no board

    alias = next((e["alias"] for e in entries
                  if e.get("native_name") == to_name), None)

    messages.record_native(sender, to_name, alias=alias,
                           delivered=delivered, msg_id=msg_id)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:
        sys.exit(0)
```

- [ ] **Step 4: Torne executável e rode os testes**

```bash
chmod +x hooks/comms-sendmessage-hook.py
python3 -m unittest tests.test_sendmessage_hook -v
```
Expected: PASS em todos

- [ ] **Step 5: Rode a suíte inteira**

Run: `python3 -m unittest discover -s tests -q`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add hooks/comms-sendmessage-hook.py tests/test_sendmessage_hook.py
git commit -m "feat: hook grava o fato de cada SendMessage no board"
```

---

### Task 4: instalar o hook com matcher

O instalador de hoje anexa grupos **sem** matcher. `PostToolUse` precisa de um,
senão o hook roda em toda ferramenta.

**Files:**
- Modify: `hooks/install_hooks.py`
- Test: `tests/test_hook.py`

**Interfaces:**
- Consumes: `hooks/comms-sendmessage-hook.py` (Task 3).

- [ ] **Step 1: Escreva o teste que falha**

Em `tests/test_hook.py`:

```python
    def test_installer_adds_the_sendmessage_hook_with_a_matcher(self):
        # Sem matcher o hook rodaria em TODA chamada de ferramenta.
        import json, os, subprocess, sys, tempfile
        settings = os.path.join(self.tmp, "settings.json")
        with open(settings, "w") as fh:
            json.dump({"hooks": {}}, fh)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(root, "hooks", "install_hooks.py")
        env = dict(os.environ, COMMS_SETTINGS=settings)
        p = subprocess.run([sys.executable, script], env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        cfg = json.load(open(settings))
        groups = cfg["hooks"]["PostToolUse"]
        self.assertTrue(any(g.get("matcher") == "SendMessage" for g in groups))
```

- [ ] **Step 2: Rode para confirmar que falha**

Run: `python3 -m unittest tests.test_hook -v -k sendmessage`
Expected: FAIL com `KeyError: 'PostToolUse'`

- [ ] **Step 3: Implemente**

Em `hooks/install_hooks.py`, substitua o topo e o laço:

```python
SETTINGS = os.environ.get("COMMS_SETTINGS") or os.path.expanduser("~/.claude/settings.json")
HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "comms-hook.py")
SEND_HOOK = os.path.join(HERE, "comms-sendmessage-hook.py")
EVENTS = ["UserPromptSubmit", "Stop", "Notification", "SessionEnd"]
# PostToolUse precisa de matcher: sem ele o hook rodaria em toda ferramenta.
MATCHED = [("PostToolUse", "SendMessage", SEND_HOOK)]
```

E, dentro de `main()`, logo após o laço de `EVENTS`:

```python
    for event, matcher, script in MATCHED:
        groups = hooks.setdefault(event, [])
        existing = [h.get("command") for g in groups for h in g.get("hooks", [])]
        if script in existing:
            continue
        groups.append({"matcher": matcher,
                       "hooks": [{"type": "command", "command": script}]})
        added.append(f"{event}({matcher})")
```

- [ ] **Step 4: Rode e confirme que passa**

Run: `python3 -m unittest tests.test_hook -v -k sendmessage`
Expected: PASS

- [ ] **Step 5: Rode a suíte inteira**

Run: `python3 -m unittest discover -s tests -q`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add hooks/install_hooks.py tests/test_hook.py
git commit -m "feat: instalador registra o hook de SendMessage com matcher"
```

---

### Task 5: a skill ensina o transporte

Sem isto nada acima é usado, e o texto atual passa a mentir sobre `CAMPAINHA`.

**Files:**
- Modify: `skills/open-comms/SKILL.md`

- [ ] **Step 1: Substitua a seção de roteamento**

Em `skills/open-comms/SKILL.md`, depois do bloco de rotas, substitua o texto que
hoje explica `surda` e `foi-embora` por:

```markdown
## Sending: native first, comms when it fails

Send with `SendMessage`. Run `comms who` to choose the alias, then `ListAgents`
to get its ` [ref]` — the ref is ephemeral, so read it fresh every time and
never store it.

If `SendMessage` comes back `success: false`, the peer is unreachable — most
often a session being replaced by a handoff. Fall back to `comms post --to
<alias>`, which lands in a durable inbox the successor will read.

Broadcast has no native equivalent: `comms post` with no `--to` stays the way
to reach everyone.

Every send is recorded on the board automatically, without its body. A failed
send you never followed up on shows in `comms log` as `⚠ NÃO ENTREGUE`.

## Reading the board

- **ESTADO `foi-embora`** — the session is gone. Nothing reaches it. Take it to
  `theo` or to `orch`.
- **CAMPAINHA `surda`** — its doorbell is not armed. Native messages still get
  through; only the comms path (fallbacks, broadcasts) waits for it to re-arm.
```

- [ ] **Step 2: Confirme que nenhum texto antigo contradiz o novo**

Run: `grep -n "stale\|não vai receber\|will not receive" skills/open-comms/SKILL.md`
Expected: nenhuma linha afirmando que `surda` não recebe mensagem

- [ ] **Step 3: Rode a suíte e o e2e**

```bash
python3 -m unittest discover -s tests -q
bash tests/test_e2e.sh
```
Expected: OK e `E2E OK`

- [ ] **Step 4: Commit**

```bash
git add skills/open-comms/SKILL.md
git commit -m "docs: skill ensina nativo primeiro, e corrige o que surda significa"
```

---

## Verificação manual, uma vez, no fim

Não substitui os testes; confirma a fiação que só existe fora deles.

1. `python3 hooks/install_hooks.py` e confirme `PostToolUse(SendMessage)` na
   saída.
2. De uma sessão no board, mande um `SendMessage` para outra.
3. `comms log` nos dois lados deve mostrar `→ ... via nativo`.
4. Mande para um nome inexistente e confirme `⚠ NÃO ENTREGUE` no log do
   remetente.
