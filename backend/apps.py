"""The apps connected to weHub, from the environment:

  WEHUB_APPS=dotrack,eatrack,patrack
  WEHUB_APP_DOTRACK_URL=https://dotrack.example.com      address people open (links on the home page)
  WEHUB_APP_DOTRACK_INTERNAL_URL=http://dotrack:3001      optional: how weHub reaches it (import), default the URL
  WEHUB_APP_DOTRACK_KEY=…                                 shared secret, the same as DOTRACK_HUB_KEY in that app
  WEHUB_APP_DOTRACK_NAME / _DESCRIPTION                   optional: shown on the home page

`python manage.py new-key` makes a key. The key lets the app ask weHub who a person is and what their family looks
like; weHub uses it to read the app's family data during the import."""
import hmac
import os

DEFAULTS = {
    'dotrack': ('doTrack', 'Cose da fare, scadenze, appuntamenti, spesa', 'To-dos, deadlines, appointments, shopping'),
    'eatrack': ('eaTrack', 'Svezzamento: pasti, dispensa, menu', 'Weaning: meals, pantry, menu'),
    'patrack': ('paTrack', 'Archivio dei documenti di famiglia', 'Family document archive'),
}


def _env(app_id, key, default=''):
    return os.environ.get(f'WEHUB_APP_{app_id.upper()}_{key}', default).strip()


def ids():
    return [a.strip().lower() for a in os.environ.get('WEHUB_APPS', '').split(',') if a.strip()]


def get(app_id):
    if app_id not in ids():
        return None
    name, desc_it, desc_en = DEFAULTS.get(app_id, (app_id, '', ''))
    url = _env(app_id, 'URL').rstrip('/')
    return {
        'id': app_id, 'name': _env(app_id, 'NAME', name), 'url': url,
        'internal_url': (_env(app_id, 'INTERNAL_URL') or url).rstrip('/'),
        'description': {'it': _env(app_id, 'DESCRIPTION', desc_it), 'en': _env(app_id, 'DESCRIPTION', desc_en)},
        'key': _env(app_id, 'KEY'),
    }


def public():
    """Apps as the interface sees them (no keys)."""
    out = []
    for i in ids():
        a = get(i)
        out.append({k: a[k] for k in ('id', 'name', 'url', 'description')})
    return out


def by_key(presented):
    """The app whose key was presented (constant-time comparison), or None."""
    if not presented:
        return None
    for i in ids():
        key = _env(i, 'KEY')
        if key and len(key) >= 24 and hmac.compare_digest(key, presented):
            return get(i)
    return None
