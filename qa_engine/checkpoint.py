"""Resumable checkpoint for analysis: persists each segment's ResolvedItem to a JSON
file keyed by segmentguid, so a long run that is interrupted (e.g. a Streamlit rerun
on a big file) resumes from where it left off instead of restarting from zero.

Keyed per input file via content_key() so different files use different caches.
Writes are atomic (write-tmp + os.replace) so an interrupted flush never corrupts it."""
import os
import json
import hashlib
from dataclasses import asdict
from .models import ResolvedItem, Resolution


def content_key(content: bytes) -> str:
    """Stable short key for a file's bytes — use in the checkpoint filename."""
    return hashlib.sha256(content).hexdigest()[:16]


def _item_from_dict(d: dict) -> ResolvedItem:
    fields = dict(d)
    fields["resolution"] = Resolution(**d["resolution"])
    return ResolvedItem(**fields)


class Checkpoint:
    """Per-segment result cache. `has`/`get_item` to resume; `save_item` then `flush`
    to persist (batch many saves, flush once per batch)."""

    def __init__(self, path=None):
        self.path = path
        self._data = {}      # segmentguid -> ResolvedItem-as-dict
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except Exception:
                self._data = {}   # corrupt/partial cache -> start fresh

    def has(self, guid) -> bool:
        return guid in self._data

    def get_item(self, guid):
        d = self._data.get(guid)
        return _item_from_dict(d) if d is not None else None

    def all_items(self):
        return [_item_from_dict(d) for d in self._data.values()]

    def save_item(self, item) -> None:
        self._data[item.segmentguid] = asdict(item)

    def flush(self) -> None:
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False)
        os.replace(tmp, self.path)   # atomic: never leaves a half-written cache

    def clear(self) -> None:
        self._data = {}
        if self.path and os.path.exists(self.path):
            os.remove(self.path)
