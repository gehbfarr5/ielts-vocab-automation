"""Rebase copied local state after both workers are stopped; never enables a writer."""

import argparse
import fcntl
import json
import sqlite3
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, required=True)
p.add_argument("--from-root", type=Path, required=True)
p.add_argument("--apply", action="store_true")
a = p.parse_args()
root, old = a.root.expanduser().resolve(), a.from_root.expanduser().resolve()
config_path = root / "config.json"
config = json.loads(config_path.read_text())
if config.get("writes_enabled"):
    raise SystemExit("Disable writes before relocation; stop source and target workers first")
with (root / "worker.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = sqlite3.connect(root / "state.sqlite3")
    changes = []
    for sid, image in db.execute("SELECT id,image FROM submissions"):
        if not image:
            continue
        path = Path(image)
        if path.is_absolute():
            if not path.is_relative_to(old / "originals"):
                raise SystemExit("Unrecognized image path; manual review required")
            target = root / path.relative_to(old)
        else:
            target = root / path
        if not target.is_file():
            raise SystemExit("Copied source image is missing")
        changes.append((str(target), sid))
    key = config.get("anki_key_file")
    if key and Path(key).is_absolute():
        if not Path(key).is_relative_to(old):
            raise SystemExit("External credential path requires target-host configuration")
        config["anki_key_file"] = str(Path(key).relative_to(old))
    config["writer_host_id"] = None
    config["writes_enabled"] = False
    config["allow_cloud_text"] = False
    config["allow_cloud_images"] = False
    # The target must explicitly configure its own iCloud path and identity.
    if a.apply:
        backup = root / "pre-relocation.sqlite3"
        if backup.exists():
            raise SystemExit("Relocation backup exists; inspect prior run before retry")
        with sqlite3.connect(backup) as dest:
            db.backup(dest)
        backup.chmod(0o600)
        with db:
            db.executemany("UPDATE submissions SET image=? WHERE id=?", changes)
            db.execute("DELETE FROM settings WHERE key IN ('last_admission_sync','synced_history')")
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        config_path.chmod(0o600)
    print(
        json.dumps(
            {
                "apply": a.apply,
                "image_paths": len(changes),
                "writer_enabled": False,
                "next": "Configure target inbox, verify profile/auth, then perform explicit writer handoff",
            }
        )
    )
    db.close()
