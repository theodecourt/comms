import os, shutil, tempfile, time, unittest

class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        for k in ("COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ.pop("COMMS_ROOT", None)
        os.environ.pop("COMMS_ALIAS", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_role_is_derived_from_alias(self):
        from comms import presence
        self.assertEqual(presence.role_for("orch"), "orchestrator")
        self.assertEqual(presence.role_for("front"), "builder")

    def test_alias_validation_rejects_spaces_and_hash(self):
        from comms import presence
        self.assertTrue(presence.valid_alias("build-1"))
        self.assertFalse(presence.valid_alias("BUILDER #1"))
        self.assertFalse(presence.valid_alias("has space"))
        self.assertFalse(presence.valid_alias(""))

    def test_open_writes_entry_with_defaults(self):
        from comms import presence
        e = presence.open("front", note="no CardModal")
        self.assertEqual(e["alias"], "front")
        self.assertEqual(e["role"], "builder")
        self.assertEqual(e["note"], "no CardModal")
        self.assertEqual(e["status"], "idle")
        self.assertIn("last_seen", e)

    def test_touch_updates_status_and_timestamp(self):
        from comms import presence
        presence.open("front")
        before = presence.read_all()[0]["last_seen"]
        time.sleep(0.01)
        presence.touch("front", status="working")
        after = [e for e in presence.read_all() if e["alias"] == "front"][0]
        self.assertEqual(after["status"], "working")
        self.assertGreater(after["last_seen"], before)

    def test_touch_without_status_preserves_it(self):
        from comms import presence
        presence.open("front")
        presence.touch("front", status="waiting-human")
        presence.touch("front")
        e = presence.read_all()[0]
        self.assertEqual(e["status"], "waiting-human")

    def test_touch_on_unknown_alias_is_silent(self):
        from comms import presence
        presence.touch("ghost", status="working")   # must not raise
        self.assertEqual(presence.read_all(), [])

    def test_stale_when_last_seen_older_than_ttl(self):
        from comms import presence, store, paths
        presence.open("infra")
        p = paths.presence_file("infra")
        entry = store.read_json(p)
        entry["last_seen"] = time.time() - (presence.TTL + 5)
        store.write_json(p, entry)
        self.assertTrue(presence.read_all()[0]["stale"])

    def test_fresh_entry_is_not_stale(self):
        from comms import presence
        presence.open("infra")
        self.assertFalse(presence.read_all()[0]["stale"])

    def test_close_removes_entry(self):
        from comms import presence
        presence.open("front")
        presence.close("front")
        self.assertEqual(presence.read_all(), [])

    def test_whoami_prefers_env_alias(self):
        from comms import presence
        os.environ["COMMS_ALIAS"] = "front"
        self.assertEqual(presence.whoami(), "front")

    def test_whoami_falls_back_to_session_match(self):
        from comms import presence
        presence.open("orch", session="sess-abc")
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-abc"
        self.assertEqual(presence.whoami(), "orch")

    def test_whoami_none_when_unknown(self):
        from comms import presence
        self.assertIsNone(presence.whoami())

    def _registry(self, *records):
        from comms import paths, store
        for i, rec in enumerate(records):
            store.write_json(os.path.join(paths.sessions_dir(), f"{i}.json"), rec)

    def test_liveness_is_unknown_when_the_registry_is_absent(self):
        # Never read a missing registry as "everybody is dead" — comms has to
        # keep working on a machine or a terminal that has no such thing.
        from comms import presence
        presence.open("infra", session="sess-1")
        self.assertIsNone(presence.read_all()[0]["live"])

    def test_live_and_native_status_come_from_the_registry(self):
        from comms import presence
        presence.open("infra", session="sess-1")
        self._registry({"sessionId": "sess-1", "pid": os.getpid(),
                        "status": "busy"})
        entry = presence.read_all()[0]
        self.assertIs(entry["live"], True)
        self.assertEqual(entry["native_status"], "busy")

    def test_a_session_missing_from_a_readable_registry_is_gone(self):
        from comms import presence
        presence.open("infra", session="sess-gone")
        self._registry({"sessionId": "sess-other", "pid": os.getpid(),
                        "status": "idle"})
        self.assertIs(presence.read_all()[0]["live"], False)

    def test_a_registered_session_on_a_dead_pid_is_gone(self):
        from comms import presence
        presence.open("infra", session="sess-1")
        self._registry({"sessionId": "sess-1", "pid": 2 ** 31 - 1,
                        "status": "busy"})
        self.assertIs(presence.read_all()[0]["live"], False)

    def test_a_registered_session_with_no_usable_pid_is_unknown(self):
        # The record exists — that is itself evidence the session is there —
        # but it carries no pid comms can ask the OS about. Reading that as
        # "dead" would be worse than not asking at all.
        from comms import presence
        presence.open("infra", session="sess-1")
        self._registry({"sessionId": "sess-1", "pid": None, "status": "busy"})
        self.assertIsNone(presence.read_all()[0]["live"])

    def test_a_corrupt_file_elsewhere_in_the_registry_does_not_mark_this_session_dead(self):
        # Claude Code's write of <pid>.json is not known to be atomic. A
        # `comms who` landing mid-write on some OTHER session's file must not
        # let this session's own, perfectly readable record be trusted as
        # proof of anything — the whole registry read degrades to unknown.
        from comms import presence, paths
        presence.open("infra", session="sess-1")
        self._registry({"sessionId": "sess-1", "pid": os.getpid(),
                        "status": "busy"})
        with open(os.path.join(paths.sessions_dir(), "half-written.json"), "w") as fh:
            fh.write('{"sessionId": "sess-2"')
        self.assertIsNone(presence.read_all()[0]["live"])

    def test_an_agent_without_a_session_id_is_unknown_not_dead(self):
        # Joining without CLAUDE_CODE_SESSION_ID leaves nothing to join on.
        # Guessing "dead" there would evict a healthy agent from the board.
        from comms import presence
        presence.open("infra", session="")
        self._registry({"sessionId": "sess-other", "pid": os.getpid(),
                        "status": "idle"})
        self.assertIsNone(presence.read_all()[0]["live"])

    def test_liveness_never_reads_the_real_session_registry(self):
        # COMMS_ROOT drags the registry path with it; if this ever regresses,
        # the suite starts depending on which sessions are open on the machine.
        from comms import paths
        self.assertTrue(paths.sessions_dir().startswith(self.tmp))

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

if __name__ == "__main__":
    unittest.main()
