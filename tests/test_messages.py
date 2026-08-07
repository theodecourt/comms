import os, tempfile, unittest, shutil

class MessagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        from comms import presence
        presence.open("orch")
        presence.open("front")

    def tearDown(self):
        os.environ.pop("COMMS_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_direct_message_reaches_only_recipient(self):
        from comms import messages
        messages.post("orch", "implementa a fase 1", to="front")
        self.assertEqual(len(messages.inbox("front")), 1)
        self.assertEqual(messages.inbox("orch"), [])

    def test_message_carries_sender_and_body(self):
        from comms import messages
        messages.post("orch", "oi", to="front")
        m = messages.inbox("front")[0]
        self.assertEqual(m["from"], "orch")
        self.assertEqual(m["body"], "oi")
        self.assertFalse(m["urgent"])

    def test_inbox_consumes_by_default(self):
        from comms import messages
        messages.post("orch", "oi", to="front")
        self.assertEqual(len(messages.inbox("front")), 1)
        self.assertEqual(messages.inbox("front"), [])

    def test_peek_does_not_consume(self):
        from comms import messages
        messages.post("orch", "oi", to="front")
        self.assertEqual(len(messages.inbox("front", peek=True)), 1)
        self.assertEqual(len(messages.inbox("front", peek=True)), 1)

    def test_broadcast_skips_sender(self):
        from comms import messages
        messages.post("orch", "todos de pe?")
        self.assertEqual(len(messages.inbox("front")), 1)
        self.assertEqual(messages.inbox("orch"), [])

    def test_log_survives_consumption(self):
        from comms import messages
        messages.post("orch", "oi", to="front")
        messages.inbox("front")
        self.assertEqual(len(messages.log("front")), 1)

    def test_messages_come_back_in_send_order(self):
        from comms import messages
        for i in range(5):
            messages.post("orch", f"m{i}", to="front")
        bodies = [m["body"] for m in messages.inbox("front")]
        self.assertEqual(bodies, ["m0", "m1", "m2", "m3", "m4"])

    def test_post_to_offline_alias_persists(self):
        from comms import messages, presence
        messages.post("orch", "para depois", to="infra")
        presence.open("infra")
        self.assertEqual(len(messages.inbox("infra")), 1)

    def test_order_holds_when_timestamps_collide(self):
        from unittest.mock import patch
        from comms import messages
        with patch("comms.messages.time.time", return_value=1234567890.0):
            for i in range(5):
                messages.post("orch", f"m{i}", to="front")
        bodies = [m["body"] for m in messages.inbox("front")]
        self.assertEqual(bodies, ["m0", "m1", "m2", "m3", "m4"])

if __name__ == "__main__":
    unittest.main()
