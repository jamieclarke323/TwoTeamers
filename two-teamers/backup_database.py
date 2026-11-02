"""Private SQLite snapshots and non-destructive recovery verification."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

PROJECT = Path(__file__).resolve().parent
REPOSITORY = PROJECT.parent


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def source_id(database: Path) -> str:
    return hashlib.sha256(str(database.resolve()).encode()).hexdigest()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _private_directory(path: Path) -> None:
    if path.resolve().is_relative_to(REPOSITORY):
        raise ValueError("Backups must be outside the repository and all public/static mappings.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_mode & 0o077:
        raise ValueError("Backup directory must have owner-only permissions (chmod 700).")


def _copy_database(source: Path, destination: Path) -> None:
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(_connect_readonly(source)) as source_db, closing(sqlite3.connect(destination)) as target:
            source_db.backup(target)
            if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("SQLite integrity check failed.")
    except Exception:
        destination.unlink()
        raise


def verify_backup(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if set(manifest["files"]) not in (
        {"database.sqlite"},
        {"database.sqlite", "vapid-private.pem"},
    ):
        raise ValueError("Unexpected backup file list.")
    for name, digest in manifest["files"].items():
        if _digest(directory / name) != digest:
            raise ValueError(f"Backup checksum failed for {name}.")
    with closing(_connect_readonly(directory / "database.sqlite")) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Backup database integrity check failed.")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Backup database foreign-key check failed.")
    return manifest


def create_backup(database: Path, destination: Path, private_key: Path | None = None) -> Path:
    if not database.is_file():
        raise ValueError("Source database does not exist.")
    _private_directory(destination)
    temporary = Path(tempfile.mkdtemp(prefix=".backup-", dir=destination))
    try:
        _copy_database(database, temporary / "database.sqlite")
        files = {"database.sqlite": _digest(temporary / "database.sqlite")}
        if private_key is not None:
            if not private_key.is_file():
                raise ValueError("Configured VAPID private key file does not exist.")
            key_target = temporary / "vapid-private.pem"
            descriptor = os.open(key_target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(private_key.read_bytes())
            files[key_target.name] = _digest(key_target)
        manifest = {"created_at": time.time(), "source_id": source_id(database), "files": files}
        manifest_path = temporary / "manifest.json"
        descriptor = os.open(manifest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as target:
            json.dump(manifest, target)
        verify_backup(temporary)
        completed = destination / f"backup-{time.time_ns()}"
        temporary.rename(completed)
        return completed
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def restore_copy(directory: Path, target: Path) -> None:
    verify_backup(directory)
    if target.resolve().is_relative_to(REPOSITORY):
        raise ValueError("Recovery copies must be outside the repository and public/static mappings.")
    _copy_database(directory / "database.sqlite", target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get(
        "DATABASE_PATH", str(PROJECT / "instance" / "two-teamers.sqlite")
    )))
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--if-due", action="store_true", help="Skip if a verified backup is less than seven days old.")
    parser.add_argument("--private-key", type=Path, default=os.environ.get("PUSH_VAPID_PRIVATE_KEY_FILE") or None)
    parser.add_argument("--verify", type=Path, help="Verify an existing backup directory without restoring.")
    parser.add_argument("--restore-from", type=Path)
    parser.add_argument("--restore-to", type=Path, help="Create a recovery copy; refuses to overwrite an existing file.")
    args = parser.parse_args()
    try:
        if args.verify:
            verify_backup(args.verify)
            print("Backup checksums, SQLite integrity and foreign keys verified.")
            return
        if args.restore_from:
            if not args.restore_to:
                parser.error("--restore-from requires --restore-to.")
            restore_copy(args.restore_from, args.restore_to)
            print("Recovery copy created; existing files were not overwritten.")
            return
        if not args.destination:
            parser.error("--destination is required for backups.")
        _private_directory(args.destination)
        if args.if_due:
            for candidate in sorted(args.destination.glob("backup-*"), reverse=True):
                manifest = verify_backup(candidate)
                age = time.time() - manifest["created_at"]
                if manifest["source_id"] == source_id(args.database) and 0 <= age < 7 * 86400:
                    print("Verified backup is less than seven days old; no new snapshot needed.")
                    return
        key = args.private_key or args.database.parent / "vapid-private.pem"
        if args.private_key is None and not key.exists():
            key = None
            print("No default VAPID key found; back up any externally managed key separately.")
        completed = create_backup(args.database, args.destination, key)
        print(f"Verified private backup created: {completed}")
    except (OSError, ValueError, sqlite3.Error, KeyError) as error:
        parser.exit(1, f"Backup operation failed: {error}\n")


if __name__ == "__main__":
    main()
