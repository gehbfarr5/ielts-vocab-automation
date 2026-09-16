from __future__ import annotations

import colorsys
import json
import subprocess
from pathlib import Path

from PIL import Image


def ocr(image: Path, binary: Path):
    if not binary.is_file():
        raise ValueError("Apple Vision helper not built; run build-ocr first")
    result = subprocess.run(
        [str(binary), str(image)], capture_output=True, text=True, check=True, timeout=60
    )
    return json.loads(result.stdout)


def color_evidence(image: Path, lines: list[dict]):
    """Diagnostic hue votes per OCR line. Never considered calibrated acceptance evidence."""
    with Image.open(image) as src:
        im = src.convert("RGB")
    output = []
    for line in lines:
        x, y, w, h = line["bbox"]
        region = im.crop(
            (
                int(x * im.width),
                int(y * im.height),
                int((x + w) * im.width),
                int((y + h) * im.height),
            )
        )
        region.thumbnail((300, 40))
        votes = dict.fromkeys(("unknown", "partial", "phrase_context_unclear"), 0)
        for r, g, b in region.getdata():
            hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if sat < 0.18 or val < 0.35:
                continue
            deg = hue * 360
            if 43 <= deg <= 75:
                votes["unknown"] += 1
            elif 15 <= deg < 43:
                votes["partial"] += 1
            elif 175 <= deg <= 250:
                votes["phrase_context_unclear"] += 1
        output.append({**line, "color_votes": votes, "calibrated": False})
    return output
