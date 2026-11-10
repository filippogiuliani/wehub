"""A tiny OpenID Connect provider FOR DEVELOPMENT ONLY: it stands in for Pocket ID when trying weHub and the apps
on a development machine. There are no passwords: the sign-in page lists the people in dev/users.json (or the file in
FAKE_OIDC_USERS) and you click one. Never expose it to the internet.

  python dev/fake_oidc.py            # http://127.0.0.1:3009 only (FAKE_OIDC_HOST to change), issuer from FAKE_OIDC_ISSUER

Configure weHub and each app with provider "pocketid", issuer = this address, any client id / secret."""
import json
import os
import secrets
import time
from html import escape
from urllib.parse import urlencode

from authlib.jose import JsonWebKey, jwt
from flask import Flask, abort, jsonify, redirect, request

ISSUER = os.environ.get('FAKE_OIDC_ISSUER', 'http://localhost:3009').rstrip('/')
HERE = os.path.dirname(os.path.abspath(__file__))
USERS = json.load(open(os.environ.get('FAKE_OIDC_USERS') or os.path.join(HERE, 'users.json')))
KEY = JsonWebKey.generate_key('RSA', 2048, is_private=True, options={'kid': 'dev'})
CODES = {}  # code → {user, nonce, client_id, redirect_uri}
TOKENS = {}  # access token → user

app = Flask(__name__)


@app.get('/.well-known/openid-configuration')
def discovery():
    return jsonify(issuer=ISSUER, authorization_endpoint=ISSUER + '/authorize', token_endpoint=ISSUER + '/token',
                   userinfo_endpoint=ISSUER + '/userinfo', jwks_uri=ISSUER + '/jwks',
                   response_types_supported=['code'], subject_types_supported=['public'],
                   id_token_signing_alg_values_supported=['RS256'], scopes_supported=['openid', 'email', 'profile'],
                   token_endpoint_auth_methods_supported=['client_secret_basic', 'client_secret_post'],
                   code_challenge_methods_supported=['S256'])


@app.get('/jwks')
def jwks():
    return jsonify(keys=[KEY.as_dict(is_private=False)])


@app.get('/authorize')
def authorize():
    a = request.args
    if not a.get('redirect_uri') or a.get('response_type') != 'code':
        abort(400)
    pick = a.get('pick')
    if pick is None:
        links = ''.join(
            f'<li><a href="/authorize?{urlencode({**a, "pick": i})}"><b>{escape(u["name"])}</b><br><small>{escape(u["email"])}</small></a></li>'
            for i, u in enumerate(USERS))
        client = escape(a.get('client_id', ''))
        return f'''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pocket ID (dev)</title>
<style>body{{font-family:system-ui;background:#f7f8fa;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;width:min(360px,90vw)}}
ul{{list-style:none;padding:0;margin:16px 0 0;display:flex;flex-direction:column;gap:8px}}
a{{display:block;padding:12px 14px;border:1px solid #d1d5db;border-radius:8px;text-decoration:none;color:#111827}}
a:hover{{background:#e8eef5;border-color:#1e3a5f}} p{{color:#6b7280;font-size:.9rem;margin:4px 0 0}}</style>
<main><h2 style="margin:0">Pocket ID – sviluppo</h2><p>Accesso a <b>{client}</b>. Scegli chi sei (solo per prove: nessuna password).</p><ul>{links}</ul></main>'''
    try:
        user = USERS[int(pick)]
    except (ValueError, IndexError):
        abort(400)
    code = secrets.token_urlsafe(24)
    CODES[code] = {'user': user, 'nonce': a.get('nonce'), 'client_id': a.get('client_id'), 'redirect_uri': a['redirect_uri']}
    sep = '&' if '?' in a['redirect_uri'] else '?'
    return redirect(a['redirect_uri'] + sep + urlencode({'code': code, 'state': a.get('state', '')}))


@app.post('/token')
def token():
    code = CODES.pop(request.form.get('code', ''), None)
    if not code:
        return jsonify(error='invalid_grant'), 400
    client_id = request.authorization.username if request.authorization else request.form.get('client_id')
    u, now = code['user'], int(time.time())
    claims = {'iss': ISSUER, 'sub': u['sub'], 'aud': client_id, 'iat': now, 'exp': now + 600, 'email': u['email'],
              'email_verified': True, 'name': u['name']}
    if code['nonce']:
        claims['nonce'] = code['nonce']
    id_token = jwt.encode({'alg': 'RS256', 'kid': 'dev'}, claims, KEY).decode()
    access = secrets.token_urlsafe(24)
    TOKENS[access] = u
    return jsonify(access_token=access, token_type='Bearer', expires_in=600, id_token=id_token)


@app.get('/userinfo')
def userinfo():
    u = TOKENS.get(request.headers.get('Authorization', '')[7:])
    if not u:
        abort(401)
    return jsonify(sub=u['sub'], email=u['email'], email_verified=True, name=u['name'])


if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('PORT', '3009'))
    host = os.environ.get('FAKE_OIDC_HOST', '127.0.0.1')
    print(f'[fake-oidc] DEVELOPMENT provider on {host}:{port}, issuer {ISSUER}, {len(USERS)} people', flush=True)
    serve(app, host=host, port=port)
