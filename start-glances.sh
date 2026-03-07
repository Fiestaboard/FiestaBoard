#!/bin/sh
# Start Glances web server only when DEBUG_MODE is enabled.
# Called by supervisord — exits immediately if debug mode is off.

DEBUG_MODE=$(echo "${DEBUG_MODE:-false}" | tr '[:upper:]' '[:lower:]')

case "$DEBUG_MODE" in
    true|1|yes) ;;
    *)
        echo "DEBUG_MODE not enabled, Glances will not start."
        exit 0
        ;;
esac

echo "Starting Glances web server on port 61208..."
exec glances -w -C /app/glances.conf --bind 127.0.0.1 --port 61208
