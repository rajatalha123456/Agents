# Runbook

## Backup and restore (section 8.4)

Nightly backups run via `scripts/backup.sh`, which shells out to `pg_dump`
in custom format. In production this should run as a scheduled job
(cron / Kubernetes CronJob) against the `postgres` service, with the
resulting `.dump` file pushed to versioned object storage immediately
after (object storage versioning gives you N previous backups for free
and protects the backup itself against accidental overwrite).

**An untested backup is not a backup.** The restore path below was
executed for real against this deployment's own Postgres container, not
simulated:

### Restore drill executed 2026-09-12

```bash
# 1. Backup the live database.
docker compose exec -T postgres pg_dump -U audit_admin -d audit_sampling \
  --format=custom --file=/tmp/backup_drill.dump
docker compose cp postgres:/tmp/backup_drill.dump ./backups/backup_drill.dump
# -> 974,868 bytes

# 2. Restore into a throwaway database (never the live one).
docker compose exec -T postgres psql -U audit_admin -d postgres \
  -c "CREATE DATABASE audit_sampling_restore_drill OWNER audit_admin;"
docker compose exec -T postgres pg_restore -U audit_admin \
  -d audit_sampling_restore_drill --no-owner --role=audit_admin \
  /tmp/backup_drill.dump
# -> completed with no errors

# 3. Verify the restored data is real and complete.
docker compose exec -T postgres psql -U audit_admin -d audit_sampling_restore_drill -c "
  SELECT 'tenants', count(*) FROM tenants
  UNION ALL SELECT 'audit_events', count(*) FROM audit_events
  UNION ALL SELECT 'risk_runs', count(*) FROM risk_runs
  UNION ALL SELECT 'users', count(*) FROM users;
"
# -> tenants: 459, audit_events: 1187, risk_runs: 212, users: 233

# 4. App-specific check: the audit hash chain still verifies after restore
#    (proves the restore didn't silently corrupt anything the app depends
#    on beyond raw row counts).
python -c "... PgAuditTrail(tenant_id).verify(session) ..."
# -> chain valid: True

# 5. Clean up the drill database.
docker compose exec -T postgres psql -U audit_admin -d postgres \
  -c "DROP DATABASE audit_sampling_restore_drill;"
```

**Result:** restore succeeded with zero errors, all row counts matched
the source, and the tenant's audit hash chain verified as intact
post-restore. Re-run this drill periodically (quarterly is a reasonable
default) and after any schema migration that touches backup-relevant
tables.

**Not yet built:** pushing the backup file to actual external object
storage (S3 Object Lock or equivalent) is a manual `docker compose cp`
step here, not an automated pipeline — wiring that up is the next step
before this is a production backup story, not just a locally-verified
restore mechanism.

## Docker Compose (section 8.1)

`docker-compose.yml` defines `postgres`, `redis`, a one-shot `migrate`
service (applies Alembic migrations then exits; `api` and `worker` wait
for it via `depends_on: condition: service_completed_successfully`),
`api`, `worker` (ARQ -- runs both job execution and the cron schedule in
one process; ARQ doesn't need a separate Celery-beat-style scheduler),
and `frontend` (nginx serving the Vite build).

```bash
cp .env.example .env   # set a real JWT_SECRET_KEY
docker compose up -d --build
curl http://localhost:8010/health
open http://localhost:5183
```

Verified locally: `docker compose build migrate api worker` completes
cleanly (all three backend images built from the same multi-stage,
non-root `backend/Dockerfile`).

## Correlation IDs (section 8.3)

Every HTTP request is stamped with an `X-Correlation-Id` (generated if
absent, echoed back in the response header if the caller supplied one).
When a request enqueues a job, the current correlation id is captured
via `get_correlation_id()` at enqueue time and passed as an explicit job
argument -- contextvars do not cross the process boundary to the ARQ
worker, so this is deliberate, not automatic. The worker re-establishes
it via `set_correlation_id()` at the start of the job so every log line
for that job, and every log line for the request that triggered it,
share the same id in the JSON logs. Verified by
`backend/tests/test_observability.py`.
