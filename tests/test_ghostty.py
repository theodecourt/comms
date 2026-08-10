# tests/test_ghostty.py — script generation only; no AppleScript is executed
import unittest
from unittest import mock

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
        self.assertIn('claude \\"$B\\"', script)

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
        path = re.search(r"head -1 '([^']+)'", line).group(1)
        try:
            # first line is the display name (empty here), body follows
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "\nVocê é ção — ok")
        finally:
            os.unlink(path)

if __name__ == "__main__":
    unittest.main()
