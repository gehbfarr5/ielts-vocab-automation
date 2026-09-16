import sqlite3

import pytest
from PIL import Image

from ielts_vocab.ingest import receive
from ielts_vocab.palette import CURRENT_SCHEME, LEGACY_SCHEME, PALETTES
from ielts_vocab.recognition import color_evidence
from ielts_vocab.store import Store


@pytest.mark.parametrize("label,color", PALETTES[CURRENT_SCHEME].items())
@pytest.mark.parametrize("alpha", [1, 0.5, 0.3])
def test_new_palette_with_white_highlighter_blend(tmp_path, label, color, alpha):
    rgb = tuple(round(255 * (1 - alpha) + int(color[i : i + 2], 16) * alpha) for i in (1, 3, 5))
    p = tmp_path / "swatch.png"
    Image.new("RGB", (30, 30), rgb).save(p)
    result = color_evidence(p, [{"bbox": [0, 0, 1, 1], "text": "word"}])[0]
    assert result["color_votes"][label] == 900
    assert sum(result["color_votes"].values()) == 900
    assert result["mark_scheme"] == CURRENT_SCHEME
    assert result["calibrated"] is False


def test_legacy_orange_still_partial(tmp_path):
    p = tmp_path / "legacy.png"
    Image.new("RGB", (20, 20), (255, 170, 60)).save(p)
    assert (
        color_evidence(p, [{"bbox": [0, 0, 1, 1]}], LEGACY_SCHEME)[0]["color_votes"]["partial"]
        == 400
    )


def test_new_receipt_records_scheme(store, tmp_path, image_bytes):
    r = receive(store, tmp_path, image_bytes)
    assert (
        store.db.execute(
            "SELECT mark_scheme FROM submissions WHERE id=?", (r["submission_id"],)
        ).fetchone()[0]
        == CURRENT_SCHEME
    )


def test_old_database_migration_preserves_legacy(tmp_path):
    p = tmp_path / "old.sqlite3"
    db = sqlite3.connect(p)
    db.execute(
        "CREATE TABLE submissions(id TEXT PRIMARY KEY,sha TEXT,image TEXT,state TEXT,created REAL,analysis TEXT,error TEXT,attempts INTEGER)"
    )
    db.execute("INSERT INTO submissions VALUES('old','sha','file','received',1,NULL,NULL,0)")
    db.commit()
    db.close()
    store = Store(p)
    assert store.db.execute("SELECT mark_scheme FROM submissions").fetchone()[0] == LEGACY_SCHEME
    store.db.close()


def test_v2_blue_retains_old_meaning(tmp_path):
    p = tmp_path / "blue.png"
    Image.new("RGB", (20, 20), "#6E83B0").save(p)
    old = color_evidence(p, [{"bbox": [0, 0, 1, 1]}], "goodnotes-muted-v2")[0]
    new = color_evidence(p, [{"bbox": [0, 0, 1, 1]}])[0]
    assert old["color_votes"]["phrase_context_unclear"] == 400
    assert new["color_votes"]["partial"] == 400


@pytest.mark.parametrize("rgb", [(255, 255, 255), (180, 180, 180), (0, 0, 0), (245, 244, 240)])
def test_neutral_background_has_no_color_votes(tmp_path, rgb):
    p = tmp_path / "neutral.png"
    Image.new("RGB", (20, 20), rgb).save(p)
    result = color_evidence(p, [{"bbox": [0, 0, 1, 1]}])[0]
    assert sum(result["color_votes"].values()) == 0
