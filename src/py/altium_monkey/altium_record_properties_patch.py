"""
Apply property edits to a record's original ``KEY=VALUE|...`` text without re-formatting it.

Records rebuilt from typed fields come out in the builder's key order and number formatting
(``0.5mil`` -> ``0.5000mil``) and lose repeated keys, so one edited field would change the whole
property block. Comparing the builder's output for the parsed state with its output now isolates
the keys that really changed; only those are written into the original text.
"""

from __future__ import annotations


def _pairs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for segment in text.strip("\x00").split("|"):
        if "=" in segment:
            key, value = segment.split("=", 1)
            out[key] = value
    return out


def patch_properties_text(
    raw: bytes,
    built_at_parse: str,
    built_now: str,
    *,
    encoding: str = "ascii",
) -> bytes | None:
    """
    Return ``raw`` with the keys whose built value changed set to their new value, or None if
    the edit can't be expressed as a patch (a key was removed) and a full rebuild is needed.
    """
    before = _pairs(built_at_parse)
    after = _pairs(built_now)
    if any(key not in after for key in before):
        return None
    changed = {k: v for k, v in after.items() if before.get(k) != v}
    if not changed:
        return raw

    body = raw.rstrip(b"\x00")
    terminator = raw[len(body) :]
    segments = body.split(b"|")
    seen: set[str] = set()
    for i, segment in enumerate(segments):
        key, sep, _ = segment.partition(b"=")
        name = key.decode("latin-1")
        if sep and name in changed:
            segments[i] = key + b"=" + changed[name].encode(encoding, errors="replace")
            seen.add(name)
    for name, value in changed.items():
        if name not in seen:
            segments.append(f"{name}={value}".encode(encoding, errors="replace"))
    return b"|".join(segments) + terminator
