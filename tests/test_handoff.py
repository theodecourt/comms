import io, os, shutil, tempfile, unittest
from contextlib import redirect_stdout


def builtins_read(path):
    with open(path) as fh:
        return fh.read()


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        # never let a test reach the real Obsidian vault: run() writes
        # a note there and pushes it. Structural, not a reminder.
        os.environ["COMMS_VAULT"] = os.path.join(self.tmp, "vault")
        self.repo = tempfile.mkdtemp()
        from comms import presence
        presence.open("orch", note="coordenando", cwd=self.repo)
        presence.open("front", cwd=self.repo)

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_VAULT", "COMMS_ALIAS",
                  "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_doc_path_lands_in_scratchpad(self):
        from comms import handoff
        p = handoff.doc_path(self.repo, "orch", "2026-08-01")
        self.assertTrue(p.startswith(os.path.join(self.repo, "scratchpad")))
        self.assertIn("2026-08-01", p)
        self.assertIn("orch", p)

    def test_write_doc_creates_file_with_body(self):
        from comms import handoff
        p = handoff.doc_path(self.repo, "orch", "2026-08-01")
        handoff.write_doc(p, "orch", "coordenando", "estado atual: X")
        self.assertIn("estado atual: X", builtins_read(p))

    def test_run_spawns_successor_and_broadcasts(self):
        from comms import handoff, messages
        calls = []
        with redirect_stdout(io.StringIO()):
            handoff.run("orch", "estado", "2026-08-01",
                        spawn_fn=lambda **kw: calls.append(kw))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["alias"], "orch")
        self.assertIn("handoff", calls[0]["briefing"].lower())
        self.assertTrue(any("handoff" in m["body"].lower()
                            for m in messages.inbox("front")))

    def test_run_returns_readable_doc(self):
        from comms import handoff
        with redirect_stdout(io.StringIO()):
            p = handoff.run("orch", "estado atual", "2026-08-01", spawn_fn=lambda **kw: None)
        self.assertIn("estado atual", builtins_read(p))

    def test_run_raises_and_preserves_board_when_spawn_reports_failure(self):
        from comms import handoff, messages, presence
        # run() prints the failure before raising; capture it so the suite's
        # output stays pristine, and assert on it while we have it.
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit):
            handoff.run("orch", "estado", "2026-08-01",
                        spawn_fn=lambda **kw: False)
        self.assertIn("continua no board", buf.getvalue())
        # old presence entry survives — the fleet must not believe orch is gone
        self.assertTrue(any(e["alias"] == "orch" for e in presence.read_all()))
        # no broadcast went out announcing a swap that never happened
        self.assertEqual(messages.inbox("front"), [])


    def test_writes_a_vault_note_with_archive_frontmatter(self):
        from comms import handoff
        vault = os.environ["COMMS_VAULT"]
        with redirect_stdout(io.StringIO()):
            handoff.run("orch", "estado do ciclo", "2026-08-10", spawn_fn=lambda **kw: True)
        notes = [f for f in os.listdir(vault) if f.endswith(".md")]
        self.assertEqual(len(notes), 1)
        text = builtins_read(os.path.join(vault, notes[0]))
        self.assertIn("date: 2026-08-10", text)
        self.assertIn("tags: [claude-session, handoff,", text)
        self.assertIn("estado do ciclo", text)

    def test_vault_note_does_not_overwrite_a_same_day_one(self):
        from comms import handoff, presence
        vault = os.environ["COMMS_VAULT"]
        with redirect_stdout(io.StringIO()):
            handoff.run("orch", "primeiro", "2026-08-10", spawn_fn=lambda **kw: True)
            presence.open("orch", note="de novo", cwd=self.repo)
            handoff.run("orch", "segundo", "2026-08-10", spawn_fn=lambda **kw: True)
        self.assertEqual(len([f for f in os.listdir(vault) if f.endswith(".md")]), 2)

    def test_successor_is_named_with_novo(self):
        from comms import handoff
        from unittest import mock
        seen = {}
        with mock.patch("comms.session.name_for", return_value="ORCH-COLETA"), \
             redirect_stdout(io.StringIO()):
            handoff.run("orch", "estado", "2026-08-10",
                        spawn_fn=lambda **kw: seen.update(kw) or True)
        self.assertEqual(seen["name"], "ORCH-COLETA-novo")

if __name__ == "__main__":
    unittest.main()
