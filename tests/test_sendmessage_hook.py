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
