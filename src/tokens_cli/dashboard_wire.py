"""Compact, versioned wire encoding for the embedded Dashboard payload."""
import json
from collections import Counter


WIRE_VERSION = 1
_MARKER = "§"


def _base36(number):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if number == 0:
        return "0"
    out = []
    while number:
        number, remainder = divmod(number, 36)
        out.append(digits[remainder])
    return "".join(reversed(out))


def _count_strings(value, counts):
    if isinstance(value, str):
        counts[value] += 1
    elif isinstance(value, dict):
        for key, item in value.items():
            counts[str(key)] += 1
            _count_strings(item, counts)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _count_strings(item, counts)


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _string_table(payload):
    counts = Counter()
    _count_strings(payload, counts)
    candidates = sorted(
        counts.items(),
        key=lambda item: (item[1] * _json_size(item[0]), item[0]),
        reverse=True,
    )
    table = []
    for text, count in candidates:
        if count < 2 or text.startswith(_MARKER):
            continue
        ref = _MARKER + _base36(len(table))
        # The table stores one original copy. Only retain entries with a net win.
        if count * (_json_size(text) - _json_size(ref)) <= _json_size(text) + 1:
            continue
        table.append(text)
    return table


def _encode(value, indexes):
    if isinstance(value, str):
        if value in indexes:
            return _MARKER + _base36(indexes[value])
        return _MARKER + value if value.startswith(_MARKER) else value
    if isinstance(value, dict):
        return {
            _encode(str(key), indexes): _encode(item, indexes)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_encode(item, indexes) for item in value]
    return value


def encode_payload(payload):
    """Return a JSON-compatible wire object decoded by the inline browser script."""
    table = _string_table(payload)
    indexes = {text: index for index, text in enumerate(table)}
    return {
        "v": WIRE_VERSION,
        "s": table,
        "d": _encode(payload, indexes),
    }


def decode_payload(wire):
    """Python reference decoder used by tests and benchmarks."""
    if wire.get("v") != WIRE_VERSION:
        raise ValueError("unsupported dashboard wire version")
    table = wire["s"]

    def decode(value):
        if isinstance(value, str):
            if not value.startswith(_MARKER):
                return value
            if value.startswith(_MARKER * 2):
                return value[1:]
            return table[int(value[1:], 36)]
        if isinstance(value, dict):
            return {decode(key): decode(item) for key, item in value.items()}
        if isinstance(value, list):
            return [decode(item) for item in value]
        return value

    return decode(wire["d"])
