#!/usr/bin/env bash
# Restore a pg_dump custom-format backup into a target database
# (section 8.4). Defaults to a throwaway database so a restore drill
# never touches the live one by accident -- pass --target to restore
# into a real database explicitly.
#
# Usage: ./scripts/restore.sh <dump_file> [--target DBNAME]
set -euo pipefail

DUMP_FILE="${1:?usage: restore.sh <dump_file> [--target DBNAME]}"
TARGET_DB="audit_sampling_restore_drill"
if [[ "${2:-}" == "--target" ]]; then
  TARGET_DB="${3:?--target requires a database name}"
fi

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-55433}"
PGUSER="${PGUSER:-audit_admin}"
export PGPASSWORD="${PGPASSWORD:-audit_admin_dev_password}"

echo "Restoring $DUMP_FILE -> database '$TARGET_DB' on $PGHOST:$PGPORT"

psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS $TARGET_DB;"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "CREATE DATABASE $TARGET_DB OWNER $PGUSER;"

pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" --no-owner --role="$PGUSER" "$DUMP_FILE"

echo "Restore complete into '$TARGET_DB'."
echo "Verifying row counts against a few key tables..."
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" -c "
  SELECT 'tenants' AS table_name, count(*) FROM tenants
  UNION ALL SELECT 'audit_events', count(*) FROM audit_events
  UNION ALL SELECT 'risk_runs', count(*) FROM risk_runs;
"
