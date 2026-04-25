# =============================================================================
# FiestaUpdater — companion sidecar container that performs in-place updates
# of the main `fiestaboard` container via the host Docker socket.
#
# Listens on port 8765 on the *internal* compose network only (no host port
# is published).  Authenticated via a bearer token shared with the main
# `fiestaboard` container through the FIESTAUPDATER_TOKEN env var.
#
# Base image: docker:cli (official, maintained by Docker Inc., multi-arch).
# =============================================================================
FROM docker:cli

# socat: tiny per-connection HTTP listener
# bash:  the handler script uses bash builtins for parsing
# tini:  proper PID 1 signal handling (already available, but explicit)
RUN apk add --no-cache bash socat tini ca-certificates

WORKDIR /app

COPY fiestaupdater.sh /app/fiestaupdater.sh
COPY handler.sh /app/handler.sh
RUN chmod +x /app/fiestaupdater.sh /app/handler.sh

# Default values; override in compose.
ENV FIESTAUPDATER_PORT=8765 \
    FIESTAUPDATER_COMPOSE_FILE=/compose/docker-compose.yml \
    FIESTAUPDATER_SERVICE=fiestaboard

EXPOSE 8765

LABEL org.opencontainers.image.title="FiestaUpdater" \
      org.opencontainers.image.description="Companion sidecar for in-place updates of FiestaBoard" \
      org.opencontainers.image.url="https://hub.docker.com/r/fiestaboard/fiestaupdater" \
      org.opencontainers.image.source="https://github.com/Fiestaboard/FiestaBoard" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="FiestaBoard"

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- "http://127.0.0.1:${FIESTAUPDATER_PORT}/healthz" >/dev/null || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/app/fiestaupdater.sh"]
