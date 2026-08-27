import os, shutil, tempfile, unittest

class RenameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        for k in ("COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_entry_moves_and_the_role_is_recomputed(self):
        # `orch-back` orchestrates and `portal-back-builder` does not, so the
        # role stored on the row has to follow the new alias, not the old one.
        from comms import presence, rename
        presence.open("orch-back", note="coordenando", session="sess-1")
        rename.run("orch-back", "portal-back-builder")
        entries = presence.read_all()
        self.assertEqual([e["alias"] for e in entries], ["portal-back-builder"])
        self.assertEqual(entries[0]["role"], "builder")
        self.assertEqual(entries[0]["note"], "coordenando")
        self.assertEqual(entries[0]["session"], "sess-1")

    def test_pending_mail_and_history_come_along(self):
        from comms import messages, presence, rename
        presence.open("orch"); presence.open("api")
        messages.post("orch", "implementa a fase 1", to="api")
        rename.run("api", "portal-back-builder")
        msgs = messages.inbox("portal-back-builder")
        self.assertEqual([m["body"] for m in msgs], ["implementa a fase 1"])
        self.assertEqual(messages.inbox("api"), [])

    def test_the_delegation_follows_the_session(self):
        from comms import delegation, presence, rename
        presence.open("orch")
        delegation.grant("orch", "publicar skills em dev")
        rename.run("orch", "portal-back-orch")
        grants = delegation.read_all()
        self.assertEqual(grants, {"portal-back-orch": "publicar skills em dev"})

    def test_it_refuses_an_alias_already_on_the_board(self):
        from comms import presence, rename
        presence.open("orch"); presence.open("api")
        with self.assertRaises(rename.RenameRefused):
            rename.run("api", "orch")
        self.assertEqual(sorted(e["alias"] for e in presence.read_all()),
                         ["api", "orch"])

    def test_it_refuses_an_alias_holding_someone_elses_grant(self):
        # The escalation this guard exists for: `orch` closes and leaves its
        # delegation behind; renaming into that alias would pick the grant up.
        from comms import delegation, presence, rename
        presence.open("orch")
        delegation.grant("orch", "publicar skills em dev")
        presence.close("orch")
        presence.open("api", session="sess-api")
        with self.assertRaises(rename.RenameRefused) as cm:
            rename.run("api", "orch")
        self.assertIn("delegação", str(cm.exception))
        self.assertEqual([e["alias"] for e in presence.read_all()], ["api"])

    def test_a_free_alias_whose_grant_was_revoked_is_fine(self):
        # The guard must key on the leftover grant, not on the name ever having
        # been used, or an alias would be poisoned forever.
        from comms import delegation, presence, rename
        presence.open("orch")
        delegation.grant("orch", "publicar skills em dev")
        delegation.revoke("orch")
        presence.close("orch")
        presence.open("api", session="sess-api")
        self.assertEqual(rename.run("api", "orch"), "orch")

    def test_it_refuses_a_junk_alias_and_changes_nothing(self):
        from comms import presence, rename
        presence.open("api")
        with self.assertRaises(rename.RenameRefused):
            rename.run("api", "PORTAL BACK")
        self.assertEqual([e["alias"] for e in presence.read_all()], ["api"])

    def test_whoami_survives_the_rename(self):
        # COMMS_ALIAS is frozen at spawn and cannot be updated from outside the
        # process. Trusting it blindly would make the renamed session post as
        # an alias that no longer exists.
        from comms import presence, rename
        presence.open("api", session="sess-api")
        os.environ["COMMS_ALIAS"] = "api"
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-api"
        rename.run("api", "portal-back-builder")
        self.assertEqual(presence.whoami(), "portal-back-builder")

if __name__ == "__main__":
    unittest.main()
