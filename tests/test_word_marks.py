import pytest
from PIL import Image, ImageDraw

from ielts_vocab.recognition import word_evidence


def test_neighbour_touch_does_not_expand_phrase(tmp_path):
    p = tmp_path / "page.png"
    im = Image.new("RGB", (500, 100), "white")
    draw = ImageDraw.Draw(im)
    draw.rectangle((100, 25, 239, 74), fill="#CCD1B8")
    im.save(p)
    line = {
        "text": "eyes were fixed on her",
        "confidence": 1,
        "bbox": [0, 0, 1, 1],
        "words": [
            {"text": t, "bbox": [x / 500, 0.25, 0.08, 0.5]}
            for t, x in [("eyes", 65), ("were", 110), ("fixed", 155), ("on", 200), ("her", 235)]
        ],
    }
    result = word_evidence(p, [line])[0]
    assert [m["text"] for m in result["marked_spans"]] == ["were fixed on"]
    assert result["marked_spans"][0]["mark"] == "phrase_context_unclear"
    assert result["calibrated"] is False


def test_dark_blue_toolbar_is_not_a_mark(tmp_path):
    p = tmp_path / "toolbar.png"
    Image.new("RGB", (400, 80), "#315B97").save(p)
    line = {
        "text": "Goodnotes",
        "confidence": 1,
        "bbox": [0, 0, 1, 1],
        "words": [{"text": "Goodnotes", "bbox": [0.1, 0.2, 0.3, 0.6]}],
    }
    result = word_evidence(p, [line])[0]
    assert result["marked_spans"] == []
    assert not result["light_page_eligible"]


def test_old_helper_output_fails_explicitly(tmp_path):
    p = tmp_path / "page.png"
    Image.new("RGB", (10, 10), "white").save(p)
    with pytest.raises(ValueError, match="rebuild"):
        word_evidence(p, [{"text": "word", "confidence": 1, "bbox": [0, 0, 1, 1]}])


def test_unmarked_gap_and_color_change_split_spans(tmp_path):
    p = tmp_path / "page.png"
    im = Image.new("RGB", (500, 100), "white")
    draw = ImageDraw.Draw(im)
    for x, color in [(20, "#E6C162"), (160, "#E6C162"), (220, "#6E83B0")]:
        draw.rectangle((x, 25, x + 39, 74), fill=color)
    im.save(p)
    line = {
        "text": "one gap two three",
        "confidence": 1,
        "bbox": [0, 0, 1, 1],
        "words": [
            {"text": t, "bbox": [x / 500, 0.25, 0.08, 0.5]}
            for t, x in [("one", 20), ("gap", 90), ("two", 160), ("three", 220)]
        ],
    }
    result = word_evidence(p, [line])[0]
    assert [m["text"] for m in result["marked_spans"]] == ["one", "two", "three"]
