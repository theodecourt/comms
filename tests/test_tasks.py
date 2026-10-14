import io, json, os, shutil, tempfile, unittest
from contextlib import redirect_stdout

def run(*args):
    from comms import cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(args))
    return code, buf.getvalue()

class TasksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["COMMS_ROOT"] = self.tmp
        os.environ["COMMS_TASKS_DIR"] = os.path.join(self.tmp, "tasks")
        os.environ["COMMS_VAULT"] = os.path.join(self.tmp, "vault")
        for k in ("COMMS_ALIAS", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k in ("COMMS_ROOT", "COMMS_TASKS_DIR", "COMMS_VAULT", "COMMS_ALIAS",
                  "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new_task(self):
        from comms import tasks
        return tasks.new("Funil de vendas", today="2026-10-07")

    def test_new_records_the_repo_of_cwd_or_the_given_ones(self):
        import subprocess
        from comms import tasks
        repo = os.path.realpath(os.path.join(self.tmp, "segura-api"))
        subprocess.run(["git", "init", "-q", repo], check=True)
        old = os.getcwd()
        os.chdir(repo)
        try:
            task = tasks.new("Funil", today="2026-10-07")
        finally:
            os.chdir(old)
        self.assertEqual(tasks.frontmatter(tasks.task_file(task))["repo"], repo)
        self.assertIn("**Repo:** `segura-api`", open(tasks.task_file(task)).read())
        task = tasks.new("Outra", today="2026-10-07", repos=[repo, "/x/front"])
        self.assertIn("**Repo:** `segura-api`, `front`", open(tasks.task_file(task)).read())

    def test_without_tasks_dir_a_relocated_board_never_reaches_the_vault(self):
        from comms import paths
        os.environ.pop("COMMS_TASKS_DIR")
        self.assertTrue(paths.tasks_root().startswith(self.tmp))

    def test_assign_writes_assignment_subtask_file_and_owner(self):
        from comms import paths, tasks
        task = self.new_task()
        self.assertTrue(task.endswith("2026-10-07-funil-de-vendas"))
        code, _ = run("task", "assign", "builder-back", "funil-de-vendas",
                      "--subtask", "01", "--resumo", "Endpoint do funil")
        self.assertEqual(code, 0)
        rec = json.load(open(paths.assignment_file("builder-back")))
        self.assertEqual((rec["task"], rec["subtask"]), (task, "01"))
        self.assertTrue(os.path.isfile(
            os.path.join(task, "subtasks", "01-endpoint-do-funil.md")))
        table = [l for l in open(tasks.task_file(task)) if l.startswith("| 01")]
        self.assertEqual(len(table), 1)
        self.assertIn("builder-back", table[0])
        self.assertIn("Endpoint do funil", table[0])

    def test_status_reads_the_subtask_frontmatter(self):
        from comms import tasks
        task = self.new_task()
        run("task", "assign", "builder-back", "funil-de-vendas", "--subtask", "01",
            "--resumo", "endpoint")
        sub = tasks.subtask_file(task, "01")
        tasks.set_frontmatter(sub, status="done", branch="feat/funil", sha="abc123")
        code, out = run("task", "status", "funil-de-vendas")
        self.assertEqual(code, 0)
        row = [l for l in out.splitlines() if l.strip().startswith("01")][0]
        for word in ("done", "builder-back", "feat/funil", "abc123"):
            self.assertIn(word, row)

    def test_close_archives_frees_and_marks_closed(self):
        from comms import paths, tasks
        task = self.new_task()
        run("task", "assign", "builder-back", "funil-de-vendas", "--subtask", "01",
            "--resumo", "endpoint")
        run("task", "assign", "builder-front", "funil-de-vendas", "--subtask", "02")
        code, out = run("task", "close", "funil-de-vendas")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.listdir(paths.assignments_dir()))
        self.assertTrue(tasks.is_closed(task))
        notes = os.listdir(os.environ["COMMS_VAULT"])
        self.assertEqual(len(notes), 1)
        note = open(os.path.join(os.environ["COMMS_VAULT"], notes[0])).read()
        self.assertIn("01-endpoint.md", note)
        self.assertIn("sem commit/push", out)
        # a closed task takes no new assignment
        code, _ = run("task", "assign", "x", "funil-de-vendas", "--subtask", "03")
        self.assertEqual(code, 2)
