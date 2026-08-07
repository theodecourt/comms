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
        for k in ("COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
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

    def test_who_marks_stale_entries(self):
        from comms import presence, store, paths
        import time
        run("open", "infra")
        e = store.read_json(paths.presence_file("infra"))
        e["last_seen"] = time.time() - 999
        store.write_json(paths.presence_file("infra"), e)
        _, out = run("who")
        self.assertIn("stale", out.lower())

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

if __name__ == "__main__":
    unittest.main()
