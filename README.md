# weHub – the family, one sign-in for all the apps

> **Disclaimer / Esclusione di responsabilità.** weHub is provided *as is*, without any warranty: the authors accept **no responsibility or liability** for data loss, security problems, missed reminders, wrong information or any other consequence of using it. Read [DISCLAIMER.md](DISCLAIMER.md) before using it with real data. · Il software è fornito *così com'è*, senza garanzie: gli autori **non hanno alcuna responsabilità**. Leggi [DISCLAIMER.md](DISCLAIMER.md).

weHub is where the family is defined, once, for **doTrack**, **eaTrack** and **paTrack**:

- **Members**: added by email; they sign in with **Pocket ID** (passkey, Face ID) using that same email.
  The same Pocket ID signs them in to every app: no other passwords, no tokens to paste.
- **Which app each member may use** (and, for paTrack, full or limited access — the details of "limited" come with
  paTrack's sharing).
- **People without an account**: kids, grandparents… A *child* also appears in eaTrack; everyone appears in doTrack
  ("people") and paTrack (who documents are about).
- **Home page** with the apps each person may use, and **links** to other services (Vaultwarden, Home Assistant,
  Immich…) in **groups**, like [Homepage](https://gethomepage.dev): managed by the admin, each shown to everyone or
  only to chosen members. Icons are written as in Homepage (`jellyfin.png`, `synology-photos`, `sh-immich`,
  `mdi-logout`, `si-gitea` or an image address); weHub downloads each one once and serves it itself. A Homepage
  `services.yaml` can be pasted in **Links → Import from Homepage** (`container`, `server`, `widget` are ignored).
  Hiding a link is not access control: those services keep their own sign-in.
- **Import**: brings in, once, the members, people and children the apps already have. Nothing is deleted in the
  apps: each one recognises its own family and people and keeps all its data (meals, to-dos, documents).
- **Merging families made separately**: if someone (e.g. the partner) had signed up on their own in an app, the import
  proposes their family there; on request the app moves all its data into the shared family (people, labels, foods
  and children with the same name become one; an identical paTrack document goes to the trash), after making a
  backup of its database.

> **Made with AI.** Like the other apps, written by an AI assistant (Anthropic's Claude) and checked with automated
> tests; review it before exposing it to the internet.

## How the apps use it
Each app keeps working on its own unless `*_HUB_URL` and `*_HUB_KEY` are set. When they are:

1. Sign-in only through the OIDC provider (Pocket ID). The app's login page sends people there directly.
2. After sign-in the app asks weHub (`POST /api/service/whoami`, with its key) who the person is and which families
   may use that app; it copies those families: members, roles, people. Someone without access is told to ask the
   family admin.
3. When a family changes in weHub, every app is told at once (`POST /api/hub/changed`) and refreshes it
   (`GET /api/service/families/<id>`); every 2 minutes (`*_HUB_SYNC_SECONDS`) the apps also check on their own, in
   case a message was lost (answered with "unchanged" when nothing changed). The family also says which apps each
   member may use: the apps show them in their app switcher (the grid next to the logo). Removed members lose access and are signed out; removed people:
   doTrack → their to-dos go back to "anyone", paTrack → their documents become the whole family's, eaTrack → the
   child is archived, meals kept.
4. If weHub is down, people who signed in before go on working with the copy.
5. In the apps, the family, its members and people become read-only, with a link to weHub.
6. The apps ask each other through weHub (`/api/service/apps/<app>/families/<id>/…`): weHub passes the request on
   with the other app's key, so no app needs another's address or token. Only the calls listed in `ALLOWED`
   (`backend/service.py`) go through, for a member of the family who may use the asking app (and, when the answer is
   paTrack's, paTrack too). Today: eaTrack sends the weekly menu to a doTrack shopping list (the admin only picks the
   list in eaTrack → Family).

Each app has its own key (`python manage.py new-key`), set both in weHub (`WEHUB_APP_<APP>_KEY`) and in the app
(`<APP>_HUB_KEY`). It is only used between servers.

## Setting it up

The code shared with the apps (mail, backups, the weHub link, sign-in) is in the `backend/famkit` submodule
([famkit](https://github.com/filippogiuliani/famkit)): clone every app with `git clone --recurse-submodules …`, or run
`git submodule update --init` in a clone made without it (`deploy/build-images.sh` does it when it is missing).
1. Pocket ID: add an OIDC client for weHub and one for each app (callback `<URL>/api/oidc/pocketid/callback`).
   Make sure Pocket ID sends `email_verified` true for your users (weHub and the apps match people by verified
   email the first time).
2. `cp .env.example .env`, fill in Pocket ID and the three apps with their keys, `./rebuild.sh` (port 3004).
3. Sign in to weHub: the first person creates the family and is its admin.
4. In each app's `.env` set `<APP>_HUB_URL`, `<APP>_HUB_KEY` and the Pocket ID client (`<APP>_OIDC=pocketid`, …),
   then rebuild it.
5. In weHub → **Import**: check which family of each app, the members and the people (the same name in several apps
   becomes one person; doubtful cases can be renamed, merged with someone already there, or skipped), then Import.
6. Add the partner (and, later, the babysitter) in weHub → Family, choosing their apps.

Before the first import, back up each app (they all have `manage.py backup`).

## Deploying
`deploy/` has the Portainer stack for the four apps (`docker-compose.yml`, `stack.env.example`, `build-images.sh`)
and a step-by-step `deploy/README.md`.

## Development
`dev/fake_oidc.py` is a stand-in for Pocket ID that lists people to click (no passwords). It listens on 127.0.0.1
only: never expose it on a network. See `dev/README.md`.

```sh
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
.venv/bin/python -m pytest
```

## License
[MIT](LICENSE). No warranty and no liability: see [DISCLAIMER.md](DISCLAIMER.md).
