#!/bin/sh
# Dev startup: supervisord manages API (with --reload), Next.js, and nginx
exec supervisord -c /app/supervisord-dev.conf
