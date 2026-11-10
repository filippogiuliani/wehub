"""API: links to other services on the home page (Vaultwarden, Home Assistant, Immich…).

Everyone sees the links meant for everyone and those the admin chose for them; the admin manages them.
Hiding a link does not protect the service: it keeps its own sign-in."""
import re
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify

import db
from auth import require_admin
from common import body, text

bp = Blueprint('shortcuts', __name__)
MAX = 60


def visible(conn, family_id, user_id):
    """The links this member sees, in order."""
    return [dict(r) for r in conn.execute(
        '''SELECT id, name, url, description, icon FROM shortcuts s WHERE family_id = ?
           AND (everyone = 1 OR EXISTS (SELECT 1 FROM shortcut_members m WHERE m.shortcut_id = s.id AND m.user_id = ?))
           ORDER BY position, id''', (family_id, user_id))]


def _all(conn):
    rows = [dict(r) for r in conn.execute('SELECT id, name, url, description, icon, everyone, position FROM shortcuts '
                                          'WHERE family_id = ? ORDER BY position, id', (g.family_id,))]
    members = {}
    for r in conn.execute('''SELECT m.shortcut_id, m.user_id FROM shortcut_members m JOIN shortcuts s ON s.id = m.shortcut_id
                             WHERE s.family_id = ?''', (g.family_id,)):
        members.setdefault(r['shortcut_id'], []).append(r['user_id'])
    for r in rows:
        r['everyone'] = bool(r['everyone'])
        r['members'] = members.get(r['id'], [])
    return rows


def _fields(conn):
    d = body()
    name = text(d.get('name'), 60)
    if not name:
        abort(400, 'Name is required')
    url = text(d.get('url'), 500)
    if '://' not in url:
        # "javascript:…", "data:…", "mailto:…": never; "vault.example.com" or "nas:8443": https
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)', url):
            abort(400, 'Invalid address')
        url = 'https://' + url
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.hostname:
        abort(400, 'Invalid address')
    icon = d.get('icon') if d.get('icon') in db.SHORTCUT_ICONS else 'link'
    everyone = d.get('everyone', True) is not False
    members = d.get('members') or []
    if not isinstance(members, list):
        abort(400, 'Invalid members')
    ok_ids = {r[0] for r in conn.execute('SELECT user_id FROM members WHERE family_id = ?', (g.family_id,))}
    members = sorted({int(m) for m in members if str(m).isdigit() and int(m) in ok_ids})
    if not everyone and not members:
        abort(400, 'Choose who sees it')
    return {'name': name, 'url': url, 'description': text(d.get('description'), 120), 'icon': icon,
            'everyone': 1 if everyone else 0}, members


def _set_members(conn, sid, members):
    conn.execute('DELETE FROM shortcut_members WHERE shortcut_id = ?', (sid,))
    for uid in members:
        conn.execute('INSERT INTO shortcut_members (shortcut_id, user_id) VALUES (?,?)', (sid, uid))


@bp.get('/shortcuts')
def mine():
    with db.transaction() as conn:
        return jsonify(visible(conn, g.family_id, g.user['id']))


@bp.get('/family/shortcuts')
def all_shortcuts():
    require_admin()
    with db.transaction() as conn:
        return jsonify(_all(conn))


@bp.post('/family/shortcuts')
def create():
    require_admin()
    with db.transaction() as conn:
        if conn.execute('SELECT COUNT(*) FROM shortcuts WHERE family_id = ?', (g.family_id,)).fetchone()[0] >= MAX:
            abort(400, 'Too many links')
        f, members = _fields(conn)
        pos = conn.execute('SELECT COALESCE(MAX(position), 0) + 1 FROM shortcuts WHERE family_id = ?', (g.family_id,)).fetchone()[0]
        sid = conn.execute('INSERT INTO shortcuts (family_id, name, url, description, icon, everyone, position) VALUES (?,?,?,?,?,?,?)',
                           (g.family_id, f['name'], f['url'], f['description'], f['icon'], f['everyone'], pos)).lastrowid
        _set_members(conn, sid, [] if f['everyone'] else members)
        return jsonify(_all(conn)), 201


def _own(conn, sid):
    if not conn.execute('SELECT 1 FROM shortcuts WHERE id = ? AND family_id = ?', (sid, g.family_id)).fetchone():
        abort(404, 'Link not found')


@bp.put('/family/shortcuts/<int:sid>')
def update(sid):
    require_admin()
    with db.transaction() as conn:
        _own(conn, sid)
        f, members = _fields(conn)
        conn.execute('UPDATE shortcuts SET name = ?, url = ?, description = ?, icon = ?, everyone = ? WHERE id = ?',
                     (f['name'], f['url'], f['description'], f['icon'], f['everyone'], sid))
        _set_members(conn, sid, [] if f['everyone'] else members)
        return jsonify(_all(conn))


@bp.post('/family/shortcuts/<int:sid>/move')
def move(sid):
    """{direction: -1 | 1}: one place earlier or later."""
    require_admin()
    step = -1 if body().get('direction') == -1 else 1
    with db.transaction() as conn:
        _own(conn, sid)
        ids = [r[0] for r in conn.execute('SELECT id FROM shortcuts WHERE family_id = ? ORDER BY position, id', (g.family_id,))]
        i = ids.index(sid)
        j = i + step
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
        for pos, x in enumerate(ids):
            conn.execute('UPDATE shortcuts SET position = ? WHERE id = ?', (pos, x))
        return jsonify(_all(conn))


@bp.delete('/family/shortcuts/<int:sid>')
def delete(sid):
    require_admin()
    with db.transaction() as conn:
        _own(conn, sid)
        conn.execute('DELETE FROM shortcuts WHERE id = ?', (sid,))
        return jsonify(_all(conn))
