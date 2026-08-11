import json, os, shutil, subprocess, sys, tempfile, unittest

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "hooks", "comms-hook.py")

def _oversized_bytes():
    """Size just over the hook's own warning threshold.

    Sized past the LARGEST threshold so one fixture serves every test — the
    alias, not the size, decides which message comes out. Reading the constant
    instead of hardcoding a number means recalibrating WARN_BYTES cannot
    silently stop these tests from exercising the warning.
    """
    import importlib.util, os
    hook = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hooks", "comms-hook.py")
    spec = importlib.util.spec_from_file_location("_comms_hook", hook)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return max(mod.WARN_BYTES.values()) + 1_000


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        from comms import presence
        presence.open("front", session="sess-1")

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fire(self, event, session="sess-1", transcript=""):
        env = dict(os.environ, COMMS_ROOT=self.tmp)
        payload = json.dumps({"session_id": session, "hook_event_name": event,
                              "cwd": "/tmp", "transcript_path": transcript})
        return subprocess.run([sys.executable, HOOK], input=payload,
                              capture_output=True, text=True, env=env)

    def status(self, alias="front"):
        from comms import presence
        return [e for e in presence.read_all() if e["alias"] == alias][0]["status"]

    def test_user_prompt_sets_working(self):
        self.fire("UserPromptSubmit")
        self.assertEqual(self.status(), "working")

    def test_stop_sets_idle(self):
        self.fire("UserPromptSubmit"); self.fire("Stop")
        self.assertEqual(self.status(), "idle")

    def test_notification_sets_waiting_human(self):
        self.fire("Notification")
        self.assertEqual(self.status(), "waiting-human")

    def test_session_end_removes_presence(self):
        from comms import presence
        self.fire("SessionEnd")
        self.assertEqual(presence.read_all(), [])

    def test_unknown_session_is_ignored_and_exits_zero(self):
        r = self.fire("Stop", session="sess-unknown")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.status(), "idle")

    def test_garbage_stdin_exits_zero(self):
        env = dict(os.environ, COMMS_ROOT=self.tmp)
        r = subprocess.run([sys.executable, HOOK], input="{not json",
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)

    def test_empty_stdin_exits_zero(self):
        env = dict(os.environ, COMMS_ROOT=self.tmp)
        r = subprocess.run([sys.executable, HOOK], input="",
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)

    def test_large_transcript_emits_context_warning(self):
        big = os.path.join(self.tmp, "big.jsonl")
        with open(big, "w") as fh:
            fh.write("x" * _oversized_bytes())
        r = self.fire("UserPromptSubmit", transcript=big)
        self.assertIn("contexto", r.stdout.lower())

    def test_large_transcript_on_stop_emits_no_warning(self):
        # Claude Code only forwards hook stdout into the model's context on
        # UserPromptSubmit (and SessionStart), never on Stop — a warning
        # printed there would be inert, so Stop must stay silent.
        big = os.path.join(self.tmp, "big.jsonl")
        with open(big, "w") as fh:
            fh.write("x" * _oversized_bytes())
        r = self.fire("Stop", transcript=big)
        self.assertNotIn("contexto", r.stdout.lower())

    def test_large_transcript_emits_orchestrator_warning(self):
        from comms import presence
        presence.open("orch", session="sess-orch")
        big = os.path.join(self.tmp, "big.jsonl")
        with open(big, "w") as fh:
            fh.write("x" * _oversized_bytes())
        r = self.fire("UserPromptSubmit", session="sess-orch", transcript=big)
        self.assertIn("comms handoff", r.stdout)

    def test_installer_adds_the_sendmessage_hook_with_a_matcher(self):
        # Sem matcher o hook rodaria em TODA chamada de ferramenta.
        settings = os.path.join(self.tmp, "settings.json")
        with open(settings, "w") as fh:
            json.dump({"hooks": {}}, fh)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(root, "hooks", "install_hooks.py")
        env = dict(os.environ, COMMS_SETTINGS=settings)
        p = subprocess.run([sys.executable, script], env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(settings) as fh:
            cfg = json.load(fh)
        groups = cfg["hooks"]["PostToolUse"]
        self.assertTrue(any(g.get("matcher") == "SendMessage" for g in groups))

if __name__ == "__main__":
    unittest.main()
