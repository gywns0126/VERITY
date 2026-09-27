"""Strict JSON contract for a member's private map document."""
import json
import math
import re
from decimal import Decimal


MAX_DOCUMENT_BYTES = 64 * 1024
MAX_LAYOUTS = 3
MAX_POSITIONS = 200
MAX_NOTES = 100
MAX_MARKS = 200
MAX_TEXT_CHARS = 2000
MAX_COORDINATE = 1_000_000
MAX_READ_REVISION = 2**53 - 1  # Exact across JSON and browser numbers.
_DISPOSITIONS = {"inbox", "later", "irrelevant"}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAP_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class InvalidDocument(ValueError):
    pass


def _object(value, allowed, required, where):
    if not isinstance(value, dict):
        raise InvalidDocument(f"{where}_must_be_object")
    keys = set(value)
    if keys - allowed or required - keys:
        raise InvalidDocument(f"{where}_fields_invalid")


def _identifier(value, where):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise InvalidDocument(f"{where}_invalid")


def _coordinate(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidDocument(f"{where}_invalid")
    if abs(value) > MAX_COORDINATE or not math.isfinite(value):
        raise InvalidDocument(f"{where}_invalid")


def document_storage_bytes(value):
    """UTF-8 size of PostgreSQL jsonb::text for the validated JSON we send.

    JSONB adds separator spaces and expands exponent notation. Key ordering
    changes neither length. Count numbers after Python's JSON normalization.
    """
    if isinstance(value, dict):
        return (2 + max(0, len(value) - 1) * 2
                + sum(document_storage_bytes(k) + 2 + document_storage_bytes(v)
                      for k, v in value.items()))
    if isinstance(value, list):
        return (2 + max(0, len(value) - 1) * 2
                + sum(document_storage_bytes(v) for v in value))
    if isinstance(value, float):
        number = Decimal(str(value))
        if number.is_zero():
            number = number.copy_abs()  # PostgreSQL numeric has no negative zero.
        return len(format(number, "f"))
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def validate_document(document):
    """Validate and return a JSON-serializable document; never accepts owner IDs."""
    _object(document, {"layouts"}, {"layouts"}, "document")
    layouts = document["layouts"]
    if not isinstance(layouts, list) or len(layouts) > MAX_LAYOUTS:
        raise InvalidDocument("layouts_limit")

    seen_keys = set()
    for layout in layouts:
        _object(layout, {"map_key", "positions", "notes", "marks"},
                {"map_key", "positions", "notes", "marks"}, "layout")
        key = layout["map_key"]
        if not isinstance(key, str) or not _MAP_KEY.fullmatch(key) or key in seen_keys:
            raise InvalidDocument("map_key_invalid")
        seen_keys.add(key)

        positions = layout["positions"]
        if not isinstance(positions, list) or len(positions) > MAX_POSITIONS:
            raise InvalidDocument("positions_limit")
        position_ids = set()
        for position in positions:
            _object(position, {"node_id", "x", "y"}, {"node_id", "x", "y"}, "position")
            node_id = position["node_id"]
            _identifier(node_id, "node_id")
            if node_id in position_ids:
                raise InvalidDocument("position_duplicate")
            position_ids.add(node_id)
            _coordinate(position["x"], "x")
            _coordinate(position["y"], "y")

        notes = layout["notes"]
        if not isinstance(notes, list) or len(notes) > MAX_NOTES:
            raise InvalidDocument("notes_limit")
        note_ids = set()
        for note in notes:
            _object(note, {"note_id", "anchor", "x", "y", "text", "done"},
                    {"note_id", "anchor", "x", "y", "text", "done"}, "note")
            note_id = note["note_id"]
            _identifier(note_id, "note_id")
            if note_id in note_ids:
                raise InvalidDocument("note_duplicate")
            note_ids.add(note_id)
            anchor = note["anchor"]
            if anchor is not None:
                _object(anchor, {"kind", "id"}, {"kind", "id"}, "anchor")
                if anchor["kind"] not in ("node", "edge"):
                    raise InvalidDocument("anchor_kind_invalid")
                _identifier(anchor["id"], "anchor_id")
            _coordinate(note["x"], "note_x")
            _coordinate(note["y"], "note_y")
            if (not isinstance(note["text"], str) or len(note["text"]) > MAX_TEXT_CHARS
                    or "\x00" in note["text"]):
                raise InvalidDocument("note_text_invalid")
            if not isinstance(note["done"], bool):
                raise InvalidDocument("note_done_invalid")

        marks = layout["marks"]
        if not isinstance(marks, dict) or len(marks) > MAX_MARKS:
            raise InvalidDocument("marks_limit")
        for item_id, mark in marks.items():
            _identifier(item_id, "mark_id")
            _object(mark, {"read_revision", "important", "disposition"},
                    {"read_revision", "important", "disposition"}, "mark")
            read_revision = mark["read_revision"]
            if (read_revision is not None and
                    (isinstance(read_revision, bool) or not isinstance(read_revision, int)
                     or not 1 <= read_revision < MAX_READ_REVISION)):
                raise InvalidDocument("mark_read_revision_invalid")
            if not isinstance(mark["important"], bool):
                raise InvalidDocument("mark_important_invalid")
            if (not isinstance(mark["disposition"], str)
                    or mark["disposition"] not in _DISPOSITIONS):
                raise InvalidDocument("mark_disposition_invalid")

    try:
        size = document_storage_bytes(document)
    except (TypeError, ValueError, UnicodeError):
        raise InvalidDocument("document_invalid")
    if size > MAX_DOCUMENT_BYTES:
        raise InvalidDocument("document_too_large")
    return document
