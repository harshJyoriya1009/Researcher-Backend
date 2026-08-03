#!/bin/sh
set -e

UPLOAD_DIR="${UPLOAD_DIR:-/app/data/uploads}"
LOG_DIR="${LOG_DIR:-/app/logs}"

mkdir -p "$UPLOAD_DIR" "$LOG_DIR"
chown -R app:app "$UPLOAD_DIR" "$LOG_DIR"

exec su app -s /bin/sh -c "$*"
