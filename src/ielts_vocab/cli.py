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

from .analysis import DEFAULT_EFFORT, DEFAULT_MODEL, codex_analyze, evidence_pack, save_analysis
from .anki import Anki, enrich, execute, make_plan, reconcile_reviews
from .ingest import receive, scan
from .models import Analysis, Candidate, DayState, digest, study_day
from .pronunciation import ipa_fields
from .recognition import color_evidence, ocr, word_evidence
from .runtime import read_config, require_writer
from .service import serve, token_from_file
from .store import Store
from .unattended import refresh_day

DEFAULT_ROOT = Path.home() / "Library/Application Support/IELTSVocab"


def record_worker_status(root, result):
    path = root / "worker-status.tmp"
    path.write_text(
        json.dumps({"observed_at": time.time(), "result": result}, ensure_ascii=False, indent=2)
    )
    path.chmod(0o600)
    path.replace(root / "worker-status.json")


def anki_client(config):
    key_path = config.get("anki_key_file")
    return Anki(config["anki_profile"], token_from_file(key_path) if key_path else None)


def process(store, root, config):
    pending = store.db.execute(
        "SELECT count(DISTINCT core_key) FROM candidates WHERE state IN ('pending','awaiting_pronunciation')"
    ).fetchone()[0]
    if store.mining_paused(pending):
        return {"state": "backpressure", "pending_cores": pending}
    rows = store.db.execute(
        "SELECT * FROM submissions WHERE state='received' OR (state='retry_wait' AND next_retry<=?) ORDER BY created LIMIT 3",
        (time.time(),),
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
            evidence["semantic_enrichment_enabled"] = config.get(
                "semantic_enrichment_enabled", False
            )
            if evidence["semantic_enrichment_enabled"]:
                from .enrichment import dictionary_evidence

                evidence["additional_evidence"].extend(dictionary_evidence(lines, root, store))
            (work / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            if not (config.get("allow_cloud_images") or config.get("allow_cloud_text")):
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
                store.db.execute(
                    "UPDATE submissions SET state='retry_wait',next_retry=?,error=? WHERE id=?",
                    (time.time() + 3600, "Analyzer call budget exhausted; waiting", sid),
                )
                results.append({"submission": sid, "state": "waiting_model_budget"})
                continue
            store.event(
                "analyzer_call",
                sid,
                {"provider": "codex", "cloud_image": bool(config.get("allow_cloud_images"))},
            )
            analyzed = codex_analyze(
                Path(row["image"]) if config.get("allow_cloud_images") else None,
                evidence,
                work,
                allow_cloud=True,
                model=config.get("analyzer_model", DEFAULT_MODEL),
                effort=config.get("analyzer_reasoning_effort", DEFAULT_EFFORT),
            )
            save_analysis(
                store,
                sid,
                analyzed,
                evidence,
                calibrated=config["calibration_verified"],
                strict=True,
            )
            results.append({"submission": sid, "state": "analyzed"})
        except Exception as e:
            attempts = row["attempts"] + 1
            retryable = isinstance(e, (OSError, subprocess.SubprocessError, RuntimeError))
            state = "retry_wait" if retryable and attempts < 3 else "error"
            store.db.execute(
                "UPDATE submissions SET state=?,error=?,attempts=?,next_retry=? WHERE id=?",
                (state, str(e), attempts, time.time() + min(3600, 60 * 2**attempts), sid),
            )
            store.event("processing_error", sid, {"type": type(e).__name__})
            results.append({"submission": sid, "state": state, "reason": str(e)})
    return results


def write_pending(store, config, prepared=None):
    if not config["writes_enabled"] or not config["legacy_inventory_reviewed"]:
        raise ValueError("Writes disabled until target inventory and acceptance are verified")
    require_writer(config)
    a = anki_client(config)
    a.guard()
    a.setup(config["anki_deck"])
    if config.get("history_authority") == "synced_mac":
        readiness = prepared if prepared is not None else refresh_day(store, a, config)
        if readiness["state"] != "ready":
            return readiness
    reconcile_reviews(store, a, config["timezone"], config["rollover_hour"])
    day = study_day(datetime.now(timezone.utc), config["timezone"], config["rollover_hour"])
    # Existing uncertain operations must be reconciled before any new admission.
    unresolved = store.db.execute(
        "SELECT id FROM operations WHERE state IN ('reserved','writing','write_uncertain')"
    ).fetchall()
    for op in unresolved:
        execute(store, a, op["id"], current_day=day)
    rows = store.db.execute(
        "SELECT * FROM candidates WHERE state IN ('pending','awaiting_pronunciation') ORDER BY priority DESC,created LIMIT 50"
    ).fetchall()
    new_writes = 0
    for row in rows:
        if new_writes >= 5:
            break
        plan = make_plan(store, a, row, config["anki_deck"])
        if plan["kind"] == "enrich":
            enrich(store, a, row, plan)
            continue
        if plan["kind"] == "create":
            ipa = ipa_fields(
                Candidate.model_validate_json(row["payload"]), config.get("ipa_cache"), store
            )
            if ipa is None:
                store.db.execute(
                    "UPDATE candidates SET state='awaiting_pronunciation' WHERE id=?", (row["id"],)
                )
                continue
            plan["fields"].update(ipa)
        op_id = digest([row["id"], plan["slot"]])[:32]
        policy_row = store.db.execute("SELECT payload FROM days WHERE day=?", (day,)).fetchone()
        if policy_row:
            policy = DayState.model_validate_json(policy_row[0])
            usage = store.usage(day)
            existing_core = store.db.execute(
                "SELECT 1 FROM operations WHERE core_key=? AND state!='cancelled'",
                (row["core_key"],),
            ).fetchone()
            if (
                usage["cards"] + 1 > policy.card_limit
                or usage["cores"] + (not existing_core) > policy.core_limit
                or usage["contexts"] + (plan["kind"] == "context") > policy.context_limit
            ):
                break
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
        new_writes += 1
    if (
        store.db.execute("SELECT 1 FROM operations WHERE state='written'").fetchone()
        or store.db.execute("SELECT 1 FROM settings WHERE key='sync_dirty'").fetchone()
    ):
        a.call("sync")
        store.db.execute("UPDATE operations SET state='sync_requested' WHERE state='written'")
        store.db.execute("DELETE FROM settings WHERE key='sync_dirty'")
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
                    "cloud_text_enabled": config.get("allow_cloud_text", False),
                    "unattended_enabled": config.get("unattended_enabled", False),
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
                    strict=True,
                )
                result = store.status()
            else:
                with (root / "worker.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    if args.command == "write-pending":
                        result = write_pending(store, config)
                    else:
                        prepared = None
                        if args.command == "run-once":
                            scan(store, root, Path(config["inbox"]))
                        if config["writes_enabled"] or config.get("unattended_enabled"):
                            require_writer(config)
                            if config.get("history_authority") == "synced_mac":
                                prepared = refresh_day(store, anki_client(config), config)
                        result = process(store, root, config)
                        if not config["writes_enabled"] and prepared is not None:
                            result = {
                                "analysis": result,
                                "admission": prepared,
                                "writes_enabled": False,
                            }
                        if config["writes_enabled"]:
                            result = {
                                "analysis": result,
                                "anki": write_pending(store, config, prepared),
                            }
        if args.command == "run-once":
            record_worker_status(root, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        if args.command == "run-once" and not isinstance(e, BlockingIOError):
            record_worker_status(
                root, {"state": "error", "type": type(e).__name__, "reason": str(e)}
            )
        print(
            json.dumps(
                {"state": "error", "type": type(e).__name__, "reason": str(e)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    finally:
        store.db.close()
