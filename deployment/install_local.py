"""Install a user-session intake/worker service. Does not enable cloud or Anki writes."""

import argparse
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, default=Path.home() / "Library/Application Support/IELTSVocab")
a = p.parse_args()
repo = Path(__file__).resolve().parents[1]
executable = repo / ".venv/bin/ielts-vocab"
if not executable.is_file() or not (a.root / "config.json").is_file():
    raise SystemExit("Run uv sync and ielts-vocab init before installing services")
folder = Path.home() / "Library/LaunchAgents"
folder.mkdir(exist_ok=True)
logs = a.root / "logs"
logs.mkdir(exist_ok=True, mode=0o700)
for suffix, command in [("intake", "serve"), ("worker", "run-once")]:
    label = "local.ielts-vocab." + suffix
    dest = folder / (label + ".plist")
    if dest.exists():
        raise SystemExit(f"{label} already exists; inspect before replacing")
    definition = {
        "Label": label,
        "ProgramArguments": [str(executable), "--root", str(a.root), command],
        "WorkingDirectory": str(repo),
        "RunAtLoad": True,
        "EnvironmentVariables": {
            "PATH": ":".join(
                dict.fromkeys(
                    [
                        str(Path(shutil.which("codex")).parent)
                        if shutil.which("codex")
                        else "/usr/local/bin",
                        str(executable.parent),
                        "/opt/homebrew/bin",
                        "/usr/local/bin",
                        "/usr/bin",
                        "/bin",
                    ]
                )
            )
        },
        "StandardOutPath": str(logs / (suffix + ".out.log")),
        "StandardErrorPath": str(logs / (suffix + ".err.log")),
        "Umask": 63,
    }
    if suffix == "worker":
        definition["StartInterval"] = 60
    else:
        definition["KeepAlive"] = {"SuccessfulExit": False}
    dest.write_bytes(plistlib.dumps(definition))
    dest.chmod(0o600)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(dest)], check=True)
    print("Installed", label)
