"""Import from the apps (admin): bring the members and people the apps already have into weHub, once.

GET  /api/import/preview[?dotrack=<local family id>&…]  reads each app's families and proposes how to merge them
POST /api/import/apply                                 creates members and people and remembers which family/person
                                                       of each app they were, so each app adopts its existing rows

Each app answers GET <app>/api/hub/export (with its key):
  {families: [{local_id, name, hub_id, members: [{email, name, role}],
               people: [{local_id, name, birth_date, kind, member_email}]}]}"""
import re
import unicodedata

import requests
from flask import Blueprint, abort, g, jsonify, request

import apps
import db
from auth import NO_PASSWORD, require_admin
from common import body, text

bp = Blueprint('import', __name__)
TIMEOUT = 15


def norm(name):
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^\w ]', ' ', s)).strip()


def fetch_export(app):
    """The app's families, or raises with a readable reason."""
    if not app['internal_url'] or not app['key']:
        raise RuntimeError('address or key not configured')
    try:
        r = requests.get(app['internal_url'] + '/api/hub/export', timeout=TIMEOUT, allow_redirects=False,
                         headers={'Authorization': 'Bearer ' + app['key'], 'User-Agent': 'weHub'})
    except requests.RequestException as e:
        raise RuntimeError(f'not reachable ({type(e).__name__})')
    if r.status_code == 401:
        raise RuntimeError('the key does not match')
    if r.status_code == 404:
        raise RuntimeError('this version of the app has no weHub support')
    if r.status_code != 200:
        raise RuntimeError(f'error {r.status_code}')
    return r.json().get('families', [])


def _proposal(conn, exports, selected):
    """Members and people groups from the chosen family of each app."""
    hub_people = [dict(r) for r in conn.execute('SELECT id, name, birth_date, kind, user_id FROM people WHERE family_id = ?',
                                                (g.family_id,))]
    hub_emails = {r[0].lower() for r in conn.execute(
        'SELECT u.email FROM members m JOIN users u ON u.id = m.user_id WHERE m.family_id = ?', (g.family_id,))}
    members, groups = {}, {}
    for app_id, fams in exports.items():
        fam = next((f for f in fams if f['local_id'] == selected.get(app_id)), None)
        if not fam:
            continue
        for m in fam.get('members', []):
            e = (m.get('email') or '').lower()
            if not e:
                continue
            cur = members.setdefault(e, {'email': e, 'name': m.get('name') or e, 'role': 'member', 'exists': e in hub_emails,
                                         'apps': []})
            cur['apps'].append(app_id)
            if m.get('role') == 'admin':
                cur['role'] = 'admin'
        for p in fam.get('people', []):
            if p.get('member_email'):
                continue  # a member: they are matched by email
            key = norm(p['name'])
            if not key:
                continue
            grp = groups.get(key)
            if not grp:
                match = next((h for h in hub_people if norm(h['name']) == key), None)
                grp = groups[key] = {'key': key, 'name': p['name'], 'birth_date': p.get('birth_date'),
                                     'kind': p.get('kind') or 'adult', 'target': match['id'] if match else None, 'sources': []}
            grp['sources'].append({'app': app_id, 'local_id': p['local_id'], 'name': p['name'],
                                   'birth_date': p.get('birth_date')})
            if p.get('kind') == 'child':
                grp['kind'] = 'child'
            if p.get('birth_date') and not grp['birth_date']:
                grp['birth_date'] = p['birth_date']
    return sorted(members.values(), key=lambda m: m['email']), list(groups.values()), hub_people


@bp.get('/import/preview')
def preview():
    require_admin()
    out, exports, selected = [], {}, {}
    with db.transaction() as conn:
        linked = {(r['app'], r['local_id']) for r in conn.execute(
            "SELECT app, local_id FROM links WHERE kind = 'family' AND hub_id = ?", (g.family_id,))}
    me = g.user['email'].lower()
    for app_id in apps.ids():
        app = apps.get(app_id)
        entry = {'id': app_id, 'name': app['name'], 'ok': True, 'error': None, 'families': [], 'selected': None}
        try:
            fams = fetch_export(app)
        except RuntimeError as e:
            entry.update(ok=False, error=str(e))
            out.append(entry)
            continue
        exports[app_id] = fams
        entry['families'] = [{'local_id': f['local_id'], 'name': f['name'], 'hub_id': f.get('hub_id'),
                              'members': [m.get('name') for m in f.get('members', [])],
                              'people': [p['name'] for p in f.get('people', []) if not p.get('member_email')]} for f in fams]
        asked = request.args.get(app_id)
        if asked == 'none':
            sel = None
        elif asked and asked.isdigit() and any(f['local_id'] == int(asked) for f in fams):
            sel = int(asked)
        else:
            # Already linked, otherwise the family I am a member of (admin first)
            sel = next((f['local_id'] for f in fams if (app_id, f['local_id']) in linked), None)
            if sel is None:
                mine = [f for f in fams if any((m.get('email') or '').lower() == me for m in f.get('members', []))]
                mine.sort(key=lambda f: 0 if any((m.get('email') or '').lower() == me and m.get('role') == 'admin'
                                                 for m in f.get('members', [])) else 1)
                sel = mine[0]['local_id'] if mine else None
        entry['selected'] = sel
        if sel is not None:
            selected[app_id] = sel
        out.append(entry)
    with db.transaction() as conn:
        members, groups, hub_people = _proposal(conn, exports, selected)
    return jsonify(apps=out, members=members, groups=groups,
                   hub_people=[{'id': h['id'], 'name': h['name']} for h in hub_people if not h['user_id']])


@bp.post('/import/apply')
def apply():
    """{selected: {app: local_id}, members: [{email, name, role, apps}], groups: [{name, birth_date, kind,
    target: hub person id | null (new) | "skip", sources: [{app, local_id}]}]}"""
    require_admin()
    d = body()
    selected = d.get('selected') or {}
    if not isinstance(selected, dict) or any(a not in apps.ids() for a in selected):
        abort(400, 'Invalid request')
    counts = {'families': 0, 'members': 0, 'people': 0, 'linked': 0}
    with db.transaction() as conn:
        for app_id, local_id in selected.items():
            if local_id is None:
                continue
            conn.execute("DELETE FROM links WHERE kind = 'family' AND app = ? AND (hub_id = ? OR local_id = ?)",
                         (app_id, g.family_id, int(local_id)))
            conn.execute("INSERT INTO links (kind, hub_id, app, local_id) VALUES ('family', ?, ?, ?)", (g.family_id, app_id, int(local_id)))
            counts['families'] += 1
        for m in d.get('members') or []:
            email = text(m.get('email'), 254).lower()
            if '@' not in email:
                continue
            u = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if u and conn.execute('SELECT 1 FROM members WHERE family_id = ? AND user_id = ?', (g.family_id, u['id'])).fetchone():
                continue
            name = text(m.get('name'), 80) or email
            uid = u['id'] if u else conn.execute(
                'INSERT INTO users (email, name, password_hash, email_verified) VALUES (?,?,?,0)', (email, name, NO_PASSWORD)).lastrowid
            granted = [a for a in (m.get('apps') or apps.ids()) if a in apps.ids()]
            db.add_member(conn, g.family_id, uid, u['name'] if u else name, 'admin' if m.get('role') == 'admin' else 'member', granted)
            counts['members'] += 1
        for grp in d.get('groups') or []:
            target = grp.get('target')
            if target == 'skip':
                continue
            if target:
                p = conn.execute('SELECT * FROM people WHERE id = ? AND family_id = ?', (int(target), g.family_id)).fetchone()
                if not p:
                    abort(400, 'Person not found')
                pid = p['id']
                if grp.get('birth_date') and not p['birth_date']:
                    conn.execute('UPDATE people SET birth_date = ? WHERE id = ?', (grp['birth_date'], pid))
                if grp.get('kind') == 'child' and p['kind'] != 'child':
                    conn.execute("UPDATE people SET kind = 'child' WHERE id = ?", (pid,))
            else:
                name = text(grp.get('name'), 60)
                if not name:
                    continue
                pid = conn.execute('INSERT INTO people (family_id, name, birth_date, kind) VALUES (?,?,?,?)',
                                   (g.family_id, name, grp.get('birth_date') or None,
                                    grp.get('kind') if grp.get('kind') in db.PERSON_KINDS else 'adult')).lastrowid
                counts['people'] += 1
            for s in grp.get('sources') or []:
                if s.get('app') in apps.ids() and str(s.get('local_id', '')).isdigit():
                    conn.execute("INSERT OR REPLACE INTO links (kind, hub_id, app, local_id) VALUES ('person', ?, ?, ?)",
                                 (pid, s['app'], int(s['local_id'])))
                    counts['linked'] += 1
        db.bump(conn, g.family_id)
    return jsonify(counts)
