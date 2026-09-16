from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .analysis import codex_analyze, evidence_pack, save_analysis
from .anki import Anki, enrich, execute, make_plan, reconcile_reviews
from .ingest import receive, scan
from .models import Analysis, DayState, digest, study_day
from .recognition import color_evidence, ocr, word_evidence
from .service import serve, token_from_file
from .store import Store

DEFAULT_ROOT = Path.home() / "Library/Application Support/IELTSVocab"


def read_config(root):
    return json.loads((root / "config.json").read_text())


def anki_client(config):
    key_path = config.get("anki_key_file")
    return Anki(config["anki_profile"], token_from_file(key_path) if key_path else None)


def process(store, root, config):
    pending = store.db.execute(
        "SELECT count(DISTINCT core_key) FROM candidates WHERE state='pending'"
    ).fetchone()[0]
    if store.mining_paused(pending):
        return {"state": "backpressure", "pending_cores": pending}
    rows = store.db.execute(
        "SELECT * FROM submissions WHERE state='received' ORDER BY created LIMIT 3"
    ).fetchall()
    results = []
    for row in rows:
        sid = row["id"]
        try:
            lines = color_evidence(
                Path(row["image"]),
                ocr(Path(row["image"]), root / "bin/vision-ocr"),
                scheme=row["mark_scheme"],
            )
            lines = word_evidence(Path(row["image"]), lines, scheme=row["mark_scheme"])
            work = root / "analysis" / sid
            work.mkdir(parents=True, exist_ok=True, mode=0o700)
            evidence = evidence_pack(row, lines, store)
            (work / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            if not config.get("allow_cloud_images"):
                store.db.execute(
                    "UPDATE submissions SET state='awaiting_analyzer' WHERE id=?", (sid,)
                )
                results.append({"submission": sid, "state": "local_ocr_complete"})
                continue
            calls = store.db.execute(
                "SELECT count(*) FROM events WHERE kind='analyzer_call' AND at>?",
                (time.time() - 86400,),
            ).fetchone()[0]
            if calls >= config.get("max_analyzer_calls_per_24h", 10):
                raise ValueError("Analyzer rolling 24h call budget exhausted")
            store.event("analyzer_call", sid, {"provider": "codex", "cloud_image": True})
            analyzed = codex_analyze(Path(row["image"]), evidence, work, allow_cloud=True)
            save_analysis(store, sid, analyzed, evidence, calibrated=config["calibration_verified"])
            results.append({"submission": sid, "state": "analyzed"})
        except Exception as e:
            store.db.execute(
                "UPDATE submissions SET state='error',error=?,attempts=attempts+1 WHERE id=?",
                (str(e), sid),
            )
            store.event("processing_error", sid, {"type": type(e).__name__})
            results.append({"submission": sid, "state": "error", "reason": str(e)})
    return results


def write_pending(store, config):
    if not config["writes_enabled"] or not config["legacy_inventory_reviewed"]:
        raise ValueError("Writes disabled until target inventory and acceptance are verified")
    a = anki_client(config)
    a.guard()
    a.setup(config["anki_deck"])
    reconcile_reviews(store, a, config["timezone"], config["rollover_hour"])
    day = study_day(datetime.now(timezone.utc), config["timezone"], config["rollover_hour"])
    # Existing uncertain operations must be reconciled before any new admission.
    unresolved = store.db.execute(
        "SELECT id FROM operations WHERE state IN ('reserved','writing','write_uncertain')"
    ).fetchall()
    for op in unresolved:
        execute(store, a, op["id"], current_day=day)
    rows = store.db.execute(
        "SELECT * FROM candidates WHERE state='pending' ORDER BY priority DESC,created LIMIT 5"
    ).fetchall()
    for row in rows:
        plan = make_plan(store, a, row, config["anki_deck"])
        if plan["kind"] == "enrich":
            enrich(store, a, row, plan)
            continue
        op_id = digest([row["id"], plan["slot"]])[:32]
        store.reserve(
            op_id,
            row["id"],
            row["core_key"],
            digest([row["lemma_key"], plan["slot"]]),
            plan["kind"] == "context",
            day,
            plan,
        )
        execute(store, a, op_id, current_day=day)
    a.call("sync")
    store.db.execute("UPDATE operations SET state='sync_requested' WHERE state='written'")
    store.event("sync_requested", day, {"mobile_verified": False})
    return store.status()


def main():
    parser = argparse.ArgumentParser(description="Local highlighted reading → bounded Anki")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("build-ocr")
    x = sub.add_parser("ingest")
    x.add_argument("image", type=Path)
    x = sub.add_parser("scan")
    x.add_argument("inbox", type=Path)
    x = sub.add_parser("serve")
    x.add_argument("--port", type=int, default=8766)
    sub.add_parser("process")
    sub.add_parser("run-once")
    sub.add_parser("write-pending")
    x = sub.add_parser("day")
    x.add_argument("file", type=Path)
    x = sub.add_parser("retry")
    x.add_argument("submission_id")
    x = sub.add_parser("import-analysis")
    x.add_argument("submission_id")
    x.add_argument("file", type=Path)
    x = sub.add_parser("history")
    x.add_argument("--query", default="")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    store = Store(root / "state.sqlite3")
    try:
        if args.command == "init":
            p = root / "config.json"
            if p.exists():
                raise ValueError("Already initialized; configuration not overwritten")
            config = {
                "anki_profile": "User 1",
                "anki_deck": "IELTS::Vocabulary",
                "timezone": "Asia/Shanghai",
                "rollover_hour": 4,
                "allow_cloud_images": False,
                "calibration_verified": False,
                "writes_enabled": False,
                "legacy_inventory_reviewed": False,
                "inbox": str(root / "inbox"),
                "anki_key_file": None,
            }
            p.write_text(json.dumps(config, ensure_ascii=False, indent=2))
            p.chmod(0o600)
            token = root / "intake.token"
            token.write_text(secrets.token_urlsafe(32))
            token.chmod(0o600)
            result = {"state": "initialized", "root": str(root), "mode": "shadow"}
        elif args.command == "status":
            result = store.status()
        elif args.command == "ingest":
            result = receive(store, root, args.image.read_bytes())
        elif args.command == "scan":
            result = scan(store, root, args.inbox)
        elif args.command == "serve":
            serve(root, token_from_file(root / "intake.token"), port=args.port)
            return
        elif args.command == "day":
            store.set_day(DayState.model_validate_json(args.file.read_text()))
            result = {"state": "day_policy_recorded"}
        elif args.command == "retry":
            with store.transaction():
                row = store.db.execute(
                    "SELECT state,attempts FROM submissions WHERE id=?", (args.submission_id,)
                ).fetchone()
                if not row or row["state"] not in ("error", "awaiting_analyzer"):
                    raise ValueError("Only failed/awaiting submissions can be retried")
                if row["attempts"] >= 3:
                    raise ValueError("Retry limit reached; inspect and fix the failure first")
                store.db.execute(
                    "UPDATE submissions SET state='received',error=NULL WHERE id=?",
                    (args.submission_id,),
                )
            result = {"state": "retry_queued"}
        elif args.command == "build-ocr":
            binary = root / "bin/vision-ocr"
            binary.parent.mkdir(exist_ok=True)
            source = Path(__file__).resolve().parent / "native/vision_ocr.swift"
            subprocess.run(["swiftc", str(source), "-o", str(binary)], check=True, timeout=120)
            result = {"state": "ocr_built"}
        else:
            config = read_config(root)
            if args.command == "doctor":
                result = {
                    "local_ocr": (root / "bin/vision-ocr").exists(),
                    "mode": "live" if config["writes_enabled"] else "shadow",
                    "cloud_images_enabled": config["allow_cloud_images"],
                }
                try:
                    a = anki_client(config)
                    a.guard()
                    result["anki"] = {"version": a.call("version"), "profile_matches": True}
                except Exception as e:
                    result["anki"] = {"state": "unavailable", "reason": str(e)}
            elif args.command == "history":
                history = anki_client(config).history(args.query)
                out = root / "history.json"
                out.write_text(json.dumps(history))
                out.chmod(0o600)
                result = {"cards": len(history["cards"]), "history_file": str(out)}
            elif args.command == "import-analysis":
                work = root / "analysis" / args.submission_id
                ev = json.loads((work / "evidence.json").read_text())
                save_analysis(
                    store,
                    args.submission_id,
                    Analysis.model_validate_json(args.file.read_text()),
                    ev,
                    calibrated=config["calibration_verified"],
                )
                result = store.status()
            else:
                with (root / "worker.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    if args.command == "write-pending":
                        result = write_pending(store, config)
                    else:
                        if args.command == "run-once":
                            scan(store, root, Path(config["inbox"]))
                        result = process(store, root, config)
                        if config["writes_enabled"]:
                            result = {"analysis": result, "anki": write_pending(store, config)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(
            json.dumps(
                {"state": "error", "type": type(e).__name__, "reason": str(e)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    finally:
        store.db.close()
