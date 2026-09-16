"""Host-local configuration resolution; copied data never grants another host write access."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
from pathlib import Path


def host_id() -> str:
    result = subprocess.run(
        ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice", "-a"],
        capture_output=True,
        check=True,
        timeout=10,
    )
    value = plistlib.loads(result.stdout)[0]["IOPlatformUUID"]
    if not isinstance(value, str) or not value:
        raise ValueError("Machine identity unavailable")
    return value


def require_writer(config):
    if config.get("writer_host_id") != host_id():
        raise ValueError("Writer host differs; complete explicit host handoff before writing")


def read_config(root: Path):
    config = json.loads((root / "config.json").read_text())
    for key in ("inbox", "anki_key_file", "ipa_cache"):
        if config.get(key):
            path = Path(os.path.expandvars(config[key])).expanduser()
            config[key] = str(path if path.is_absolute() else root / path)
    return config
