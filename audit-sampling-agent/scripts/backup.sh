#!/usr/bin/env bash
# Nightly Postgres backup (section 8.4). Run via a scheduled task
# (cron, a Kubernetes CronJob, etc.) against the postgres service.
#
# Usage: ./scripts/backup.sh [output_dir]
set -euo pipefail

OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$OUT_DIR/audit_sampling_${TIMESTAMP}.dump"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-55433}"
PGUSER="${PGUSER:-audit_admin}"
PGDATABASE="${PGDATABASE:-audit_sampling}"
export PGPASSWORD="${PGPASSWORD:-audit_admin_dev_password}"

echo "Backing up $PGDATABASE@$PGHOST:$PGPORT -> $OUT_FILE"
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" --format=custom --file="$OUT_FILE"

echo "Backup complete: $(du -h "$OUT_FILE" | cut -f1)"
echo "$OUT_FILE"
