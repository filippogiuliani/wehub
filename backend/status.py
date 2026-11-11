"""Is a link's service up? weHub opens its address, like Homepage's siteMonitor.

Any HTTP answer below 500 counts as up: a sign-in page, a redirect to Pocket ID or a 401 still mean the service is
there. 5xx (e.g. the reverse proxy's 502 when the container is stopped), a timeout or no connection mean down.
Redirects are not followed and certificates are not checked: only reachability is looked at, nothing is read.
Results are kept for a minute, so opening the home page often does not hammer the services."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TIMEOUT = 5
KEEP = 60
_cache = {}  # url → (checked at, result)
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='status')


def _check(url):
    start = time.monotonic()
    try:
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=False, verify=False, headers={'User-Agent': 'weHub status'})
        if r.status_code in (405, 501):  # HEAD not supported: ask with GET (body not read)
            r = requests.get(url, timeout=TIMEOUT, allow_redirects=False, verify=False, stream=True,
                             headers={'User-Agent': 'weHub status'})
            r.close()
        ms = round((time.monotonic() - start) * 1000)
        return {'up': r.status_code < 500, 'code': r.status_code, 'ms': ms}
    except requests.Timeout:
        return {'up': False, 'code': None, 'ms': None, 'reason': 'timeout'}
    except requests.RequestException:
        return {'up': False, 'code': None, 'ms': None, 'reason': 'unreachable'}


def check_many(urls):
    """{url: result} for these addresses, from the cache when fresh, the others checked in parallel."""
    now = time.monotonic()
    out, todo = {}, []
    with _lock:
        for u in set(urls):
            hit = _cache.get(u)
            if hit and now - hit[0] < KEEP:
                out[u] = hit[1]
            else:
                todo.append(u)
    for u, res in zip(todo, _pool.map(_check, todo)):
        out[u] = res
        with _lock:
            _cache[u] = (time.monotonic(), res)
    return out


def clear():
    with _lock:
        _cache.clear()
