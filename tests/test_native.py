import json, os, shutil, tempfile, unittest

class NativeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        os.makedirs(os.path.join(self.tmp, "sessions"), exist_ok=True)

    def tearDown(self):
        os.environ.pop("COMMS_ROOT", None)
        os.environ.pop("COMMS_SESSIONS_DIR", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, text):
        with open(os.path.join(self.tmp, "sessions", name), "w") as fh:
            fh.write(text)

    def test_missing_registry_reads_as_empty_not_as_an_error(self):
        from comms import native
        os.environ["COMMS_SESSIONS_DIR"] = os.path.join(self.tmp, "nope")
        self.assertEqual(native.sessions(), {})

    def test_sessions_are_keyed_by_session_id(self):
        from comms import native
        self._write("63696.json", json.dumps(
            {"sessionId": "sess-a", "pid": 1, "status": "busy"}))
        self.assertEqual(native.sessions()["sess-a"]["status"], "busy")

    def test_junk_in_the_registry_is_skipped_not_fatal(self):
        # Valid JSON that just is not a usable record — a list, an object
        # with no sessionId, a non-.json file — is ordinary noise, not
        # evidence that anything is broken, so it must not touch the result.
        from comms import native
        self._write("good.json", json.dumps({"sessionId": "sess-a", "pid": 1}))
        self._write("a-list.json", "[1, 2, 3]")
        self._write("no-session-id.json", json.dumps({"pid": 7}))
        self._write("notes.txt", "ignored")
        self.assertEqual(list(native.sessions()), ["sess-a"])

    def test_a_file_that_fails_to_parse_degrades_the_whole_read(self):
        # Unlike the junk above, a half-written file is not something comms
        # can tell apart from a session mid-write by Claude Code — the exact
        # case this registry exists to answer correctly. Skipping only that
        # one file would let every OTHER record look fully trustworthy,
        # including reporting the mid-write session itself as gone by
        # omission. One bad file has to cost the whole answer.
        from comms import native
        self._write("good.json", json.dumps({"sessionId": "sess-a", "pid": 1}))
        self._write("half-written.json", '{"sessionId": "sess-b"')
        self.assertEqual(native.sessions(), {})

    def test_pid_alive_on_this_very_process(self):
        from comms import native
        self.assertTrue(native.pid_alive(os.getpid()))

    def test_pid_alive_is_false_for_a_dead_or_bogus_pid(self):
        from comms import native
        self.assertFalse(native.pid_alive(2 ** 31 - 1))
        self.assertFalse(native.pid_alive(None))
        self.assertFalse(native.pid_alive("not-a-pid"))

    def test_liveness_is_true_for_this_process(self):
        from comms import native
        self.assertIs(native.liveness(os.getpid()), True)

    def test_liveness_is_false_for_a_real_but_dead_pid(self):
        from comms import native
        self.assertIs(native.liveness(2 ** 31 - 1), False)

    def test_liveness_is_none_without_a_usable_pid(self):
        # A record with no pid, or a bogus one, is a gap in the registry, not
        # proof of death — pid_alive's own False for these would tell
        # presence.read_all() a live session had gone, which is the exact
        # misread this helper exists to prevent.
        from comms import native
        self.assertIsNone(native.liveness(None))
        self.assertIsNone(native.liveness("not-a-pid"))

if __name__ == "__main__":
    unittest.main()
