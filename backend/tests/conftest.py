"""Shared fixtures: a fresh database per test, three connected apps with keys, emails captured."""
import os
import sys
import tempfile

os.environ['WEHUB_DATA'] = tempfile.mkdtemp(prefix='wehub-test-')
for k in [k for k in os.environ if k.startswith('WEHUB_') and k != 'WEHUB_DATA']:
    del os.environ[k]
KEYS = {'dotrack': 'k-dotrack-' + 'x' * 30, 'eatrack': 'k-eatrack-' + 'y' * 30, 'patrack': 'k-patrack-' + 'z' * 30}
os.environ['WEHUB_APPS'] = 'dotrack,eatrack,patrack'
for app_id, key in KEYS.items():
    os.environ[f'WEHUB_APP_{app_id.upper()}_URL'] = f'http://{app_id}.test'
    os.environ[f'WEHUB_APP_{app_id.upper()}_KEY'] = key
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import auth  # noqa: E402
import backup  # noqa: E402
import db  # noqa: E402
import mail  # noqa: E402
import oidc  # noqa: E402
from app import create_app  # noqa: E402

PASSWORD = 'secret123'


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mail, 'send', lambda to, subject, body: sent.append((to, subject, body)))
    return sent


@pytest.fixture
def app(tmp_path, monkeypatch, outbox):
    monkeypatch.setattr(db, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'wehub.db'))
    monkeypatch.setattr(backup, 'BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setattr(oidc, 'PROVIDERS', {})
    auth._attempts.clear()
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client


def ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.get_data(as_text=True)[:500])
    return r.get_json()


def sign_up(c, email='fil@example.com', name='Fil'):
    ok(c.post('/api/signup', json={'name': name, 'email': email, 'password': PASSWORD, 'consent': True}), 201)
    return ok(c.get('/api/me'))


def service(c, app_id, method, path, **kw):
    return c.open('/api/service' + path, method=method, headers={'Authorization': 'Bearer ' + KEYS[app_id]}, **kw)


@pytest.fixture
def admin(client):
    c = client()
    sign_up(c)
    return c
