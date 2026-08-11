# tests/test_ghostty.py — script generation only; no AppleScript is executed
import os, shutil, tempfile, unittest
from unittest import mock

class WaitForSessionTest(unittest.TestCase):
    """Focus must stay on the spawned tab until its SessionStart hook ran."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp      # drags the sessions dir along
        os.makedirs(os.path.join(self.tmp, "sessions"), exist_ok=True)

    def tearDown(self):
        os.environ.pop("COMMS_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _register(self, sid, cwd):
        from comms import store, paths
        store.write_json(os.path.join(paths.sessions_dir(), sid + ".json"),
                         {"sessionId": sid, "cwd": cwd, "pid": os.getpid()})

    def test_returns_true_once_the_new_session_registers(self):
        from comms import ghostty
        self._register("sess-new", "/tmp/repo")
        self.assertTrue(ghostty.wait_for_session("/tmp/repo", set(), settle=0))

    def test_times_out_when_nothing_ever_registers(self):
        # False must still let the caller restore focus — a session that never
        # starts must not strand the user's focus on a dead tab.
        from comms import ghostty
        self.assertFalse(
            ghostty.wait_for_session("/tmp/repo", set(), timeout=0.3, settle=0))

    def test_a_session_that_was_already_there_does_not_count(self):
        # Otherwise the spawning session itself satisfies the wait instantly,
        # which is exactly the bug: same repo, same cwd, wrong tab.
        from comms import ghostty
        self._register("sess-old", "/tmp/repo")
        self.assertFalse(ghostty.wait_for_session(
            "/tmp/repo", {"sess-old"}, timeout=0.3, settle=0))

    def test_a_new_session_in_another_repo_does_not_count(self):
        from comms import ghostty
        self._register("sess-elsewhere", "/tmp/other")
        self.assertFalse(ghostty.wait_for_session(
            "/tmp/repo", set(), timeout=0.3, settle=0))

    def test_a_record_with_no_cwd_never_counts(self):
        # os.path.realpath("") resolves to the CURRENT directory, which
        # equals `target` whenever spawning into this process's own cwd —
        # the common case. Without the guard, any unrelated new session
        # missing `cwd` would satisfy the wait instantly.
        from comms import ghostty, store, paths
        store.write_json(os.path.join(paths.sessions_dir(), "sess-nocwd.json"),
                         {"sessionId": "sess-nocwd", "pid": os.getpid()})
        self.assertFalse(ghostty.wait_for_session(
            os.getcwd(), set(), timeout=0.3, settle=0))

    def test_spawn_waits_before_restoring_focus(self):
        from comms import ghostty
        order = []
        rows = [{"window": "w1", "terminal": "t-prev", "cwd": "/tmp/repo",
                 "selected": True, "front_window": "w1"}]

        def fake_osascript(script):
            order.append("restore" if "activate window" in script else "script")
            return True, ""

        with mock.patch.object(ghostty, "list_terminals", return_value=rows), \
             mock.patch.object(ghostty, "_osascript", side_effect=fake_osascript), \
             mock.patch.object(ghostty, "wait_for_session",
                               side_effect=lambda *a, **k: order.append("wait")):
            ghostty.spawn("front", "/tmp/repo", "leia o plano")

        self.assertIn("wait", order)
        self.assertIn("restore", order)
        self.assertLess(order.index("wait"), order.index("restore"),
                        "o foco voltou antes de a sessão nova registrar sua aba")

    def test_spawn_does_not_wait_when_the_spawn_itself_failed(self):
        # A spawn that already failed — Ghostty not running, Automation
        # permission denied — has no tab to wait for. Waiting anyway would
        # hold the caller for the full 30s timeout before it could report
        # the error that already happened.
        from comms import ghostty
        rows = [{"window": "w1", "terminal": "t-prev", "cwd": "/tmp/repo",
                 "selected": True, "front_window": "w1"}]

        with mock.patch.object(ghostty, "list_terminals", return_value=rows), \
             mock.patch.object(ghostty, "_osascript", return_value=(False, "")), \
             mock.patch.object(ghostty, "wait_for_session") as wait:
            ok = ghostty.spawn("front", "/tmp/repo", "leia o plano")

        self.assertFalse(ok)
        wait.assert_not_called()


class GhosttyScriptTest(unittest.TestCase):
    def test_spawn_script_carries_all_four_fields(self):
        from comms import ghostty
        s = ghostty.build_spawn_script(
            cwd="/Users/theo/segura/segura-api", command="claude",
            initial_input="você é o front", env=["COMMS_ALIAS=front"],
            window="tab-group-1")
        self.assertIn("initial working directory:\"/Users/theo/segura/segura-api\"", s)
        self.assertIn("command:\"claude\"", s)
        self.assertIn("COMMS_ALIAS=front", s)
        self.assertIn("você é o front", s)
        self.assertIn("tab-group-1", s)

    def test_spawn_script_opens_new_window_when_no_target(self):
        from comms import ghostty
        s = ghostty.build_spawn_script(cwd="/tmp", command="claude",
                                       initial_input="oi", env=[], window=None)
        self.assertIn("new window", s)
        self.assertNotIn("new tab in", s)

    def test_quotes_are_escaped(self):
        from comms import ghostty
        s = ghostty.build_spawn_script(cwd="/tmp", command="claude",
                                       initial_input='diga "olá"', env=[], window=None)
        self.assertIn('\\"olá\\"', s)

    def test_restore_orders_tab_before_window(self):
        from comms import ghostty
        s = ghostty.build_restore_script(target_window="w1",
                                         prev_terminal="T1", front_window="w2")
        self.assertLess(s.index("select tab"), s.index("activate window"))

    def test_window_for_cwd_matches_by_directory(self):
        from comms import ghostty
        rows = [{"window": "w1", "terminal": "t1", "cwd": "/a", "selected": True},
                {"window": "w2", "terminal": "t2", "cwd": "/b", "selected": True}]
        self.assertEqual(ghostty.window_for_cwd("/b", rows), "w2")
        self.assertIsNone(ghostty.window_for_cwd("/zzz", rows))

    def test_briefing_with_newline_quote_and_backslash_is_safe(self):
        # Self-review case: a briefing containing a newline, a quote, and a
        # backslash together. _esc must escape backslashes BEFORE quotes —
        # doing it the other way round would double-escape the quote's own
        # backslash and corrupt the AppleScript string literal. The literal
        # newline is left as-is: AppleScript string literals tolerate a raw
        # line break between the quotes (this is the same reason LIST_SCRIPT
        # and build_restore_script are written as multi-line strings passed
        # whole to a single `-e`).
        from comms import ghostty
        tricky = 'linha 1\nele disse "oi" \\ ok'
        s = ghostty.build_spawn_script(cwd="/tmp", command="claude",
                                       initial_input=tricky, env=[], window=None)
        self.assertIn('linha 1\nele disse \\"oi\\" \\\\ ok', s)

    def test_spawn_returns_false_when_osascript_fails(self):
        # _osascript never runs for real here — it's monkeypatched to report
        # the failure pair a caller would see if Ghostty weren't running or
        # Automation permission were denied.
        from comms import ghostty
        with mock.patch.object(ghostty, "_osascript", return_value=(False, "")):
            self.assertFalse(ghostty.spawn("front", "/tmp", "oi"))

    def test_spawn_returns_true_when_osascript_succeeds(self):
        from comms import ghostty
        with mock.patch.object(ghostty, "_osascript", return_value=(True, "")):
            self.assertTrue(ghostty.spawn("front", "/tmp", "oi"))

    def test_list_terminals_empty_when_osascript_fails(self):
        from comms import ghostty
        with mock.patch.object(ghostty, "_osascript", return_value=(False, "")):
            self.assertEqual(ghostty.list_terminals(), [])

    def test_falsy_command_omits_the_command_field(self):
        # Ghostty runs a configured `command` under `bash --noprofile --norc`,
        # which strips ~/.local/bin from PATH: `claude` is not found and the
        # spawned session could not run `comms` either. Omitting the field
        # gets the default login shell instead. Measured 2026-08-10.
        from comms import ghostty
        s = ghostty.build_spawn_script(cwd="/tmp", command=None,
                                       initial_input="oi", env=[], window=None)
        self.assertNotIn("command:", s)
        self.assertIn('initial working directory:"/tmp"', s)

    def test_shell_quote_survives_single_quotes(self):
        from comms import ghostty
        self.assertEqual(ghostty.shell_quote("ab"), "'ab'")
        # a briefing containing an apostrophe must not break out of the quoting
        self.assertEqual(ghostty.shell_quote("it's"), "'it'\\''s'")

    def test_spawn_launches_claude_from_the_shell_not_from_command(self):
        from comms import ghostty
        # spawn() calls _osascript more than once (the terminal listing comes
        # first), so collect every script and pick the one that spawns.
        scripts = []

        def fake(script):
            scripts.append(script)
            return True, ""

        with mock.patch.object(ghostty, "_osascript", side_effect=fake):
            ghostty.spawn("front", "/tmp", "leia o plano")
        spawn_scripts = [s for s in scripts if "with configuration" in s]
        self.assertEqual(len(spawn_scripts), 1)
        script = spawn_scripts[0]
        self.assertNotIn("command:", script)
        # the double quotes are AppleScript-escaped by the time they land here
        self.assertIn('claude -n \'front\' \\"$B\\"', script)

    def test_spawn_names_the_native_session_after_the_alias(self):
        # Without -n, Claude Code auto-names the session after its directory
        # (measured: a `probe` spawned in ~/comms came up as `comms-9d`), so
        # ListAgents and `comms who` named the same agent differently and no
        # peer could address it by the alias the board shows.
        from comms import ghostty
        line = ghostty._briefing_launch("leia o plano", "front")
        self.assertIn("claude -n 'front' \"$B\"", line)
        self.assertTrue(line.isascii())

    def test_spawn_without_an_alias_omits_the_name_flag(self):
        from comms import ghostty
        line = ghostty._briefing_launch("leia o plano")
        self.assertNotIn(" -n ", line)
        self.assertIn('claude "$B"', line)

    def test_accented_briefing_never_reaches_the_applescript(self):
        # Ghostty's `input text` reads UTF-8 bytes as Latin-1 and re-encodes:
        # "ê" (c3 aa) arrives as c3 83 c2 aa. Measured 2026-08-10 against a
        # real spawn. The briefing therefore travels via a UTF-8 file and only
        # ASCII crosses the boundary — assert exactly that.
        from comms import ghostty
        scripts = []
        with mock.patch.object(ghostty, "_osascript",
                               side_effect=lambda s: (scripts.append(s), (True, ""))[1]):
            ghostty.spawn("front", "/tmp", "Você é o agente — não altere nada")
        script = [s for s in scripts if "with configuration" in s][0]
        self.assertTrue(script.isascii(), "o script AppleScript precisa ser ASCII puro")
        self.assertNotIn("Você", script)

    def test_briefing_file_holds_the_accented_text_intact(self):
        import os, re
        from comms import ghostty
        line = ghostty._briefing_launch("Você é ção — ok")
        self.assertTrue(line.isascii())
        path = re.search(r"cat '([^']+)'", line).group(1)
        try:
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "Você é ção — ok")
        finally:
            os.unlink(path)

    def test_window_for_cwd_falls_back_to_the_nearest_ancestor(self):
        # A session working in <repo>/scratchpad/foo belongs in the window
        # already open on <repo> — exact-match-only gave every such session
        # its own window (observed 2026-08-10 with the `ai` session).
        from comms import ghostty
        rows = [{"window": "w-repo", "terminal": "t1",
                 "cwd": "/Users/theo/segura/segura-intelligence", "selected": True}]
        self.assertEqual(
            ghostty.window_for_cwd(
                "/Users/theo/segura/segura-intelligence/scratchpad/helena", rows),
            "w-repo")

    def test_window_for_cwd_prefers_the_deepest_ancestor(self):
        from comms import ghostty
        rows = [{"window": "w-shallow", "terminal": "t1", "cwd": "/Users/theo/segura",
                 "selected": True},
                {"window": "w-deep", "terminal": "t2",
                 "cwd": "/Users/theo/segura/segura-api", "selected": True}]
        self.assertEqual(
            ghostty.window_for_cwd("/Users/theo/segura/segura-api/app", rows), "w-deep")

    def test_window_for_cwd_does_not_match_a_sibling_sharing_a_prefix(self):
        # "/a/segura-api" must not be treated as an ancestor of
        # "/a/segura-api-experiments" just because the string starts the same.
        from comms import ghostty
        rows = [{"window": "w1", "terminal": "t1", "cwd": "/a/segura-api",
                 "selected": True}]
        self.assertIsNone(ghostty.window_for_cwd("/a/segura-api-experiments", rows))

    def test_exact_match_still_wins(self):
        from comms import ghostty
        rows = [{"window": "w-parent", "terminal": "t1", "cwd": "/a", "selected": True},
                {"window": "w-exact", "terminal": "t2", "cwd": "/a/b", "selected": True}]
        self.assertEqual(ghostty.window_for_cwd("/a/b", rows), "w-exact")

    def test_list_script_does_not_use_a_bare_tab_separator(self):
        # Inside `tell application "Ghostty"` the word `tab` resolves to
        # Ghostty's own tab CLASS, not the AppleScript tab character: the
        # script emitted the literal text "tab", every row failed to parse,
        # list_terminals() returned empty, and every spawn silently opened a
        # new window with no focus restore. Measured 2026-08-10.
        from comms import ghostty
        import re
        self.assertIsNone(re.search(r"&\s*tab\s*&", ghostty.LIST_SCRIPT),
                          "LIST_SCRIPT voltou a usar `tab` como separador")
        self.assertIn('"|:|"', ghostty.LIST_SCRIPT)

    def test_list_terminals_parses_the_separator_it_emits(self):
        # Guards the parser and the script against drifting apart.
        from comms import ghostty
        row = "w1|:|t1|:|/a/b|:|1|:|wfront"
        with mock.patch.object(ghostty, "_osascript", return_value=(True, row)):
            parsed = ghostty.list_terminals()
        self.assertEqual(parsed, [{"window": "w1", "terminal": "t1", "cwd": "/a/b",
                                   "selected": True, "front_window": "wfront"}])

if __name__ == "__main__":
    unittest.main()
