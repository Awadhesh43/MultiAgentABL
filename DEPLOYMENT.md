# Deploying the Agentic ABL Platform with Docker on a single EC2 instance

This guide containerizes the two-service web app described in
[WEBAPP_README.md](WEBAPP_README.md) — the FastAPI backend and the Angular
frontend — and deploys both to one AWS EC2 instance behind a single public
port.

```
┌─────────────────────────── EC2 instance ───────────────────────────┐
│                                                                      │
│   :80  ┌───────────────┐   /api/*   ┌───────────────┐  :8000        │
│  ─────►│   frontend    │───────────►│    backend    │               │
│        │ nginx + Angular│           │ FastAPI/uvicorn│               │
│        └───────────────┘           └───────┬────────┘               │
│                                             │                        │
│                                     named volumes: db_data,          │
│                                     chroma_data, uploaded_docs       │
└──────────────────────────────────────────────────────────────────┘
```

Only port 80 (and 22 for SSH) is exposed publicly. The frontend container
serves the built Angular app and reverse-proxies `/api/*` to the backend
container over the private Docker network — the browser only ever talks to
port 80, so no CORS configuration is needed.

## What's already in the repo

This session added:

| File | Purpose |
|---|---|
| [backend/Dockerfile](backend/Dockerfile) | Python 3.11-slim image running uvicorn |
| [frontend/Dockerfile](frontend/Dockerfile) | Multi-stage: `node:20-slim` build → `nginx:alpine` serve |
| [frontend/nginx.conf](frontend/nginx.conf) | Serves the Angular build, proxies `/api/` to the backend container |
| [docker-compose.yml](docker-compose.yml) | Wires both services together with named volumes |
| [.dockerignore](.dockerignore) / [frontend/.dockerignore](frontend/.dockerignore) | Keeps build contexts small, keeps secrets and local dev data out of images |

One small backend code change went with it:
[backend/app/config.py](backend/app/config.py) now reads an optional
`ABL_DB_DIR` env var for where the SQLite file lives (defaults to the old
behavior — `backend/abl_platform.db` — when unset). Docker Compose points it
at a named volume so the database survives container recreation; a bare
`python -m uvicorn` run outside Docker is unaffected.

**Note:** Docker wasn't available in the sandbox this guide was written in,
so the images below are unbuilt — logically verified against the app's
actual code paths, but not build-tested. Run `docker compose build` as your
first step (see below) and treat any error there as the place to start
debugging, not a sign the whole approach is wrong.

---

## 1. Build and test locally first

Do this on your own machine before touching EC2 — it's much faster to
iterate here than over SSH.

```bash
# from the repo root, with Docker Desktop (or the Docker Engine) running
cp .env.example .env        # if you haven't already; fill in ANTHROPIC_API_KEY
docker compose build
docker compose up -d
docker compose logs -f      # watch both services start; Ctrl+C to stop watching
```

Open http://localhost — you should see the dashboard. `/api/health` proxied
through nginx should return `{"status":"ok",...}`:

```bash
curl http://localhost/api/health
```

Seed the demo portfolio (optional, one-time — this drops and recreates the
7 demo deals described in WEBAPP_README.md):

```bash
docker compose exec backend python seed.py
```

Tear down when you're done testing:

```bash
docker compose down          # stops and removes containers, keeps volumes
docker compose down -v       # also deletes the named volumes (db, chroma index, uploads)
```

---

## 2. Launch the EC2 instance

Console → EC2 → Launch instance:

- **AMI**: Ubuntu Server 22.04 LTS (or 24.04 LTS), x86_64
- **Instance type**: `t3.small` (2 vCPU / 2 GB) is enough for this demo-scale
  app — SQLite + a local Chroma index, single uvicorn worker. Go to
  `t3.medium` if you plan to keep several browser tabs hammering it or run
  the LLM-backed stage agents heavily.
- **Key pair**: create or select one you have the `.pem` for
- **Storage**: 20 GB gp3 is comfortable (base OS + Docker images + the
  Chroma/SQLite volumes)
- **Security group**: create one allowing
  - SSH (22) from **your IP only** — not `0.0.0.0/0`
  - HTTP (80) from `0.0.0.0/0`
  - Leave 8000 closed — the backend is never exposed directly, only reached
    through nginx inside the Docker network
- **Network**: default VPC/subnet is fine for a single demo instance;
  allocate a public IP (default for a default-VPC subnet)

Launch, then note the instance's public IP or DNS name.

---

## 3. Install Docker on the instance

```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

Log out and back in (or run `newgrp docker`) so your shell picks up the
`docker` group membership without needing `sudo` for every command.

Verify:

```bash
docker --version
docker compose version
```

---

## 4. Get the code onto the instance

Pick whichever fits how the repo is hosted:

**If it's pushed to a Git remote (recommended):**

```bash
git clone <your-repo-url> MultiAgentABL
cd MultiAgentABL
```

**If it's local-only, copy it up with `rsync`** (run this from your local
machine, not the EC2 instance — it skips the heavy/regenerable
directories so the transfer is small):

```bash
rsync -avz --progress \
  --exclude node_modules --exclude .angular --exclude dist \
  --exclude chroma_db --exclude __pycache__ --exclude .venv \
  --exclude backend/abl_platform.db --exclude backend/uploaded_docs \
  -e "ssh -i /path/to/your-key.pem" \
  ./ ubuntu@<EC2_PUBLIC_IP>:~/MultiAgentABL/
```

Either way, create the `.env` file on the instance — **don't commit or copy
your real key into the image**, it's read by Compose at container-start
time via `env_file`:

```bash
cd ~/MultiAgentABL
cp .env.example .env
nano .env        # paste your ANTHROPIC_API_KEY
```

The app works without a key too — see "Works with or without an API key" in
WEBAPP_README.md — so this step is optional if you're fine with the
rule-based fallback behavior.

---

## 5. Build and run

```bash
docker compose up -d --build
```

First build downloads base images, npm/pip dependencies, and (on first
backend request that touches the ABL Wiki) the `all-MiniLM-L6-v2` embedding
model used by ChromaDB — that last part needs outbound internet access once,
which the default VPC setup provides.

Check both containers are healthy:

```bash
docker compose ps
docker compose logs -f --tail=50
```

Seed the demo portfolio (optional, one-time):

```bash
docker compose exec backend python seed.py
```

Visit `http://<EC2_PUBLIC_IP>` in a browser. `curl http://localhost/api/health`
on the instance should return `{"status":"ok","llm_configured":true}` (or
`false` if you skipped the API key).

---

## 6. Persistence, restarts, and reboots

- `restart: unless-stopped` in [docker-compose.yml](docker-compose.yml)
  means both containers come back automatically if they crash or if the
  instance reboots (Docker's own systemd unit is enabled from step 3, so
  the daemon itself also starts on boot).
- The SQLite database, the Chroma vector index, and uploaded documents live
  in named volumes (`db_data`, `chroma_data`, `uploaded_docs`) — they
  survive `docker compose down`, container recreation, and image rebuilds.
  They're **only** deleted by an explicit `docker compose down -v`.

**Back up the volumes** periodically:

```bash
docker run --rm -v multiagentabl_db_data:/data -v $PWD:/backup alpine \
  tar czf /backup/db_data_$(date +%Y%m%d).tgz -C /data .
```

(swap the volume name for `chroma_data`/`uploaded_docs` as needed — check
the actual names with `docker volume ls`, since Compose prefixes them with
the project/directory name).

---

## 7. Updating the deployed app

```bash
cd ~/MultiAgentABL
git pull                          # or re-run the rsync from step 4
docker compose up -d --build      # rebuilds only what changed, keeps volumes
docker image prune -f             # optional: drop old dangling image layers
```

---

## 8. Optional: put a domain and HTTPS in front of it

For a demo bound to a public IP, plain HTTP is usually fine. If you point a
domain at the instance and want TLS, the simplest path is swapping nginx for
[Caddy](https://caddyserver.com/) in the frontend container (automatic
Let's Encrypt certs), or keeping nginx and running `certbot` on the host in
front of it. Both are a bigger change than this guide's scope — ask if you
want that built out.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `docker compose build` fails on the backend at `pip install` | Outbound internet blocked from the build (unlikely on default VPC); retry, check the security group only restricts *inbound* |
| Frontend loads but every API call 502s | Backend container isn't healthy yet — check `docker compose logs backend`; the Chroma/embedding model download can take a bit on first run |
| `/api/health` returns `llm_configured: false` unexpectedly | `.env` wasn't created, or `ANTHROPIC_API_KEY` is blank/typo'd — `docker compose exec backend env \| grep ANTHROPIC` to check what actually reached the container |
| Data disappears after redeploy | Someone ran `docker compose down -v` — that deletes the named volumes; regular `docker compose down` / `up` does not |
| Can't reach the site at all | Security group missing the port 80 inbound rule, or you're using the private IP instead of the public one |
