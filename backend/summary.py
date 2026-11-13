"""weHub's home: a short summary from each app the person may use in the family (what is coming up in doTrack,
today's meals in eaTrack, documents to fix or expiring in paTrack). weHub asks the apps in parallel, with its keys
(GET /api/hub/families/<id>/summary, see each app's hub_hooks / links); an app that does not answer in a few seconds
is simply left out."""
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Blueprint, g, jsonify

import apps
import db

bp = Blueprint('summary', __name__)
TIMEOUT = 4


def _ask(app, family_id, user_id, level):
    try:
        r = requests.get(f"{app['internal_url']}/api/hub/families/{family_id}/summary", timeout=TIMEOUT, allow_redirects=False,
                         params={'user': user_id, 'level': level, 'from': 'wehub'},
                         headers={'Authorization': f"Bearer {app['key']}", 'User-Agent': 'weHub'})
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


@bp.get('/home/summary')
def summary():
    """{apps: {app id: summary | null (did not answer)}} for the apps the person may use in the current family."""
    with db.transaction() as conn:
        levels = {r['app']: r['level'] for r in conn.execute(
            'SELECT app, level FROM access WHERE family_id = ? AND user_id = ?', (g.family_id, g.user['id']))}
    targets = [a for a in (apps.get(i) for i in apps.ids() if i in levels) if a and a['key'] and a['internal_url']]
    if not targets:
        return jsonify(apps={})
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {a['id']: pool.submit(_ask, a, g.family_id, g.user['id'], levels[a['id']]) for a in targets}
    return jsonify(apps={k: f.result() for k, f in futures.items()})
