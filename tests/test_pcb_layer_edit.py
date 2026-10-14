"""Moving existing primitives to another layer (altium_pcb_layer_edit): every stored copy of the layer
changes together, nothing else in the record does, and placed rectangles move as a whole."""

from pathlib import Path

import pytest

from altium_monkey import AltiumPcbLib
from altium_monkey.altium_pcb_layer_edit import (
    PcbLayerEditError,
    footprint_smart_unions,
    move_primitives_to_layer,
)
from altium_monkey.altium_pcb_layer_ref import PcbLayerRef
from altium_monkey.altium_record_properties_patch import patch_properties_text

RECTANGLE = (
    "SELECTION<EQ>FALSE<Pipe>LAYER<EQ>MECHANICAL11<Pipe>LOCKED<EQ>FALSE<Pipe>UNIONINDEX<EQ>3"
    "<Pipe>X1<EQ>49897.5mil<Pipe>Y1<EQ>49947.5mil<Pipe>X2<EQ>50102.5mil<Pipe>Y2<EQ>50052.5mil"
    "<Pipe>ROTATION<EQ>0.00000000000000E+0000<Pipe>UNIONTYPE<EQ>9<Pipe>FUNIONINDEX<EQ>3"
)


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    library = AltiumPcbLib()
    fp = library.add_footprint("FP")
    fp.add_track((-80, -40), (80, -40), width_mils=5, layer="MECHANICAL13")
    fp.add_arc(center_mils=(0, 0), radius_mils=20, start_angle_degrees=0, end_angle_degrees=360,
               width_mils=5, layer="MECHANICAL13")
    fp.add_fill(corner1_mils=(-10, -10), corner2_mils=(10, 10), layer="MECHANICAL13")
    fp.add_text(text=".Designator", position_mils=(0, 60), height_mils=30, layer="MECHANICAL1")
    fp.add_region(outline_points_mils=[(-30, -30), (30, -30), (30, 30), (-30, 30)], layer="MECHANICAL1")
    fp.add_extruded_3d_body(outline_points_mils=[(-30, -30), (30, -30), (30, 30), (-30, 30)],
                            layer="MECHANICAL5", overall_height_mils=40)
    for start, end in (((-100, -50), (100, -50)), ((100, -50), (100, 50)),
                       ((-100, 50), (100, 50)), ((-100, -50), (-100, 50))):
        fp.add_track(start, end, width_mils=5, layer="MECHANICAL11")
    fp.parameters["SMARTUNIONSSTORAGE"] = "1"
    fp.parameters["SMARTUNION_ITEM0"] = RECTANGLE
    path = tmp_path / "source.PcbLib"
    library.save(path)
    return path


def _reload(library: AltiumPcbLib, tmp_path: Path, name: str = "out.PcbLib"):
    out = tmp_path / name
    library.save(out)
    return AltiumPcbLib(out).footprints[0]


def test_every_layer_copy_moves_including_mechanical_above_16(source: Path, tmp_path: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.footprints[0]
    target = PcbLayerRef.mechanical(19)
    moved = move_primitives_to_layer(
        fp, [fp.tracks[0], fp.arcs[0], fp.fills[0], fp.texts[0], fp.regions[0], fp.component_bodies[0]],
        target,
    )
    assert moved == 6

    fp = _reload(library, tmp_path)
    for p in (fp.tracks[0], fp.arcs[0], fp.fills[0], fp.texts[0], fp.regions[0], fp.component_bodies[0]):
        assert p.layer_ref().token == "MECHANICAL19"
        assert int(p.layer) == 72  # legacy byte for every mechanical layer above 16
    for p in (fp.tracks[0], fp.arcs[0], fp.fills[0]):
        assert p.v7_layer_id == target.v7_saved_layer_id
    assert fp.texts[0].barcode_layer_v7 == target.v7_saved_layer_id
    assert fp.regions[0].v7_layer == "MECHANICAL19"
    assert fp.component_bodies[0].v7_layer == "MECHANICAL19"


def test_region_and_body_properties_change_only_the_layer(source: Path, tmp_path: Path) -> None:
    before = AltiumPcbLib(source).footprints[0]
    library = AltiumPcbLib(source)
    fp = library.footprints[0]
    move_primitives_to_layer(fp, [fp.regions[0], fp.component_bodies[0]], "MECHANICAL3")
    after = _reload(library, tmp_path)

    for old, new in ((before.regions[0], after.regions[0]), (before.component_bodies[0], after.component_bodies[0])):
        old_segments = old._properties_raw.decode("latin-1").split("|")
        new_segments = new._properties_raw.decode("latin-1").split("|")
        assert "V7_LAYER=MECHANICAL3" in new_segments
        assert [s for s in new_segments if not s.startswith("V7_LAYER=")] == [
            s for s in old_segments if not s.startswith("V7_LAYER=")
        ]


def test_patch_keeps_formatting_order_and_repeated_keys() -> None:
    raw = b"V7_LAYER=MECHANICAL5|NAME= |ARCRESOLUTION=0.5mil|CAVITYHEIGHT=0mil|ARCRESOLUTION=0.5mil\x00"
    built_then = "V7_LAYER=MECHANICAL5|NAME= |ARCRESOLUTION=0.5000mil|CAVITYHEIGHT=0.0000mil"
    built_now = "V7_LAYER=MECHANICAL6|NAME= |ARCRESOLUTION=0.5000mil|CAVITYHEIGHT=0.0000mil|NEW=1"
    assert patch_properties_text(raw, built_then, built_now) == (
        b"V7_LAYER=MECHANICAL6|NAME= |ARCRESOLUTION=0.5mil|CAVITYHEIGHT=0mil|ARCRESOLUTION=0.5mil|NEW=1\x00"
    )
    assert patch_properties_text(raw, built_then, "V7_LAYER=MECHANICAL6") is None


def test_placed_rectangle_moves_with_its_smart_union(source: Path, tmp_path: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.footprints[0]
    (union,) = footprint_smart_unions(fp)
    assert [fp.tracks.index(t) for t in union.members] == [1, 2, 3, 4]

    move_primitives_to_layer(fp, union.members, "MECHANICAL1")
    fp = _reload(library, tmp_path)
    assert "LAYER<EQ>MECHANICAL1<Pipe>" in fp.parameters["SMARTUNION_ITEM0"]
    assert fp.parameters["SMARTUNION_ITEM0"] == RECTANGLE.replace("MECHANICAL11", "MECHANICAL1")
    assert {t.layer_ref().token for t in fp.tracks[1:]} == {"MECHANICAL1"}


def test_moving_part_of_a_rectangle_is_refused_and_changes_nothing(source: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.footprints[0]
    with pytest.raises(PcbLayerEditError):
        move_primitives_to_layer(fp, [fp.tracks[0], fp.tracks[1]], "MECHANICAL1")
    assert fp.tracks[0].layer_ref().token == "MECHANICAL13"
    assert fp.tracks[1].layer_ref().token == "MECHANICAL11"
    assert fp.parameters["SMARTUNION_ITEM0"] == RECTANGLE


def test_other_primitives_on_the_rectangle_layer_leave_the_union_alone(source: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.footprints[0]
    move_primitives_to_layer(fp, [fp.tracks[0]], "MECHANICAL11")
    move_primitives_to_layer(fp, [fp.tracks[0]], "MECHANICAL3")
    assert fp.parameters["SMARTUNION_ITEM0"] == RECTANGLE


def test_pads_are_refused(source: Path) -> None:
    library = AltiumPcbLib(source)
    fp = library.edit_footprint("FP")
    pad = fp.add_pad(designator="1", position_mils=(0, 0), width_mils=40, height_mils=60, layer="TOP")
    with pytest.raises(PcbLayerEditError):
        move_primitives_to_layer(fp, [pad], "BOTTOM")
