from ielts_vocab.dictionary import select_ipa
from ielts_vocab.palette import CURRENT_SCHEME
from ielts_vocab.quality import check_candidate


def test_quality_matches_explicit_mark_and_complete_sentence(candidate):
    ev = {
        "mark_scheme": CURRENT_SCHEME,
        "ocr_lines": [
            {
                "text": candidate.source_sentence,
                "confidence": 1,
                "light_page_eligible": True,
                "marked_spans": [{"text": "maintain", "mark": "partial"}],
            }
        ],
    }
    assert not check_candidate(candidate, ev)
    assert "incomplete_sentence" in check_candidate(
        candidate.model_copy(update={"source_sentence": "maintain the system"}), ev
    )
    assert "no_matching_highlight" in check_candidate(
        candidate.model_copy(update={"surface_form": "system"}), ev
    )
    ev["ocr_lines"][0]["light_page_eligible"] = False
    assert "weak_ocr_or_page" in check_candidate(candidate, ev)


def test_ipa_never_assigns_unlabelled_accent_or_wrong_pos():
    entry = {"word": "record", "lang_code": "en", "pos": "noun", "sounds": [{"ipa": "/a/"}]}
    assert select_ipa([entry], "record", "noun") is None
    entry["sounds"] = [{"ipa": "/a/", "tags": ["General-American", "Received-Pronunciation"]}]
    assert select_ipa([entry], "record", "verb") is None
    assert select_ipa([entry], "record", "noun")["us"] == "/a/"
    other = {
        **entry,
        "sounds": [{"ipa": "/b/", "tags": ["General-American", "Received-Pronunciation"]}],
    }
    assert select_ipa([entry, other], "record", "noun") is None


def test_dictionary_network_wait_then_verified_cache(store, tmp_path, monkeypatch):
    import json
    import urllib.error

    from ielts_vocab.dictionary import fetch_ipa

    calls = []

    def offline(*args, **kwargs):
        calls.append(1)
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    path = tmp_path / "ipa.json"
    assert fetch_ipa("record", "noun", path, store) is None
    assert fetch_ipa("record", "noun", path, store) is None
    assert len(calls) == 1 and not path.exists()
    store.db.execute("DELETE FROM settings WHERE key LIKE 'dictionary_retry:%'")

    class Response:
        url = "https://kaikki.org/dictionary/English/meaning/r/re/record.jsonl"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return json.dumps(
                {
                    "word": "record",
                    "lang_code": "en",
                    "pos": "noun",
                    "sounds": [{"ipa": "/a/", "tags": ["US", "UK"]}],
                }
            ).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: Response())
    assert fetch_ipa("record", "noun", path, store)["us"] == "/a/"
    assert json.loads(path.read_text())["record|noun"]["source_sha256"]
