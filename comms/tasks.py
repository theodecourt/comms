"""Shared tasks: one folder per task, one writer per file.

    <tasks_root>/<AAAA-MM-DD>-<slug>/
      TASK.md              only the orchestrator writes it
      subtasks/01-<slug>.md   only that subtask's owner writes it

Several agents appending to one markdown file overwrite each other, which is
why the state is split by writer. The subtask file's frontmatter is the source
of truth for progress; the table in TASK.md is the orchestrator's view of it.

Who holds what lives in `assignments/<alias>.json`, outside presence, so it
survives SessionEnd, a handoff and a `/clear` — keyed by alias, not session.
"""
import datetime, os, re, time, unicodedata
from comms import paths, presence, store

STATUSES = ("todo", "doing", "blocked", "done")
_ID_RE = re.compile(r"^[a-z0-9]+$")


class TaskError(Exception):
    """A refusal with a message for the user, in Portuguese."""


def slugify(text: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")
    return slug[:50].rstrip("-")


def _template(name: str, **values) -> str:
    with open(os.path.join(paths.templates_dir(), name), encoding="utf-8") as fh:
        text = fh.read()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── frontmatter ─────────────────────────────────────────────────────────────
# Flat `key: value` only — what the templates write. No YAML dependency: the
# rest of comms is stdlib, and nested frontmatter is not something an agent
# needs to write here.

def frontmatter(path: str) -> dict:
    try:
        lines = _read(path).splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        key, sep, value = line.partition(":")
        if sep and key.strip():
            out[key.strip()] = value.strip().strip("'\"")
    return {}                       # never closed: not frontmatter


def set_frontmatter(path: str, **values) -> None:
    lines = _read(path).splitlines()
    if not lines or lines[0].strip() != "---":
        lines = ["---", "---"] + lines
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    pending = dict(values)
    for i in range(1, end):
        key = lines[i].partition(":")[0].strip()
        if key in pending:
            lines[i] = f"{key}: {pending.pop(key)}"
    lines[end:end] = [f"{k}: {v}" for k, v in pending.items()]
    store.write_text(path, "\n".join(lines) + "\n")


# ── tasks ───────────────────────────────────────────────────────────────────

def task_file(task: str) -> str:
    return os.path.join(task, "TASK.md")


def is_closed(task: str) -> bool:
    return frontmatter(task_file(task)).get("status") == "closed"


def new(name: str, today: str = None) -> str:
    slug = slugify(name)
    if not slug:
        raise TaskError(f"nome sem letras ou dígitos: {name!r}")
    today = today or datetime.date.today().isoformat()
    task = os.path.join(paths.tasks_root(), f"{today}-{slug}")
    if os.path.exists(task):
        raise TaskError(f"já existe uma task em {task}")
    os.makedirs(os.path.join(task, "subtasks"))
    store.write_text(task_file(task), _template("TASK.md", nome=name, data=today))
    return task


def resolve(ref: str) -> str:
    """A task named by folder name, by slug without the date, or by path."""
    root = paths.tasks_root()
    for candidate in (ref, os.path.join(root, ref)):
        if os.path.isfile(task_file(candidate)):
            return os.path.abspath(candidate)
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    hits = [n for n in names if n.endswith("-" + ref)
            and os.path.isfile(task_file(os.path.join(root, n)))]
    if len(hits) == 1:
        return os.path.join(root, hits[0])
    if hits:
        raise TaskError(f"{ref!r} é ambíguo: {', '.join(hits)} — use o nome inteiro")
    raise TaskError(f"task {ref!r} não encontrada em {root}")


def all_tasks() -> list:
    root = paths.tasks_root()
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [os.path.join(root, n) for n in names
            if os.path.isfile(task_file(os.path.join(root, n)))]


# ── subtasks ────────────────────────────────────────────────────────────────

def subtask_id(filename: str) -> str:
    return os.path.splitext(filename)[0].split("-", 1)[0]


def subtask_file(task: str, sid: str):
    """The file for subtask `sid`, or None. Named by the subtask, not by the
    agent, so whoever takes over tomorrow continues the same file."""
    folder = os.path.join(task, "subtasks")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        if name.endswith(".md") and subtask_id(name) == sid:
            return os.path.join(folder, name)
    return None


def _create_subtask(task: str, sid: str, resumo: str) -> str:
    slug = slugify(resumo or "")
    path = os.path.join(task, "subtasks", f"{sid}-{slug}.md" if slug else f"{sid}.md")
    store.write_text(path, _template("subtask.md", id=sid, resumo=resumo or ""))
    return path


# ── the TASK.md table ───────────────────────────────────────────────────────

def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _set_owner(task: str, sid: str, alias: str, resumo: str) -> None:
    """Write the owner into the subtask table, adding the row if missing.

    Columns are found by header name, so an orchestrator that reorders or adds
    columns does not get its table scrambled. A TASK.md with no table is left
    alone: the assignment file and the subtask's own file already say it all."""
    path = task_file(task)
    lines = _read(path).splitlines()
    header = next((i for i, l in enumerate(lines)
                   if l.lstrip().startswith("|") and "dono" in _cells(l)), None)
    if header is None:
        return
    cols = _cells(lines[header])
    end = header + 1
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    for i in range(header + 2, end):
        row = _cells(lines[i])
        if row and row[0] == sid:
            row += [""] * (len(cols) - len(row))
            row[cols.index("dono")] = alias
            if resumo and "resumo" in cols and not row[cols.index("resumo")]:
                row[cols.index("resumo")] = resumo
            lines[i] = "| " + " | ".join(row) + " |"
            break
    else:
        row = [""] * len(cols)
        row[0] = sid
        for col, value in (("dono", alias), ("resumo", resumo or ""),
                           ("estado", "todo")):
            if col in cols:
                row[cols.index(col)] = value
        lines.insert(end, "| " + " | ".join(row) + " |")
    store.write_text(path, "\n".join(lines) + "\n")


# ── assignments ─────────────────────────────────────────────────────────────

def assignment(alias: str):
    rec = store.read_json(paths.assignment_file(alias))
    return rec if isinstance(rec, dict) else None


def assignments() -> dict:
    out = {}
    try:
        names = sorted(os.listdir(paths.assignments_dir()))
    except OSError:
        return out
    for name in names:
        if name.endswith(".json"):
            rec = assignment(name[:-5])
            if rec:
                out[name[:-5]] = rec
    return out


def assign(alias: str, ref: str, sid: str, resumo: str = None) -> dict:
    if not presence.valid_alias(alias):
        raise TaskError(f"alias inválido: {alias!r}")
    if not _ID_RE.match(sid or ""):
        raise TaskError(f"id de subtarefa inválido: {sid!r} — use dígitos, como 01")
    task = resolve(ref)
    if is_closed(task):
        raise TaskError(f"{os.path.basename(task)} está fechada")
    path = subtask_file(task, sid) or _create_subtask(task, sid, resumo)
    previous = assignment(alias)
    rec = {"task": task, "subtask": sid, "assigned_at": time.time()}
    store.write_json(paths.assignment_file(alias), rec)
    _set_owner(task, sid, alias, resumo)
    return {**rec, "file": path, "previous": previous}


def status(task: str) -> list:
    """One row per subtask file, read from its frontmatter — the file is the
    truth, whatever the TASK.md table says."""
    owners = {(a["task"], a.get("subtask")): alias
              for alias, a in assignments().items()}
    folder = os.path.join(task, "subtasks")
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".md"))
    except OSError:
        names = []
    rows = []
    for name in names:
        fm = frontmatter(os.path.join(folder, name))
        sid = subtask_id(name)
        rows.append({"id": sid, "status": fm.get("status") or "?",
                     "branch": fm.get("branch", ""), "sha": fm.get("sha", ""),
                     "owner": owners.get((task, sid), ""), "file": name})
    return rows


def notice(alias: str):
    """The 📋 line for `alias`, or None. Silent about a task that is gone or
    closed: a stale pointer is worse than none."""
    rec = assignment(alias)
    if not rec or not isinstance(rec.get("task"), str):
        return None
    task, sid = rec["task"], str(rec.get("subtask") or "")
    if not os.path.isfile(task_file(task)) or is_closed(task):
        return None
    sub = subtask_file(task, sid)
    where = (f"{task_file(task)} e {sub}" if sub else task_file(task))
    return f"📋 {os.path.basename(task)} · subtarefa {sid} → leia {where}"


def _body(path: str) -> str:
    """A markdown file without its frontmatter."""
    text = _read(path)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def close(ref: str, stamp: str = None) -> dict:
    """Archive the task in the vault, free whoever held it, mark it closed.

    The note goes first: if it cannot be written nothing else changes, and the
    close can simply be run again. The push goes last and may fail on its own —
    the note is on disk by then, as with a handoff."""
    from comms import handoff
    task = resolve(ref)
    if is_closed(task):
        raise TaskError(f"{os.path.basename(task)} já está fechada")
    stamp = stamp or datetime.date.today().isoformat()
    name = os.path.basename(task)

    parts = [_body(task_file(task)).rstrip(), "", "## Subtarefas ao fechar", ""]
    rows = status(task)
    for r in rows:
        parts.append(f"- **{r['id']}** {r['status']} · {r['owner'] or '—'} · "
                     f"{r['branch'] or '—'} · {r['sha'] or '—'}")
    for r in rows:
        parts += ["", f"### {r['file']}", "",
                  _body(os.path.join(task, "subtasks", r["file"])).rstrip()]
    parts += ["", f"Pasta da task: `{task}`"]

    vp = handoff.vault_path(name, stamp, label="Task")
    try:
        handoff.write_vault_note(vp, name, stamp, "tasks",
                                 os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
                                 "\n".join(parts), kind="task")
    except OSError as e:
        raise TaskError(f"nota do vault não foi escrita ({e}) — a task segue aberta")

    freed = []
    for alias, rec in assignments().items():
        if rec.get("task") == task:
            try:
                os.unlink(paths.assignment_file(alias))
                freed.append(alias)
            except OSError:
                pass
    set_frontmatter(task_file(task), status="closed", closed=stamp)
    return {"task": task, "note": vp, "freed": freed,
            "archived": handoff.archive(vp, kind="task")}
