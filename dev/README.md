# Trying weHub and the apps without Pocket ID (development only)

`fake_oidc.py` is a stand-in OpenID Connect provider: its sign-in page lists the people in `users.json` and you
click one (no passwords). It listens on 127.0.0.1 only: **never expose it on a network**, anyone reaching it signs in as anyone.
