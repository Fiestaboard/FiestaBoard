---
sidebar_position: 2
description: "Production deployment best practices for running FiestaBoard reliably with Docker, SSL, and monitoring."
keywords: [FiestaBoard production, deployment guide, Docker production, SSL setup, self-hosted, best practices]
---

# Production Deployment

Best practices for deploying FiestaBoard in a production environment.

## Docker Compose for Production

Use the production-optimized Docker Compose file:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Or use pre-built images from Docker Hub:

```bash
docker compose -f docker-compose.hub.yml up -d
```

## Recommended Configuration

### Environment Variables

```bash
# In .env
REFRESH_INTERVAL_SECONDS=300   # Refresh every 5 minutes (default)
SILENCE_SCHEDULE_START_TIME=22:00       # Set quiet hours
SILENCE_SCHEDULE_END_TIME=07:00
```

### Data Backup

FiestaBoard stores all persistent state in two directories on the host:

| Directory | Contents |
|-----------|----------|
| `data/` | Config, pages, schedules, carousels, settings, logs, and migration backups |
| `external_plugins/` | Marketplace plugins installed via the Integrations page |

Both directories are automatically bind-mounted by Docker Compose. Back up both to fully preserve your setup:

```bash
# One-shot backup (run from the directory containing your docker compose file)
tar -czf fiestaboard-backup-$(date +%Y%m%d).tar.gz data/ external_plugins/

# Automated daily backup via cron (runs at 2 AM)
0 2 * * * tar -czf /backups/fiestaboard-$(date +\%Y\%m\%d).tar.gz /path/to/FiestaBoard/data/ /path/to/FiestaBoard/external_plugins/
```

**Restore from backup:**

```bash
# Stop the container before restoring
docker compose down

# Extract the backup (overwrites existing data/ and external_plugins/)
tar -xzf fiestaboard-backup-20240101.tar.gz

# Start again — all pages, settings, and plugins are restored
docker compose up -d
```

:::tip What each file contains

- `data/config.json` — Board API key and connection settings
- `data/settings.json` — Display preferences, active page, schedule
- `data/pages.json` — All board pages
- `data/schedules.json` / `data/carousels.json` — Automation rules
- `data/*.backup` — Automatic pre-migration snapshots (safe to delete after confirming an upgrade works)
- `data/tls/` — Certificate and private key when built-in self-signed HTTPS is enabled; protect backups containing the key
:::

## Updating

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

:::tip Zero-Downtime Updates
Pull the latest code and rebuild the images first, then bring down the old containers and start the new ones. The downtime is minimal, just a few seconds while containers swap.
:::

## Monitoring

### Health Checks

FiestaBoard provides a health endpoint:

```bash
curl http://localhost:4420/api/health
```

You can use this with monitoring tools like Uptime Kuma or Healthchecks.io.

### Logs

```bash
# View all logs
docker compose logs -f

# View FiestaBoard container logs only
docker compose logs -f fiestaboard
```

## Security Considerations

- **Never commit `.env` files** to version control
- **Enable authentication** - Keep [login](/docs/setup/authentication) enabled for any installation reachable from the public internet
- **Use trusted HTTPS** - Use your own trusted certificate with built-in TLS, or put FiestaBoard behind a reverse proxy with HTTPS
- **Keep Docker updated** - Regularly update Docker and Docker Compose

## Built-in HTTPS

FiestaBoard serves HTTP by default at `http://your-host:4420`. Built-in TLS is an optional additional listener: container port `3443`, published as `4443` by `docker-compose.tls.yml`. HTTP stays available on `4420`, including the existing healthcheck. There is no automatic HTTPS redirect or HTTP Strict Transport Security header. Restrict access to HTTP at your firewall if you require clients to use HTTPS.

Run the examples from your existing installation directory so the same `.env` and data mounts are used. The examples use `docker-compose.hub.yml`; substitute `docker-compose.prod.yml` or `docker-compose.yml` for a source build, adding `--build` when needed. Keep the same list of compose files on every start, update, and recreate.

:::warning One-click updates and overlays
The optional FiestaUpdater sidecar reads only its mounted base compose file. It does not preserve the TLS overlay or a custom certificate mount supplied in another file. Before using these examples, remove `fiestaupdater` from `COMPOSE_PROFILES` in `.env` and stop any running sidecar with `docker compose -f docker-compose.hub.yml stop fiestaupdater`. Use the manual update commands below. An in-app update could otherwise remove the HTTPS port mapping or certificate mount.
:::

### Self-signed certificate

Set these values in `.env`, replacing the example names and address with the ones your clients use:

```bash
FIESTABOARD_TLS_MODE=self-signed
FIESTABOARD_TLS_HOSTS=fiestaboard.local,192.168.1.50
FIESTABOARD_TLS_PORT=4443
```

The hosts list accepts 1–32 comma-separated DNS names or IP addresses. Use bare names and addresses without schemes, ports, paths, or wildcards. These become the certificate's subject alternative names; adding a name does not configure DNS or reserve an IP address.

```bash
docker compose -f docker-compose.hub.yml -f docker-compose.tls.yml up -d --force-recreate fiestaboard
```

Open `https://fiestaboard.local:4443` using a name included in your hosts list. On first startup, FiestaBoard generates a certificate valid for 365 days and saves it as `data/tls/server.crt` with its key at `data/tls/server.key`. Restarts reuse the same pair. The directory is mode `0700` and the private key is mode `0600`.

Browsers do not automatically trust a self-signed certificate. Install only the public certificate in each client's appropriate trust store and verify it belongs to your hub. Never distribute `server.key`. Dismissing a certificate warning does not reliably enable service workers, installation, or push: those features require a secure context accepted by the browser. For devices where managing trust is impractical, use a certificate they already trust or a reverse proxy with one.

### Bring your own certificate

Use a PEM certificate with its intermediate chain and a matching, unencrypted PEM private key. Their validity dates and matching key are checked at startup. FiestaBoard does not modify these files or obtain certificates from a certificate authority.

Place the files in an existing `tls/` directory beside your compose file. Make that directory traversable and both files readable by the container's `appuser` (UID `1000`), while restricting access to the private key. On a Linux host, for files dedicated to this service:

```bash
sudo chown -R 1000:1000 tls
sudo chmod 700 tls
sudo chmod 600 tls/privkey.pem
sudo chmod 644 tls/fullchain.pem
```

Create `docker-compose.tls-custom.yml` with this directory mount. Keeping it separate means self-signed mode does not require a host certificate directory:

```yaml
services:
  fiestaboard:
    volumes:
      - type: bind
        source: ./tls
        target: /run/fiestaboard-tls
        read_only: true
        bind:
          create_host_path: false
```

Set the absolute **container paths** in `.env`:

```bash
FIESTABOARD_TLS_MODE=custom
FIESTABOARD_TLS_CERT_FILE=/run/fiestaboard-tls/fullchain.pem
FIESTABOARD_TLS_KEY_FILE=/run/fiestaboard-tls/privkey.pem
FIESTABOARD_TLS_PORT=4443
```

```bash
docker compose -f docker-compose.hub.yml -f docker-compose.tls.yml -f docker-compose.tls-custom.yml up -d --force-recreate fiestaboard
```

Use a hostname covered by your certificate. If the files are symbolic links, their targets must also be accessible inside the mounted directory. A directory mount allows an external renewal tool to replace files; a bind mount of an individual file can retain the old file after replacement.

### Renewal and updates

FiestaBoard does not run an ACME client or automatically renew certificates. For custom certificates, renew them externally, keep the paths and permissions valid, then recreate the container using all three compose files shown above. The running server does not automatically reload renewed files.

For a self-signed certificate that expires or needs a different hosts list, stop FiestaBoard using the same compose files first. Back up `data/tls/` securely, then move that directory aside while the service is stopped. Update `FIESTABOARD_TLS_HOSTS` if needed and recreate the container. A new pair is generated; distribute and trust the replacement public certificate on each client. Simply changing the hosts list or restarting an expired certificate does not silently rotate its identity.

For manual image updates in self-signed mode:

```bash
docker compose -f docker-compose.hub.yml -f docker-compose.tls.yml pull fiestaboard
docker compose -f docker-compose.hub.yml -f docker-compose.tls.yml up -d --force-recreate fiestaboard
```

For custom mode, include `-f docker-compose.tls-custom.yml` in both commands as well. Back up custom certificate material separately from `data/`, using your certificate provider's procedures.

### Disable TLS or recover from an error

Invalid TLS settings, unreadable files, an expired certificate, or a mismatched certificate and key stop container startup. There is no silent fallback to HTTP when TLS was requested. Check `docker compose -f docker-compose.hub.yml logs fiestaboard`, correct the configuration, and recreate with the same compose files.

To deliberately return to HTTP, set `FIESTABOARD_TLS_MODE=off` in `.env` and recreate the service. The TLS listener configuration is removed, but stored certificates and keys are retained. You can also omit the TLS overlays when recreating to remove their port and mount. Browse to `http://your-host:4420` again.

### Home Assistant ingress

Keep `FIESTABOARD_TLS_MODE=off` when Home Assistant or another proxy already terminates HTTPS. Home Assistant ingress continues to connect to FiestaBoard over HTTP on container port `3000`; retain the existing ingress path rewrite configuration. The browser's HTTPS connection and certificate trust come from Home Assistant. Built-in TLS is unnecessary for this path and does not replace Home Assistant's certificate configuration.

## Running Behind a Reverse Proxy

If you want to access FiestaBoard from outside your local network, use a reverse proxy with HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name fiestaboard.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:4420;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Next Steps

- [Raspberry Pi](/docs/deployment/raspberry-pi) - Deploy on a Raspberry Pi
- [Docker Setup](/docs/setup/docker-setup) - Docker architecture details
- [Cloud API](/docs/setup/cloud-api) - Remote board access via cloud API
