from __future__ import annotations

import colorsys
import json
import subprocess
from pathlib import Path

from PIL import Image

from .palette import CURRENT_SCHEME, LEGACY_SCHEME, palette_for


def ocr(image: Path, binary: Path):
    if not binary.is_file():
        raise ValueError("Apple Vision helper not built; run build-ocr first")
    result = subprocess.run(
        [str(binary), str(image)], capture_output=True, text=True, check=True, timeout=60
    )
    return json.loads(result.stdout)


def color_evidence(image: Path, lines: list[dict], scheme=CURRENT_SCHEME):
    """Diagnostic hue votes per OCR line. Never considered calibrated acceptance evidence."""
    palette = palette_for(scheme)
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
        pixels = region.load()
        for r, g, b in (pixels[x, y] for y in range(region.height) for x in range(region.width)):
            hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if sat < (0.18 if scheme == LEGACY_SCHEME else 0.05) or val < 0.35:
                continue
            deg = hue * 360
            if scheme != LEGACY_SCHEME:
                distances = {}
                for label, color in palette.items():
                    rgb = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
                    target = colorsys.rgb_to_hsv(*rgb)[0] * 360
                    distances[label] = abs((deg - target + 180) % 360 - 180)
                closest = min(distances, key=distances.get)
                if distances[closest] <= 18:
                    votes[closest] += 1
            elif 43 <= deg <= 75:
                votes["unknown"] += 1
            elif 15 <= deg < 43:
                votes["partial"] += 1
            elif 175 <= deg <= 250:
                votes["phrase_context_unclear"] += 1
        output.append({**line, "color_votes": votes, "calibrated": False, "mark_scheme": scheme})
    return output


def word_evidence(image: Path, lines: list[dict], scheme=CURRENT_SCHEME):
    """Conservative light-page diagnostics; never a calibrated admission signal.

    Use real Vision word boxes, reject dark/saturated interface backgrounds, and
    require substantial word coverage so a stroke touching a neighbour is not a mark.
    """
    with Image.open(image) as source:
        im = source.convert("RGB")

    def crop(box):
        x, y, w, h = box
        region = im.crop(
            (
                int(x * im.width),
                int(y * im.height),
                int((x + w) * im.width),
                int((y + h) * im.height),
            )
        )
        region.thumbnail((300, 40))
        return region

    output = []
    for line in lines:
        if "words" not in line:
            raise ValueError("Word boxes missing: rebuild the Vision helper before processing")
        region = crop(line["bbox"])
        pixels = region.load()
        area = region.width * region.height
        light = sum(
            value >= 0.75 and saturation <= 0.65
            for _, saturation, value in (
                colorsys.rgb_to_hsv(*(c / 255 for c in pixels[x, y]))
                for y in range(region.height)
                for x in range(region.width)
            )
        ) / max(1, area)
        eligible = light >= 0.70 and line["confidence"] >= 0.8
        words = color_evidence(image, line["words"], scheme)
        marks = []
        previous_index = -2
        for index, word in enumerate(words):
            r = crop(word["bbox"])
            votes = word["color_votes"]
            label = max(votes, key=votes.get)
            coverage = votes[label] / max(1, r.width * r.height)
            dominance = votes[label] / max(1, sum(votes.values()))
            word["coverage"] = round(coverage, 3)
            word["mark"] = label if eligible and coverage >= 0.30 and dominance >= 0.80 else None
            if word["mark"]:
                if marks and previous_index == index - 1 and marks[-1]["mark"] == label:
                    marks[-1]["text"] += " " + word["text"]
                    marks[-1]["word_indices"].append(index)
                else:
                    marks.append({"text": word["text"], "mark": label, "word_indices": [index]})
                previous_index = index
        output.append(
            {
                **line,
                "words": words,
                "marked_spans": marks,
                "light_page_eligible": eligible,
                "light_fraction": round(light, 3),
                "calibrated": False,
            }
        )
    return output
