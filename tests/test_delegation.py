import os, shutil, tempfile, unittest


class DelegationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        for k in ("COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_delegation_by_default(self):
        from comms import delegation
        self.assertIsNone(delegation.scope_for("orch"))
        self.assertEqual(delegation.read_all(), {})

    def test_grant_records_the_scope(self):
        from comms import delegation
        delegation.grant("orch", "publicar skills em dev")
        self.assertEqual(delegation.scope_for("orch"), "publicar skills em dev")

    def test_grant_is_per_alias(self):
        from comms import delegation
        delegation.grant("orch", "publicar em dev")
        self.assertIsNone(delegation.scope_for("ai"))

    def test_grant_overwrites_previous_scope(self):
        from comms import delegation
        delegation.grant("orch", "escopo antigo")
        delegation.grant("orch", "escopo novo")
        self.assertEqual(delegation.scope_for("orch"), "escopo novo")

    def test_revoke_removes_it(self):
        from comms import delegation
        delegation.grant("orch", "publicar em dev")
        self.assertTrue(delegation.revoke("orch"))
        self.assertIsNone(delegation.scope_for("orch"))

    def test_revoke_is_silent_when_nothing_granted(self):
        from comms import delegation
        self.assertFalse(delegation.revoke("orch"))

    def test_read_all_maps_alias_to_scope(self):
        from comms import delegation
        delegation.grant("orch", "publicar em dev")
        delegation.grant("infra", "reiniciar containers locais")
        self.assertEqual(delegation.read_all(),
                         {"orch": "publicar em dev", "infra": "reiniciar containers locais"})

    def test_empty_scope_is_rejected(self):
        # A delegation with no scope would read as blanket authority — the one
        # thing this mechanism exists to prevent.
        from comms import delegation
        with self.assertRaises(ValueError):
            delegation.grant("orch", "   ")

    def test_grant_rejects_invalid_alias(self):
        from comms import delegation
        with self.assertRaises(ValueError):
            delegation.grant("BUILDER #1", "qualquer coisa")

    def test_record_carries_the_grant_time(self):
        from comms import delegation
        delegation.grant("orch", "publicar em dev")
        rec = delegation.record_for("orch")
        self.assertIn("granted_at", rec)
        self.assertEqual(rec["alias"], "orch")


if __name__ == "__main__":
    unittest.main()
