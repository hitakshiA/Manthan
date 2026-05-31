# VPS deployment

Manthan runs on any Ubuntu 22.04 / 24.04 VPS - DigitalOcean, Linode,
Vultr, Hetzner, AWS Lightsail, OVH, or your own metal. The stack is a
single Docker image, fronted by Caddy for TLS. Three supported paths
from a fresh VPS to a running Manthan.

## A · One-click cloud-init

When provisioning a new VPS that accepts cloud-init / user-data in the
console (DigitalOcean's "User data" field, Vultr's "Startup Script",
Linode's "Stackscript"), paste the contents of [`cloud-init.yaml`](cloud-init.yaml).
The VM boots, installs Docker, clones this repo, brings up
`docker compose`, and reports its IP. Three to five minutes end to end.

After it finishes:

```bash
ssh root@<your-vps-ip>
nano /opt/manthan/.env             # paste GEMINI_API_KEY
docker compose -f /opt/manthan/docker-compose.yml restart
```

Open `http://<your-vps-ip>:8000` - you're live.

## B · Manual bootstrap

For VPS providers without cloud-init in the console, or if you prefer
to watch the install in real time, SSH into the VPS as `root` and:

```bash
curl -fsSL https://raw.githubusercontent.com/hitakshiA/Manthan/main/infra/vps/setup.sh | bash
```

The same `setup.sh` that `cloud-init.yaml` runs under the hood. Streams
its progress to your terminal. About three minutes.

## C · TLS + a real hostname (recommended for a public demo)

Point a domain at the VPS IP, then put Caddy in front:

```bash
ssh root@<your-vps-ip>
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy
```

Copy `infra/vps/Caddyfile.example` to `/etc/caddy/Caddyfile`, replace
`your-domain.com` with the real hostname, then:

```bash
systemctl restart caddy
```

Caddy auto-provisions a Let's Encrypt cert on the first HTTPS request.
`https://your-domain.com` now reverse-proxies to the FastAPI container
on `localhost:8000` with proper SSE buffering, gzip, and HSTS.

## Env vars

At minimum, `.env` must contain:

```
GEMINI_API_KEY=<from https://aistudio.google.com/apikey>
```

All other settings have sensible defaults. The default model cascade is
`gemini-3-flash-preview` → `gemini-3.1-pro-preview` - Flash for speed,
Pro as the escalation fallback. See `.env.example` for the full list.

## Resources

Manthan + DuckDB on a 4 GB VPS handles the demo datasets comfortably
(138 K-row DABstep payments, 540 K-row UK retail, ~750 K total rows
across the five pre-loaded datasets). On a 2 GB VPS, set
`DUCKDB_MEMORY_LIMIT=1500MB` in `.env` and expect tight head-room.
For production loads, scale up.

## Optional · Lobster Trap security ribbon

The agent's connection to Google AI Studio can be routed through Veea's
Lobster Trap DPI proxy for prompt-injection and credential-leak
inspection - see [`infra/lobstertrap/README.md`](../lobstertrap/README.md).
On a production VPS you'd run Lobster Trap as a sibling container or
systemd service and point `GEMINI_BASE_URL` at `http://localhost:8080/v1beta/openai`.
