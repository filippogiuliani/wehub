"""API for the apps (doTrack, eaTrack, paTrack), authenticated with each app's key (Authorization: Bearer <key>).

- POST /api/service/whoami       after a sign-in with Pocket ID: who is this person, which families may they use
                                 this app in, and what those families look like
- GET  /api/service/families/<id> the current picture of a family (members with access to the app, people)

A snapshot: {hub_id, name, version, local_id, members: [{hub_id, name, email, role, level, apps}],
             people: [{hub_id, name, birth_date, kind, user_hub_id, local_id}], apps: [{id, name, url, description}]}
members[].apps: the apps that member may use in the family (for the app switcher).
local_id is the app's own id of that family/person when weHub knows it (from the import): the app adopts that row.

- /api/service/apps/<app>/families/<id>/<path>?user=<id>   one app asking another (see ALLOWED): weHub passes the
  request on to <app>'s /api/hub/families/<id>/<path> with that app's key, adding ?level= (the person's access to
  <app>, empty when none) and ?from= (the asking app)."""
import re

import requests
from flask import Blueprint, abort, g, jsonify, request

import apps
import db
from common import body, text

bp = Blueprint('service', __name__)


@bp.before_request
def app_key():
    auth = request.headers.get('Authorization', '')
    app = apps.by_key(auth[7:].strip() if auth.startswith('Bearer ') else '')
    if not app:
        return jsonify(error='Unknown app key'), 401
    g.app = app
    return None


def _link(conn, kind, hub_id):
    r = conn.execute('SELECT local_id FROM links WHERE kind = ? AND hub_id = ? AND app = ?', (kind, hub_id, g.app['id'])).fetchone()
    return r[0] if r else None


def snapshot(conn, family_id):
    f = conn.execute('SELECT id, name, version FROM families WHERE id = ?', (family_id,)).fetchone()
    if not f:
        return None
    can_use = {}
    for r in conn.execute('SELECT user_id, app FROM access WHERE family_id = ? ORDER BY app', (family_id,)):
        can_use.setdefault(r['user_id'], []).append(r['app'])
    members = [{'hub_id': r['id'], 'name': r['name'], 'email': r['email'], 'role': r['role'], 'level': r['level'],
                'language': r['language'], 'apps': can_use.get(r['id'], [])}
               for r in conn.execute('''SELECT u.id, u.name, u.email, u.language, m.role, a.level FROM members m
                                        JOIN users u ON u.id = m.user_id
                                        JOIN access a ON a.family_id = m.family_id AND a.user_id = m.user_id AND a.app = ?
                                        WHERE m.family_id = ? ORDER BY m.created_at''', (g.app['id'], family_id))]
    people = [{'hub_id': r['id'], 'name': r['name'], 'birth_date': r['birth_date'], 'kind': r['kind'],
               'user_hub_id': r['user_id'], 'local_id': _link(conn, 'person', r['id'])}
              for r in conn.execute('SELECT * FROM people WHERE family_id = ? ORDER BY id', (family_id,))]
    conn.execute("INSERT INTO app_seen (family_id, app, at) VALUES (?, ?, datetime('now')) "
                 "ON CONFLICT(family_id, app) DO UPDATE SET at = excluded.at", (family_id, g.app['id']))
    return {'hub_id': f['id'], 'name': f['name'], 'version': f['version'], 'local_id': _link(conn, 'family', f['id']),
            'members': members, 'people': people, 'apps': apps.public()}


def _user(u):
    return {'hub_id': u['id'], 'name': u['name'], 'email': u['email'], 'language': u['language']}


@bp.post('/service/whoami')
def whoami():
    d = body()
    issuer, subject = text(d.get('issuer'), 300), text(d.get('subject'), 300)
    email = text(d.get('email'), 254).lower()
    if not subject:
        abort(400, 'subject is required')
    with db.transaction() as conn:
        u = conn.execute('''SELECT u.* FROM identities i JOIN users u ON u.id = i.user_id
                            WHERE i.issuer = ? AND i.subject = ?''', (issuer, subject)).fetchone()
        if not u and email and d.get('email_verified'):
            # First time this person comes through an app: their account in weHub has the same (verified) email
            u = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if u:
                conn.execute('INSERT OR IGNORE INTO identities (provider, subject, user_id, email, issuer) VALUES (?,?,?,?,?)',
                             (issuer or 'oidc', subject, u['id'], email, issuer))
                if not u['email_verified']:
                    conn.execute('UPDATE users SET email_verified = 1 WHERE id = ?', (u['id'],))
        if not u:
            return jsonify(known=False)
        fams = [r[0] for r in conn.execute('''SELECT m.family_id FROM members m JOIN access a
                                              ON a.family_id = m.family_id AND a.user_id = m.user_id AND a.app = ?
                                              WHERE m.user_id = ? ORDER BY m.created_at''', (g.app['id'], u['id']))]
        return jsonify(known=True, user=_user(u), families=[snapshot(conn, f) for f in fams])


@bp.get('/service/families/<int:family_id>')
def family(family_id):
    """With ?version=N: {unchanged: true} when nothing changed since that version."""
    with db.transaction() as conn:
        f = conn.execute('SELECT version FROM families WHERE id = ?', (family_id,)).fetchone()
        if not f:
            abort(404, 'Family not found')
        if request.args.get('version') == str(f['version']):
            conn.execute("UPDATE app_seen SET at = datetime('now') WHERE family_id = ? AND app = ?", (family_id, g.app['id']))
            return jsonify(unchanged=True, version=f['version'])
        return jsonify(snapshot(conn, family_id))


# ---------- One app asking another, through weHub ----------
# The asking app never needs the other app's address or key: weHub passes the request on with the key it holds, for a
# family the person is in and may use the asking app in. Only the calls listed here go through.
#   (asking app, answering app): [(method, path regex, the person must also have access to the answering app)]
ALLOWED = {
    ('eatrack', 'dotrack'): [('GET', r'/lists', False),                      # weekly menu → shopping list
                             ('POST', r'/lists/\d+/items', False)],
    ('patrack', 'dotrack'): [('PUT', r'/deadlines/patrack-\d+', False),       # a document's expiry → a deadline
                             ('DELETE', r'/deadlines/patrack-\d+', False)],
    ('dotrack', 'patrack'): [('POST', r'/documents', True)],                 # a deadline's document → the archive
    ('eatrack', 'patrack'): [('GET', r'/plans', True)],                      # the paediatrician's plans of a child
}
MAX_RELAYED = 30 * 1024 * 1024   # a document (base64) from doTrack to paTrack; everything else stays under 1 MB
PASSED_ON = (200, 201, 400, 403, 404, 409)


def _allowed(target, method, path):
    """(allowed, the person must have access to the target too)"""
    for m, rule, needs_access in ALLOWED.get((g.app['id'], target), []):
        if m == method and re.fullmatch(rule, path):
            return True, needs_access
    return False, False


def _level(conn, family_id, user_id, app_id):
    """The person's access to that app in that family ('full', 'limited'), None when they may not use it."""
    r = conn.execute('''SELECT a.level FROM members m JOIN access a ON a.family_id = m.family_id AND a.user_id = m.user_id
                        WHERE m.family_id = ? AND m.user_id = ? AND a.app = ?''', (family_id, user_id, app_id)).fetchone()
    return r['level'] if r else None


@bp.route('/service/apps/<target>/families/<int:family_id>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def relay(target, family_id, path):
    path = '/' + path
    allowed, needs_access = _allowed(target, request.method, path)
    if not allowed:
        abort(403, 'This app may not ask that')
    app = apps.get(target)
    if not app or not app['key']:
        abort(404, f'{target} is not connected to weHub')
    user_id = request.args.get('user', type=int)
    with db.transaction() as conn:
        if not _level(conn, family_id, user_id, g.app['id']):
            abort(403, 'Not a member of this family')
        target_level = _level(conn, family_id, user_id, target)
    if needs_access and not target_level:
        abort(403, f"You do not use {app['name']} in this family")
    params = {k: v for k, v in request.args.items() if k not in ('user', 'level', 'from')}
    params.update({'user': user_id, 'level': target_level or '', 'from': g.app['id']})
    payload = request.get_json(silent=True) if request.method in ('POST', 'PUT') else None
    try:
        r = requests.request(request.method, f"{app['internal_url']}/api/hub/families/{family_id}{path}", params=params,
                             json=payload, timeout=10, allow_redirects=False,
                             headers={'Authorization': f"Bearer {app['key']}", 'User-Agent': 'weHub'})
    except requests.RequestException:
        return jsonify(error=f"{app['name']} is not reachable"), 502
    try:
        data = r.json()
    except ValueError:
        return jsonify(error=f"{app['name']} answered with an error"), 502
    return jsonify(data), (r.status_code if r.status_code in PASSED_ON else 502)


# The addresses eaTrack used before the general route (images built before 2026-11-13)
@bp.get('/service/dotrack/families/<int:family_id>/lists')
def dotrack_lists(family_id):
    return relay('dotrack', family_id, 'lists')


@bp.post('/service/dotrack/families/<int:family_id>/lists/<int:list_id>/items')
def dotrack_items(family_id, list_id):
    return relay('dotrack', family_id, f'lists/{list_id}/items')
