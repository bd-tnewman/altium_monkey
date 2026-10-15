"""In-place edits of a parsed PcbLib footprint (AltiumPcbLib.edit_footprint): only the edited
footprint's index-dependent streams may change, and surviving primitives keep their identities."""

import struct
import uuid
from pathlib import Path

import pytest

from altium_monkey import AltiumPcbLib
from altium_monkey.altium_ole import AltiumOleFile


def _streams(path: Path) -> dict[str, bytes]:
    with AltiumOleFile(str(path)) as ole:
        return {"/".join(p): ole.openstream(p) for p in ole.listdir()}


def _guids(data: bytes) -> list[tuple[int, int, uuid.UUID]]:
    return [
        (*struct.unpack("<II", data[i : i + 8]), uuid.UUID(bytes_le=data[i + 8 : i + 24]))
        for i in range(0, len(data), 24)
    ]


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    library = AltiumPcbLib()
    for name in ("FP_A", "FP_B"):
        fp = library.add_footprint(name)
        fp.add_pad(designator="1", position_mils=(-50, 0), width_mils=40, height_mils=60, layer="TOP")
        fp.add_pad(designator="2", position_mils=(50, 0), width_mils=40, height_mils=60, layer="TOP")
        fp.add_track((-80, -40), (80, -40), width_mils=5, layer="TOPOVERLAY")
        fp.add_track((-80, 40), (80, 40), width_mils=5, layer="TOPOVERLAY")
        fp.add_text(text="REF", position_mils=(0, 60), height_mils=30, layer="TOPOVERLAY")
    path = tmp_path / "source.PcbLib"
    library.save(path)
    return path


def test_edit_mode_without_changes_is_byte_identical(source: Path, tmp_path: Path) -> None:
    library = AltiumPcbLib(source)
    for fp in library.footprints:
        library.edit_footprint(fp)
    out = tmp_path / "noop.PcbLib"
    library.save(out)

    assert _streams(out) == _streams(source)


def test_edits_touch_only_the_edited_footprint(source: Path, tmp_path: Path) -> None:
    before = _streams(source)
    library = AltiumPcbLib(source)
    fp = library.edit_footprint("FP_A")
    pad_2 = fp.pads[1]
    pad_2_guid = next(g for t, i, g in _guids(before["FP_A/PrimitiveGuids/Data"]) if t == 2 and i == 1)
    unique_ids = before["FP_A/UniqueIDPrimitiveInformation/Data"]

    fp.remove_primitive(fp.pads[0])
    fp.remove_primitive(fp.tracks[0])
    fp.add_track((0, 0), (40, 0), width_mils=4, layer="MECHANICAL15")
    fp.add_arc(center_mils=(0, 0), radius_mils=10, start_angle_degrees=0,
               end_angle_degrees=360, width_mils=4, layer="MECHANICAL15")
    fp.add_text(text=".Designator", position_mils=(0, 0), height_mils=20, layer="MECHANICAL15")
    out = tmp_path / "edited.PcbLib"
    library.save(out)

    after = _streams(out)
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    assert changed and all(k.startswith("FP_A/") for k in changed)

    reopened = AltiumPcbLib(out).find_footprint("FP_A")
    assert [p.designator for p in reopened.pads] == ["2"]
    assert len(reopened.tracks) == 2 and len(reopened.arcs) == 1
    assert sorted(t.text_content for t in reopened.texts) == [".Designator", "REF"]

    guids = _guids(after["FP_A/PrimitiveGuids/Data"])
    # Altium's layout: the component GUID first, records grouped by type (arc 1, pad 2, track 4, text 5).
    assert guids[0][0] == 0x55
    assert [t for t, _, _ in guids[1:]] == [1, 2, 4, 4, 5, 5]
    assert (2, 1, pad_2_guid) in guids
    assert len(guids) == len(reopened._record_order) + 1
    unique_id_2 = unique_ids.split(b"PRIMITIVEINDEX=1|PRIMITIVEOBJECTID=Pad|UNIQUEID=")[1][:8]
    assert b"PRIMITIVEINDEX=1|PRIMITIVEOBJECTID=Pad|UNIQUEID=" + unique_id_2 in after[
        "FP_A/UniqueIDPrimitiveInformation/Data"
    ]
    assert reopened.pads[0] is not pad_2
    assert [t.widestring_index for t in reopened.texts] == [0, 1]


def test_remove_primitive_requires_edit_mode(source: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.find_footprint("FP_A")
    with pytest.raises(RuntimeError, match="edit_footprint"):
        fp.remove_primitive(fp.tracks[0])


def test_new_primitives_follow_altium_conventions(source: Path, tmp_path: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.edit_footprint("FP_A")
    fp.add_track((40, 30), (-40, 30), width_mils=4, layer="MECHANICAL1")
    fp.add_arc(center_mils=(0, 0), radius_mils=8, start_angle_degrees=0,
               end_angle_degrees=360, width_mils=4, layer="MECHANICAL1")
    fp.add_text(text=".Designator", position_mils=(0, 0), height_mils=19.685,
                stroke_width_mils=2.953, layer="MECHANICAL1", text_justification=5)
    out = tmp_path / "conventions.PcbLib"
    library.save(out)
    reopened = AltiumPcbLib(out).find_footprint("FP_A")

    track = reopened.tracks[-1]
    assert (track.start_x, track.start_y) < (track.end_x, track.end_y)
    assert track.polygon_index == 0xFFFF and reopened.arcs[-1].polygon_index == 0xFFFF

    text = next(t for t in reopened.texts if t.text_content == ".Designator")
    assert text.stroke_width == 29530
    # Values from the same string placed natively in Altium (0.5 mm high, centred at the origin).
    assert text.textbox_rect_width == pytest.approx(2026918, abs=20)
    assert text.textbox_rect_height == pytest.approx(321437, abs=20)
    assert (text.x, text.y) == (pytest.approx(-983931, abs=20), pytest.approx(-65595, abs=20))
    assert (text.snap_point_x, text.snap_point_y) == (0, 0)
    assert text.is_justification_valid and not text.is_designator


def test_rotated_justified_text_turns_about_the_anchor(source: Path, tmp_path: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.edit_footprint("FP_A")
    fp.add_text(text=".Designator", position_mils=(100, 50), height_mils=19.685, rotation_degrees=90,
                stroke_width_mils=2.953, layer="MECHANICAL1", text_justification=5)
    out = tmp_path / "rotated.PcbLib"
    library.save(out)
    text = next(t for t in AltiumPcbLib(out).find_footprint("FP_A").texts if t.text_content == ".Designator")
    # The unrotated offset from X/Y to the centre (above), turned 90 degrees.
    assert (text.x - 1000000, text.y - 500000) == (pytest.approx(65595, abs=20), pytest.approx(-983931, abs=20))
    assert (text.snap_point_x, text.snap_point_y) == (1000000, 500000)
    assert text.rotation == 90
