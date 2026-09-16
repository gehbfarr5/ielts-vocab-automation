"""Conservative admission for the validated Goodnotes light-page colour profile."""

import re

from .palette import CURRENT_SCHEME


def tokens(value):
    return re.findall(r"[a-z]+(?:['’-][a-z]+)*", value.casefold())


def check_candidate(candidate, evidence):
    reasons = []
    if evidence.get("mark_scheme") != CURRENT_SCHEME:
        reasons.append("unsupported_mark_scheme")
    sentence = candidate.source_sentence.strip()
    if not re.match(r'^["“\'‘(]*[A-Z]', sentence) or not re.search(r'[.!?]["”\'’)]*$', sentence):
        reasons.append("incomplete_sentence")
    selected = set(tokens(candidate.surface_form))
    matching = []
    for line in evidence["ocr_lines"]:
        for mark in line.get("marked_spans", []):
            if mark["mark"] == candidate.mark_type and selected & set(tokens(mark["text"])):
                matching.append(line)
    if not matching:
        reasons.append("no_matching_highlight")
    elif not any(
        line.get("light_page_eligible") and line.get("confidence", 0) >= 0.98 for line in matching
    ):
        reasons.append("weak_ocr_or_page")
    # Each surface form must preserve what was actually read, not substitute a lemma.
    if " ".join(tokens(candidate.surface_form)) not in " ".join(tokens(sentence)):
        reasons.append("surface_not_in_sentence")
    return reasons
