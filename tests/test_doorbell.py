import os, shutil, tempfile, threading, time, unittest

class DoorbellTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        from comms import presence
        presence.open("front")
        presence.open("orch")

    def tearDown(self):
        os.environ.pop("COMMS_ROOT", None)
        os.environ.pop("COMMS_ALIAS", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sigterm_names_itself_instead_of_dying_silently(self):
        # A reaped doorbell used to exit with nothing on stdout, and an empty
        # output reads equally well as "re-arm" or as "this is broken, stop".
        # The second reading is what left a real session deaf for hours.
        import signal, subprocess, sys
        from comms import store, paths
        initial = store.read_json(paths.presence_file("front"))["last_seen"]
        env = dict(os.environ, COMMS_ROOT=self.tmp, COMMS_ALIAS="front")
        p = subprocess.Popen(
            [sys.executable, "-c",
             "from comms.cli import main; raise SystemExit(main(['wait']))"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env, stdout=subprocess.PIPE, text=True)
        # Poll for the doorbell's own heartbeat instead of sleeping a fixed
        # amount: a fixed sleep signals blind, and if the child has not yet
        # installed its SIGTERM handler the signal kills it with default
        # disposition, failing the very test guarding that handler. The
        # doorbell touches `last_seen` every loop iteration, so watching it
        # advance is proof the loop — and therefore the handler — is live.
        deadline = time.time() + 10
        while time.time() < deadline:
            e = store.read_json(paths.presence_file("front"))
            if e and e["last_seen"] > initial:
                break
            time.sleep(0.05)
        else:
            p.kill()
            p.communicate(timeout=10)
            self.fail("doorbell nunca avançou last_seen — não deu para provar "
                      "que o loop chegou a rodar")
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=10)
        self.assertIn("DOORBELL: killed", out)

    def test_has_mail_false_when_inbox_empty(self):
        from comms import doorbell
        self.assertFalse(doorbell.has_mail("front"))

    def test_has_mail_true_after_post(self):
        from comms import doorbell, messages
        messages.post("orch", "oi", to="front")
        self.assertTrue(doorbell.has_mail("front"))

    def test_wait_returns_mail_when_message_arrives(self):
        from comms import doorbell, messages
        result = {}
        t = threading.Thread(target=lambda: result.update(
            r=doorbell.wait("front", interval=0.05, max_seconds=5)))
        t.start()
        time.sleep(0.2)
        messages.post("orch", "acorda", to="front")
        t.join(timeout=5)
        self.assertEqual(result.get("r"), "mail")

    def test_wait_returns_closed_when_presence_removed(self):
        from comms import doorbell, presence
        result = {}
        t = threading.Thread(target=lambda: result.update(
            r=doorbell.wait("front", interval=0.05, max_seconds=5)))
        t.start()
        time.sleep(0.2)
        presence.close("front")
        t.join(timeout=5)
        self.assertEqual(result.get("r"), "closed")

    def test_wait_heartbeats_presence(self):
        from comms import doorbell, presence, store, paths
        p = paths.presence_file("front")
        e = store.read_json(p)
        e["last_seen"] = time.time() - 999
        store.write_json(p, e)
        doorbell.wait("front", interval=0.05, max_seconds=0.4)
        fresh = [x for x in presence.read_all() if x["alias"] == "front"][0]
        self.assertFalse(fresh["stale"])

    def test_wait_times_out(self):
        from comms import doorbell
        self.assertEqual(
            doorbell.wait("front", interval=0.05, max_seconds=0.3), "timeout")

    def test_wait_times_out_without_waiting_a_whole_interval(self):
        from comms import doorbell
        started = time.time()
        self.assertEqual(
            doorbell.wait("front", interval=5, max_seconds=0.1), "timeout")
        self.assertLess(time.time() - started, 1.0)

if __name__ == "__main__":
    unittest.main()
