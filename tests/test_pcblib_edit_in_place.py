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
    assert (2, 0, pad_2_guid) in guids
    assert len(guids) == len(reopened._record_order) + 1
    unique_id_2 = unique_ids.split(b"PRIMITIVEINDEX=1|PRIMITIVEOBJECTID=Pad|UNIQUEID=")[1][:8]
    assert b"PRIMITIVEINDEX=0|PRIMITIVEOBJECTID=Pad|UNIQUEID=" + unique_id_2 in after[
        "FP_A/UniqueIDPrimitiveInformation/Data"
    ]
    assert reopened.pads[0] is not pad_2


def test_remove_primitive_requires_edit_mode(source: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.find_footprint("FP_A")
    with pytest.raises(RuntimeError, match="edit_footprint"):
        fp.remove_primitive(fp.tracks[0])
