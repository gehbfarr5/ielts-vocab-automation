"""Bounded retrieval of existing vocabulary; never generates new study targets."""

import re

FUNCTION_WORDS = {"a", "an", "the", "in", "on", "at", "to", "of", "for", "and", "or", "be", "it"}


def words(text):
    return re.findall(r"[a-z]+(?:['’-][a-z]+)*", text.casefold())


def forms(word):
    # Retrieval only: conservative common inflections, not derivations/word families.
    result = {word, word + "s", word + "es", word + "ed", word + "ing"}
    if word.endswith("e"):
        result.update((word + "d", word[:-1] + "ing"))
    if len(word) > 2 and word.endswith("y") and word[-2] not in "aeiou":
        result.update((word[:-1] + "ies", word[:-1] + "ied"))
    if (
        len(word) > 2
        and word[-1] not in "aeiouwxy"
        and word[-2] in "aeiou"
        and word[-3] not in "aeiou"
    ):
        result.update((word + word[-1] + "ed", word + word[-1] + "ing"))
    return result


def relevant(lemma, surfaces, lines):
    variants = [[forms(w) for w in words(lemma)]]
    variants += [[{w} for w in words(surface)] for surface in surfaces]
    for index, line in enumerate(lines):
        marked = {
            w for mark in line.get("marked_spans", []) for w in words(mark["text"])
        } - FUNCTION_WORDS
        if not marked:
            continue
        context = words(" ".join(x["text"] for x in lines[max(0, index - 2) : index + 3]))
        for pattern in variants:
            if not pattern:
                continue
            for start in range(len(context) - len(pattern) + 1):
                span = context[start : start + len(pattern)]
                if marked.intersection(span) and all(
                    w in allowed for w, allowed in zip(span, pattern, strict=True)
                ):
                    return True
    return False


def restrict_history(evidence):
    """Filter at the outbound boundary, including saved evidence/replay calls."""
    supplied = dict(evidence)
    lines = evidence["ocr_lines"]
    surfaces = evidence.get("known_surfaces", {})
    supplied.pop("known_surfaces", None)
    supplied["known_senses"] = [
        x
        for x in evidence.get("known_senses", [])
        if relevant(x["lemma"], surfaces.get(x["lemma"], []), lines)
    ]
    history = evidence.get("anki_review_history")
    if history is not None:
        entries = []
        for entry in history["entries"]:
            if relevant(entry["lemma"], surfaces.get(entry["lemma"], []), lines):
                # Only aggregate scheduling facts are needed; do not send card IDs or raw logs.
                entries.append(
                    {
                        "lemma": entry["lemma"],
                        "cards": [
                            {k: c[k] for k in ("interval", "reps", "lapses")}
                            for c in entry["cards"]
                        ],
                    }
                )
        supplied["anki_review_history"] = {
            "observed_at": history["observed_at"],
            "entries": entries,
        }
    return supplied
