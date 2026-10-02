"""Round-trip fidelity of parsed PcbLib footprints: stored name headers, CornerRadiusChamfer lanes this
model does not interpret (SCRn.CRSIZE), and Data streams with bytes the parser cannot read."""

import struct

import pytest

from altium_monkey.altium_pcb_corner_radius_chamfer import (
    AltiumPcbCornerRadiusChamfer,
    attach_corner_radius_chamfer_to_pads,
    corner_radius_chamfer_records_for_pads,
    serialize_corner_radius_chamfer_footprint_stream,
)
from altium_monkey.altium_pcblib import AltiumPcbFootprint
from altium_monkey.altium_record_pcb__pad import AltiumPcbPad
from altium_monkey.altium_record_pcb__track import AltiumPcbTrack


def _name_header(name: str) -> bytes:
    pascal = bytes([len(name)]) + name.encode("ascii")
    return struct.pack("<I", len(pascal)) + pascal


def _track_record() -> bytes:
    track = AltiumPcbTrack()
    track.layer = 33
    track.end_x = 100000
    track.width = 10000
    return track.serialize_to_binary()


def _crsize_record(index: int) -> AltiumPcbCornerRadiusChamfer:
    payload = f"|SCR0.LAYER=TOP|SCR0.CRSIZE=19685|PRIMITIVEINDEX={index}\x00".encode()
    return AltiumPcbCornerRadiusChamfer.from_payload(payload)


def test_stored_name_header_is_kept_until_rename() -> None:
    data = _name_header("PART_LOCK") + _track_record()
    footprint = AltiumPcbFootprint.from_data_stream("PART", data)

    assert footprint.serialize_data_stream() == data

    footprint.name = "RENAMED"
    assert footprint.serialize_data_stream().startswith(_name_header("RENAMED"))


def test_crsize_records_survive_untouched() -> None:
    pads = [AltiumPcbPad(), AltiumPcbPad()]
    records = [_crsize_record(0), _crsize_record(1)]
    attach_corner_radius_chamfer_to_pads(records, pads)

    assert corner_radius_chamfer_records_for_pads(records, pads) is records


def test_crsize_records_follow_their_pad_when_primitives_move() -> None:
    track, pad_a, pad_b = AltiumPcbTrack(), AltiumPcbPad(), AltiumPcbPad()
    records = [_crsize_record(1), _crsize_record(2)]
    attach_corner_radius_chamfer_to_pads(records, [track, pad_a, pad_b])

    saved = corner_radius_chamfer_records_for_pads(records, [pad_a, pad_b])

    assert [r.primitive_index for r in saved] == [0, 1]
    stream = serialize_corner_radius_chamfer_footprint_stream(saved)
    assert stream.count(b"SCR0.CRSIZE=19685") == 2
    assert b"PRIMITIVEINDEX=0" in stream and b"PRIMITIVEINDEX=1" in stream


def test_crsize_record_dropped_only_with_its_pad() -> None:
    pad_a, pad_b = AltiumPcbPad(), AltiumPcbPad()
    records = [_crsize_record(0), _crsize_record(1)]
    attach_corner_radius_chamfer_to_pads(records, [pad_a, pad_b])

    saved = corner_radius_chamfer_records_for_pads(records, [pad_b])

    assert len(saved) == 1
    assert saved[0].primitive_index == 0
    assert saved[0].properties["SCR0.CRSIZE"] == "19685"


def test_unparsed_bytes_are_saved_verbatim_and_edits_refused() -> None:
    data = _name_header("PART") + _track_record() + b"\xee\xee"
    footprint = AltiumPcbFootprint.from_data_stream("PART", data)

    assert footprint._data_stream_for_save() == data

    footprint.tracks[0].width += 10000
    with pytest.raises(ValueError, match="could not be parsed"):
        footprint._data_stream_for_save()
