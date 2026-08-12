import io, os, shutil, tempfile, unittest
from contextlib import redirect_stdout

def run(*args):
    from comms import cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(args))
    return code, buf.getvalue()

class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        # never let a test reach the real Obsidian vault: run() writes
        # a note there and pushes it. Structural, not a reminder.
        os.environ["COMMS_VAULT"] = os.path.join(self.tmp, "vault")
        for k in ("COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_VAULT", "COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_open_then_who_lists_the_alias(self):
        run("open", "orch", "--note", "coordenando")
        code, out = run("who")
        self.assertEqual(code, 0)
        self.assertIn("orch", out)
        self.assertIn("coordenando", out)

    def test_open_rejects_invalid_alias(self):
        code, out = run("open", "BUILDER #1")
        self.assertEqual(code, 2)
        self.assertIn("alias", out.lower())

    def test_who_has_no_bell_column(self):
        # The bell reported whether a `comms wait` was armed. There is no
        # `comms wait` any more: native sends need no doorbell, and comms-path
        # mail surfaces through the hook at the agent's next turn.
        run("open", "infra")
        _, out = run("who")
        self.assertNotIn("CAMPAINHA", out)
        self.assertNotIn("surda", out)
        self.assertNotIn("armada", out)

    def test_there_is_no_wait_command(self):
        # A command that exists gets used. Removing it is what makes "no
        # doorbell for any session" true rather than merely recommended.
        # argparse rejects an unknown subcommand inside parse_args, before
        # main()'s own SystemExit handler, so it propagates rather than
        # becoming a return code.
        import contextlib, io
        from comms import cli
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()):
            cli.main(["wait"])

    def test_who_still_reports_a_dead_agent(self):
        # Liveness comes from Claude Code's session registry, not from the
        # heartbeat, so removing the bell must not cost us this.
        import os
        from comms import store, paths
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-alive"
        run("open", "vivo")
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-gone"
        run("open", "gone")
        store.write_json(os.path.join(paths.sessions_dir(), "1.json"),
                         {"sessionId": "sess-alive", "pid": os.getpid(),
                          "status": "busy"})
        _, out = run("who")
        vivo = [l for l in out.splitlines() if l.startswith("vivo")][0]
        gone = [l for l in out.splitlines() if l.startswith("gone")][0]
        self.assertNotIn("foi-embora", vivo)
        self.assertIn("foi-embora", gone)

    def test_a_long_native_name_keeps_both_ends(self):
        # This column is an addressing key matched against ListAgents. Cutting
        # the tail forced an agent to guess by prefix in a real test on
        # 2026-08-12; keeping head and tail leaves the name recognisable.
        from comms import cli
        out = cli._trunc("joao-claude-setup-skills-commands-e-mais-coisa", 34)
        self.assertEqual(len(out), 34)
        self.assertTrue(out.startswith("joao-claude"))
        self.assertTrue(out.endswith("coisa"))

    def test_post_and_inbox_roundtrip(self):
        run("open", "orch")
        run("open", "front")
        os.environ["COMMS_ALIAS"] = "orch"
        run("post", "--to", "front", "implementa")
        os.environ["COMMS_ALIAS"] = "front"
        code, out = run("inbox")
        self.assertEqual(code, 0)
        self.assertIn("implementa", out)
        self.assertIn("orch", out)

    def test_commands_fail_clearly_without_identity(self):
        run("open", "orch")
        code, out = run("post", "--to", "orch", "oi")
        self.assertEqual(code, 2)
        self.assertIn("comms open", out)

    def test_close_removes_from_who(self):
        run("open", "front")
        os.environ["COMMS_ALIAS"] = "front"
        run("close")
        _, out = run("who")
        self.assertNotIn("front", out)

    def test_who_is_friendly_when_board_is_empty(self):
        code, out = run("who")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip())

    def test_handoff_reports_alias_not_on_board(self):
        # No `open` was ever run for this alias — it is simply not on the
        # board. The CLI must print why, not just exit non-zero silently.
        os.environ["COMMS_ALIAS"] = "fantasma"
        code, out = run("handoff", "estado qualquer")
        self.assertNotEqual(code, 0)
        self.assertIn("não está no board", out)

    def test_handoff_reports_spawn_failure_and_keeps_old_session_on_board(self):
        from comms import presence
        from unittest import mock
        repo = tempfile.mkdtemp()
        try:
            presence.open("orch", note="coordenando", cwd=repo)
            os.environ["COMMS_ALIAS"] = "orch"
            # The temp repo has never been opened in Claude Code, so the
            # trust-dialog guard would fire first. Neutralise it — this test
            # is about the spawn-failure path, which sits after that guard.
            with mock.patch("comms.ghostty.spawn", return_value=False), \
                 mock.patch("comms.ghostty.is_trusted_dir", return_value=True):
                code, out = run("handoff", "estado atual")
            self.assertNotEqual(code, 0)
            self.assertIn("continua no board", out)
            self.assertTrue(any(e["alias"] == "orch" for e in presence.read_all()))
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_handoff_refuses_untrusted_dir_before_touching_the_board(self):
        from comms import presence
        from unittest import mock
        repo = tempfile.mkdtemp()
        try:
            presence.open("orch", note="coordenando", cwd=repo)
            os.environ["COMMS_ALIAS"] = "orch"
            with mock.patch("comms.ghostty.is_trusted_dir", return_value=False):
                code, out = run("handoff", "estado atual")
            self.assertNotEqual(code, 0)
            self.assertIn("nunca foi aberto", out)
            # the board must be untouched: losing orch is the whole risk here
            self.assertTrue(any(e["alias"] == "orch" for e in presence.read_all()))
            self.assertFalse(os.path.isdir(os.path.join(repo, "scratchpad")))
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_spawn_refuses_untrusted_dir(self):
        from unittest import mock
        with mock.patch("comms.ghostty.is_trusted_dir", return_value=False):
            code, out = run("spawn", "build-1", "--cwd", "/tmp", "--briefing", "oi")
        self.assertEqual(code, 2)
        self.assertIn("nunca foi aberto", out)

    def test_who_shows_the_native_name_for_addressing(self):
        # É por esse nome que o agente endereça o SendMessage; sem ele o board
        # diz com quem falar e não diz como.
        from comms import store, paths
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-front"
        run("open", "front")
        store.write_json(os.path.join(paths.sessions_dir(), "1.json"),
                         {"sessionId": "sess-front", "pid": os.getpid(),
                          "status": "busy", "name": "front-tab"})
        _, out = run("who")
        self.assertIn("front-tab", out)

    def test_a_real_derived_name_fits_without_truncation(self):
        # `joao-claude-setup-skills-commands` (33 chars) is what a manually
        # joined session actually gets on this machine. The column is sized so
        # the common case is shown whole — truncating it was what forced an
        # agent to match by prefix.
        from comms import store, paths
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-front"
        run("open", "front")
        real_name = "joao-claude-setup-skills-commands"
        store.write_json(os.path.join(paths.sessions_dir(), "1.json"),
                         {"sessionId": "sess-front", "pid": os.getpid(),
                          "status": "busy", "name": real_name})
        _, out = run("who")
        line = [l for l in out.splitlines() if l.startswith("front")][0]
        self.assertIn(real_name, line)

    def test_who_keeps_columns_aligned_past_the_name_width(self):
        # Padding without truncating pushes VISTO and NOTA out of alignment
        # for every row, so a name past the column width still has to be cut.
        from comms import cli, store, paths
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-front"
        run("open", "front")
        long_name = "x" * (cli.NATIVE_NAME_WIDTH + 20)
        store.write_json(os.path.join(paths.sessions_dir(), "1.json"),
                         {"sessionId": "sess-front", "pid": os.getpid(),
                          "status": "busy", "name": long_name})
        _, out = run("who")
        header, line = out.splitlines()[0], \
            [l for l in out.splitlines() if l.startswith("front")][0]
        self.assertIn("…", line)
        visto_col = header.index("VISTO")
        self.assertEqual(line[visto_col:visto_col + 5], "agora")

    def test_log_renders_a_native_record_without_a_body(self):
        # cmd_log lê m["body"] direto; um registro nativo não tem corpo e
        # levantaria KeyError.
        from comms import messages
        os.environ["COMMS_ALIAS"] = "orch"
        run("open", "orch")
        messages.record_native("orch", "builder", alias="builder",
                               delivered=True, msg_id="abc")
        code, out = run("log")
        self.assertEqual(code, 0)
        self.assertIn("via nativo", out)

    def test_log_marks_an_undelivered_native_record(self):
        from comms import messages
        os.environ["COMMS_ALIAS"] = "orch"
        run("open", "orch")
        messages.record_native("orch", "builder", alias="builder",
                               delivered=False, msg_id="")
        _, out = run("log")
        self.assertIn("NÃO ENTREGUE", out)


if __name__ == "__main__":
    unittest.main()
