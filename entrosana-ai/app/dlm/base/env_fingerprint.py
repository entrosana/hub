"""Capture the runtime environment for the audit trail.

The DLM itself produces deterministic outputs without external state, but the
code that wires it together can drift. This module records what the Python
process and the source tree looked like at decision time, so audits can pin
a Decision to a specific code revision.

Usage:
    python -m app.dlm.base.env_fingerprint dlm/core.py dlm/cashctrl.py
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .core import fingerprint


@dataclass(frozen=True, slots=True)
class RuntimeFingerprint:
    python_version: str
    platform: str
    git_sha: str | None
    git_dirty: bool
    code_paths_sha256: tuple[tuple[str, str], ...]

    @property
    def fp(self) -> str:
        return fingerprint(asdict(self))

    @classmethod
    def capture(cls, code_files: list[Path]) -> RuntimeFingerprint:
        return cls(
            python_version=sys.version,
            platform=platform.platform(),
            git_sha=_git_sha(),
            git_dirty=_git_dirty(),
            code_paths_sha256=tuple(sorted((str(p), _file_sha256(p)) for p in code_files)),
        )


def _git_sha() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
        )
        return bool(out.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("usage: python -m app.dlm.base.env_fingerprint <file>...", file=sys.stderr)
        sys.exit(2)
    rf = RuntimeFingerprint.capture(paths)
    print(f"python:    {rf.python_version.split()[0]}")
    print(f"platform:  {rf.platform}")
    print(f"git_sha:   {rf.git_sha}")
    print(f"git_dirty: {rf.git_dirty}")
    print("files:")
    for p, sha in rf.code_paths_sha256:
        print(f"  {sha[:16]}  {p}")
    print(f"\nfingerprint: {rf.fp}")
