"""Migration smoke test — a fresh DB must come up via Alembic, not just
`Base.metadata.create_all` (audit M7: production had zero migrations).

Runs `alembic upgrade head` against a throwaway SQLite file in a subprocess
(clean env, no app import side effects) and asserts the core tables exist.
"""

import os
import pathlib
import sqlite3
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_initial_migration_applies_and_creates_schema(tmp_path):
    db = tmp_path / "migrated.db"
    env = {
        **os.environ,
        "SECRET_KEY": "x" * 40,
        "DLM_AUDIT_HMAC_KEY": "y" * 40,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db}",
        "ENVIRONMENT": "development",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()

    required = {"alembic_version", "identity_users", "audit_events", "audit_chain_head"}
    assert required <= tables, f"missing tables: {required - tables}"
