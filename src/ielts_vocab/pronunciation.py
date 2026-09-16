"""Only sourced IPA enters word cards; phrases deliberately have no IPA."""

import html
import json
from pathlib import Path


def ipa_fields(candidate, cache_path):
    if candidate.unit_type == "phrase":
        return {}
    if cache_path is None:
        return None
    cache = json.loads(Path(cache_path).read_text())
    value = cache.get(candidate.lemma.casefold())
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
        "IPA_Source": '<a href="' + html.escape(value["source"], quote=True) + '">音标来源</a>',
        "IPA_Note": "",
    }
