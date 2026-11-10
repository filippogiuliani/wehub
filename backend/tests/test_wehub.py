"""weHub: the family, members by email, access per app, the service API the apps use, the import."""
import pytest

import api_import
import auth
from conftest import KEYS, ok, service, sign_up


def me(c):
    return ok(c.get('/api/me'))


def test_first_user_creates_the_family_then_sign_up_closes(client):
    c = client()
    m = sign_up(c)
    assert m['role'] == 'admin' and [a['id'] for a in m['apps']] == ['dotrack', 'eatrack', 'patrack']
    assert ok(c.get('/api/family'))['people'][0]['name'] == 'Fil'
    r = client().post('/api/signup', json={'name': 'X', 'email': 'x@example.com', 'password': 'secret123', 'consent': True})
    assert r.status_code == 403 and 'weHub' in r.get_json()['error']
    assert ok(client().get('/api/me'))['signup_open'] is False


def test_members_people_and_access(admin, client):
    f = ok(admin.post('/api/family/members', json={'name': 'Sara', 'email': 'Sara@Example.com', 'apps': ['dotrack', 'patrack']}), 201)
    sara = next(m for m in f['members'] if m['email'] == 'sara@example.com')
    assert sara['access'] == {'dotrack': 'full', 'patrack': 'full'} and not sara['signed_in']
    assert admin.post('/api/family/members', json={'name': 'Sara', 'email': 'sara@example.com'}).status_code == 409
    f = ok(admin.put(f"/api/family/members/{sara['id']}", json={'apps': {'patrack': 'limited', 'eatrack': 'full'}, 'name': 'Sara R.'}))
    sara = next(m for m in f['members'] if m['id'] == sara['id'])
    assert sara['access'] == {'patrack': 'limited', 'eatrack': 'full'} and sara['name'] == 'Sara R.'
    f = ok(admin.post('/api/family/people', json={'name': 'Luca', 'birth_date': '2025-01-10', 'kind': 'child'}), 201)
    assert any(p['name'] == 'Luca' and p['kind'] == 'child' for p in f['people'])
    assert admin.post('/api/family/people', json={'name': 'luca'}).status_code == 409
    # The only admin cannot step down or leave
    uid = me(admin)['user']['id']
    assert admin.put(f'/api/family/members/{uid}', json={'role': 'member'}).status_code == 400
    # Removing a member keeps their person
    f = ok(admin.delete(f"/api/family/members/{sara['id']}"))
    assert any(p['name'] == 'Sara R.' and p['user_id'] is None for p in f['people'])
    assert all(m['email'] != 'sara@example.com' for m in f['members'])


def test_member_signs_in_with_the_provider(admin, client, monkeypatch):
    import oidc
    ok(admin.post('/api/family/members', json={'name': 'Sara', 'email': 'sara@example.com'}), 201)

    class Fake:
        user = None
        def authorize_redirect(self, url):
            from flask import redirect
            return redirect('https://id.example/auth')
        def authorize_access_token(self):
            return {'userinfo': self.user}
    fake = Fake()
    monkeypatch.setattr(oidc, 'PROVIDERS', {'pocketid': 'Pocket ID'})
    monkeypatch.setattr(oidc, '_client', lambda pid: fake)
    s = client()
    s.get('/api/oidc/pocketid/login')
    fake.user = {'sub': 'sara-sub', 'email': 'sara@example.com', 'email_verified': True, 'iss': 'https://id.example'}
    r = s.get('/api/oidc/pocketid/callback?code=x&state=y')
    assert r.status_code == 302 and r.headers['Location'].endswith('#/')
    m = me(s)
    assert m['user']['name'] == 'Sara' and m['family']['name'] == me(admin)['family']['name'] and m['role'] == 'member'
    # A stranger cannot get in (sign-up closed)
    s2 = client()
    s2.get('/api/oidc/pocketid/login')
    fake.user = {'sub': 'x', 'email': 'stranger@example.com', 'email_verified': True, 'iss': 'https://id.example'}
    assert 'signup' in s2.get('/api/oidc/pocketid/callback').headers['Location']
    assert s2.post('/api/oidc/complete', json={'consent': True}).status_code == 403


def test_service_needs_a_key(client, admin):
    assert client().post('/api/service/whoami', json={'subject': 'x'}).status_code == 401
    assert client().post('/api/service/whoami', json={'subject': 'x'}, headers={'Authorization': 'Bearer nope'}).status_code == 401


def test_whoami_and_snapshots(admin, client):
    ok(admin.post('/api/family/members', json={'name': 'Sara', 'email': 'sara@example.com', 'apps': ['patrack']}), 201)
    ok(admin.post('/api/family/people', json={'name': 'Luca', 'kind': 'child', 'birth_date': '2025-01-10'}), 201)
    c = client()
    # Unknown person
    assert ok(service(c, 'dotrack', 'POST', '/whoami', json={'issuer': 'https://id', 'subject': 's1', 'email': 'nobody@x.it',
                                                              'email_verified': True})) == {'known': False}
    # First time: matched by verified email, then by issuer + subject
    w = ok(service(c, 'dotrack', 'POST', '/whoami', json={'issuer': 'https://id', 'subject': 'fil-sub', 'email': 'fil@example.com',
                                                           'email_verified': True}))
    assert w['known'] and w['user']['name'] == 'Fil' and len(w['families']) == 1
    snap = w['families'][0]
    assert [m['email'] for m in snap['members']] == ['fil@example.com']   # Sara has no doTrack access
    assert {p['name']: p['kind'] for p in snap['people']} == {'Fil': 'adult', 'Sara': 'adult', 'Luca': 'child'}
    w2 = ok(service(c, 'dotrack', 'POST', '/whoami', json={'issuer': 'https://id', 'subject': 'fil-sub', 'email': 'other@x.it'}))
    assert w2['user']['hub_id'] == w['user']['hub_id']
    # An unverified email is not enough
    assert ok(service(c, 'dotrack', 'POST', '/whoami', json={'issuer': 'https://id', 'subject': 'other', 'email': 'sara@example.com',
                                                              'email_verified': False}))['known'] is False
    # Sara may use paTrack only
    w = ok(service(c, 'dotrack', 'POST', '/whoami', json={'issuer': 'https://id', 'subject': 'sara', 'email': 'sara@example.com',
                                                           'email_verified': True}))
    assert w['known'] and w['families'] == []
    w = ok(service(c, 'patrack', 'POST', '/whoami', json={'issuer': 'https://id', 'subject': 'sara'}))
    assert len(w['families'][0]['members']) == 2
    # Version check: unchanged until something changes
    fid, v = snap['hub_id'], snap['version']
    assert ok(service(c, 'dotrack', 'GET', f'/families/{fid}?version={v}'))['unchanged']
    ok(admin.put('/api/family', json={'name': 'Casa Rossi'}))
    assert ok(service(c, 'dotrack', 'GET', f'/families/{fid}?version={v}'))['name'] == 'Casa Rossi'
    assert service(c, 'dotrack', 'GET', '/families/999').status_code == 404
    assert set(ok(admin.get('/api/family'))['seen']) == {'dotrack', 'patrack'}


EXPORTS = {
    'dotrack': [{'local_id': 4, 'name': 'Famiglia di Fil', 'members': [{'email': 'fil@example.com', 'name': 'Fil', 'role': 'admin'},
                                                                     {'email': 'sara@example.com', 'name': 'Sara', 'role': 'member'}],
                 'people': [{'local_id': 7, 'name': 'Luca', 'kind': 'adult'}, {'local_id': 8, 'name': 'Nonna Anna', 'kind': 'adult'}]},
                {'local_id': 9, 'name': 'Altra', 'members': [{'email': 'x@x.it', 'name': 'X', 'role': 'admin'}], 'people': []}],
    'eatrack': [{'local_id': 1, 'name': 'Famiglia', 'members': [{'email': 'fil@example.com', 'name': 'Fil', 'role': 'admin'}],
                 'people': [{'local_id': 3, 'name': 'luca', 'kind': 'child', 'birth_date': '2025-01-10'}]}],
}


def test_import(admin, monkeypatch):
    def fake(app):
        if app['id'] == 'patrack':
            raise RuntimeError('not reachable (ConnectionError)')
        return EXPORTS[app['id']]
    monkeypatch.setattr(api_import, 'fetch_export', fake)
    p = ok(admin.get('/api/import/preview'))
    by = {a['id']: a for a in p['apps']}
    assert by['dotrack']['selected'] == 4 and by['eatrack']['selected'] == 1 and not by['patrack']['ok']
    assert [m['email'] for m in p['members'] if not m['exists']] == ['sara@example.com']
    groups = {g['key']: g for g in p['groups']}
    assert set(groups) == {'luca', 'nonna anna'}
    luca = groups['luca']
    assert luca['kind'] == 'child' and luca['birth_date'] == '2025-01-10' and len(luca['sources']) == 2
    r = ok(admin.post('/api/import/apply', json={'selected': {'dotrack': 4, 'eatrack': 1},
                                                 'members': [m for m in p['members'] if not m['exists']],
                                                 'groups': p['groups']}))
    assert r == {'families': 2, 'members': 1, 'people': 2, 'linked': 3, 'merges': {}}
    f = ok(admin.get('/api/family'))
    assert {pp['name'] for pp in f['people']} == {'Fil', 'Sara', 'Luca', 'Nonna Anna'}
    # The apps now get their own ids back
    from flask import Flask  # noqa
    import app as appmod  # noqa
    w = ok(service(admin, 'eatrack', 'POST', '/whoami', json={'issuer': 'i', 'subject': 's', 'email': 'fil@example.com',
                                                              'email_verified': True}))
    snap = w['families'][0]
    assert snap['local_id'] == 1 and next(x for x in snap['people'] if x['name'] == 'Luca')['local_id'] == 3
    # Importing again: everything already there, nothing duplicated
    p = ok(admin.get('/api/import/preview'))
    assert all(m['exists'] for m in p['members']) and all(g['target'] for g in p['groups'])
    r = ok(admin.post('/api/import/apply', json={'selected': {'dotrack': 4}, 'members': [], 'groups': p['groups']}))
    assert r['people'] == 0
    assert len(ok(admin.get('/api/family'))['people']) == 4


def test_import_is_admin_only(admin, client):
    ok(admin.post('/api/family/members', json={'name': 'Sara', 'email': 'sara@example.com'}), 201)
    # Sara signs in with a password set by nobody: simulate by giving her a session
    import db
    with db.transaction() as conn:
        uid = conn.execute("SELECT id FROM users WHERE email = 'sara@example.com'").fetchone()[0]
    s = client()
    with s.session_transaction() as sess:
        sess['uid'], sess['ver'] = uid, 1
    assert s.get('/api/import/preview').status_code == 403
    assert s.post('/api/family/members', json={'name': 'X', 'email': 'x@x.it'}).status_code == 403
    assert ok(s.get('/api/family'))['role'] == 'member'


def _session_for(client, email):
    import db
    with db.transaction() as conn:
        uid = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()[0]
    s = client()
    with s.session_transaction() as sess:
        sess['uid'], sess['ver'] = uid, 1
    return s, uid


def test_shortcuts_per_person(admin, client):
    f = ok(admin.post('/api/family/members', json={'name': 'Tata', 'email': 'tata@example.com', 'apps': ['patrack']}), 201)
    tata = next(m['id'] for m in f['members'] if m['email'] == 'tata@example.com')
    me_id = me(admin)['user']['id']
    ok(admin.post('/api/family/shortcuts', json={'name': 'Vaultwarden', 'url': 'vault.example.com', 'icon': 'lock',
                                                 'everyone': False, 'members': [me_id]}), 201)
    links = ok(admin.post('/api/family/shortcuts', json={'name': 'Meteo', 'url': 'https://meteo.example.com', 'description': 'Previsioni'}), 201)
    assert [l['url'] for l in links] == ['https://vault.example.com', 'https://meteo.example.com']
    # Validation
    for bad in ('javascript:alert(1)', 'data:text/html,x', 'ftp://x.it', 'https://'):
        assert admin.post('/api/family/shortcuts', json={'name': 'X', 'url': bad}).status_code == 400, bad
    nas = ok(admin.post('/api/family/shortcuts', json={'name': 'NAS', 'url': 'nas.local:5001'}), 201)
    assert nas[-1]['url'] == 'https://nas.local:5001'
    ok(admin.delete(f"/api/family/shortcuts/{nas[-1]['id']}"))
    assert admin.post('/api/family/shortcuts', json={'name': 'X', 'url': 'https://x.it', 'everyone': False, 'members': []}).status_code == 400
    assert admin.post('/api/family/shortcuts', json={'name': '', 'url': 'https://x.it'}).status_code == 400
    # Each one sees their own
    assert [l['name'] for l in me(admin)['shortcuts']] == ['Vaultwarden', 'Meteo']
    s, _ = _session_for(client, 'tata@example.com')
    assert [l['name'] for l in ok(s.get('/api/shortcuts'))] == ['Meteo']
    assert s.get('/api/family/shortcuts').status_code == 403
    assert s.post('/api/family/shortcuts', json={'name': 'X', 'url': 'https://x.it'}).status_code == 403
    # Show Vaultwarden to the babysitter too, move it after Meteo
    vault = links[0]['id']
    ok(admin.put(f'/api/family/shortcuts/{vault}', json={'name': 'Vaultwarden', 'url': 'https://vault.example.com',
                                                        'everyone': False, 'members': [me_id, tata]}))
    links = ok(admin.post(f'/api/family/shortcuts/{vault}/move', json={'direction': 1}))
    assert [l['name'] for l in links] == ['Meteo', 'Vaultwarden'] and links[1]['members'] == sorted([me_id, tata])
    assert [l['name'] for l in ok(s.get('/api/shortcuts'))] == ['Meteo', 'Vaultwarden']
    # Removing the babysitter removes her from the links
    ok(admin.delete(f'/api/family/members/{tata}'))
    assert ok(admin.get('/api/family/shortcuts'))[1]['members'] == [me_id]
    ok(admin.delete(f'/api/family/shortcuts/{vault}'))
    assert [l['name'] for l in me(admin)['shortcuts']] == ['Meteo']


def test_import_merges_a_family_made_separately(admin, monkeypatch):
    """Sara had made her own doTrack family: it is proposed for merging, and merged on request."""
    exports = {
        'dotrack': [{'local_id': 4, 'name': 'Famiglia di Fil', 'members': [{'email': 'fil@example.com', 'name': 'Fil', 'role': 'admin'}],
                     'people': [{'local_id': 7, 'name': 'Luca', 'kind': 'adult'}]},
                    {'local_id': 10, 'name': 'Famiglia di Sara', 'members': [{'email': 'sara@example.com', 'name': 'Sara', 'role': 'admin'}],
                     'people': [{'local_id': 11, 'name': 'luca', 'kind': 'adult'}, {'local_id': 12, 'name': 'Nonna', 'kind': 'adult'}]},
                    {'local_id': 20, 'name': 'Estranei', 'members': [{'email': 'x@x.it', 'name': 'X', 'role': 'admin'}], 'people': []}],
        'eatrack': [], 'patrack': [],
    }
    monkeypatch.setattr(api_import, 'fetch_export', lambda app: exports[app['id']])
    ok(admin.post('/api/family/members', json={'name': 'Sara', 'email': 'sara@example.com'}), 201)
    p = ok(admin.get('/api/import/preview'))
    do = next(a for a in p['apps'] if a['id'] == 'dotrack')
    assert do['selected'] == 4 and do['merge_candidates'] == [10] and do['merge'] == []   # strangers are never proposed
    assert {g['key'] for g in p['groups']} == {'luca'}
    # Choosing to merge: Sara's people join the proposal
    p = ok(admin.get('/api/import/preview?merge_dotrack=10,20'))
    do = next(a for a in p['apps'] if a['id'] == 'dotrack')
    assert do['merge'] == [10]
    groups = {g['key']: g for g in p['groups']}
    assert set(groups) == {'luca', 'nonna'} and len(groups['luca']['sources']) == 2
    calls = []
    monkeypatch.setattr(api_import, 'merge_in_app', lambda app, into, fams: calls.append((app['id'], into, fams)) or {'items': 3, 'families': 1})
    r = ok(admin.post('/api/import/apply', json={'selected': {'dotrack': 4}, 'merge': {'dotrack': [10]}, 'members': [],
                                                 'groups': p['groups']}))
    assert calls == [('dotrack', 4, [10])] and r['merges'] == {'dotrack': {'items': 3, 'families': 1}}


def test_merge_in_app_reports_errors(monkeypatch):
    import requests

    class Resp:
        def __init__(self, code, data):
            self.status_code, self._data = code, data
        def json(self):
            return self._data
    app = {'internal_url': 'http://dotrack.test', 'key': KEYS['dotrack']}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Resp(200, {'report': {'items': 2}}))
    assert api_import.merge_in_app(app, 1, [2]) == {'items': 2}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Resp(409, {'error': 'family 2 still has rows'}))
    assert api_import.merge_in_app(app, 1, [2]) == {'error': 'family 2 still has rows'}
    def down(*a, **k):
        raise requests.ConnectionError('x')
    monkeypatch.setattr(requests, 'post', down)
    assert 'not reachable' in api_import.merge_in_app(app, 1, [2])['error']
