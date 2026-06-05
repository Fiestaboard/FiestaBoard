# Security

## Reporting a vulnerability

If you believe you've found a security issue, please report it privately:

- **Do not** open a public GitHub issue or post in Discord.
- File a private report via [GitHub Security Advisories](https://github.com/Fiestaboard/FiestaBoard/security/advisories/new).

We will acknowledge your report, work with you to understand it, and coordinate a fix and disclosure timeline. Please do not publicly share details of the issue until a fix is released.

## Supported versions

We provide security fixes for the latest released version on the `main` branch and the `latest` Docker tag. Older versions are best-effort.

## Sensitive data handling

- **Secrets** (API keys, tokens, passwords) are never logged or returned in API responses. Plugin and board configs are masked (sensitive fields replaced with `***`) when returned by the API.
- **Configuration** is loaded from the `data/` directory and from environment variables. Never commit `.env` or files under `data/` (such as `data/config.json` or `data/settings.json`) — they are listed in `.gitignore`.
- **Docker** Compose files reference `env_file: .env` so secrets stay on the host; no secrets are baked into images.

## Deployment

- Run the API and UI in Docker; put a reverse proxy (for example nginx) with TLS in front if you expose FiestaBoard to the internet.
- Restrict access to the API and UI when possible (VPN, firewall, or auth proxy). FiestaBoard's HTTP API has no built-in authentication today.
- Use strong, unique API keys for your Vestaboard and any third-party services (weather, transit, etc.).
