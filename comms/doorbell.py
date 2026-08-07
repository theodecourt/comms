"""The doorbell is a background process whose EXIT wakes an idle session.
While it polls it also heartbeats presence — it is the only liveness signal."""
import os, time
from comms import paths, presence, store

def has_mail(alias: str) -> bool:
    try:
        return any(n.endswith(".json") for n in os.listdir(paths.inbox_dir(alias)))
    except OSError:
        return False

def wait(alias: str, interval: float = presence.POLL_INTERVAL,
         max_seconds: float = None) -> str:
    started = time.time()
    while True:
        if store.read_json(paths.presence_file(alias)) is None:
            return "closed"
        if has_mail(alias):
            return "mail"
        presence.touch(alias)                     # heartbeat
        if max_seconds is None:
            time.sleep(interval)
            continue
        remaining = max_seconds - (time.time() - started)
        if remaining <= 0:
            return "timeout"
        time.sleep(min(interval, remaining))
