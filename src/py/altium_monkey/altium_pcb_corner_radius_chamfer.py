"""
Typed PCB CornerRadiusChamfer stream model.

Altium stores exact (fractional) pad corner-radius percentages outside the
Pads6 binary record:

- PcbDoc: top-level ``CornerRadiusChamfer`` section (uint32 record count in
  ``Header``, length-prefixed text records in ``Data``).
- PcbLib: one ``<Footprint>/CornerRadiusChamfer`` stream per footprint with a
  leading uint32 record count followed by the same length-prefixed records.

Each record is a pipe-delimited payload such as
``|SCR0.LAYER=TOP|SCR0.CRPCTEX=18.181818|PRIMITIVEINDEX=0`` where ``SCR``
stands for Stack Corner Radius and ``PRIMITIVEINDEX`` links the record to a
pad primitive. The rounded integer percent is still stored in the pad's
SubRecord 6 lane; this stream carries the exact value.
"""

from __future__ import annotations

import re
import struct

from typing import Sequence

from .altium_pcb_property_helpers import (
    clean_pcb_property_text as _clean_text,
    parse_pcb_int_token as _parse_int_token,
    parse_pcb_property_payload,
    PcbLengthPrefixedPropertyRecordMixin,
)
from .altium_record_pcb__pad import AltiumPcbPad


class AltiumPcbCornerRadiusChamfer(PcbLengthPrefixedPropertyRecordMixin):
    """
    Typed wrapper for one CornerRadiusChamfer record.
    """

    def __init__(self) -> None:
        self.properties: dict[str, str] = {}
        self.primitive_index: int | None = None
        # (layer_token, crpctex_token) pairs in SCR<index> order. Tokens are
        # kept verbatim as text so unmodified records round-trip byte-exactly.
        self.stack_entries: list[tuple[str, str]] = []
        self.raw_record_payload: bytes | None = None
        self._typed_signature_at_parse: tuple | None = None
        self._properties_raw_signature: tuple | None = None
        # Pad this record was attached to at parse time; followed by identity so
        # PRIMITIVEINDEX can be re-pointed when primitives are added or removed.
        self._target_pad: AltiumPcbPad | None = None

    @classmethod
    def from_payload(cls, payload: bytes) -> "AltiumPcbCornerRadiusChamfer":
        item = cls()
        item.raw_record_payload = bytes(payload)
        item.properties = parse_pcb_property_payload(payload)
        item._load_typed_fields_from_properties()
        item._typed_signature_at_parse = item._typed_signature()
        item._properties_raw_signature = item._properties_signature()
        return item

    def exact_percent_for_layer_token(self, layer_token: str) -> float | None:
        """
        Return the exact corner percent for a layer token such as ``TOP``.
        """
        wanted = str(layer_token or "").strip().upper()
        for token, percent_token in self.stack_entries:
            if token.strip().upper() != wanted:
                continue
            try:
                return float(percent_token)
            except ValueError:
                return None
        return None

    def _load_typed_fields_from_properties(self) -> None:
        props = self.properties or {}
        self.primitive_index = _parse_int_token(props.get("PRIMITIVEINDEX", ""))
        entries: list[tuple[str, str]] = []
        index = 0
        while True:
            layer_key = f"SCR{index}.LAYER"
            percent_key = f"SCR{index}.CRPCTEX"
            if layer_key not in props and percent_key not in props:
                break
            entries.append(
                (
                    _clean_text(props.get(layer_key, "")),
                    _clean_text(props.get(percent_key, "")),
                )
            )
            index += 1
        self.stack_entries = entries

    def _sync_typed_fields_to_properties(self) -> None:
        # Update in place so key order and lanes this model does not interpret
        # (for example SCRn.CRSIZE absolute corner sizes) survive a rewrite.
        props: dict[str, str] = dict(self.properties or {})
        count = len(self.stack_entries)
        for key in list(props):
            match = re.match(r"SCR(\d+)\.", key)
            if match is not None and int(match.group(1)) >= count:
                del props[key]
        for index, (layer_token, percent_token) in enumerate(self.stack_entries):
            props[f"SCR{index}.LAYER"] = str(layer_token)
            percent_key = f"SCR{index}.CRPCTEX"
            if str(percent_token) != "" or percent_key in props:
                props[percent_key] = str(percent_token)
        if self.primitive_index is not None:
            props["PRIMITIVEINDEX"] = str(int(self.primitive_index))
        else:
            props.pop("PRIMITIVEINDEX", None)
        self.properties = props

    def _typed_signature(self) -> tuple:
        return (self.primitive_index, tuple(self.stack_entries))

    def _properties_signature(self) -> tuple:
        return tuple(
            (str(key), str(value)) for key, value in (self.properties or {}).items()
        )


def parse_corner_radius_chamfer_records(
    raw: bytes,
) -> list[AltiumPcbCornerRadiusChamfer]:
    """
    Parse bare length-prefixed CornerRadiusChamfer records (PcbDoc Data).
    """
    out: list[AltiumPcbCornerRadiusChamfer] = []
    pos = 0
    total = len(raw or b"")
    while pos + 4 <= total:
        record_len = int.from_bytes(raw[pos : pos + 4], byteorder="little")
        pos += 4
        if record_len <= 0 or pos + record_len > total:
            break
        payload = raw[pos : pos + record_len]
        pos += record_len
        out.append(AltiumPcbCornerRadiusChamfer.from_payload(payload))
    return out


def parse_corner_radius_chamfer_footprint_stream(
    raw: bytes,
) -> list[AltiumPcbCornerRadiusChamfer]:
    """
    Parse a PcbLib per-footprint stream: uint32 record count plus records.
    """
    data = raw or b""
    if len(data) < 4:
        return []
    return parse_corner_radius_chamfer_records(data[4:])


def serialize_corner_radius_chamfer_records(
    items: list[AltiumPcbCornerRadiusChamfer],
) -> bytes:
    """
    Serialize records for a PcbDoc CornerRadiusChamfer/Data stream.
    """
    return b"".join(item.serialize_record() for item in items)


def serialize_corner_radius_chamfer_footprint_stream(
    items: list[AltiumPcbCornerRadiusChamfer],
) -> bytes:
    """
    Serialize a PcbLib per-footprint stream (uint32 count plus records).
    """
    return struct.pack("<I", len(items)) + serialize_corner_radius_chamfer_records(
        items
    )


def attach_corner_radius_chamfer_to_pads(
    records: list[AltiumPcbCornerRadiusChamfer],
    primitives: Sequence[object],
) -> None:
    """
    Copy exact percents onto pads addressed by ``PRIMITIVEINDEX``.

    ``primitives`` defines the index addressing space: the footprint record
    order for PcbLib streams and the document pad list for PcbDoc sections.
    """
    for record in records:
        index = record.primitive_index
        if index is None or not 0 <= index < len(primitives):
            continue
        primitive = primitives[index]
        if not isinstance(primitive, AltiumPcbPad):
            continue
        record._target_pad = primitive
        for layer_token, percent_token in record.stack_entries:
            try:
                value = float(percent_token)
            except ValueError:
                continue
            token = layer_token.strip().upper()
            primitive.exact_corner_radius_percent_by_layer[token] = value


def _expected_corner_entries(
    primitives: Sequence[object],
) -> list[tuple[int, tuple[tuple[str, float], ...]]]:
    expected: list[tuple[int, tuple[tuple[str, float], ...]]] = []
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, AltiumPcbPad):
            continue
        exact = primitive.exact_corner_radius_percent_by_layer
        if not exact:
            continue
        expected.append(
            (
                index,
                tuple((str(token), float(value)) for token, value in exact.items()),
            )
        )
    return expected


def _record_semantic_entries(
    record: AltiumPcbCornerRadiusChamfer,
) -> tuple[tuple[str, float], ...] | None:
    entries: list[tuple[str, float]] = []
    for layer_token, percent_token in record.stack_entries:
        try:
            entries.append((layer_token.strip().upper(), float(percent_token)))
        except ValueError:
            return None
    return tuple(entries)


def corner_radius_chamfer_records_for_pads(
    existing: list[AltiumPcbCornerRadiusChamfer],
    primitives: Sequence[object],
) -> list[AltiumPcbCornerRadiusChamfer]:
    """
    Return save-ready records for the pads in ``primitives``.

    Unmodified records are returned unchanged so files round-trip
    byte-faithfully. Records follow their pad by identity: they are re-pointed
    when primitives move, dropped only when their pad is removed, and rebuilt
    only when the pad's exact percent values were edited. Records whose lanes
    this model does not interpret (for example ``SCRn.CRSIZE``) and records that
    cannot be attributed to a pad are preserved verbatim.
    """
    index_by_id = {id(primitive): i for i, primitive in enumerate(primitives)}
    out: list[AltiumPcbCornerRadiusChamfer] = []
    covered: set[int] = set()
    changed = False
    for record in existing:
        target = record._target_pad
        if target is None:
            index = record.primitive_index
            if (
                index is not None
                and 0 <= index < len(primitives)
                and isinstance(primitives[index], AltiumPcbPad)
            ):
                target = primitives[index]
        if target is None:
            out.append(record)
            continue
        new_index = index_by_id.get(id(target))
        if new_index is None:
            changed = True
            continue
        covered.add(id(target))
        semantic = _record_semantic_entries(record)
        if semantic:
            exact = tuple(
                (str(token), float(value))
                for token, value in target.exact_corner_radius_percent_by_layer.items()
            )
            if semantic != exact:
                changed = True
                if exact:
                    out.append(
                        build_corner_radius_chamfer_record(
                            primitive_index=new_index, entries=list(exact)
                        )
                    )
                continue
        if new_index != record.primitive_index:
            record.primitive_index = new_index
            changed = True
        out.append(record)
    for index, entries in _expected_corner_entries(primitives):
        if id(primitives[index]) not in covered:
            out.append(
                build_corner_radius_chamfer_record(
                    primitive_index=index, entries=list(entries)
                )
            )
            changed = True
    return out if changed else existing


def build_corner_radius_chamfer_record(
    *,
    primitive_index: int,
    entries: list[tuple[str, float]],
) -> AltiumPcbCornerRadiusChamfer:
    """
    Build one CornerRadiusChamfer record from (layer_token, percent) pairs.

    Percent values use the native six-decimal text format (for example
    ``18.181818`` or ``50.000000``).
    """
    item = AltiumPcbCornerRadiusChamfer()
    item.primitive_index = int(primitive_index)
    item.stack_entries = [
        (str(layer_token), f"{float(percent):.6f}") for layer_token, percent in entries
    ]
    item._sync_typed_fields_to_properties()
    item._typed_signature_at_parse = item._typed_signature()
    item._properties_raw_signature = item._properties_signature()
    item.raw_record_payload = None
    return item
