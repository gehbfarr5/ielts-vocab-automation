"""Suppress only Anki's localized collection-sync success tooltip."""

from functools import wraps

import aqt.sync
from aqt.utils import tr

_original_tooltip = aqt.sync.tooltip


@wraps(_original_tooltip)
def _quiet_success(*args, **kwargs):
    message = kwargs.get("msg", args[0] if args else None)
    if message == tr.sync_collection_complete():
        return None
    return _original_tooltip(*args, **kwargs)


aqt.sync.tooltip = _quiet_success
