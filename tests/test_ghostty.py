# tests/test_ghostty.py — script generation only; no AppleScript is executed
import unittest

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

if __name__ == "__main__":
    unittest.main()
