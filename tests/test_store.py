import json, os, shutil, tempfile, unittest

class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp

    def tearDown(self):
        os.environ.pop("COMMS_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_root_honours_env(self):
        from comms import paths
        self.assertEqual(paths.root(), self.tmp)

    def test_paths_are_under_root(self):
        from comms import paths
        self.assertTrue(paths.presence_file("orch").startswith(self.tmp))
        self.assertTrue(paths.inbox_dir("orch").startswith(self.tmp))
        self.assertTrue(paths.log_file("orch").startswith(self.tmp))

    def test_write_then_read_roundtrip(self):
        from comms import paths, store
        p = paths.presence_file("orch")
        store.write_json(p, {"alias": "orch", "n": 1})
        self.assertEqual(store.read_json(p)["alias"], "orch")

    def test_write_leaves_no_temp_files(self):
        from comms import paths, store
        store.write_json(paths.presence_file("orch"), {"a": 1})
        leftovers = [f for f in os.listdir(paths.presence_dir()) if not f.endswith(".json")]
        self.assertEqual(leftovers, [])

    def test_read_missing_returns_none(self):
        from comms import store
        self.assertIsNone(store.read_json(os.path.join(self.tmp, "nope.json")))

    def test_read_corrupt_returns_none(self):
        from comms import paths, store
        p = paths.presence_file("bad")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write("{not json")
        self.assertIsNone(store.read_json(p))

if __name__ == "__main__":
    unittest.main()
