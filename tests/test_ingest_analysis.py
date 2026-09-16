import hashlib
import io
import json
import os
import time

import pytest
from PIL import Image

from ielts_vocab.analysis import save_analysis
from ielts_vocab.ingest import receive, scan
from ielts_vocab.models import Analysis


def test_duplicate_and_id_conflict(store, tmp_path, image_bytes):
    r = receive(store, tmp_path, image_bytes, "one")
    assert receive(store, tmp_path, image_bytes, "two")["submission_id"] == r["submission_id"]
    assert receive(store, tmp_path, image_bytes, "one")["duplicate"]
    changed = io.BytesIO()
    Image.new("RGB", (300, 100), "orange").save(changed, format="PNG")
    with pytest.raises(ValueError, match="different"):
        receive(store, tmp_path, changed.getvalue(), "one")
    assert store.db.execute("SELECT count(*) FROM submissions").fetchone()[0] == 1


@pytest.mark.parametrize("sid", ["../bad", "with/slash", "a?token=secret", "", "x" * 101])
def test_invalid_id(store, tmp_path, image_bytes, sid):
    if sid == "":
        return  # Empty optional ID creates a server-generated ID.
    with pytest.raises(ValueError):
        receive(store, tmp_path, image_bytes, sid)


def test_partial_package_and_symlink(store, tmp_path, image_bytes):
    inbox = tmp_path / "inbox"
    package = inbox / "batch"
    package.mkdir(parents=True)
    (package / "ready.json").write_text("{}")
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "submission_id": "batch",
                "images": [
                    {"file": "first.png", "sha256": hashlib.sha256(image_bytes).hexdigest()},
                    {"file": "second.png", "sha256": hashlib.sha256(image_bytes).hexdigest()},
                ],
            }
        )
    )
    (package / "first.png").write_bytes(image_bytes)
    result = scan(store, tmp_path, inbox)
    assert result[0]["state"] == "waiting_or_invalid"
    assert store.db.execute("SELECT count(*) FROM submissions").fetchone()[0] == 0
    (package / "second.png").write_bytes(image_bytes)
    assert all("submission_id" in x for x in scan(store, tmp_path, inbox))


def test_plain_file_waits_until_stable(store, tmp_path, image_bytes):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    p = inbox / "one.png"
    p.write_bytes(image_bytes)
    assert scan(store, tmp_path, inbox) == []
    os.utime(p, (time.time() - 10, time.time() - 10))
    assert len(scan(store, tmp_path, inbox)) == 1


def test_uncalibrated_accept_deferred(store, tmp_path, image_bytes, candidate):
    r = receive(store, tmp_path, image_bytes)
    ev = {
        "source_id": "source:test",
        "inference_id": "inferred:agent-gloss",
        "ocr_lines": [{"text": candidate.source_sentence}],
    }
    save_analysis(
        store, r["submission_id"], Analysis(candidates=[candidate], notes=""), ev, calibrated=False
    )
    assert store.db.execute("SELECT state FROM candidates").fetchone()[0] == "deferred"


def test_hallucinated_evidence_atomic_reject(store, tmp_path, image_bytes, candidate):
    r = receive(store, tmp_path, image_bytes)
    ev = {
        "source_id": "source:test",
        "inference_id": "inferred:agent-gloss",
        "ocr_lines": [{"text": candidate.source_sentence}],
    }
    c2 = candidate.model_copy(update={"lemma": "other", "evidence_refs": ["made-up-official-cefr"]})
    with pytest.raises(ValueError, match="Unknown evidence"):
        save_analysis(
            store,
            r["submission_id"],
            Analysis(candidates=[candidate, c2], notes=""),
            ev,
            calibrated=True,
        )
    assert store.db.execute("SELECT count(*) FROM candidates").fetchone()[0] == 0


def test_source_fabrication_deferred(store, tmp_path, image_bytes, candidate):
    r = receive(store, tmp_path, image_bytes)
    ev = {
        "source_id": "source:test",
        "inference_id": "inferred:agent-gloss",
        "ocr_lines": [{"text": "Other text."}],
    }
    save_analysis(
        store, r["submission_id"], Analysis(candidates=[candidate], notes=""), ev, calibrated=True
    )
    assert store.db.execute("SELECT state FROM candidates").fetchone()[0] == "deferred"


def test_alias_id_cannot_be_reused_for_changed_content(store, tmp_path, image_bytes):
    receive(store, tmp_path, image_bytes, "first")
    receive(store, tmp_path, image_bytes, "alias")
    buf = io.BytesIO()
    Image.new("RGB", (300, 100), "blue").save(buf, format="PNG")
    with pytest.raises(ValueError, match="different"):
        receive(store, tmp_path, buf.getvalue(), "alias")


def test_unbacked_academic_score_rejected(store, tmp_path, image_bytes, candidate):
    r = receive(store, tmp_path, image_bytes)
    ev = {
        "source_id": "source:test",
        "inference_id": "inferred:agent-gloss",
        "ocr_lines": [{"text": candidate.source_sentence}],
    }
    c = candidate.model_copy(update={"academic": 95})
    with pytest.raises(ValueError, match="Academic score"):
        save_analysis(
            store, r["submission_id"], Analysis(candidates=[c], notes=""), ev, calibrated=True
        )


def test_deferred_candidate_can_be_reevaluated_without_duplicate(
    store, tmp_path, image_bytes, candidate
):
    r = receive(store, tmp_path, image_bytes)
    ev = {
        "source_id": "source:test",
        "inference_id": "inferred:agent-gloss",
        "ocr_lines": [{"text": candidate.source_sentence}],
    }
    result = Analysis(candidates=[candidate], notes="")
    save_analysis(store, r["submission_id"], result, ev, calibrated=False)
    save_analysis(store, r["submission_id"], result, ev, calibrated=True)
    assert store.db.execute("SELECT count(*) FROM candidates").fetchone()[0] == 1
    assert store.db.execute("SELECT state FROM candidates").fetchone()[0] == "pending"
