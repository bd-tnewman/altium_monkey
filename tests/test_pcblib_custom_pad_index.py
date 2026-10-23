"""PcbLib custom pads: a region's PADINDEX is the 1-based position of its pad among ALL of the
footprint's records (as Altium reads and writes it), so it has to follow the pad when records are
added or removed ahead of it. Altium drops the custom shape of a pad whose region points elsewhere."""

from pathlib import Path

from altium_monkey import AltiumPcbLib


def _link(footprint) -> tuple[int, object]:
    region = next(r for r in footprint.regions if (r.properties or {}).get("PADINDEX"))
    index = int(region.properties["PADINDEX"])
    return index, footprint.primitives[index - 1]


def _custom_pad_library(path: Path) -> Path:
    library = AltiumPcbLib()
    fp = library.add_footprint("CUSTOM")
    fp.add_pad(designator="1", position_mils=(-100, 0), width_mils=40, height_mils=60, layer="TOP")
    fp.add_custom_pad(designator="2", position_mils=(100, 0),
                      outline_points_mils=[(-40, -40), (40, -40), (40, 40), (-40, 40)])
    fp.add_track((-150, -80), (150, -80), width_mils=5, layer="TOPOVERLAY")
    library.save(path)
    return path


def test_padindex_follows_the_pad_when_records_are_added_and_removed(tmp_path: Path) -> None:
    source = _custom_pad_library(tmp_path / "source.PcbLib")
    fp = AltiumPcbLib(source).footprints[0]
    index, record = _link(fp)
    assert getattr(record, "designator", None) == "2" and record.custom_shape is not None

    library = AltiumPcbLib(source)
    edit = library.edit_footprint("CUSTOM")
    edit.add_arc(center_mils=(0, 0), radius_mils=10, start_angle_degrees=0, end_angle_degrees=360,
                 width_mils=4, layer="MECHANICAL1")
    library.save(tmp_path / "with_arc.PcbLib")
    fp = AltiumPcbLib(tmp_path / "with_arc.PcbLib").footprints[0]
    moved_index, record = _link(fp)
    assert type(fp.primitives[0]).__name__ == "AltiumPcbArc"     # the arc lands ahead of the pads
    assert moved_index == index + 1
    assert getattr(record, "designator", None) == "2" and record.custom_shape is not None

    library = AltiumPcbLib(tmp_path / "with_arc.PcbLib")
    edit = library.edit_footprint("CUSTOM")
    edit.remove_primitive(edit.arcs[0])
    library.save(tmp_path / "arc_removed.PcbLib")
    fp = AltiumPcbLib(tmp_path / "arc_removed.PcbLib").footprints[0]
    back_index, record = _link(fp)
    assert back_index == index
    assert getattr(record, "designator", None) == "2" and record.custom_shape is not None


def test_padindex_counts_records_not_pads_when_reading(tmp_path: Path) -> None:
    source = _custom_pad_library(tmp_path / "source.PcbLib")
    library = AltiumPcbLib(source)
    edit = library.edit_footprint("CUSTOM")
    edit.add_arc(center_mils=(0, 0), radius_mils=10, start_angle_degrees=0, end_angle_degrees=360,
                 width_mils=4, layer="MECHANICAL1")
    library.save(tmp_path / "with_arc.PcbLib")
    fp = AltiumPcbLib(tmp_path / "with_arc.PcbLib").footprints[0]
    assert [p.designator for p in fp.pads if p.custom_shape is not None] == ["2"]
