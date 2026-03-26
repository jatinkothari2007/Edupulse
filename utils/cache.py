"""
utils/cache.py — Simple in-memory TTL cache for EduPulse.
Reduces Firestore reads by caching results for a configurable number of seconds.
"""
import time
import threading

_store  = {}   # key → (value, expires_at)
_lock   = threading.Lock()


def get(key):
    """Return cached value or None if missing/expired."""
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del _store[key]
            return None
        return value


def set(key, value, ttl: int = 300):
    """Cache value for ttl seconds (default 5 min)."""
    with _lock:
        _store[key] = (value, time.time() + ttl)


def delete(key):
    """Invalidate a specific cache key."""
    with _lock:
        _store.pop(key, None)


def delete_prefix(prefix: str):
    """Invalidate all keys starting with prefix."""
    with _lock:
        keys = [k for k in _store if k.startswith(prefix)]
        for k in keys:
            del _store[k]


def clear():
    """Wipe the entire cache (e.g. on server restart)."""
    with _lock:
        _store.clear()
