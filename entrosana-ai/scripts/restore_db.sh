#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: restore_db.sh [--yes] DUMP_FILE

Restore a gzip-compressed plain SQL PostgreSQL dump.
DATABASE_URL must be set. Without --yes, type RESTORE to confirm.
EOF
}

assume_yes=false
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
elif [[ "${1:-}" == "--yes" ]]; then
    assume_yes=true
    shift
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "error: DATABASE_URL must be set" >&2
    exit 1
fi
if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi

dump_path="$1"
if [[ ! -f "$dump_path" ]]; then
    echo "error: dump file not found: $dump_path" >&2
    exit 1
fi

command -v psql >/dev/null || {
    echo "error: psql is required but was not found on PATH" >&2
    exit 1
}
command -v gunzip >/dev/null || {
    echo "error: gunzip is required but was not found on PATH" >&2
    exit 1
}

if [[ "$assume_yes" != true ]]; then
    read -r -p "This will overwrite database contents. Type RESTORE to continue: " confirmation
    if [[ "$confirmation" != "RESTORE" ]]; then
        echo "restore cancelled" >&2
        exit 1
    fi
fi

database_url="${DATABASE_URL/+asyncpg/}"
gunzip -c "$dump_path" | psql "$database_url"
