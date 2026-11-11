"""Icons of the home-page links, written as in Homepage (gethomepage.dev):

  lock, home, film…           one of weHub's own line icons (db.SHORTCUT_ICONS)
  jellyfin.png / jellyfin     dashboard-icons (github.com/homarr-labs/dashboard-icons), .png .svg or .webp
  sh-immich(.png)             selfh.st icons
  mdi-logout                  Material Design Icons (drawn in the text colour)
  si-gitea                    Simple Icons (drawn in the text colour)
  https://…/logo.png          any image

weHub downloads each icon once and keeps it in <data>/icons: browsers only ever load icons from weHub itself (no
third-party requests, the CSP stays 'self'). Only the admin can choose an address, and what comes back is kept only
if it is an image."""
import hashlib
import os
import re
import time

import requests

import db

NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,100}$')
EXTS = ('png', 'svg', 'webp')
DASHBOARD = 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/{ext}/{name}.{ext}'
SELFHST = 'https://cdn.jsdelivr.net/gh/selfhst/icons/{ext}/{name}.{ext}'
MDI = 'https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/{name}.svg'
SIMPLE = 'https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{name}.svg'
MAX_BYTES = 1024 * 1024
TIMEOUT = 8
RETRY_MISSING = 24 * 3600  # an icon that could not be downloaded is tried again after a day
TYPES = {'image/png': 'png', 'image/svg+xml': 'svg', 'image/webp': 'webp', 'image/jpeg': 'jpg', 'image/gif': 'gif',
         'image/x-icon': 'ico', 'image/vnd.microsoft.icon': 'ico'}
MIME = {v: k for k, v in TYPES.items()}


def _split(name):
    """'jellyfin.png' → ('jellyfin', 'png'); 'jellyfin' → ('jellyfin', 'png')."""
    base, _, ext = name.rpartition('.')
    if base and ext in EXTS:
        return base, ext
    return name, 'png'


def resolve(spec):
    """(kind, source): kind is 'builtin' (source = icon name), 'mono' (an SVG drawn in the text colour) or 'image';
    None when the text is not an icon weHub understands."""
    s = str(spec or '').strip()
    if not s:
        return None
    if s in db.SHORTCUT_ICONS:
        return 'builtin', s
    if re.match(r'^https?://\S+$', s, re.I):
        return 'image', s
    s = s.lower()
    if not NAME_RE.match(s):
        return None
    if s.startswith('mdi-') and len(s) > 4:
        return 'mono', MDI.format(name=_split(s[4:])[0])
    if s.startswith('si-') and len(s) > 3:
        return 'mono', SIMPLE.format(name=_split(s[3:])[0])
    if s.startswith('sh-') and len(s) > 3:
        name, ext = _split(s[3:])
        return 'image', SELFHST.format(name=name, ext=ext)
    name, ext = _split(s)
    return 'image', DASHBOARD.format(name=name, ext=ext)


def clean(spec):
    """The icon as stored: what the admin wrote when weHub understands it, otherwise the plain link icon."""
    s = str(spec or '').strip()[:500]
    if s.startswith(('http://', 'https://', 'HTTP://', 'HTTPS://')):
        return s
    s = s.lower() if s not in db.SHORTCUT_ICONS else s
    return s if resolve(s) else 'link'


def version(spec):
    return hashlib.sha256(str(spec).encode()).hexdigest()[:16]


def describe(spec, shortcut_id):
    """For the interface: {icon_kind, icon_url} (icon_url only for downloaded icons)."""
    r = resolve(spec) or ('builtin', 'link')
    if r[0] == 'builtin':
        return {'icon_kind': 'builtin', 'icon_url': None}
    return {'icon_kind': r[0], 'icon_url': f'/api/icons/{shortcut_id}?v={version(spec)}'}


def _dir():
    d = os.path.join(db.DATA_DIR, 'icons')
    os.makedirs(d, exist_ok=True)
    return d


def _download(url):
    """(bytes, ext) or None. Only images, at most MAX_BYTES."""
    try:
        with requests.get(url, timeout=TIMEOUT, stream=True, headers={'User-Agent': 'weHub'}) as r:
            if r.status_code != 200 or not r.url.lower().startswith(('http://', 'https://')):
                return None
            ctype = r.headers.get('Content-Type', '').split(';')[0].strip().lower()
            data = b''
            for chunk in r.iter_content(65536):
                data += chunk
                if len(data) > MAX_BYTES:
                    return None
    except requests.RequestException:
        return None
    ext = TYPES.get(ctype)
    head = data[:512].lstrip().lower()
    if ext is None and ctype in ('text/plain', 'application/octet-stream', 'text/xml', 'application/xml', ''):
        # Some servers (raw files) do not say what they send: recognise the image by its first bytes
        if head.startswith(b'\x89png'):
            ext = 'png'
        elif head.startswith((b'<svg', b'<?xml')) and b'<svg' in data[:2048].lower():
            ext = 'svg'
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            ext = 'webp'
    if ext is None or not data:
        return None
    return data, ext


def fetch(spec):
    """(path, mime type) of the icon on disk, downloaded the first time; None when it cannot be had."""
    r = resolve(spec)
    if not r or r[0] == 'builtin':
        return None
    key = hashlib.sha256(r[1].encode()).hexdigest()[:32]
    d = _dir()
    for ext in MIME:
        path = os.path.join(d, f'{key}.{ext}')
        if os.path.exists(path):
            return path, MIME[ext]
    missing = os.path.join(d, f'{key}.missing')
    if os.path.exists(missing) and time.time() - os.path.getmtime(missing) < RETRY_MISSING:
        return None
    got = _download(r[1])
    if not got:
        with open(missing, 'w') as f:
            f.write(r[1])
        print(f'[icons] could not download {r[1]}', flush=True)
        return None
    data, ext = got
    path = os.path.join(d, f'{key}.{ext}')
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
    if os.path.exists(missing):
        os.remove(missing)
    return path, MIME[ext]
