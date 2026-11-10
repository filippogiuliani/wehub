"""API: the family. Members (added by email, they sign in with Pocket ID), roles, which apps each may use,
people without an account. Every change bumps the family version: the apps pick it up within a couple of minutes."""
from flask import Blueprint, abort, g, jsonify, session

import apps
import db
from auth import NO_PASSWORD, require_admin, valid_email
from common import body, text, valid_date

bp = Blueprint('family', __name__)
MAX_PEOPLE = 50


def _family(conn):
    f = conn.execute('SELECT id, name, version FROM families WHERE id = ?', (g.family_id,)).fetchone()
    members = [dict(r) for r in conn.execute(
        '''SELECT u.id, u.name, u.email, m.role, u.email_verified,
                  EXISTS (SELECT 1 FROM identities i WHERE i.user_id = u.id) OR u.password_hash != ? AS signed_in
           FROM members m JOIN users u ON u.id = m.user_id WHERE m.family_id = ? ORDER BY m.created_at''',
        (NO_PASSWORD, g.family_id))]
    access = {}
    for r in conn.execute('SELECT user_id, app, level FROM access WHERE family_id = ?', (g.family_id,)):
        access.setdefault(r['user_id'], {})[r['app']] = r['level']
    for m in members:
        m['me'] = m['id'] == g.user['id']
        m['signed_in'] = bool(m['signed_in'])
        m['access'] = access.get(m['id'], {})
    people = [dict(r) for r in conn.execute(
        'SELECT id, name, birth_date, kind, user_id FROM people WHERE family_id = ? ORDER BY user_id IS NULL, kind, name COLLATE NOCASE',
        (g.family_id,))]
    seen = {r['app']: r['at'] for r in conn.execute('SELECT app, at FROM app_seen WHERE family_id = ?', (g.family_id,))}
    return {**dict(f), 'members': members, 'people': people, 'role': g.role, 'apps': apps.public(), 'seen': seen}


@bp.get('/family')
def get_family():
    with db.transaction() as conn:
        return jsonify(_family(conn))


@bp.put('/family')
def rename():
    require_admin()
    name = text(body().get('name'), 80)
    if not name:
        abort(400, 'Name is required')
    with db.transaction() as conn:
        conn.execute('UPDATE families SET name = ? WHERE id = ?', (name, g.family_id))
        db.bump(conn, g.family_id)
        return jsonify(_family(conn))


@bp.post('/family/switch')
def switch():
    try:
        family_id = int(body().get('family_id'))
    except (TypeError, ValueError):
        abort(400, 'invalid family_id')
    if not any(f['id'] == family_id for f in g.families):
        abort(404, 'Family not found')
    session['family_id'] = family_id
    return jsonify(ok=True)


# ---------- Members ----------

def _apps_from(value):
    """{app: 'full'|'limited'|None} or [app, …] → {app: level} for known apps."""
    if isinstance(value, list):
        value = {a: 'full' for a in value}
    if not isinstance(value, dict):
        abort(400, 'Invalid apps')
    out = {}
    for app, level in value.items():
        if app not in apps.ids():
            abort(400, 'Invalid apps')
        if level:
            if level not in db.ACCESS_LEVELS:
                abort(400, 'Invalid apps')
            out[app] = level
    return out


@bp.post('/family/members')
def add_member():
    """Add someone by email. They sign in with Pocket ID using that same email."""
    require_admin()
    d = body()
    email = valid_email(d.get('email'))
    name = text(d.get('name'), 80)
    if not name:
        abort(400, 'Name is required')
    role = d.get('role') if d.get('role') in db.ROLES else 'member'
    granted = _apps_from(d.get('apps', apps.ids()))
    with db.transaction() as conn:
        u = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if u and conn.execute('SELECT 1 FROM members WHERE family_id = ? AND user_id = ?', (g.family_id, u['id'])).fetchone():
            abort(409, 'Already in the family')
        uid = u['id'] if u else conn.execute(
            "INSERT INTO users (email, name, password_hash, email_verified) VALUES (?,?,?,0)", (email, name, NO_PASSWORD)).lastrowid
        # A person with this name and no account (e.g. imported) becomes this member
        existing = conn.execute('SELECT id FROM people WHERE family_id = ? AND user_id IS NULL AND name = ? COLLATE NOCASE',
                                (g.family_id, u['name'] if u else name)).fetchone()
        if existing:
            conn.execute('UPDATE people SET user_id = ? WHERE id = ?', (uid, existing['id']))
        db.add_member(conn, g.family_id, uid, u['name'] if u else name, role, list(granted))
        for app, level in granted.items():
            conn.execute('UPDATE access SET level = ? WHERE family_id = ? AND user_id = ? AND app = ?', (level, g.family_id, uid, app))
        return jsonify(_family(conn)), 201


def _admins_after(conn, uid, new_role=None, removing=False):
    rows = conn.execute('SELECT user_id, role FROM members WHERE family_id = ?', (g.family_id,)).fetchall()
    admins = [r['user_id'] for r in rows if r['role'] == 'admin' and r['user_id'] != uid]
    if not removing and (new_role or '') == 'admin':
        admins.append(uid)
    return admins


@bp.put('/family/members/<int:uid>')
def update_member(uid):
    """Role and apps (admin only)."""
    require_admin()
    d = body()
    with db.transaction() as conn:
        m = conn.execute('SELECT role FROM members WHERE family_id = ? AND user_id = ?', (g.family_id, uid)).fetchone()
        if not m:
            abort(404, 'Member not found')
        if 'role' in d:
            if d['role'] not in db.ROLES:
                abort(400, 'Invalid role')
            if not _admins_after(conn, uid, d['role']):
                abort(400, 'The family needs at least one admin')
            conn.execute('UPDATE members SET role = ? WHERE family_id = ? AND user_id = ?', (d['role'], g.family_id, uid))
        if 'apps' in d:
            granted = _apps_from(d['apps'])
            conn.execute('DELETE FROM access WHERE family_id = ? AND user_id = ?', (g.family_id, uid))
            for app, level in granted.items():
                conn.execute('INSERT INTO access (family_id, user_id, app, level) VALUES (?,?,?,?)', (g.family_id, uid, app, level))
        if 'name' in d:
            name = text(d['name'], 80)
            u = conn.execute('SELECT password_hash FROM users WHERE id = ?', (uid,)).fetchone()
            # The name of someone who already signed in is theirs to change; before that the admin can fix it
            if name and not conn.execute('SELECT 1 FROM identities WHERE user_id = ?', (uid,)).fetchone() and u['password_hash'] == NO_PASSWORD:
                conn.execute('UPDATE users SET name = ? WHERE id = ?', (name, uid))
                conn.execute('UPDATE people SET name = ? WHERE user_id = ?', (name, uid))
        db.bump(conn, g.family_id)
        return jsonify(_family(conn))


@bp.delete('/family/members/<int:uid>')
def remove_member(uid):
    """An admin removes a member, anyone can leave. Their person stays (things about them stay in the apps)."""
    if uid != g.user['id']:
        require_admin()
    with db.transaction() as conn:
        members = conn.execute('SELECT user_id FROM members WHERE family_id = ?', (g.family_id,)).fetchall()
        if not any(m['user_id'] == uid for m in members):
            abort(404, 'Member not found')
        if len(members) == 1:
            abort(400, "You're the only member of the family")
        if not _admins_after(conn, uid, removing=True):
            abort(400, 'The family needs at least one admin')
        conn.execute('DELETE FROM members WHERE family_id = ? AND user_id = ?', (g.family_id, uid))
        conn.execute('DELETE FROM access WHERE family_id = ? AND user_id = ?', (g.family_id, uid))
        conn.execute('UPDATE people SET user_id = NULL WHERE family_id = ? AND user_id = ?', (g.family_id, uid))
        conn.execute('DELETE FROM shortcut_members WHERE user_id = ? AND shortcut_id IN (SELECT id FROM shortcuts WHERE family_id = ?)',
                     (uid, g.family_id))
        db.bump(conn, g.family_id)
        return jsonify(_family(conn))


# ---------- People without an account ----------

def _person_fields(conn, exclude=None, member=False):
    d = body()
    out = {}
    if not member:
        name = text(d.get('name'), 60)
        if not name:
            abort(400, 'Name is required')
        if conn.execute('SELECT 1 FROM people WHERE family_id = ? AND name = ? COLLATE NOCASE AND id IS NOT ?',
                        (g.family_id, name, exclude)).fetchone():
            abort(409, 'There is already someone with this name')
        out['name'] = name
    out['birth_date'] = valid_date(d['birth_date'], 'birth_date') if d.get('birth_date') else None
    out['kind'] = d.get('kind') if d.get('kind') in db.PERSON_KINDS else 'adult'
    return out


@bp.post('/family/people')
def add_person():
    with db.transaction() as conn:
        if conn.execute('SELECT COUNT(*) FROM people WHERE family_id = ?', (g.family_id,)).fetchone()[0] >= MAX_PEOPLE:
            abort(400, 'Too many people')
        f = _person_fields(conn)
        conn.execute('INSERT INTO people (family_id, name, birth_date, kind) VALUES (?,?,?,?)',
                     (g.family_id, f['name'], f['birth_date'], f['kind']))
        db.bump(conn, g.family_id)
        return jsonify(_family(conn)), 201


def _person(conn, pid):
    p = conn.execute('SELECT * FROM people WHERE id = ? AND family_id = ?', (pid, g.family_id)).fetchone()
    if not p:
        abort(404, 'Person not found')
    return p


@bp.put('/family/people/<int:pid>')
def update_person(pid):
    with db.transaction() as conn:
        p = _person(conn, pid)
        f = _person_fields(conn, exclude=pid, member=bool(p['user_id']))
        sets = ', '.join(f'{k} = ?' for k in f)
        conn.execute(f'UPDATE people SET {sets} WHERE id = ?', (*f.values(), pid))
        db.bump(conn, g.family_id)
        return jsonify(_family(conn))


@bp.delete('/family/people/<int:pid>')
def delete_person(pid):
    with db.transaction() as conn:
        p = _person(conn, pid)
        if p['user_id']:
            abort(400, 'A member is removed from the members')
        conn.execute('DELETE FROM people WHERE id = ?', (pid,))
        conn.execute("DELETE FROM links WHERE kind = 'person' AND hub_id = ?", (pid,))
        db.bump(conn, g.family_id)
        return jsonify(_family(conn))
