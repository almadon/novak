#!/usr/bin/env python3
"""Make one consistent copy of everything Novak keeps, in a single directory a backup tool can pick up.

`novak backup` calls this. It exists because the databases cannot be copied as plain files while the stack
runs: Hindsight is an embedded Postgres, and Open WebUI, ingest and the gateway keep SQLite files that may
have changes still in a journal. So this takes a proper copy of each (SQLite's online backup, a Postgres
dump) and copies the plain files next to them (settings, secrets, the registry, uploads). A separate tool
(restic, Arkeep and so on) then backs up that one directory. See decision #80.

It builds the copy in a temporary directory beside the destination and renames it into place at the end, so a
run that stops halfway is never what gets backed up and the previous copy is still there. It keeps only the
latest copy; the backup tool keeps the history. The directory is mode 700 and secrets.env keeps its mode 600.
It prints names and sizes, never a value, and exits non-zero if anything failed.

  backup.py [--dest DIR]        default $NOVAK_HOME/backup/staging
"""
import argparse
import datetime
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT = "novak"
GATEWAY_VOLUME = "novak_gateway-data"
# Plain files at the top of NOVAK_HOME that matter and are small.
TOP_FILES = [".env", "secrets.env", "router-config.yaml", "gateway.env", "autostart", "name", "project_name"]
# What is left out of data/ directories: the databases (taken separately), SQLite sidecars and caches.
SKIP_SUFFIXES = (".db-wal", ".db-shm", ".db-journal")


class BackupError(Exception):
    pass


def _ignore_backups(_dir, names):
    return [n for n in names if ".bak-" in n or n.endswith(".bak")]


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def sqlite_copy(src: Path, dst: Path) -> None:
    """A consistent copy of a live SQLite database (its own online backup, journal included)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
            if target.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise BackupError(f"{src.name}: could not turn the copy into a plain file")
        finally:
            target.close()
    finally:
        source.close()
    check = sqlite3.connect(dst)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError(f"{src.name}: the copy failed its integrity check")
    finally:
        check.close()
    for side in ("-wal", "-shm"):                       # empty leftovers; the data is all in the main file
        leftover = Path(str(dst) + side)
        if leftover.exists() and leftover.stat().st_size == 0 or side == "-shm":
            leftover.unlink(missing_ok=True)


def copy_tree(src: Path, dst: Path, skip_dbs=()) -> None:
    """Copy a directory without the named databases, their sidecar files and any dated backups."""
    def ignore(d, names):
        out = set(_ignore_backups(d, names))
        for n in names:
            if n in skip_dbs or n.endswith(SKIP_SUFFIXES):
                out.add(n)
        return out
    shutil.copytree(src, dst, ignore=ignore, symlinks=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, check=False)


def stream(cmd, dst: Path):
    """Run a command and write its output to a file. Returns (exit code, error text)."""
    with open(dst, "wb") as fh:
        r = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, check=False)
    return r.returncode, r.stderr.decode(errors="replace")


def container_id(service: str, runner=run) -> str:
    """The running container for a compose service, found by label so a renamed container still counts."""
    r = runner(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}",
                "--filter", f"label=com.docker.compose.service={service}"])
    ids = r.stdout.decode().split()
    if r.returncode or not ids:
        raise BackupError(f"no running {service} container")
    return ids[0]


def postgres_dump(dst: Path, runner=run, streamer=stream) -> None:
    """Dump Hindsight's embedded Postgres. The password stays inside the container: the shell there reads it
    from pg0's own instance file and passes it by environment, so it is never on a command line."""
    cid = container_id("hindsight", runner)
    script = (
        "set -e; I=/home/hindsight/.pg0/instances/hindsight/instance.json; "
        "B=$(ls -d /home/hindsight/.pg0/installation/*/bin | head -1); "
        "eval \"$(python3 - \"$I\" <<'EOF'\n"
        "import json, shlex, sys\n"
        "d = json.load(open(sys.argv[1]))\n"
        "print('PGPASSWORD=%s PGUSER=%s PGDATABASE=%s PGPORT=%s' % tuple(shlex.quote(str(d[k])) for k in "
        "('password', 'username', 'database', 'port')))\n"
        "EOF\n)\"; export PGPASSWORD PGUSER PGDATABASE PGPORT; "
        "\"$B/pg_dump\" -h 127.0.0.1 -Fc"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    code, err = streamer(["docker", "exec", cid, "sh", "-c", script], dst)
    if code:
        raise BackupError("the Postgres dump failed: " + err[:200].replace("\n", " "))
    if dst.stat().st_size < 1024:
        raise BackupError("the Postgres dump is empty")


def volume_path(name: str, runner=run) -> Path:
    r = runner(["docker", "volume", "inspect", "--format", "{{.Mountpoint}}", name])
    p = r.stdout.decode().strip()
    if r.returncode or not p:
        raise BackupError(f"no Docker volume {name}")
    return Path(p)


def build(home: Path, tmp: Path, runner=run, streamer=stream, out=print) -> dict:
    """Fill `tmp` with the copy. Returns the manifest items (name -> bytes)."""
    items = {}

    def record(name, path):
        items[name] = _size(path)
        out(f"  {name:28} {human(items[name])}")

    top = tmp / "files"
    top.mkdir()
    for f in TOP_FILES:
        src = home / f
        if src.is_file():
            shutil.copy2(src, top / f)
            record(f"files/{f}", top / f)
    if (home / "secrets.env").is_file():
        os.chmod(top / "secrets.env", 0o600)

    if (home / "registry").is_dir():
        shutil.copytree(home / "registry", tmp / "registry", ignore=_ignore_backups, symlinks=True)
        record("registry/", tmp / "registry")
    else:
        raise BackupError("no registry directory: is NOVAK_HOME right?")

    for name, db in (("open-webui", "webui.db"), ("ingest", "ingest.db")):
        src = home / "data" / name
        if not src.is_dir():
            continue
        copy_tree(src, tmp / "data" / name, skip_dbs=(db,))
        if (src / db).is_file():
            sqlite_copy(src / db, tmp / "data" / name / db)
        record(f"data/{name}/", tmp / "data" / name)

    vol = volume_path(GATEWAY_VOLUME, runner)
    gw = tmp / "gateway-data"
    gw.mkdir()
    for db in sorted(vol.glob("*.db")):
        sqlite_copy(db, gw / db.name)
    record("gateway-data/", gw)

    postgres_dump(tmp / "hindsight.dump", runner, streamer)
    record("hindsight.dump", tmp / "hindsight.dump")
    return items


def main(argv=None, env=os.environ, runner=run, streamer=stream, out=print) -> int:
    ap = argparse.ArgumentParser(description="One consistent copy of Novak's data, for a backup tool to pick up")
    ap.add_argument("--dest", help="where the copy goes (default: $NOVAK_HOME/backup/staging)")
    args = ap.parse_args(argv)
    home = Path(env.get("NOVAK_HOME") or Path.home() / ".novak")
    dest = Path(args.dest) if args.dest else home / "backup" / "staging"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tmp = dest.parent / f"{dest.name}.tmp-{stamp}"
    old = dest.parent / f"{dest.name}.old-{stamp}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    for leftover in dest.parent.glob(f"{dest.name}.tmp-*"):          # an earlier run that did not finish
        shutil.rmtree(leftover, ignore_errors=True)
    os.umask(0o077)
    tmp.mkdir(mode=0o700)
    started = datetime.datetime.now(datetime.timezone.utc)
    try:
        out(f"Backing up {home} into {dest}")
        items = build(home, tmp, runner, streamer, out)
        manifest = {"made": started.isoformat(timespec="seconds"), "home": str(home),
                    "items": items, "total_bytes": sum(items.values())}
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        os.chmod(tmp, 0o700)
        if dest.exists():
            dest.rename(old)
        tmp.rename(dest)
        shutil.rmtree(old, ignore_errors=True)
    except (BackupError, OSError, sqlite3.Error) as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        if old.exists() and not dest.exists():                       # put the previous copy back
            old.rename(dest)
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    out(f"Done: {human(manifest['total_bytes'])} in {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
