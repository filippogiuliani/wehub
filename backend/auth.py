"""Authentication: users, sessions, single-use tokens and rate limiting.

In production people sign in only with the OIDC provider (Pocket ID). Password sign-in exists for development and
for a first admin before the provider is set up (WEHUB_PASSWORD_LOGIN=0 turns it off)."""
import datetime
import hashlib
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, abort, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import apps
import db
import i18n
import mail
from common import body, text

bp = Blueprint('auth', __name__)

# WEHUB_SIGNUP=open: anyone signing in creates their own family. Default closed: only the very first user does,
# everybody else is added by an admin (by email) and then signs in.
SIGNUP_OPEN = os.environ.get('WEHUB_SIGNUP', 'closed') == 'open'
PASSWORD_LOGIN = os.environ.get('WEHUB_PASSWORD_LOGIN', '1') not in ('0', 'off', 'false', 'no')
BASE_URL = os.environ.get('WEHUB_URL', '').rstrip('/')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PASSWORD_MIN = 8
NO_PASSWORD = '!'
_DUMMY_HASH = generate_password_hash('dummy-password-for-constant-timing')

PUBLIC = {'/api/me', '/api/login', '/api/signup', '/api/verify-email'}
# /api/service/: called by the apps with their key (see service.py)
PUBLIC_PREFIXES = ('/api/oidc/', '/api/service/')

_attempts = defaultdict(deque)
_lock = threading.Lock()


def rate_limit(key, limit, window_s):
    now = time.monotonic()
    with _lock:
        q = _attempts[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            abort(429, 'Too many attempts, try again in a few minutes')
        q.append(now)


def client_ip():
    return request.remote_addr or '?'


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def create_token(conn, kind, hours, user_id=None, family_id=None):
    token = secrets.token_urlsafe(32)
    expires = (_utc_now() + datetime.timedelta(hours=hours)).isoformat(timespec='seconds')
    conn.execute('INSERT INTO tokens (hash, kind, user_id, family_id, expires_at) VALUES (?,?,?,?,?)',
                 (_hash(token), kind, user_id, family_id, expires))
    return token, expires


def read_token(conn, token, kind):
    if not token or len(token) > 100:
        return None
    r = conn.execute('SELECT * FROM tokens WHERE hash = ? AND kind = ?', (_hash(token), kind)).fetchone()
    if not r or r['used_at'] or r['expires_at'] < _utc_now().isoformat(timespec='seconds'):
        return None
    return r


def use_token(conn, token):
    conn.execute("UPDATE tokens SET used_at = datetime('now') WHERE hash = ?", (_hash(token),))


def app_link(path):
    return f"{BASE_URL or request.host_url.rstrip('/')}/#/{path}"


def start_session(user, family_id=None):
    session.clear()
    session.permanent = True
    session['uid'] = user['id']
    session['ver'] = user['session_version']
    if family_id:
        session['family_id'] = family_id


def load_user():
    uid = session.get('uid')
    if not uid:
        return False
    with db.transaction() as conn:
        u = conn.execute('SELECT id, email, name, email_verified, session_version, language FROM users WHERE id = ?',
                         (uid,)).fetchone()
        if not u or u['session_version'] != session.get('ver'):
            session.clear()
            return False
        families = conn.execute('''SELECT f.id, f.name, m.role FROM members m JOIN families f ON f.id = m.family_id
                                   WHERE m.user_id = ? ORDER BY m.created_at''', (uid,)).fetchall()
    g.user = dict(u)
    g.families = [dict(f) for f in families]
    current = next((f for f in g.families if f['id'] == session.get('family_id')), g.families[0] if g.families else None)
    g.family_id = current['id'] if current else None
    g.role = current['role'] if current else None
    session['family_id'] = g.family_id
    return True


def require_login():
    path = request.path
    if not path.startswith('/api/') or path in PUBLIC or path.startswith(PUBLIC_PREFIXES):
        if path.startswith('/api/') and not path.startswith('/api/service/'):
            load_user()
        return None
    if not load_user():
        return jsonify(error=i18n.tr('Sign-in required')), 401
    if g.family_id is None and not path.startswith(('/api/account', '/api/logout')):
        return jsonify(error=i18n.tr('No family associated')), 403
    return None


def require_admin():
    if g.role != 'admin':
        abort(403, 'Only the family admin can do this')


def valid_email(value):
    e = text(value, 254).lower()
    if not EMAIL_RE.match(e):
        abort(400, 'Invalid email')
    return e


def _password(value):
    p = str(value or '')
    if len(p) < PASSWORD_MIN:
        abort(400, f'Password must be at least {PASSWORD_MIN} characters')
    if len(p) > 200:
        abort(400, 'Password too long')
    return p


def _no_users():
    with db.transaction() as conn:
        return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


@bp.get('/me')
def me():
    import oidc
    base = {'signup_open': SIGNUP_OPEN or _no_users(), 'oidc': oidc.public_providers(), 'password_login': PASSWORD_LOGIN}
    if not getattr(g, 'user', None):
        return jsonify(authenticated=False, **base)
    with db.transaction() as conn:
        password_hash = conn.execute('SELECT password_hash FROM users WHERE id = ?', (g.user['id'],)).fetchone()[0]
        identities = [r[0] for r in conn.execute('SELECT provider FROM identities WHERE user_id = ?', (g.user['id'],))]
        mine = {r[0]: r[1] for r in conn.execute('SELECT app, level FROM access WHERE family_id = ? AND user_id = ?',
                                                 (g.family_id, g.user['id']))}
        from api_shortcuts import visible
        shortcuts = visible(conn, g.family_id, g.user['id']) if g.family_id else []
    family = next((f for f in g.families if f['id'] == g.family_id), None)
    user = {k: g.user[k] for k in ('id', 'email', 'name', 'email_verified', 'language')}
    user.update(has_password=password_hash != NO_PASSWORD, identities=identities)
    my_apps = [{**a, 'level': mine[a['id']]} for a in apps.public() if a['id'] in mine]
    return jsonify(authenticated=True, user=user, family=family, families=g.families, role=g.role, apps=my_apps,
                   all_apps=apps.public(), shortcuts=shortcuts, **base)


@bp.post('/signup')
def signup():
    if not PASSWORD_LOGIN:
        abort(403, 'Sign-up with a password is disabled: use one of the providers')
    rate_limit(f'signup:{client_ip()}', 10, 3600)
    d = body()
    name = text(d.get('name'), 80)
    if not name:
        abort(400, 'Name is required')
    email, password = valid_email(d.get('email')), _password(d.get('password'))
    if not d.get('consent'):
        abort(400, 'To sign up you must accept the privacy notice')
    with db.transaction() as conn:
        user, family_id = create_user(conn, name, email, generate_password_hash(password), False, d.get('language'))
    start_session(user, family_id)
    return jsonify(ok=True), 201


def create_user(conn, name, email, password_hash, email_verified, language=None):
    """A new account with its own family (admin, access to every app). Only when sign-up is open or nobody exists yet."""
    if not SIGNUP_OPEN and conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0:
        abort(403, 'Ask the family admin to add you in weHub')
    if conn.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone():
        abort(409, 'An account with this email already exists')
    lang = i18n.normalize(language) or i18n.language()
    uid = conn.execute("INSERT INTO users (email, name, password_hash, email_verified, language, consent_at) "
                       "VALUES (?,?,?,?,?,datetime('now'))",
                       (email, name, password_hash, 1 if email_verified else 0, lang)).lastrowid
    family_id = db.create_family(conn, i18n.tr("{name}'s family", lang, name=name))
    db.add_member(conn, family_id, uid, name, 'admin')
    if not email_verified:
        _send_verification(conn, uid, email)
    return conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone(), family_id


def _send_verification(conn, user_id, email):
    token, _ = create_token(conn, 'verify', 72, user_id=user_id)
    lang = conn.execute('SELECT language FROM users WHERE id = ?', (user_id,)).fetchone()['language']
    mail.send(email, *i18n.email('verify', lang, link=app_link('verify/' + token)))


@bp.post('/login')
def login():
    if not PASSWORD_LOGIN:
        abort(403, 'Sign-in with a password is disabled: use one of the providers')
    d = body()
    email = text(d.get('email'), 254).lower()
    rate_limit(f'login-ip:{client_ip()}', 30, 900)
    rate_limit(f'login-email:{email}', 10, 900)
    with db.transaction() as conn:
        u = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if not check_password_hash(u['password_hash'] if u else _DUMMY_HASH, str(d.get('password') or '')) or not u:
        abort(401, 'Wrong email or password')
    start_session(u)
    return jsonify(ok=True)


@bp.post('/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.post('/verify-email')
def verify_email():
    token = body().get('token')
    with db.transaction() as conn:
        t = read_token(conn, token, 'verify')
        if not t:
            abort(400, 'Invalid or expired link')
        conn.execute('UPDATE users SET email_verified = 1 WHERE id = ?', (t['user_id'],))
        use_token(conn, token)
    return jsonify(ok=True)


@bp.put('/account')
def update_account():
    d = body()
    name = text(d.get('name', g.user['name']), 80)
    if not name:
        abort(400, 'Name is required')
    lang = i18n.normalize(d.get('language')) or g.user['language']
    with db.transaction() as conn:
        conn.execute('UPDATE users SET name = ?, language = ? WHERE id = ?', (name, lang, g.user['id']))
        conn.execute('UPDATE people SET name = ? WHERE user_id = ?', (name, g.user['id']))
        for (fid,) in conn.execute('SELECT family_id FROM members WHERE user_id = ?', (g.user['id'],)).fetchall():
            db.bump(conn, fid)
    return jsonify(ok=True)


@bp.post('/account/sessions/revoke')
def revoke_sessions():
    with db.transaction() as conn:
        conn.execute('UPDATE users SET session_version = session_version + 1 WHERE id = ?', (g.user['id'],))
        user = conn.execute('SELECT * FROM users WHERE id = ?', (g.user['id'],)).fetchone()
    start_session(user, g.family_id)
    return jsonify(ok=True)
