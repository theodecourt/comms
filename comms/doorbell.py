"""The doorbell is a background process whose EXIT wakes an idle session.
While it polls it also heartbeats presence — it is the only liveness signal."""
import os, signal, time
from comms import paths, presence, store

class _Terminated(Exception):
    """SIGTERM arrived — the loop unwinds so the caller can name the reason."""

def _terminate(signum, frame):
    raise _Terminated

def has_mail(alias: str) -> bool:
    try:
        return any(n.endswith(".json") for n in os.listdir(paths.inbox_dir(alias)))
    except OSError:
        return False

def wait(alias: str, interval: float = presence.POLL_INTERVAL,
         max_seconds: float = None) -> str:
    """Blocks until there is a reason to wake the session, and names the reason.

    Catching SIGTERM matters more than it looks. Something outside comms reaps
    long-lived background processes — observed on 2026-08-11 in three separate
    sessions, always with an empty output and no reason line. An agent reading
    that silence has two equally defensible readings, "I was reaped, re-arm" and
    "this failed, stop trying", and one of them leaves it deaf: that is exactly
    how the `ai` session went hours without a doorbell. Naming the reason
    removes the guess.

    SIGKILL cannot be caught, so silence is still possible. The skill therefore
    also tells agents to read an empty output as "re-arm" — this handler shrinks
    that case rather than eliminating it.
    """
    started = time.time()
    previous = {}
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            previous[sig] = signal.signal(sig, _terminate)
        except (ValueError, OSError):
            pass          # not the main thread, or the platform lacks it
    try:
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
    except _Terminated:
        return "killed"
    finally:
        for sig, handler in previous.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
