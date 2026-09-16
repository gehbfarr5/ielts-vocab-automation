"""Small source-backed teaching notes; no extra study targets or remote card assets."""

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .context import FUNCTION_WORDS, words


def dictionary_evidence(lines, root, store):
    """Retrieve only marked text, with bounded caching and explicit missing entries."""
    targets = []
    for line in lines:
        for mark in line.get("marked_spans", []):
            tokens = words(mark["text"])
            if 1 < len(tokens) <= 5:
                targets.append(" ".join(tokens))
            targets.extend(w for w in tokens if w not in FUNCTION_WORDS)
    targets = list(dict.fromkeys(targets))[:16]
    folder = root / "lexicon"
    folder.mkdir(mode=0o700, exist_ok=True)
    evidence = []
    for term in targets:
        if not re.fullmatch(r"[a-z][a-z '’-]{0,79}", term):
            continue
        encoded = urllib.parse.quote(term, safe="")
        url = f"https://kaikki.org/dictionary/English/meaning/{encoded[:1]}/{encoded[:2]}/{encoded}.jsonl"
        cache = folder / (hashlib.sha256(term.encode()).hexdigest() + ".json")
        saved = json.loads(cache.read_text()) if cache.exists() else None
        lifetime = 30 * 86400 if saved and saved["status"] == "found" else 86400
        if saved is None or time.time() - saved["at"] > lifetime:
            request = urllib.request.Request(url, headers={"User-Agent": "IELTSVocab/0.1"})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    if urllib.parse.urlsplit(response.url).hostname != "kaikki.org":
                        raise ValueError("Unexpected lexical source redirect")
                    raw = response.read(2_000_001)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                # A documented missing entry is not a network failure fallback.
                saved = {"at": time.time(), "status": "not_found", "records": []}
            else:
                if len(raw) > 2_000_000:
                    raise ValueError("Lexical response exceeds size limit")
                records = [json.loads(line) for line in raw.splitlines() if line]
                selected = []
                for entry in records:
                    if entry.get("word", "").casefold() != term or entry.get("lang_code") != "en":
                        continue
                    selected.append(
                        {
                            "word": entry["word"],
                            "pos": entry.get("pos"),
                            "senses": [
                                {
                                    "glosses": s.get("glosses", [])[:2],
                                    "tags": s.get("tags", []),
                                    "form_of": s.get("form_of", []),
                                    "examples": [
                                        {"text": x.get("text", "")[:300]}
                                        for x in s.get("examples", [])[:1]
                                    ],
                                }
                                for s in entry.get("senses", [])[:6]
                            ],
                            "forms": entry.get("forms", [])[:10],
                            "derived": entry.get("derived", [])[:6],
                            "etymology_text": entry.get("etymology_text", "")[:1000],
                        }
                    )
                saved = {
                    "at": time.time(),
                    "status": "found" if selected else "no_matching_entry",
                    "records": selected[:3],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(saved, ensure_ascii=False))
            tmp.chmod(0o600)
            tmp.replace(cache)
        item = {
            "id": "dict:" + term,
            "kind": "dictionary",
            "provider": "Kaikki/Wiktionary",
            "reference": url,
            "license": "CC BY-SA 4.0",
            **saved,
        }
        evidence.append(item)
        store.event("lexical_evidence", term, {"status": saved["status"], "reference": url})
    return evidence


def validate_enrichment(candidate, evidence):
    item = candidate.enrichment
    dictionaries = {
        x["id"]
        for x in evidence.get("additional_evidence", [])
        if x.get("kind") == "dictionary" and x.get("status") == "found"
    }
    if item.usage_kind == "source_expression":
        if set(item.usage_refs) != {evidence["source_id"]}:
            raise ValueError("Original expression must cite its source")
        normalize = lambda x: " ".join(x.casefold().split())
        if normalize(item.usage) not in normalize(candidate.source_sentence):
            raise ValueError("Original expression not present in original sentence")
    elif not set(item.usage_refs) <= dictionaries:
        raise ValueError("Usage lacks supplied dictionary evidence")
    for note in item.word_notes:
        if not set(note.evidence_refs) <= dictionaries:
            raise ValueError("Word note lacks supplied dictionary evidence")
    if not item.word_notes and not item.omitted_reason.strip():
        raise ValueError("Missing word notes require an explicit evidence limitation")


def render_enrichment(candidate):
    e = candidate.enrichment
    if e is None:
        # Old queued records remain valid; do not fabricate enrichment during rendering.
        return "<br>".join(map(html.escape, candidate.collocations))
    escape = html.escape
    label = "原文表达" if e.usage_kind == "source_expression" else "词典支持用法"
    main = (
        f"<p>{escape(e.core_image_zh)}</p><p><b>{escape(e.usage)}</b><br>"
        f"{escape(e.usage_zh)} <small>· {label}</small></p>"
    )
    notes = "".join(f"<p>{escape(n.text)}</p>" for n in e.word_notes)
    refs = set(e.usage_refs)
    for n in e.word_notes:
        refs.update(n.evidence_refs)
    links = []
    for ref in sorted(refs):
        if ref.startswith("dict:"):
            term = ref[5:]
            url = "https://en.wiktionary.org/wiki/" + urllib.parse.quote(term, safe="")
            links.append(f'<a href="{escape(url, quote=True)}">{escape(term)}</a>')
    attribution = (
        (
            "词典依据："
            + " · ".join(links)
            + ' · Wiktionary，经Kaikki提取 · <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>；中文解释经改写。'
        )
        if links
        else "用法依据：上方原文。"
    )
    more = (
        f'<details class="learning-extra"><summary>展开学习补充</summary>{notes}'
        f"<p><b>新情境 · Agent自编</b><br>{escape(e.example_en)}<br>{escape(e.example_zh)}</p>"
        f"<p><b>想一想</b><br>{escape(e.recall_question)}</p>"
        f"<details><summary>参考答案</summary>{escape(e.recall_answer)}</details>"
        f'<p class="metadata">{attribution}<br>场景解释与练习为Agent教学推断，不是词典引文。</p></details>'
    )
    return main + more
