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

    def _stop_the_doorbell(self, alias):
        from comms import store, paths
        import time
        e = store.read_json(paths.presence_file(alias))
        e["last_seen"] = time.time() - 999
        store.write_json(paths.presence_file(alias), e)

    def test_who_reports_an_unarmed_doorbell_as_surda(self):
        # A dead doorbell means "will not be woken by a message", which is
        # about reachability — not about whether the agent is still there.
        run("open", "infra")
        self._stop_the_doorbell("infra")
        _, out = run("who")
        self.assertIn("surda", out)
        self.assertNotIn("foi-embora", out)

    def test_who_separates_a_dead_agent_from_a_deaf_one(self):
        # The whole point of the split: these two rows used to be identical,
        # yet a sender should wait for one and give up on the other.
        import json, os
        from comms import store, paths
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-deaf"
        run("open", "deaf")
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-gone"
        run("open", "gone")
        for alias in ("deaf", "gone"):
            self._stop_the_doorbell(alias)
        # Only `deaf` is still in the registry, and on a pid that exists.
        store.write_json(os.path.join(paths.sessions_dir(), "1.json"),
                         {"sessionId": "sess-deaf", "pid": os.getpid(),
                          "status": "busy"})
        _, out = run("who")
        deaf = [l for l in out.splitlines() if l.startswith("deaf")][0]
        gone = [l for l in out.splitlines() if l.startswith("gone")][0]
        self.assertIn("surda", deaf)
        self.assertNotIn("foi-embora", deaf)
        self.assertIn("foi-embora", gone)

    def test_wait_is_bounded_by_default(self):
        # An unbounded doorbell that gets reaped leaves an empty output the
        # agent has to interpret; a bound makes the common case say why.
        from unittest import mock
        from comms import cli, doorbell
        os.environ["COMMS_ALIAS"] = "orch"
        run("open", "orch")
        with mock.patch.object(doorbell, "wait", return_value="timeout") as w:
            run("wait")
        self.assertEqual(w.call_args.kwargs["max_seconds"],
                         cli.DEFAULT_WAIT_SECONDS)

    def test_wait_zero_restores_the_unbounded_wait(self):
        from unittest import mock
        from comms import cli, doorbell
        os.environ["COMMS_ALIAS"] = "orch"
        run("open", "orch")
        with mock.patch.object(doorbell, "wait", return_value="mail") as w:
            run("wait", "--max-seconds", "0")
        self.assertIsNone(w.call_args.kwargs["max_seconds"])

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


if __name__ == "__main__":
    unittest.main()
