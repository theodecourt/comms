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

    def test_a_bare_role_picks_up_the_layer_from_the_repo(self):
        # `segura-api` does not say "back" anywhere in its name — that is the
        # whole reason the alias carries the layer.
        from comms import presence
        self.assertEqual(
            presence.resolve_alias("builder", cwd="/x/segura-api"),
            "builder-back")
        self.assertEqual(
            presence.resolve_alias("builder", cwd="/x/segura-intelligence-front"),
            "builder-front")
        self.assertEqual(
            presence.resolve_alias("orch", cwd="/x/segura-intelligence"),
            "orch-back")
        self.assertEqual(
            presence.resolve_alias("orch", cwd="/x/segura-portal-corretores"),
            "orch-front")

    def test_a_repo_without_layers_keeps_the_bare_role(self):
        from comms import presence
        self.assertEqual(presence.resolve_alias("builder", cwd="/x/comms"),
                         "builder")

    def test_an_alias_that_names_its_layer_is_taken_as_given(self):
        from comms import presence
        self.assertEqual(
            presence.resolve_alias("builder-front", cwd="/x/segura-api"),
            "builder-front")

    def test_a_collision_gets_the_next_free_number(self):
        from comms import presence
        presence.open("builder-back", session="sess-a")
        self.assertEqual(
            presence.resolve_alias("builder", cwd="/x/segura-api",
                                   session="sess-b"),
            "builder-back-2")
        presence.open("builder-back-2", session="sess-b")
        self.assertEqual(
            presence.resolve_alias("builder", cwd="/x/segura-api",
                                   session="sess-c"),
            "builder-back-3")

    def test_reopening_updates_my_own_row_instead_of_cloning_it(self):
        # Re-running `comms open` to change the note must not leave the board
        # holding two rows for one session.
        from comms import presence
        presence.open("builder-back", session="sess-a")
        self.assertEqual(
            presence.resolve_alias("builder", cwd="/x/segura-api",
                                   session="sess-a"),
            "builder-back")

    def test_a_numbered_orchestrator_still_orchestrates(self):
        from comms import presence
        self.assertEqual(presence.role_for("orch-back-2"), "orchestrator")

    def test_a_prefixed_alias_still_orchestrates(self):
        # One board, two orchestrators — a front and a back for the same
        # project — need distinct aliases, since the alias is the board's key.
        from comms import presence
        self.assertEqual(presence.role_for("orch-front"), "orchestrator")
        self.assertEqual(presence.role_for("orch-back"), "orchestrator")

    def test_the_hyphen_is_what_makes_it_a_prefix(self):
        # Otherwise any alias merely starting with those four letters would be
        # promoted, and the role decides the context-warning threshold.
        from comms import presence
        self.assertEqual(presence.role_for("orchid"), "builder")
        self.assertEqual(presence.role_for("orchestration-helper"), "builder")

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

    def test_close_removes_entry(self):
        from comms import presence
        presence.open("front")
        presence.close("front")
        self.assertEqual(presence.read_all(), [])

    def test_whoami_prefers_env_alias(self):
        from comms import presence
        presence.open("front")
        os.environ["COMMS_ALIAS"] = "front"
        self.assertEqual(presence.whoami(), "front")

    def test_whoami_ignores_an_env_alias_that_left_the_board(self):
        # COMMS_ALIAS is frozen at spawn and cannot be updated from outside the
        # process, so after a rename or a close it names an identity that no
        # longer exists. The session id outlives both.
        from comms import presence
        presence.open("portal-back-builder", session="sess-1")
        os.environ["COMMS_ALIAS"] = "api"           # o nome de antes
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-1"
        self.assertEqual(presence.whoami(), "portal-back-builder")

    def test_whoami_is_none_when_the_env_alias_is_all_there_is(self):
        # Better to say "I do not know who I am" than to post as a ghost.
        from comms import presence
        os.environ["COMMS_ALIAS"] = "fantasma"
        self.assertIsNone(presence.whoami())

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
