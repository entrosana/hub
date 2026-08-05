#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: backup_db.sh [BACKUP_DIR]

Create a gzip-compressed plain SQL PostgreSQL dump.
DATABASE_URL must be set. BACKUP_DIR defaults to ./backups.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "error: DATABASE_URL must be set" >&2
    exit 1
fi

command -v pg_dump >/dev/null || {
    echo "error: pg_dump is required but was not found on PATH" >&2
    exit 1
}
command -v gzip >/dev/null || {
    echo "error: gzip is required but was not found on PATH" >&2
    exit 1
}

backup_dir="${1:-./backups}"
mkdir -p "$backup_dir"
database_url="${DATABASE_URL/+asyncpg/}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_path="${backup_dir%/}/entrosana-${timestamp}.sql.gz"

pg_dump "$database_url" | gzip >"$dump_path"
echo "$dump_path"
