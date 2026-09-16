from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import uuid
import warnings
from pathlib import Path

from PIL import Image, ImageOps

from .palette import CURRENT_SCHEME
from .store import Store

MAX_BYTES = 20 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def validate_image(data: bytes):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Image empty or larger than 20 MiB")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError("Only PNG/JPEG/WebP supported; export HEIC as PNG")
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            return ImageOps.exif_transpose(im).convert("RGB")


def receive(store: Store, root: Path, data: bytes, submission_id: str | None = None):
    im = validate_image(data)
    sid = submission_id or str(uuid.uuid4())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", sid):
        raise ValueError("Invalid submission ID")
    sha = hashlib.sha256(data).hexdigest()
    folder = root / "originals"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with store.transaction():
        alias = store.db.execute("SELECT * FROM receipts WHERE id=?", (sid,)).fetchone()
        if alias:
            if alias["sha"] != sha:
                raise ValueError("Submission ID reused with different content")
            old = store.db.execute(
                "SELECT * FROM submissions WHERE id=?", (alias["submission"],)
            ).fetchone()
            return {"submission_id": old["id"], "state": old["state"], "duplicate": True}
        old = store.db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if old and old["sha"] != sha:
            raise ValueError("Submission ID reused with different content")
        if old:
            return {"submission_id": sid, "state": old["state"], "duplicate": True}
        same = store.db.execute("SELECT * FROM submissions WHERE sha=?", (sha,)).fetchone()
        if same:
            store.db.execute("INSERT INTO receipts VALUES(?,?,?)", (sid, sha, same["id"]))
            return {"submission_id": same["id"], "state": same["state"], "duplicate": True}
        if store.db.execute("SELECT count(*) FROM submissions").fetchone()[0] >= 5000:
            raise ValueError("Local intake capacity reached; archive through retention review")
        if (
            sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
            + len(data)
            + im.width * im.height * 3
            > 1024**3
        ):
            raise ValueError("Local screenshot storage capacity (1 GiB) reached")
        original = folder / (sha + ".original")
        with original.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        original.chmod(0o600)
        image = folder / (sha + ".png")
        with image.open("wb") as f:
            im.save(f, format="PNG")
            f.flush()
            os.fsync(f.fileno())
        image.chmod(0o600)
        store.db.execute(
            "INSERT INTO submissions(id,sha,image,created,mark_scheme) VALUES(?,?,?,?,?)",
            (sid, sha, str(image), time.time(), CURRENT_SCHEME),
        )
        store.db.execute("INSERT INTO receipts VALUES(?,?,?)", (sid, sha, sid))
        store.event("received", sid, {"sha256": sha, "mark_scheme": CURRENT_SCHEME})
    return {"submission_id": sid, "state": "received", "duplicate": False}


def scan(store: Store, root: Path, inbox: Path):
    results = []
    inbox.mkdir(parents=True, exist_ok=True)
    # Check regular, stable files only; never traverse aliases or arbitrary symlinks.
    for p in sorted(inbox.iterdir()):
        if (
            p.is_symlink()
            or not p.is_file()
            or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp")
        ):
            continue
        stat = p.stat()
        if time.time() - stat.st_mtime < 3:
            continue
        try:
            data = p.read_bytes()
            if p.stat().st_size != stat.st_size or p.stat().st_mtime_ns != stat.st_mtime_ns:
                continue
            results.append(receive(store, root, data))
        except (OSError, ValueError, Image.UnidentifiedImageError) as e:
            store.event("intake_error", p.name, {"type": type(e).__name__})
            results.append({"file": p.name, "state": "error", "reason": str(e)})
    # Manifest submission packages are committed only after all files validate.
    for folder in sorted(inbox.iterdir()):
        if folder.is_symlink() or not folder.is_dir() or not (folder / "ready.json").is_file():
            continue
        try:
            manifest_path = folder / "manifest.json"
            if manifest_path.is_symlink() or manifest_path.stat().st_size > 100_000:
                raise ValueError("Unsafe manifest")
            m = json.loads(manifest_path.read_text())
            files = m["images"]
            if not 1 <= len(files) <= 10:
                raise ValueError("Package must contain 1..10 images")
            contents = []
            for f in files:
                name = f["file"]
                p = folder / name
                if Path(name).name != name or p.is_symlink() or not p.is_file():
                    raise ValueError("Invalid package path or not yet downloaded")
                data = p.read_bytes()
                if hashlib.sha256(data).hexdigest() != f["sha256"]:
                    raise ValueError("Package checksum mismatch or partial download")
                validate_image(data)
                contents.append(data)
            for i, data in enumerate(contents):
                results.append(receive(store, root, data, f"{m['submission_id']}_{i}"))
        except (OSError, ValueError, KeyError, TypeError) as e:
            results.append({"file": folder.name, "state": "waiting_or_invalid", "reason": str(e)})
    return results
