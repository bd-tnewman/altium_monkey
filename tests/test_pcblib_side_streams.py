"""PcbLib footprint side data that points at records by position, and footprint storage lookup.

CustomShapes: each entry's PRIMITIVEINDEX is the 0-based position of its (custom) pad among all of the
footprint's records, as Altium writes it, so it has to follow the pad when records are added or removed.

SectionKeys: when a long footprint name truncates to another footprint's name, Altium stores one of the
two under a different storage name, records the choice in SectionKeys, and can swap them between saves.
"""

import re
import struct
from pathlib import Path

from altium_monkey import AltiumPcbLib
from altium_monkey.altium_ole import AltiumOleFile, AltiumOleWriter
from altium_monkey.altium_pcblib_sections import PcbLibSectionKeyEntry, PcbLibSectionKeys


def _streams(path: Path) -> dict[str, bytes]:
    with AltiumOleFile(str(path)) as ole:
        return {"/".join(p): ole.openstream(p) for p in ole.listdir(streams=True, storages=False)}


def _write(path: Path, streams: dict[str, bytes]) -> Path:
    writer = AltiumOleWriter()
    for name, data in streams.items():
        writer.add_stream(name, data)
    writer.write(path)
    return path


def _custom_shapes_library(path: Path) -> Path:
    library = AltiumPcbLib()
    fp = library.add_footprint("CUSTOM")
    fp.add_pad(designator="1", position_mils=(-100, 0), width_mils=40, height_mils=60, layer="TOP")
    fp.add_custom_pad(designator="2", position_mils=(100, 0),
                      outline_points_mils=[(-40, -40), (40, -40), (40, 40), (-40, 40)])
    library.save(path)
    anchor = next(i for i, r in enumerate(AltiumPcbLib(path).footprints[0].primitives)
                  if getattr(r, "designator", "") == "2")
    body = f"|PRIMITIVEINDEX={anchor}|S0.LAYER=TOP|S0.XSIZE=10000|S0.SHAPEKIND=3\x00".encode()
    streams = _streams(path)
    streams["CUSTOM/CustomShapes"] = struct.pack("<II", 1, len(body)) + body
    return _write(path, streams)


def _custom_shape_target(path: Path) -> object:
    raw = _streams(path)["CUSTOM/CustomShapes"]
    index = int(re.search(rb"\|PRIMITIVEINDEX=(\d+)", raw).group(1))
    return AltiumPcbLib(path).footprints[0].primitives[index]


def test_custom_shapes_follow_the_pad_when_records_are_added_and_removed(tmp_path: Path) -> None:
    source = _custom_shapes_library(tmp_path / "source.PcbLib")
    assert getattr(_custom_shape_target(source), "designator", None) == "2"

    library = AltiumPcbLib(source)
    edit = library.edit_footprint("CUSTOM")
    edit.add_arc(center_mils=(0, 0), radius_mils=10, start_angle_degrees=0, end_angle_degrees=360,
                 width_mils=4, layer="MECHANICAL1")
    library.save(tmp_path / "with_arc.PcbLib")
    assert type(AltiumPcbLib(tmp_path / "with_arc.PcbLib").footprints[0].primitives[0]).__name__ == "AltiumPcbArc"
    assert getattr(_custom_shape_target(tmp_path / "with_arc.PcbLib"), "designator", None) == "2"

    library = AltiumPcbLib(tmp_path / "with_arc.PcbLib")
    edit = library.edit_footprint("CUSTOM")
    edit.remove_primitive(edit.arcs[0])
    library.save(tmp_path / "arc_removed.PcbLib")
    assert _streams(tmp_path / "arc_removed.PcbLib")["CUSTOM/CustomShapes"] == _streams(source)["CUSTOM/CustomShapes"]


def test_unedited_custom_shapes_keep_their_bytes(tmp_path: Path) -> None:
    source = _custom_shapes_library(tmp_path / "source.PcbLib")
    AltiumPcbLib(source).save(tmp_path / "resaved.PcbLib")
    assert _streams(tmp_path / "resaved.PcbLib")["CUSTOM/CustomShapes"] == _streams(source)["CUSTOM/CustomShapes"]


SHORT = "CONN_TEST_COMBICON_16_1_M_V_5.0"          # 31 characters: the longest plain storage name
LONG = SHORT + "_LOCK"                             # truncates to SHORT


def _colliding_library(path: Path) -> tuple[Path, str]:
    library = AltiumPcbLib()
    short = library.add_footprint(SHORT)
    for i in range(2):
        short.add_pad(designator=str(i + 1), position_mils=(i * 100, 0), width_mils=40, height_mils=60, layer="TOP")
    long = library.add_footprint(LONG)
    for i in range(3):
        long.add_pad(designator=str(i + 1), position_mils=(i * 100, 0), width_mils=40, height_mils=60, layer="TOP")
    library.save(path)
    keys = PcbLibSectionKeys.from_bytes(_streams(path)["SectionKeys"]).to_mapping()
    assert keys.get(LONG) not in (None, SHORT)
    return path, keys[LONG]


def _pads_by_name(path: Path) -> dict[str, tuple[int, str]]:
    return {fp.name: (len(fp.pads), fp.parameters.get("PATTERN")) for fp in AltiumPcbLib(path).footprints}


def test_section_keys_decide_storage_when_names_collide(tmp_path: Path) -> None:
    path, other = _colliding_library(tmp_path / "plain.PcbLib")
    assert _pads_by_name(path) == {SHORT: (2, SHORT), LONG: (3, LONG)}

    # Altium's other layout: the long name in the plain storage, the short name under the other key
    streams = {}
    for name, data in _streams(path).items():
        top, _, rest = name.partition("/")
        swapped = {SHORT: other, other: SHORT}.get(top, top) if rest else top
        streams[f"{swapped}/{rest}" if rest else name] = data
    streams["SectionKeys"] = PcbLibSectionKeys(entries=(
        PcbLibSectionKeyEntry(full_name=SHORT, ole_key=other),
        PcbLibSectionKeyEntry(full_name=LONG, ole_key=SHORT),
    )).to_bytes()
    swapped_path = _write(tmp_path / "swapped.PcbLib", streams)
    assert _pads_by_name(swapped_path) == {SHORT: (2, SHORT), LONG: (3, LONG)}

    AltiumPcbLib(swapped_path).save(tmp_path / "resaved.PcbLib")
    assert _pads_by_name(tmp_path / "resaved.PcbLib") == {SHORT: (2, SHORT), LONG: (3, LONG)}
