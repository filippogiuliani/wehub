"""weHub – Flask server: JSON API under /api (the interface and /api/service for the apps) and the built frontend."""
import datetime
import os
import secrets
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, send_from_directory

import auth
from famkit import backup
import db
import i18n
import oidc
import service
from api_family import bp as family_bp
from api_import import bp as import_bp
from api_shortcuts import bp as shortcuts_bp
from service import bp as service_bp
from summary import bp as summary_bp

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def _secret_key():
    if os.environ.get('WEHUB_SECRET_KEY'):
        return os.environ['WEHUB_SECRET_KEY']
    path = os.path.join(db.DATA_DIR, '.secret_key')
    if not os.path.exists(path):
        os.makedirs(db.DATA_DIR, exist_ok=True)
        with open(path, 'w') as f:
            f.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip()


def create_app():
    db.init_db()
    app = Flask(__name__, static_folder=None)
    app.secret_key = _secret_key()
    app.config.update(
        SESSION_COOKIE_NAME='wehub_session', SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('WEHUB_COOKIE_SECURE') == '1',
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=60), MAX_CONTENT_LENGTH=service.MAX_RELAYED, JSON_AS_ASCII=False,
    )
    if os.environ.get('WEHUB_PROXY') == '1':
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    oidc.configure(app)
    for bp in (auth.bp, oidc.bp, family_bp, import_bp, service_bp, shortcuts_bp, summary_bp):
        app.register_blueprint(bp, url_prefix='/api')

    @app.before_request
    def size_limit():
        # 1 MB is plenty for weHub itself; only documents passed from one app to another are bigger
        if (request.content_length or 0) > 1024 * 1024 and not request.path.startswith('/api/service/apps/'):
            abort(413)

    @app.before_request
    def protect():
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.path.startswith('/api/') \
                and not request.path.startswith('/api/service/'):
            origin = request.headers.get('Origin') or request.headers.get('Referer')
            if origin and urlparse(origin).netloc != request.host:
                return jsonify(error=i18n.tr('Origin not allowed')), 403
        return auth.require_login()

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('Content-Security-Policy', CSP)
        if request.path.startswith('/api/'):
            resp.headers.setdefault('Cache-Control', 'no-store')
        return resp

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    @app.errorhandler(500)
    def json_error(e):
        if request.path.startswith('/api/'):
            return jsonify(error=i18n.tr(getattr(e, 'description', None) or 'Server error')), getattr(e, 'code', 500) or 500
        return e

    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path='index.html'):
        if path.startswith('api/'):
            abort(404)
        if not os.path.isdir(STATIC_DIR):
            return 'Frontend not built: run "npm run build" in frontend/', 503
        if os.path.isfile(os.path.join(STATIC_DIR, path)):
            resp = send_from_directory(STATIC_DIR, path)
            if path.startswith('assets/'):
                resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            return resp
        resp = send_from_directory(STATIC_DIR, 'index.html')
        resp.headers['Cache-Control'] = 'no-cache'
        return resp

    return app


if __name__ == '__main__':
    from waitress import serve
    import apps
    app = create_app()
    backup.start_scheduler()
    port = int(os.environ.get('PORT', '3004'))
    for a in apps.ids():
        cfg = apps.get(a)
        if len(cfg['key']) < 24:
            print(f'[weHub] WARNING: app "{a}" has no key (WEHUB_APP_{a.upper()}_KEY, at least 24 characters)', flush=True)
    print(f'[weHub] listening on http://0.0.0.0:{port} – apps: {", ".join(apps.ids()) or "none"}', flush=True)
    proxy = {'trusted_proxy': '*', 'trusted_proxy_headers': {'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host'}} \
        if os.environ.get('WEHUB_PROXY') == '1' else {}
    serve(app, host='0.0.0.0', port=port, threads=8, **proxy)
