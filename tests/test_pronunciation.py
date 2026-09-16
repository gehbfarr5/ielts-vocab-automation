import json

import pytest

from ielts_vocab.pronunciation import ipa_fields


def test_no_guessed_ipa(candidate, tmp_path):
    assert ipa_fields(candidate, None) is None
    assert ipa_fields(candidate.model_copy(update={"unit_type": "phrase"}), None) == {}
    p = tmp_path / "ipa.json"
    p.write_text(json.dumps({"maintain": {"us": "/x/", "uk": "/x/"}}))
    with pytest.raises(ValueError, match="provenance"):
        ipa_fields(candidate, p)
    p.write_text(
        json.dumps(
            {
                "maintain": {
                    "us": "/x/",
                    "uk": "/x/",
                    "source": "https://example.org",
                    "verified_at": "2026-09-17",
                }
            }
        )
    )
    assert ipa_fields(candidate, p)["IPA_US"] == "/x/"
