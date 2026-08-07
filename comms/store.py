"""Atomic write, tolerant read. A half-written file must never be readable."""
import json, os, tempfile
from comms import paths

def _mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def ensure_dirs(alias: str) -> None:
    _mkdir(paths.presence_dir())
    _mkdir(paths.inbox_dir(alias))
    _mkdir(os.path.dirname(paths.log_file(alias)))

def write_json(path: str, obj: dict) -> None:
    _mkdir(os.path.dirname(path))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, indent=2)
        os.replace(tmp, path)          # atomic within one filesystem
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def read_json(path: str):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
