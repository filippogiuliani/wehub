"""SQLite database: connection and schema. weHub is where the family is defined: who is in it, who the people
without an account are (kids, grandparents), and who may use which app."""
import os
import sqlite3
from contextlib import contextmanager

DATA_DIR = os.environ.get('WEHUB_DATA', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
DB_PATH = os.path.join(DATA_DIR, 'wehub.db')

SCHEMA_VERSION = 3
ROLES = ['admin', 'member']
PERSON_KINDS = ['adult', 'child']
# full = everything the app offers; limited = only what is about some people (used by apps that support it)
ACCESS_LEVELS = ['full', 'limited']
# weHub's own icons for links (drawn by the interface); links can also use Homepage-style icons, see icons.py
SHORTCUT_ICONS = ['link', 'lock', 'home', 'photo', 'film', 'music', 'server', 'chart', 'mail', 'calendar', 'book', 'cloud', 'tool']

SCHEMA = '''
CREATE TABLE IF NOT EXISTS families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,        -- bumped on every change: apps compare it before syncing
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    session_version INTEGER NOT NULL DEFAULT 1,
    consent_at TEXT,
    language TEXT NOT NULL DEFAULT 'it',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS members (
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (family_id, user_id)
);
-- Sign-in identities. `issuer` identifies the provider for the apps (they all use the same Pocket ID)
CREATE TABLE IF NOT EXISTS identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT,
    issuer TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (provider, subject)
);
CREATE INDEX IF NOT EXISTS idx_identities_issuer ON identities(issuer, subject);
CREATE TABLE IF NOT EXISTS tokens (
    hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Everyone documents, meals and to-dos can be about: each member (user_id set) and people without an account
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    birth_date DATE,
    kind TEXT NOT NULL DEFAULT 'adult',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_people_user ON people(family_id, user_id);
-- Which app each member may use (no row = no access)
CREATE TABLE IF NOT EXISTS access (
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'full',
    PRIMARY KEY (family_id, user_id, app)
);
-- What a family or a person was called inside an app before weHub (from the import): the app adopts that row
CREATE TABLE IF NOT EXISTS links (
    kind TEXT NOT NULL,                -- family | person
    hub_id INTEGER NOT NULL,
    app TEXT NOT NULL,
    local_id INTEGER NOT NULL,
    PRIMARY KEY (kind, app, local_id)
);
-- Links on the home page to other services (Vaultwarden, Home Assistant…): shown to everyone or to chosen members.
-- Showing a link is not access control: those services keep their own sign-in.
CREATE TABLE IF NOT EXISTS shortcuts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT 'link',          -- see icons.py
    grp TEXT NOT NULL DEFAULT '',               -- group on the home page ('' = none), as in Homepage's services.yaml
    monitor INTEGER NOT NULL DEFAULT 1,         -- 1 = the home page shows whether the service is up (status.py)
    everyone INTEGER NOT NULL DEFAULT 1,        -- 0 = only the members in shortcut_members
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS shortcut_members (
    shortcut_id INTEGER NOT NULL REFERENCES shortcuts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (shortcut_id, user_id)
);
-- When each app last fetched each family (shown to the admin)
CREATE TABLE IF NOT EXISTS app_seen (
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    app TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (family_id, app)
);
'''


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def bump(conn, family_id):
    if family_id:
        conn.execute('UPDATE families SET version = version + 1 WHERE id = ?', (family_id,))


def create_family(conn, name):
    return conn.execute('INSERT INTO families (name) VALUES (?)', (name,)).lastrowid


def add_member(conn, family_id, user_id, name, role='member', app_ids=None):
    """Member + their person + access to the given apps (default: every configured app)."""
    import apps
    conn.execute('INSERT OR IGNORE INTO members (family_id, user_id, role) VALUES (?,?,?)', (family_id, user_id, role))
    conn.execute('INSERT OR IGNORE INTO people (family_id, user_id, name) VALUES (?,?,?)', (family_id, user_id, name))
    for app in (apps.ids() if app_ids is None else app_ids):
        conn.execute("INSERT OR IGNORE INTO access (family_id, user_id, app, level) VALUES (?,?,?,'full')", (family_id, user_id, app))
    bump(conn, family_id)


def _migrate(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(shortcuts)')}
    if 'grp' not in cols:  # version 2: groups of links
        conn.execute("ALTER TABLE shortcuts ADD COLUMN grp TEXT NOT NULL DEFAULT ''")
    if 'monitor' not in cols:  # version 3: is the service up?
        conn.execute('ALTER TABLE shortcuts ADD COLUMN monitor INTEGER NOT NULL DEFAULT 1')


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        conn.execute('PRAGMA journal_mode = WAL')
        conn.commit()
    finally:
        conn.close()
