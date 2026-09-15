"""SQLite metadata and tenant-scoped, server-generated artifact locations."""
import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

def identifier(prefix: str) -> str:
    return prefix + '_' + uuid.uuid4().hex

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'metadata.sqlite3'
        with self.connect() as con:
            con.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY, name TEXT, key_hash TEXT, config TEXT);
            CREATE TABLE IF NOT EXISTS objects(tenant TEXT, kind TEXT, id TEXT, body TEXT, PRIMARY KEY(tenant,kind,id));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, tenant TEXT, event TEXT, body TEXT, timestamp TEXT);
            ''')
    def connect(self):
        return sqlite3.connect(self.db, timeout=30)
    def create_tenant(self, name, edges):
        tid, key = identifier('tenant'), secrets.token_urlsafe(32)
        with self.connect() as con:
            con.execute('INSERT INTO tenants VALUES(?,?,?,?)', (tid, name, digest(key), json.dumps({'band_edges': edges})))
        self.audit(tid, 'tenant.created', {})
        return {'tenant_id': tid, 'name': name, 'api_key': key, 'band_edges': edges}
    def tenant(self, tid):
        with self.connect() as con:
            row = con.execute('SELECT id,name,key_hash,config FROM tenants WHERE id=?', (tid,)).fetchone()
        if not row:
            raise KeyError('Tenant not found')
        return {'tenant_id': row[0], 'name': row[1], 'key_hash': row[2], **json.loads(row[3])}
    def path(self, tid, *parts):
        self.tenant(tid)
        path = self.root.joinpath(tid, *parts).resolve()
        if not path.is_relative_to(self.root / tid):
            raise ValueError('Invalid artifact path')
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    def put(self, tid, kind, oid, body):
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?,?)', (tid, kind, oid, json.dumps(body, allow_nan=False)))
    def get(self, tid, kind, oid):
        with self.connect() as con:
            row = con.execute('SELECT body FROM objects WHERE tenant=? AND kind=? AND id=?', (tid, kind, oid)).fetchone()
        if not row:
            raise KeyError(f'{kind} not found')
        return json.loads(row[0])
    def list(self, tid, kind):
        with self.connect() as con:
            rows = con.execute('SELECT body FROM objects WHERE tenant=? AND kind=? ORDER BY rowid', (tid, kind)).fetchall()
        return [json.loads(r[0]) for r in rows]
    def audit(self, tid, event, body):
        # Callers supply only IDs/metrics, never member records, raw messages or credentials.
        with self.connect() as con:
            con.execute('INSERT INTO audit(tenant,event,body,timestamp) VALUES(?,?,?,?)', (tid, event, json.dumps(body), now()))
    def events(self, tid):
        with self.connect() as con:
            rows = con.execute('SELECT event,body,timestamp FROM audit WHERE tenant=? ORDER BY id DESC LIMIT 200', (tid,)).fetchall()
        return [{'event': r[0], 'details': json.loads(r[1]), 'timestamp': r[2]} for r in rows]
    def promote(self, tid, version):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            rows = con.execute("SELECT id,body FROM objects WHERE tenant=? AND kind='model'", (tid,)).fetchall()
            models = {r[0]: json.loads(r[1]) for r in rows}
            if version not in models or models[version]['status'] not in ('validated', 'production', 'retired'):
                raise ValueError('Only validated models can be promoted')
            for mid, body in models.items():
                if mid == version or body['status'] == 'production':
                    body['status'] = 'production' if mid == version else 'retired'
                    con.execute("UPDATE objects SET body=? WHERE tenant=? AND kind='model' AND id=?", (json.dumps(body), tid, mid))
        self.audit(tid, 'model.promoted', {'version': version})
