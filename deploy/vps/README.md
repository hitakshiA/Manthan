# VPS deployment

Manthan runs on any Ubuntu 22.04 / 24.04 VPS - DigitalOcean, Linode,
Vultr, Hetzner, AWS Lightsail, OVH, or your own metal. Three
supported paths from a fresh VPS to a running Manthan. Full deploy
walkthrough (env vars, Caddy config, Stripe / Slack / Resend wiring)
lives in [`../../DEPLOY.md`](../../DEPLOY.md).

## A · One-click cloud-init

When provisioning a new VPS that accepts cloud-init / user-data in
the console (DigitalOcean's "User data" field, Vultr's "Startup
Script", Linode's "Stackscript"), paste the contents of
[`cloud-init.yaml`](cloud-init.yaml). The VM boots, installs Docker
+ `uv`, clones the repo into `/opt/manthan`, brings up Postgres in a
container, installs the four systemd services, and reports its IP.
Three to five minutes end to end.

After it finishes:

```bash
ssh root@<vps-ip>
nano /opt/manthan/manthan-api/.env       # paste real secrets
systemctl restart manthan-api manthan-investigate manthan-actor manthan-prettifier
```

Open `http://<vps-ip>:8765` to confirm the API is up. Add a domain
+ Caddy (path C below) to get HTTPS.

## B · Manual bootstrap

For VPS providers without cloud-init in the console, or if you prefer
to watch the install in real time, SSH in as root and:

```bash
curl -fsSL https://raw.githubusercontent.com/akash-mondal/manthan/main/deploy/vps/setup.sh | bash
```

The same `setup.sh` that `cloud-init.yaml` runs under the hood.
Streams progress to your terminal.

## C · TLS + a real hostname (recommended for any public access)

Point a domain at the VPS IP, then put Caddy in front:

```bash
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy
```

Copy [`Caddyfile.example`](Caddyfile.example) to `/etc/caddy/Caddyfile`,
replace `your-domain.com` with the real hostname, then:

```bash
systemctl restart caddy
```

Caddy auto-provisions a Let's Encrypt cert on the first HTTPS
request. `https://your-domain.com` now reverse-proxies to the
FastAPI service on `localhost:8765` with proper SSE buffering, gzip,
and HSTS. The same Caddyfile also serves the UI from
`/opt/manthan/manthan-ui/dist/` as static files alongside the API
routes.

## What's running on the box afterwards

| Process | Source |
|---|---|
| `caddy` | systemd, terminates TLS, proxies to :8765 + serves static UI |
| `manthan-api` | systemd, FastAPI on `127.0.0.1:8765` via `uv run uvicorn` |
| `manthan-investigate` | systemd, agent loop worker |
| `manthan-actor` | systemd, action executor worker |
| `manthan-prettifier` | systemd, event-summary worker |
| `manthan-postgres` | Docker container, PG 16 on `127.0.0.1:5432` |
| `coral` | spawned per-investigation by manthan-investigate over MCP stdio |

Logs:
```bash
journalctl -u manthan-api -f
journalctl -u manthan-investigate -f
tail -f /var/log/manthan-actor.log         # actor uses StandardOutput=append to file
tail -f /var/log/manthan-prettifier.log
```

## Env vars

At minimum, `/opt/manthan/manthan-api/.env` must contain:

```
DATABASE_URL=postgresql://manthan:<pg-password>@127.0.0.1:5432/manthan
OPENROUTER_API_KEY=sk-or-v1-...
CORAL_BINARY=/usr/local/bin/coral
CLERK_SECRET_KEY=sk_test_...
WEB_APP_ORIGIN=https://your-domain.com
```

The full env-var menu (Stripe, HubSpot, Slack, Resend, signing
secrets, model overrides) is documented in
[`../../DEPLOY.md`](../../DEPLOY.md). The agent itself only reads
three vars (`OPENROUTER_API_KEY`, `MANTHAN_MODEL`, `CORAL_BINARY`) -
the rest are for the API, the actor's write adapters, and webhook
signature verification. Per-source API credentials (Stripe / HubSpot
read tokens for the agent) live on the Coral side via
`coral source add`, not here.

## Resources

The whole stack fits comfortably on a 4 vCPU / 8 GB / 80 GB VPS.
Postgres workload is small (one case is a few KB of events + a
handful of findings + a few action rows), the agent does its heavy
work over network round-trips to OpenRouter + Coral rather than on
the box. We've run the public demo at
[manthan.quest](https://manthan.quest) on a single 4-vCPU droplet
without breaking a sweat.

For higher throughput (real production, not just the demo), the
bottleneck is the LLM round-trips per investigation. Scale by
running more `manthan-investigate` worker instances and pointing
them all at the same Postgres - `LISTEN/NOTIFY` plus `FOR UPDATE
SKIP LOCKED` on `cases` already gives you safe horizontal scaling.

## Updates

The day-to-day deploy loop we use at manthan.quest:

```bash
ssh root@<vps-ip>
cd /opt/manthan
git fetch origin main && git reset --hard origin/main
systemctl restart manthan-api manthan-investigate manthan-actor manthan-prettifier
```

UI changes also need a build + rsync from your laptop:

```bash
# laptop
cd manthan-ui && npm run build
rsync -avz --delete dist/ root@<vps-ip>:/opt/manthan/manthan-ui/dist/
```

Hard-refresh the browser after rsync to pick up the new JS bundle
hash.
