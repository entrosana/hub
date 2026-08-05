# Disaster recovery runbook

This runbook covers the repository's PostgreSQL dump and restore scripts. It
does not define production backup scheduling, retention, or failover policy.

## Create a backup

Set `DATABASE_URL` to the PostgreSQL connection URL and run:

```bash
DATABASE_URL='postgresql+asyncpg://user:password@host/db' \
  ./scripts/backup_db.sh ./backups
```

The script creates a timestamped `entrosana-*.sql.gz` plain-SQL dump. PostgreSQL
credentials should be supplied through the URL or the normal PostgreSQL client
environment; do not commit them.

## Restore a backup

1. Confirm the target database and dump file.
2. Ensure `DATABASE_URL` points to the intended target.
3. Run the restore interactively:

   ```bash
   DATABASE_URL='postgresql+asyncpg://user:password@host/db' \
     ./scripts/restore_db.sh ./backups/entrosana-YYYYMMDDTHHMMSSZ.sql.gz
   ```

4. Type `RESTORE` at the confirmation prompt. For an automated, explicitly
   authorized operation, pass `--yes`.
5. Run migrations and verify the application health probes.

## Recovery checklist

- [ ] Declare the incident and identify the recovery owner.
- [ ] Select and verify the backup timestamp.
- [ ] Confirm the target database and access credentials.
- [ ] Restore with the confirmation guard.
- [ ] Apply pending migrations.
- [ ] Check `/health/live`, `/health/ready`, and `/health/startup`.
- [ ] Verify critical application reads and writes.
- [ ] Record the restore timestamp and validation results.

> **TODO — requires infra decision:** automated backup schedule, retention, and
> off-host backup storage.

> **TODO — requires infra decision:** point-in-time recovery and WAL archival.

> **TODO — requires infra decision:** multi-region replication and failover.
