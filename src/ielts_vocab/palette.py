"""Versioned mark semantics. RGB values are pen settings, not rendered screenshot pixels."""

CURRENT_SCHEME = "goodnotes-muted-v2"
LEGACY_SCHEME = "yellow-orange-blue-v1"
PALETTES = {
    CURRENT_SCHEME: {
        "unknown": "#E6C162",
        "partial": "#BF8486",
        "phrase_context_unclear": "#6E83B0",
    },
    LEGACY_SCHEME: {
        "unknown": "yellow",
        "partial": "orange",
        "phrase_context_unclear": "blue",
    },
}


def palette_for(scheme):
    if scheme not in PALETTES:
        raise ValueError(f"Unknown mark scheme: {scheme}")
    return PALETTES[scheme]
