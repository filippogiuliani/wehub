"""API for the apps (doTrack, eaTrack, paTrack), authenticated with each app's key (Authorization: Bearer <key>).

- POST /api/service/whoami       after a sign-in with Pocket ID: who is this person, which families may they use
                                 this app in, and what those families look like
- GET  /api/service/families/<id> the current picture of a family (members with access to the app, people)

A snapshot: {hub_id, name, version, local_id, members: [{hub_id, name, email, role, level}],
             people: [{hub_id, name, birth_date, kind, user_hub_id, local_id}]}
local_id is the app's own id of that family/person when weHub knows it (from the import): the app adopts that row.

- GET  /api/service/dotrack/families/<id>/lists?user=<id>        doTrack's shopping lists of that family
- POST /api/service/dotrack/families/<id>/lists/<list>/items?user=<id>  {items}: add to one of them
  For eaTrack (weekly menu → shopping list): weHub passes the request on to doTrack with doTrack's key, so eaTrack
  needs no doTrack address or token. Only for a family the person is in and may use the calling app in."""
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
    members = [{'hub_id': r['id'], 'name': r['name'], 'email': r['email'], 'role': r['role'], 'level': r['level'],
                'language': r['language']}
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
            'members': members, 'people': people}


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


# ---------- One app asking another (eaTrack → doTrack), through weHub ----------

def _relay(family_id, method, path, payload=None):
    target = apps.get('dotrack')
    if not target or not target['key'] or g.app['id'] == 'dotrack':
        abort(404, 'doTrack is not connected to weHub')
    user_id = request.args.get('user', type=int)
    with db.transaction() as conn:
        ok = conn.execute('''SELECT 1 FROM members m JOIN access a ON a.family_id = m.family_id AND a.user_id = m.user_id
                             WHERE m.family_id = ? AND m.user_id = ? AND a.app = ?''', (family_id, user_id, g.app['id'])).fetchone()
    if not ok:
        abort(403, 'Not a member of this family')
    try:
        r = requests.request(method, f"{target['internal_url']}/api/hub/families/{family_id}{path}", params={'user': user_id},
                             json=payload, timeout=10, allow_redirects=False,
                             headers={'Authorization': f"Bearer {target['key']}", 'User-Agent': 'weHub'})
    except requests.RequestException:
        return jsonify(error='doTrack is not reachable'), 502
    try:
        data = r.json()
    except ValueError:
        return jsonify(error='doTrack answered with an error'), 502
    return jsonify(data), (r.status_code if r.status_code in (200, 201, 400, 404) else 502)


@bp.get('/service/dotrack/families/<int:family_id>/lists')
def dotrack_lists(family_id):
    return _relay(family_id, 'GET', '/lists')


@bp.post('/service/dotrack/families/<int:family_id>/lists/<int:list_id>/items')
def dotrack_items(family_id, list_id):
    items = body().get('items')
    if not isinstance(items, list) or not items or len(items) > 200:
        abort(400, 'Invalid request')
    return _relay(family_id, 'POST', f'/lists/{list_id}/items', {'items': items})
