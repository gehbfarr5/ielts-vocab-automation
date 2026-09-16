"""Deploy the approved learning layout with a private backup; does not create cards."""

import argparse
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

from ielts_vocab.anki import FIELDS, MODEL, TEMPLATES
from ielts_vocab.card_layout import CSS
from ielts_vocab.cli import anki_client
from ielts_vocab.runtime import read_config, require_writer

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, required=True)
a = p.parse_args()
root = a.root.expanduser().resolve()
config = read_config(root)
require_writer(config)
with (root / "worker.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    anki = anki_client(config)
    anki.guard()
    if anki.call("modelFieldNames", modelName=MODEL) != FIELDS:
        raise SystemExit("Unexpected model fields; deployment stopped before modification")
    before = {
        "model": MODEL,
        "templates": anki.call("modelTemplates", modelName=MODEL),
        "styling": anki.call("modelStyling", modelName=MODEL),
    }
    expected = {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in TEMPLATES}
    if set(before["templates"]) != set(expected):
        raise SystemExit("Unexpected template slots; deployment stopped before modification")
    folder = (
        root
        / "acceptance"
        / ("learning-layout-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    folder.mkdir(mode=0o700)
    path = folder / "before.json"
    path.write_text(json.dumps(before, ensure_ascii=False, indent=2))
    path.chmod(0o600)
    anki.call("updateModelTemplates", model={"name": MODEL, "templates": expected})
    anki.call("updateModelStyling", model={"name": MODEL, "css": CSS})
    # Reopen serialized config to preserve portable relative paths.
    raw = json.loads((root / "config.json").read_text())
    raw["semantic_enrichment_enabled"] = True
    tmp = root / "config.json.tmp"
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    tmp.chmod(0o600)
    tmp.replace(root / "config.json")
    receipt = folder / "deployment.json"
    receipt.write_text(
        json.dumps(
            {
                "layout_applied": True,
                "enrichment_enabled": True,
                "tests_run": False,
                "cards_created": 0,
                "mobile_acceptance": "pending_real_courses",
            },
            indent=2,
        )
    )
    receipt.chmod(0o600)
    print("Learning layout and config deployed. No cards created. Private backup:", folder)
