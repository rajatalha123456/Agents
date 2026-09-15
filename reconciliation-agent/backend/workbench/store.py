"""Transactional local persistence; not a replacement for PostgreSQL RLS."""
import copy
import json
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _seeded_users_once():
    """Password hashing is deliberately slow (that's the point of PBKDF2) —
    computed once per process and cached, never recomputed on every
    `read()`/`transaction()` call. Callers get a deep copy so mutating one
    state dict's `users` list can never leak into another's.
    """
    from workbench.auth import seed_users
    return seed_users()


def _cheap_defaults():
    return {"records": [], "imports": [], "matches": [], "breaks": [], "journal_drafts": [], "runs": [], "audit": [], "periods": {}, "sample_loaded": False}


def empty_state():
    state = _cheap_defaults()
    state["users"] = copy.deepcopy(_seeded_users_once())
    return state


def _migrate(state: dict) -> dict:
    """A database created before a new top-level key existed (e.g.
    `journal_drafts`) would otherwise KeyError the first time code reads
    it — this fills in any missing key with a cheap structural default,
    once, on every load, rather than requiring a one-off migration script
    for a local dev SQLite file. `users` is the one expensive default
    (real password hashing), so it's computed at most once per process
    (see `_seeded_users_once`) and only touched at all when actually
    missing, never reconstructed just to be discarded.
    """
    if "users" not in state:
        state["users"] = copy.deepcopy(_seeded_users_once())
    for key, default in _cheap_defaults().items():
        state.setdefault(key, default)
    return state


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO workspace VALUES (1, ?)", (json.dumps(empty_state()),))

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = _migrate(json.loads(connection.execute("SELECT payload FROM workspace WHERE id=1").fetchone()[0]))
            yield state
            connection.execute("UPDATE workspace SET payload=? WHERE id=1", (json.dumps(state),))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self):
        with sqlite3.connect(self.path) as connection:
            return _migrate(json.loads(connection.execute("SELECT payload FROM workspace WHERE id=1").fetchone()[0]))
