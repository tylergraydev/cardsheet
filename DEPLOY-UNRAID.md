# Getting cardsheet onto Unraid

Three routes. The first matches how you already ship things and is the one
worth doing.

---

## Route A: GHCR + Unraid template (recommended)

Push the source to GitHub, let Actions build the image, let Unraid pull it.
Updates become "click Update" in the Docker tab forever after.

### 1. Push it

The repo is already committed locally, with `origin` pointed at
`https://github.com/tylergraydev/cardsheet.git`. Create the empty repo and
push:

```bash
cd cardsheet-app
gh repo create tylergraydev/cardsheet --public \
  -d "Build Cricut Print-Then-Cut card sheets: drop four images, print them yourself, let Cricut only cut."
git push -u origin main
```

If `gh` is not installed, make the repo at
<https://github.com/new> (name `cardsheet`, public, no README or .gitignore)
and then just `git push -u origin main`.

`.github/workflows/docker.yml` is already in the tree. It builds on every push
to `main` and publishes `ghcr.io/<you>/cardsheet-app:latest` plus a
short-SHA tag. No secrets to configure, `GITHUB_TOKEN` covers GHCR.

Watch the first run:

```bash
gh run watch
```

### 2. Make the package public

The Action publishes `ghcr.io/tylergraydev/cardsheet`. GHCR packages default to
**private even when the repo is public**, so this step is not optional:

repo → Packages (right sidebar) → cardsheet → Package settings →
Danger Zone → Change visibility → **Public**

Also under Package settings, confirm the package is linked to the repo so the
Unraid template's Registry link resolves.

Without this, Unraid's pull fails with `denied` and you would have to add a
`ghcr.io` credential in the Docker tab with a PAT scoped `read:packages`.

### 3. Add the container

`unraid-template.xml` already points at your account. Either:

- Drop it in `/boot/config/plugins/dockerMan/templates-user/` and pick
  **cardsheet** from the template dropdown in Add Container, or
- Docker tab → Add Container → paste the raw GitHub URL of the file into the
  **Template** field.

Defaults it sets:

| | |
|---|---|
| Port | `8080` → container `8000` |
| Data | `/mnt/user/appdata/cardsheet` → `/data` |

Apply, then open `http://<unraid-ip>:8080`.

### 4. Updating

Push to `main`, wait for the Action, hit **Update** on the container. Your
template PDF and sheets live in appdata and survive it.

---

## Route B: Compose Manager, build on the box

No GitHub involved. Good if you want it running in five minutes.

1. Apps → search **Docker Compose Manager** (dcflachs) → Install.
2. Copy the `cardsheet-app` folder to the server, e.g.
   `/mnt/user/appdata/cardsheet-src/`. Over SMB, or:
   ```bash
   scp -r cardsheet-app root@<unraid-ip>:/mnt/user/appdata/cardsheet-src
   ```
3. Docker tab → Compose → Add New Stack → name it `cardsheet` → Edit Stack →
   point it at that directory, or paste:
   ```yaml
   services:
     cardsheet:
       build: /mnt/user/appdata/cardsheet-src
       image: cardsheet:latest
       container_name: cardsheet
       ports:
         - "8080:8000"
       volumes:
         - /mnt/user/appdata/cardsheet:/data
       restart: unless-stopped
   ```
4. Compose Up.

The first build pulls node and python base images and takes a few minutes.
Downside versus Route A: every update means rebuilding on the server, and the
container will not show an Update available badge.

---

## Route C: build here, ship the tar

No GitHub, no building on Unraid. Useful if the server's outbound access is
restricted.

```bash
# on your workstation
docker build -t cardsheet:latest cardsheet-app
docker save cardsheet:latest | gzip > cardsheet.tar.gz
scp cardsheet.tar.gz root@<unraid-ip>:/mnt/user/appdata/

# on Unraid
gunzip -c /mnt/user/appdata/cardsheet.tar.gz | docker load
```

Then Add Container with Repository `cardsheet:latest` and the same port and
path mappings as the template. Updating means repeating the whole dance, so
this is a fallback, not a workflow.

---

## About the "app store"

Pushing to GHCR does **not** make this appear in Community Applications. CA is
a curated catalog, not a registry mirror, and it only lists apps that have been
submitted and scanned.

For your own server you do not need CA at all. The template XML route above is
the normal way to run your own container, and it behaves identically once
installed: same Docker tab entry, same Update button, same WebUI link.

If you ever do want it listed publicly, submission goes through
<https://ca.unraid.net/submit>. It needs a separate public repo of template
XML files plus author and support metadata, and it gets a live scan that checks
for duplicates and validates the XML before it is published. Worth doing only
if you want strangers installing it.

## Reaching it

Local only is fine: `http://<unraid-ip>:8080`.

You already run Cloudflare Tunnels, so if you want it from anywhere, add a
public hostname pointing at `http://<unraid-ip>:8080`. Put Cloudflare Access in
front of it. The app has no authentication of its own, and anyone who reaches
it can read and replace your template.

---

## Notes for this container

- **Runs as root**, like most Unraid containers. Files in appdata end up
  root-owned, which is normal there. No PUID/PGID handling.
- **Stateless except `/data`.** Back up `/mnt/user/appdata/cardsheet` and you
  never redo the Design Space setup. It holds `ds_template.pdf`,
  `template.json`, and every sheet you have built under `sheets/`.
- **Sheets accumulate.** Each is a few hundred KB. Nothing prunes them. If it
  ever bothers you, `rm /mnt/user/appdata/cardsheet/sheets/*.pdf`.
- **Health check** is built in, so Unraid shows the container as healthy once
  the API answers.
- **amd64 only** in the workflow, which is what Unraid is. Add
  `linux/arm64` to `platforms:` if that ever changes.

## Printing from the server

The app hands you a PDF in the browser, so printing happens on whatever machine
you open it from, not on Unraid. Nothing to configure server-side.

Your ET-2903 is a Letter-class EcoTank, so stick with the Letter 2x2 template.
The Legal and Tabloid layouts I mentioned earlier would need a different
printer. Worth confirming Legal support in its specs if you ever want the 6-up
sheet, since that would get you from 4 cards per sheet to 6.

Whatever you print from, the rule does not change: **100% scale, no fit to
page.**
