"""API: links to other services on the home page (Vaultwarden, Home Assistant, Immich…), in groups, like
Homepage (gethomepage.dev). A Homepage services.yaml can be imported as it is.

Everyone sees the links meant for everyone and those the admin chose for them; the admin manages them.
Hiding a link does not protect the service: it keeps its own sign-in."""
import os
import re
from urllib.parse import urlparse

import yaml
from flask import Blueprint, abort, g, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

import db
import icons
from auth import require_admin
from common import body, text

bp = Blueprint('shortcuts', __name__)
MAX = 100
COLS = 'id, name, url, description, icon, grp AS "group", monitor'


def _decorate(r):
    r = dict(r)
    r['monitor'] = bool(r['monitor'])
    r.update(icons.describe(r['icon'], r['id']))
    return r


def visible(conn, family_id, user_id):
    """The links this member sees, in order."""
    return [_decorate(r) for r in conn.execute(
        f'''SELECT {COLS} FROM shortcuts s WHERE family_id = ?
           AND (everyone = 1 OR EXISTS (SELECT 1 FROM shortcut_members m WHERE m.shortcut_id = s.id AND m.user_id = ?))
           ORDER BY position, id''', (family_id, user_id))]


def _all(conn):
    rows = [_decorate(r) for r in conn.execute(f'SELECT {COLS}, everyone, position FROM shortcuts '
                                               'WHERE family_id = ? ORDER BY position, id', (g.family_id,))]
    members = {}
    for r in conn.execute('''SELECT m.shortcut_id, m.user_id FROM shortcut_members m JOIN shortcuts s ON s.id = m.shortcut_id
                             WHERE s.family_id = ?''', (g.family_id,)):
        members.setdefault(r['shortcut_id'], []).append(r['user_id'])
    for r in rows:
        r['everyone'] = bool(r['everyone'])
        r['members'] = members.get(r['id'], [])
    return rows


def _url(value):
    url = text(value, 500)
    if '://' not in url:
        # "javascript:…", "data:…", "mailto:…": never; "vault.example.com" or "nas:8443": https
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)', url):
            abort(400, 'Invalid address')
        url = 'https://' + url
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.hostname:
        abort(400, 'Invalid address')
    return url


def _fields(conn):
    d = body()
    name = text(d.get('name'), 60)
    if not name:
        abort(400, 'Name is required')
    url = _url(d.get('url'))
    icon = icons.clean(d.get('icon'))
    everyone = d.get('everyone', True) is not False
    members = d.get('members') or []
    if not isinstance(members, list):
        abort(400, 'Invalid members')
    ok_ids = {r[0] for r in conn.execute('SELECT user_id FROM members WHERE family_id = ?', (g.family_id,))}
    members = sorted({int(m) for m in members if str(m).isdigit() and int(m) in ok_ids})
    if not everyone and not members:
        abort(400, 'Choose who sees it')
    return {'name': name, 'url': url, 'description': text(d.get('description'), 120), 'icon': icon,
            'group': text(d.get('group'), 60), 'monitor': 0 if d.get('monitor') is False else 1,
            'everyone': 1 if everyone else 0}, members


def _set_members(conn, sid, members):
    conn.execute('DELETE FROM shortcut_members WHERE shortcut_id = ?', (sid,))
    for uid in members:
        conn.execute('INSERT INTO shortcut_members (shortcut_id, user_id) VALUES (?,?)', (sid, uid))


@bp.get('/shortcuts')
def mine():
    with db.transaction() as conn:
        return jsonify(visible(conn, g.family_id, g.user['id']))


@bp.get('/shortcuts/status')
def status_of_mine():
    """{link id: {up, code, ms}} for the links this member sees and that are monitored."""
    import status
    with db.transaction() as conn:
        links = [l for l in visible(conn, g.family_id, g.user['id']) if l['monitor']]
    results = status.check_many([l['url'] for l in links])
    return jsonify({str(l['id']): results[l['url']] for l in links})


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
        sid = _insert(conn, f)
        _set_members(conn, sid, [] if f['everyone'] else members)
        return jsonify(_all(conn)), 201


def _insert(conn, f):
    """A new link at the end of its group (or at the end of the list when the group is new)."""
    last = conn.execute('SELECT MAX(position) FROM shortcuts WHERE family_id = ? AND grp = ?', (g.family_id, f['group'])).fetchone()[0]
    if last is None:
        pos = conn.execute('SELECT COALESCE(MAX(position), 0) + 1 FROM shortcuts WHERE family_id = ?', (g.family_id,)).fetchone()[0]
    else:
        pos = last + 1
        conn.execute('UPDATE shortcuts SET position = position + 1 WHERE family_id = ? AND position >= ?', (g.family_id, pos))
    return conn.execute('INSERT INTO shortcuts (family_id, name, url, description, icon, grp, monitor, everyone, position) '
                        'VALUES (?,?,?,?,?,?,?,?,?)', (g.family_id, f['name'], f['url'], f['description'], f['icon'],
                                                       f['group'], f.get('monitor', 1), f['everyone'], pos)).lastrowid


def _own(conn, sid):
    if not conn.execute('SELECT 1 FROM shortcuts WHERE id = ? AND family_id = ?', (sid, g.family_id)).fetchone():
        abort(404, 'Link not found')


@bp.put('/family/shortcuts/<int:sid>')
def update(sid):
    require_admin()
    with db.transaction() as conn:
        _own(conn, sid)
        f, members = _fields(conn)
        conn.execute('UPDATE shortcuts SET name = ?, url = ?, description = ?, icon = ?, grp = ?, monitor = ?, everyone = ? WHERE id = ?',
                     (f['name'], f['url'], f['description'], f['icon'], f['group'], f['monitor'], f['everyone'], sid))
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


# ---------- Import of a Homepage services.yaml ----------

def _services(doc):
    """[(group, name, fields)] from Homepage's services.yaml: a list of {group: [{name: {href, icon, description…}}]}.
    Groups inside groups keep the inner name; entries without href (widgets only) are skipped."""
    out = []

    def walk(group, entries):
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            for name, v in entry.items():
                if isinstance(v, list):
                    walk(str(name), v)
                elif isinstance(v, dict):
                    out.append((group, str(name), v))

    if not isinstance(doc, list):
        abort(400, 'This is not a Homepage services.yaml')
    for block in doc:
        if isinstance(block, dict):
            for group, entries in block.items():
                walk(str(group), entries)
    if not out:
        abort(400, 'This is not a Homepage services.yaml')
    return out


@bp.post('/family/shortcuts/import')
def import_yaml():
    """{yaml}: the links of a Homepage services.yaml. A link with the same address is updated, the others added
    (for everyone). Fields weHub does not use (container, server, widget, ping…) are ignored."""
    require_admin()
    src = body().get('yaml')
    if not isinstance(src, str) or not src.strip():
        abort(400, 'Paste the content of services.yaml')
    try:
        doc = yaml.safe_load(src)
    except yaml.YAMLError as e:
        mark = getattr(e, 'problem_mark', None)
        abort(400, f'Invalid YAML (line {mark.line + 1})' if mark else 'Invalid YAML')
    added, updated, skipped = [], [], []
    with db.transaction() as conn:
        for group, name, v in _services(doc):
            name, group = text(name, 60), text(group, 60)
            href = v.get('href')
            if not name or not isinstance(href, str) or not href.strip():
                skipped.append(name or '?')
                continue
            try:
                url = _url(href)
            except HTTPException:  # an invalid address
                skipped.append(name)
                continue
            f = {'name': name, 'url': url, 'description': text(v.get('description'), 120),
                 'icon': icons.clean(v.get('icon')), 'group': group, 'everyone': 1}
            r = conn.execute('SELECT id FROM shortcuts WHERE family_id = ? AND url = ?', (g.family_id, url)).fetchone()
            if r:
                conn.execute('UPDATE shortcuts SET name = ?, description = ?, icon = ?, grp = ? WHERE id = ?',
                             (f['name'], f['description'], f['icon'], f['group'], r['id']))
                updated.append(name)
                continue
            if conn.execute('SELECT COUNT(*) FROM shortcuts WHERE family_id = ?', (g.family_id,)).fetchone()[0] >= MAX:
                skipped.append(name)
                continue
            _insert(conn, f)
            added.append(name)
        return jsonify(added=added, updated=updated, skipped=skipped, links=_all(conn))


# ---------- Icons ----------

@bp.get('/icons/<int:sid>')
def icon(sid):
    """The image of a link's icon, downloaded once and kept by weHub (see icons.py)."""
    with db.transaction() as conn:
        r = conn.execute('SELECT icon FROM shortcuts WHERE id = ? AND family_id = ?', (sid, g.family_id)).fetchone()
    if not r:
        abort(404, 'Link not found')
    got = icons.fetch(r['icon'])
    if not got:
        abort(404, 'Icon not available')
    path, mime = got
    resp = send_file(path, mimetype=mime, max_age=0, conditional=True, etag=True)
    # The address carries the icon's version (?v=): the browser may keep it
    resp.headers['Cache-Control'] = 'private, max-age=604800' if request.args.get('v') else 'private, no-cache'
    # An SVG opened on its own runs nothing
    resp.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    resp.headers['Content-Disposition'] = f'inline; filename="{os.path.basename(path)}"'
    return resp
