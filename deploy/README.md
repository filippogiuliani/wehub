# Deploying the family apps (Portainer)

One stack with **weHub**, **doTrack**, **eaTrack** and **paTrack**. Pocket ID is not in the stack: use yours.

## 1. Pocket ID
Create four OIDC clients (weHub, doTrack, eaTrack, paTrack). Callback URL of each:
`https://<app address>/api/oidc/pocketid/callback`. Make sure the users' emails count as verified (the apps match a
person by verified email the first time).

## 2. Images
On the Docker host, with the four source folders side by side (`wehub/`, `dotrack/`, `eatrack/`, `patrack/`):
```sh
./wehub/deploy/build-images.sh        # SRC=… and DOTRACK_DIR=… if your folders are elsewhere / named differently
```
The stack uses these local images (`wehub:latest`, …). After an update: build again, then **Update the stack**.

## 3. Variables
Copy `stack.env.example`, fill it in (addresses, Pocket ID clients, three keys, SMTP, optionally the paTrack
mailbox) and in Portainer → Stacks → Add stack → Web editor paste `docker-compose.yml`, then
"Environment variables" → **Load variables from .env file**. Create `DATA_ROOT` on the host first
(e.g. `mkdir -p /srv/family`).

## 4. Reverse proxy
Forward each public HTTPS address to the published port of the host (weHub 3004, doTrack 3001, eaTrack 3000,
paTrack 3002 by default). The apps trust the proxy's `X-Forwarded-*` headers. If your proxy runs in Docker you can
instead attach it to the `family` network and point it at `wehub:3004`, `dotrack:3001`, …

## 5. First run
1. Before the first start with weHub, if you already use doTrack/eaTrack/paTrack: back up their data folders and
   copy them into `DATA_ROOT/dotrack`, `DATA_ROOT/eatrack`, `DATA_ROOT/patrack`.
2. Open weHub and sign in: the first person creates the family.
3. weHub → **Import** → check and confirm.
4. weHub → **Family**: add the partner, the people, the links (Vaultwarden, Home Assistant…).

## Backups
Everything is under `DATA_ROOT`. paTrack's NAS script (`patrack/scripts/backup-to-nas.sh`) works with the stack:
set `PATRACK_DATA_DIR=$DATA_ROOT/patrack` in its `backup.env` (the container is called `patrack`). The same Borg
repository can also take the other three folders: add `$DATA_ROOT/wehub $DATA_ROOT/dotrack $DATA_ROOT/eatrack`
(their `backups/` subfolders hold consistent daily copies of each database).
