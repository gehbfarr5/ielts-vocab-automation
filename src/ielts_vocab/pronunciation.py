"""Only sourced IPA enters word cards; phrases deliberately have no IPA."""

import html
import json
from pathlib import Path


def ipa_fields(candidate, cache_path, store=None):
    if candidate.unit_type == "phrase":
        return {}
    if cache_path is None:
        return None
    path = Path(cache_path)
    cache = json.loads(path.read_text()) if path.exists() else {}
    value = cache.get(candidate.lemma.casefold() + "|" + candidate.part_of_speech.casefold())
    if value is None:
        value = cache.get(candidate.lemma.casefold())
    if value is None and store is not None:
        from .dictionary import fetch_ipa

        value = fetch_ipa(candidate.lemma, candidate.part_of_speech, cache_path, store)
    if value is None:
        return None
    if not value.get("verified_at") or not value.get("source", "").startswith("https://"):
        raise ValueError("IPA cache entry lacks verified provenance")
    for key in ("us", "uk"):
        ipa = value.get(key)
        if not isinstance(ipa, str) or not (ipa.startswith("/") and ipa.endswith("/")):
            raise ValueError("Invalid IPA cache entry")
    return {
        "IPA_US": html.escape(value["us"]),
        "IPA_UK": html.escape(value["uk"]),
        "IPA_Source": '<a href="'
        + html.escape(value["source"], quote=True)
        + '">音标来源</a>'
        + (
            ' · Wiktionary / <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>'
            if value.get("license") == "CC BY-SA 4.0"
            else ""
        ),
        "IPA_Note": "",
    }
