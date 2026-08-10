import json, os, shutil, tempfile, unittest
from unittest import mock


class SessionNameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, pid, session_id, name):
        with open(os.path.join(self.tmp, f"{pid}.json"), "w") as fh:
            json.dump({"pid": pid, "sessionId": session_id, "name": name}, fh)

    def test_finds_the_name_by_session_id(self):
        from comms import session
        self._write(111, "uuid-a", "ORCH-COLETA-RISCO")
        self._write(222, "uuid-b", "OUTRA")
        with mock.patch.object(session, "SESSIONS_DIR", self.tmp):
            self.assertEqual(session.name_for("uuid-a"), "ORCH-COLETA-RISCO")

    def test_unknown_session_returns_none(self):
        from comms import session
        with mock.patch.object(session, "SESSIONS_DIR", self.tmp):
            self.assertIsNone(session.name_for("uuid-desconhecido"))

    def test_empty_session_id_returns_none(self):
        from comms import session
        self.assertIsNone(session.name_for(""))

    def test_missing_directory_returns_none(self):
        from comms import session
        with mock.patch.object(session, "SESSIONS_DIR", "/nao/existe"):
            self.assertIsNone(session.name_for("uuid-a"))

    def test_corrupt_file_is_skipped_not_fatal(self):
        from comms import session
        with open(os.path.join(self.tmp, "333.json"), "w") as fh:
            fh.write("{nao json")
        self._write(444, "uuid-c", "BOA")
        with mock.patch.object(session, "SESSIONS_DIR", self.tmp):
            self.assertEqual(session.name_for("uuid-c"), "BOA")

    def test_successor_gets_the_novo_suffix(self):
        from comms import session
        self.assertEqual(session.successor_name("ORCH"), "ORCH-NOVO")

    def test_successor_suffix_does_not_stack(self):
        # handing off twice must not produce ORCH-NOVO-NOVO
        from comms import session
        self.assertEqual(session.successor_name("ORCH-NOVO"), "ORCH-NOVO")

    def test_successor_of_nothing_is_nothing(self):
        from comms import session
        self.assertEqual(session.successor_name(""), "")


if __name__ == "__main__":
    unittest.main()
