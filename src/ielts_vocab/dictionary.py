"""Bounded, attributed Kaikki/Wiktionary lookup; no guessed accent assignments."""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

POS = {
    "verb": "verb",
    "v.": "verb",
    "noun": "noun",
    "n.": "noun",
    "adjective": "adj",
    "adj.": "adj",
    "adj": "adj",
    "adverb": "adv",
    "adv.": "adv",
    "adv": "adv",
}


def select_ipa(records, lemma, pos):
    entries = [
        x
        for x in records
        if x.get("word") == lemma
        and x.get("lang_code") == "en"
        and x.get("pos") == POS.get(pos.casefold(), pos.casefold())
    ]
    variants = {"us": [], "uk": []}
    # Multiple etymologies may assign distinct pronunciations to the same POS.
    # Refuse inconsistent entries; within one entry retain the first documented variant.
    pairs = []
    for entry in entries:
        found = {"us": [], "uk": []}
        for sound in entry.get("sounds", []):
            ipa = sound.get("ipa", "")
            tags = set(sound.get("tags", []))
            if not re.fullmatch(r"/[^<>\n]{1,120}/", ipa):
                continue
            for accent, labels in [
                ("us", {"General-American", "US"}),
                ("uk", {"Received-Pronunciation", "UK"}),
            ]:
                if tags & labels and ipa not in found[accent]:
                    found[accent].append(ipa)
        if not all(found.values()):
            return None
        pairs.append((found["us"][0], found["uk"][0]))
        for accent in variants:
            variants[accent].extend(found[accent])
    if not pairs or len(set(pairs)) != 1:
        return None
    return {"us": pairs[0][0], "uk": pairs[0][1], "variants": variants}


def fetch_ipa(lemma, pos, cache_path, store):
    if not re.fullmatch(r"[A-Za-z][A-Za-z'-]{1,79}", lemma):
        return None
    key = "dictionary_retry:" + lemma.casefold() + ":" + pos
    previous = store.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    prior = json.loads(previous[0]) if previous else {}
    if time.time() < prior.get("after", 0):
        return None
    encoded = urllib.parse.quote(lemma, safe="")
    url = (
        f"https://kaikki.org/dictionary/English/meaning/{encoded[:1]}/{encoded[:2]}/{encoded}.jsonl"
    )
    attempt = prior.get("attempt", 0) + 1
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "IELTSVocab/0.1 (+https://github.com/gehbfarr5/ielts-vocab-automation)"
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if urllib.parse.urlsplit(response.url).hostname != "kaikki.org":
                raise ValueError("Unexpected dictionary redirect")
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Dictionary response exceeds limit")
        value = select_ipa([json.loads(line) for line in data.splitlines() if line], lemma, pos)
        if value is None:
            raise ValueError("No unambiguous labelled US/UK pronunciation for this POS")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        delay = (
            86400
            if isinstance(exc, ValueError) or getattr(exc, "code", None) == 404
            else min(3600, 300 * 2 ** min(attempt - 1, 4))
        )
        detail = {
            "after": time.time() + delay,
            "attempt": attempt,
            "error": type(exc).__name__,
            "reason": str(exc)[:300],
        }
        store.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(detail)))
        store.event("dictionary_wait", lemma, detail)
        return None
    value.update(
        source=url,
        verified_at=datetime.now(timezone.utc).isoformat(),
        provider="Kaikki/Wiktionary",
        license="CC BY-SA 4.0",
        source_sha256=hashlib.sha256(data).hexdigest(),
        part_of_speech=pos,
    )
    path = Path(cache_path)
    cache = json.loads(path.read_text()) if path.exists() else {}
    cache[lemma.casefold() + "|" + pos.casefold()] = value
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    tmp.chmod(0o600)
    tmp.replace(path)
    store.db.execute("DELETE FROM settings WHERE key=?", (key,))
    store.event("dictionary_verified", lemma, {"source": url, "sha256": value["source_sha256"]})
    return value
