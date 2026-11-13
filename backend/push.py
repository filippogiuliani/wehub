"""Telling the apps at once that a family changed (members, roles, people, who may use which app).

db.bump() calls changed(family_id). About a second later (the change is committed by then, and several changes in a
row become one message) every connected app gets POST /api/hub/changed {family: id} with its key, and refreshes that
family right away instead of at its next periodic refresh (which stays, in case a message is lost)."""
import threading
import time

import requests

import apps

DELAY = 1.0
ENABLED = True   # tests turn it off and call flush() themselves
_pending = set()
_lock = threading.Lock()
_wake = threading.Event()
_worker = None


def changed(family_id):
    global _worker
    if not ENABLED or not family_id:
        return
    with _lock:
        _pending.add(family_id)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, daemon=True, name='push-apps')
            _worker.start()
    _wake.set()


def _loop():
    while True:
        _wake.wait()
        time.sleep(DELAY)
        _wake.clear()
        try:
            flush()
        except Exception as e:  # must never stop the worker
            print(f'[push] {e}', flush=True)


def flush():
    """Send the pending messages now. Returns {app id: [family ids told]}."""
    with _lock:
        families = sorted(_pending)
        _pending.clear()
    told = {}
    for app_id in apps.ids():
        app = apps.get(app_id)
        if not app or not app['key'] or not app['internal_url']:
            continue
        for fid in families:
            try:
                r = requests.post(f"{app['internal_url']}/api/hub/changed", json={'family': fid}, timeout=5,
                                  allow_redirects=False, headers={'Authorization': f"Bearer {app['key']}", 'User-Agent': 'weHub'})
                if r.status_code == 200:
                    told.setdefault(app_id, []).append(fid)
                elif r.status_code != 404:   # 404: an app image without /changed yet, it refreshes on its own
                    print(f'[push] {app_id}: family {fid}: answered {r.status_code}', flush=True)
            except requests.RequestException as e:
                print(f'[push] {app_id} not reachable: {type(e).__name__}', flush=True)
    return told
