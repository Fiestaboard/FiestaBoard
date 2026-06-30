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

Back up the `data/` directory regularly to preserve your pages, schedules, and settings:

```bash
# Simple backup
cp -r data/ data-backup-$(date +%Y%m%d)/

# Or use a cron job
0 2 * * * tar -czf /backups/fiestaboard-$(date +\%Y\%m\%d).tar.gz /path/to/FiestaBoard/data/
```

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
- **Restrict API access** - The API has no authentication by default
- **Use a reverse proxy** - For external access, put FiestaBoard behind Nginx or Traefik with HTTPS
- **Keep Docker updated** - Regularly update Docker and Docker Compose

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
