"""Bounded, incremental JSON validation and Claude-event projection.

Only ``finish_line()`` returns a candidate.  This module deliberately has no file,
configuration, or collection dependencies.  Limits are engineering accounting,
not an estimate of Python RSS.  Unselected data is validated without retaining
its strings, keys, or number spellings.
"""

import codecs
import io
import json
import re
import sys


class BadJSON(ValueError):
    """A malformed physical line; the exception never includes input data."""

    def __init__(self):
        super().__init__("bad_json")


class ProjectionLimit(ValueError):
    """An engineering guard, distinct from an ignorable malformed line."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


_DROP, _FULL, _ROOT, _MESSAGE, _USAGE = range(5)
_FIELDS = {
    _ROOT: ("type", "timestamp", "sessionId", "cwd", "message"),
    _MESSAGE: ("model", "id", "usage"),
    _USAGE: (
        "input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ),
}
_SPACE = " \t\r\n"
_STRING_SPECIAL = re.compile(r'["\\\x00-\x1f]')
_DIGITS = re.compile(r"[0-9]+")
_HEX = frozenset("0123456789abcdefABCDEF")
_ESCAPES = {
    '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
    "n": "\n", "r": "\r", "t": "\t",
}
_CHUNK_BYTES = 64 * 1024


def _utf8_size(text):
    return len(text.encode("utf-8", "surrogatepass"))


class _Value:
    __slots__ = ("value", "bytes", "nodes")

    def __init__(self, value):
        self.value = value
        self.bytes = 128
        self.nodes = 1


class _Member:
    __slots__ = ("key", "child")

    def __init__(self, key):
        self.key = key
        self.child = None


class _Frame:
    __slots__ = ("kind", "mode", "node", "state", "members", "key")

    def __init__(self, kind, mode, node):
        self.kind = kind
        self.mode = mode
        self.node = node
        self.state = "key_or_end" if kind == "object" else "value_or_end"
        self.members = {} if node is not None and kind == "object" else None
        self.key = None


class _String:
    __slots__ = (
        "is_key", "node", "builder", "candidates", "position", "bytes",
        "escape", "hex_value", "hex_count", "high",
    )

    def __init__(self, is_key, node, retain, candidates=()):
        self.is_key = is_key
        self.node = node
        self.builder = io.StringIO() if retain else None
        self.candidates = candidates
        self.position = 0
        self.bytes = 0
        self.escape = "normal"
        self.hex_value = 0
        self.hex_count = 0
        self.high = None


class _Number:
    __slots__ = ("node", "builder", "bytes", "state", "digits", "floating")

    def __init__(self, node):
        self.node = node
        self.builder = io.StringIO() if node is not None else None
        self.bytes = 0
        self.state = "start"
        self.digits = 0
        self.floating = False


class _Literal:
    __slots__ = ("node", "word", "position", "numeric", "bytes")

    def __init__(self, node, word, position=0):
        self.node = node
        self.word = word
        self.position = position
        self.numeric = word in ("NaN", "Infinity", "-Infinity")
        self.bytes = position if self.numeric and node is not None else 0


class ProjectionParser:
    """Validate one UTF-8 physical line and retain only event-relevant values.

    ``feed`` accepts bytes, bytearray, and contiguous memoryview objects, does
    not retain the input buffer, and always returns None.  The parser is single
    use: ``finish_line`` flushes UTF-8 replacement decoding and returns the
    projection only after validating the entire line.  Valid non-object roots
    return None.  Empty lines raise BadJSON, as do subsequent calls after finish.

    Root/message/usage objects retain their fixed field sets.  Selected leaves,
    and non-object message/usage values, retain their complete JSON value/type.
    Limits can be reduced for synthetic tests.  ``stats`` returns a snapshot;
    byte/node counters include in-progress selected values and decoded keys.
    Each punctuation, string/key, number, or literal is one token; EOF is not.
    """

    def __init__(
        self, *, max_depth=256, max_tokens=2_000_000,
        max_projection_bytes=8 * 1024 * 1024,
        max_projection_nodes=65_536, max_number_bytes=64 * 1024,
    ):
        limits = (
            max_depth, max_tokens, max_projection_bytes,
            max_projection_nodes, max_number_bytes,
        )
        if any(type(limit) is not int or limit < 0 for limit in limits):
            raise ValueError("invalid_parser_limit")
        self.max_depth = max_depth
        self.max_tokens = max_tokens
        self.max_projection_bytes = max_projection_bytes
        self.max_projection_nodes = max_projection_nodes
        self.max_number_bytes = max_number_bytes
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._stack = []
        self._lex = None
        self._root = None
        self._root_done = False
        self._finished = False
        self._failure = None
        self._bytes = self._nodes = self._tokens = 0
        self._peak_bytes = self._peak_nodes = self._peak_depth = 0
        self._peak_number = self._peak_key = self._peak_string = 0

    @property
    def stats(self):
        return {
            "tokens": self._tokens,
            "peak_tokens": self._tokens,
            "depth": len(self._stack),
            "peak_depth": self._peak_depth,
            "projection_bytes": self._bytes,
            "peak_projection_bytes": self._peak_bytes,
            "projection_nodes": self._nodes,
            "peak_projection_nodes": self._peak_nodes,
            "peak_number_bytes": self._peak_number,
            "peak_key_bytes": self._peak_key,
            "peak_string_bytes": self._peak_string,
        }

    def _check_active(self):
        if self._failure is not None:
            if self._failure == "bad_json":
                raise BadJSON()
            raise ProjectionLimit(self._failure)
        if self._finished:
            raise BadJSON()

    def _discard_after_error(self, error):
        # Store a fixed code, not an exception/traceback retaining input buffers.
        self._failure = (
            error.reason if isinstance(error, ProjectionLimit) else "bad_json"
        )
        self._stack.clear()
        self._lex = self._root = None
        self._bytes = self._nodes = 0
        self._decoder.reset()

    def feed(self, data):
        self._check_active()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("feed_requires_bytes_like")
        view = memoryview(data).cast("B")
        try:
            # A caller may hand over its entire small-line buffer.  Decoding
            # still uses bounded pieces and never saves a reference to it.
            for offset in range(0, len(view), _CHUNK_BYTES):
                text = self._decoder.decode(view[offset:offset + _CHUNK_BYTES])
                self._consume(text)
        except (BadJSON, ProjectionLimit) as error:
            self._discard_after_error(error)
            raise
        finally:
            # Release the exported buffer even on error paths, so the caller
            # can clear its bytearray without hitting BufferError.
            view.release()
        return None

    def finish_line(self):
        self._check_active()
        try:
            self._consume(self._decoder.decode(b"", final=True))
            if isinstance(self._lex, _Number):
                self._finish_number()
            if self._lex is not None or self._stack or not self._root_done:
                raise BadJSON()
            self._finished = True
            return self._root.value if self._root is not None else None
        except (BadJSON, ProjectionLimit) as error:
            self._discard_after_error(error)
            raise

    def _charge(self, amount, nodes=0):
        if (self._bytes + amount > self.max_projection_bytes or
                self._nodes + nodes > self.max_projection_nodes):
            raise ProjectionLimit("json_projection_limit")
        self._bytes += amount
        self._nodes += nodes
        self._peak_bytes = max(self._peak_bytes, self._bytes)
        self._peak_nodes = max(self._peak_nodes, self._nodes)

    def _release(self, amount, nodes=0):
        self._bytes -= amount
        self._nodes -= nodes

    def _token(self):
        if self._tokens >= self.max_tokens:
            raise ProjectionLimit("json_token_limit")
        self._tokens += 1

    def _new_value(self, mode, value=None):
        if mode == _DROP:
            return None
        self._charge(128, 1)
        return _Value(value)

    def _value_mode(self):
        if not self._stack:
            return _ROOT
        frame = self._stack[-1]
        if frame.mode == _DROP or (frame.kind == "object" and frame.key is None):
            return _DROP
        if frame.mode == _ROOT:
            return _MESSAGE if frame.key == "message" else _FULL
        if frame.mode == _MESSAGE:
            return _USAGE if frame.key == "usage" else _FULL
        return _FULL

    def _accept_value(self, node):
        if not self._stack:
            self._root = node
            self._root_done = True
            return
        frame = self._stack[-1]
        if node is not None:
            if frame.kind == "object":
                frame.node.value[frame.key] = node.value
                frame.members[frame.key].child = node
            else:
                frame.node.value.append(node.value)
            frame.node.bytes += node.bytes
            frame.node.nodes += node.nodes
        frame.key = None
        frame.state = "comma_or_end"

    def _start_value(self, char):
        mode = self._value_mode()
        self._token()
        if char in "{[":
            if len(self._stack) >= self.max_depth:
                raise ProjectionLimit("json_depth_limit")
            if char == "[":
                # A non-object root is unselected, but selected exceptional
                # message/usage arrays must keep their full truthiness/type.
                mode = _DROP if mode == _ROOT else (_FULL if mode != _DROP else _DROP)
            node = self._new_value(mode, {} if char == "{" else [])
            self._stack.append(_Frame("object" if char == "{" else "array", mode, node))
            self._peak_depth = max(self._peak_depth, len(self._stack))
        else:
            if mode == _ROOT:
                mode = _DROP
            elif mode != _DROP:
                mode = _FULL
            node = self._new_value(mode)
            if char == '"':
                self._lex = _String(False, node, node is not None)
            elif char == "-" or "0" <= char <= "9":
                self._lex = _Number(node)
                self._number_piece(char)
                if char == "-":
                    self._lex.state = "sign"
                else:
                    self._lex.state = "zero" if char == "0" else "int"
                    self._lex.digits = 1
            elif char in "tfnNI":
                word = {
                    "t": "true", "f": "false", "n": "null",
                    "N": "NaN", "I": "Infinity",
                }[char]
                self._lex = _Literal(node, word)
                self._literal_piece(1)
            else:
                raise BadJSON()

    def _start_key(self):
        self._token()
        frame = self._stack[-1]
        if frame.mode == _FULL:
            # Even an as-yet unidentified duplicate key is simultaneously live
            # with the old member while being decoded.
            self._charge(64)
            self._lex = _String(True, None, True)
        else:
            self._lex = _String(True, None, False, _FIELDS.get(frame.mode, ()))

    def _finish_key(self, token):
        frame = self._stack[-1]
        if frame.mode == _FULL:
            key = token.builder.getvalue()
            temporary = 64 + token.bytes
            member = frame.members.get(key)
            if member is None:
                member = _Member(key)
                frame.members[key] = member
                frame.node.bytes += temporary
            else:
                self._release(temporary)
        else:
            key = next((name for name in token.candidates if len(name) == token.position), None)
            if key is None:
                frame.key = None
                frame.state = "colon"
                return
            member = frame.members.get(key)
            if member is None:
                key_bytes = _utf8_size(key)
                self._charge(64 + key_bytes)
                self._peak_key = max(self._peak_key, key_bytes)
                member = _Member(key)
                frame.members[key] = member
                frame.node.bytes += 64 + key_bytes
        if member.child is not None:
            old = member.child
            # Release the *whole* previous value before constructing its
            # replacement; duplicate objects are never merged.
            frame.node.value.pop(member.key)
            frame.node.bytes -= old.bytes
            frame.node.nodes -= old.nodes
            self._release(old.bytes, old.nodes)
            member.child = None
        frame.key = member.key
        frame.state = "colon"

    def _string_piece(self, piece, prepaid=0):
        token = self._lex
        if token.builder is not None:
            amount = _utf8_size(piece) - prepaid
            self._charge(amount)
            token.bytes += amount
            if token.is_key:
                self._peak_key = max(self._peak_key, token.bytes)
            else:
                token.node.bytes += amount
                self._peak_string = max(self._peak_string, token.bytes)
            token.builder.write(piece)
        elif token.is_key and token.candidates:
            token.candidates = tuple(
                name for name in token.candidates
                if name.startswith(piece, token.position)
            )
            # Once all fixed candidates have failed, neither the length nor
            # the contents of a huge unknown key need to be remembered.
            if token.candidates:
                token.position += len(piece)

    def _flush_high(self):
        token = self._lex
        if token.high is not None:
            self._string_piece(chr(token.high), prepaid=3)
            token.high = None

    def _unicode_unit(self, unit):
        token = self._lex
        if token.high is not None:
            if 0xDC00 <= unit <= 0xDFFF:
                combined = 0x10000 + ((token.high - 0xD800) << 10) + unit - 0xDC00
                token.high = None
                self._string_piece(chr(combined), prepaid=3)
                return
            self._flush_high()
        if 0xD800 <= unit <= 0xDBFF:
            # A pending decoded surrogate is already a live string fragment.
            # Charge its three surrogatepass bytes before remembering it; a
            # following low surrogate needs only the remaining one byte.
            if token.builder is not None:
                self._charge(3)
                token.bytes += 3
                if token.is_key:
                    self._peak_key = max(self._peak_key, token.bytes)
                else:
                    token.node.bytes += 3
                    self._peak_string = max(self._peak_string, token.bytes)
            token.high = unit
        else:
            self._string_piece(chr(unit))

    def _consume_string(self, text, position):
        token = self._lex
        end = len(text)
        while position < end:
            if token.escape == "normal":
                match = _STRING_SPECIAL.search(text, position)
                stop = match.start() if match is not None else end
                if stop > position:
                    self._flush_high()
                    if token.builder is not None or token.candidates:
                        self._string_piece(text[position:stop])
                    position = stop
                if position == end:
                    break
                char = text[position]
                position += 1
                if char == '"':
                    self._flush_high()
                    self._lex = None
                    if token.is_key:
                        self._finish_key(token)
                    else:
                        if token.node is not None:
                            token.node.value = token.builder.getvalue()
                        self._accept_value(token.node)
                    return position
                if char == "\\":
                    token.escape = "escape"
                else:
                    raise BadJSON()
            elif token.escape == "escape":
                char = text[position]
                position += 1
                if char == "u":
                    token.escape = "unicode"
                    token.hex_value = token.hex_count = 0
                elif char in _ESCAPES:
                    self._flush_high()
                    self._string_piece(_ESCAPES[char])
                    token.escape = "normal"
                else:
                    raise BadJSON()
            else:
                char = text[position]
                position += 1
                if char not in _HEX:
                    raise BadJSON()
                token.hex_value = token.hex_value * 16 + int(char, 16)
                token.hex_count += 1
                if token.hex_count == 4:
                    self._unicode_unit(token.hex_value)
                    token.escape = "normal"
        return position

    def _number_piece(self, piece):
        token = self._lex
        if token.node is None:
            return
        amount = len(piece)
        if token.bytes + amount > self.max_number_bytes:
            raise ProjectionLimit("json_number_limit")
        self._charge(amount)
        token.bytes += amount
        token.node.bytes += amount
        self._peak_number = max(self._peak_number, token.bytes)
        token.builder.write(piece)

    def _finish_number(self):
        token = self._lex
        if token.state not in ("zero", "int", "frac", "exp"):
            raise BadJSON()
        if not token.floating:
            get_limit = getattr(sys, "get_int_max_str_digits", None)
            limit = get_limit() if get_limit is not None else 0
            if limit and token.digits > limit:
                raise BadJSON()
        if token.node is not None:
            raw = token.builder.getvalue()
            try:
                token.node.value = float(raw) if token.floating else int(raw)
            except (ValueError, OverflowError):
                raise BadJSON() from None
        self._lex = None
        self._accept_value(token.node)

    def _consume_number(self, text, position):
        token = self._lex
        end = len(text)
        while position < end:
            char = text[position]
            state = token.state
            if state == "sign" and char == "I":
                # The minus was already charged as part of this one token.
                self._lex = _Literal(token.node, "-Infinity", 1)
                return position
            if state in ("sign", "dot", "exp_start", "exp_sign"):
                if state == "exp_start" and char in "+-":
                    self._number_piece(char)
                    token.state = "exp_sign"
                    position += 1
                    continue
                if not "0" <= char <= "9":
                    raise BadJSON()
                if state == "sign":
                    self._number_piece(char)
                    token.digits = 1
                    token.state = "zero" if char == "0" else "int"
                    position += 1
                    continue
                token.state = "frac" if state == "dot" else "exp"
                # Consume this digit and any subsequent run below.
                state = token.state
            if state in ("int", "frac", "exp") and "0" <= char <= "9":
                match = _DIGITS.match(text, position)
                stop = match.end()
                if token.node is not None:
                    self._number_piece(text[position:stop])
                if state == "int":
                    token.digits += stop - position
                position = stop
                continue
            if state in ("zero", "int") and char == ".":
                self._number_piece(char)
                token.floating = True
                token.state = "dot"
                position += 1
            elif state in ("zero", "int", "frac") and char in "eE":
                self._number_piece(char)
                token.floating = True
                token.state = "exp_start"
                position += 1
            else:
                self._finish_number()
                return position
        return position

    def _literal_piece(self, amount):
        token = self._lex
        if token.numeric and token.node is not None:
            if token.bytes + amount > self.max_number_bytes:
                raise ProjectionLimit("json_number_limit")
            self._charge(amount)
            token.bytes += amount
            token.node.bytes += amount
            self._peak_number = max(self._peak_number, token.bytes)
        token.position += amount

    def _consume_literal(self, text, position):
        token = self._lex
        amount = min(len(token.word) - token.position, len(text) - position)
        if text[position:position + amount] != token.word[token.position:token.position + amount]:
            raise BadJSON()
        self._literal_piece(amount)
        position += amount
        if token.position == len(token.word):
            if token.node is not None:
                # Use the decoder's shared NaN object: its identity affects
                # first-wins ID and fallback-tuple deduplication.
                token.node.value = json.loads(token.word)
            self._lex = None
            self._accept_value(token.node)
        return position

    def _close(self, char):
        frame = self._stack[-1]
        if char != ("}" if frame.kind == "object" else "]"):
            raise BadJSON()
        self._token()
        self._stack.pop()
        self._accept_value(frame.node)

    def _consume(self, text):
        position = 0
        end = len(text)
        while position < end:
            if isinstance(self._lex, _String):
                position = self._consume_string(text, position)
                continue
            if isinstance(self._lex, _Number):
                position = self._consume_number(text, position)
                continue
            if isinstance(self._lex, _Literal):
                position = self._consume_literal(text, position)
                continue
            char = text[position]
            if not self._stack:
                # This exactly models decode(...).strip(): Unicode whitespace
                # is allowed only outside the root, never inside a container.
                if char.isspace():
                    position += 1
                    continue
                if self._root_done:
                    raise BadJSON()
                self._start_value(char)
                position += 1
                continue
            frame = self._stack[-1]
            if char in _SPACE:
                position += 1
                continue
            state = frame.state
            if state in ("key_or_end", "key"):
                if char == "}" and state == "key_or_end":
                    self._close(char)
                elif char == '"':
                    self._start_key()
                else:
                    raise BadJSON()
            elif state == "colon":
                if char != ":":
                    raise BadJSON()
                self._token()
                frame.state = "value"
            elif state in ("value_or_end", "value"):
                if char == "]" and state == "value_or_end":
                    self._close(char)
                else:
                    self._start_value(char)
            else:
                if char == ",":
                    self._token()
                    frame.state = "key" if frame.kind == "object" else "value"
                else:
                    self._close(char)
            position += 1
