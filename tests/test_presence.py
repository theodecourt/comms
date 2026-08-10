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

if __name__ == "__main__":
    unittest.main()
