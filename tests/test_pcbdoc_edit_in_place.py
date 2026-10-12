"""PcbDoc saves keep untouched streams/records byte-identical; component library links can be edited in place."""

from pathlib import Path

import pytest

from altium_monkey import AltiumPcbDoc
from altium_monkey.altium_ole import AltiumOleFile

FIXTURE = Path(__file__).resolve().parents[1] / "examples/assets/projects/m2_emmc/m2_emmc.PcbDoc"


def _streams(path: Path) -> dict[str, bytes]:
    with AltiumOleFile(path) as ole:
        return {"/".join(p): ole.openstream(p) for p in ole.listdir(streams=True, storages=False)}


def test_untouched_save_is_stream_identical(tmp_path: Path) -> None:
    out = tmp_path / "copy.PcbDoc"
    AltiumPcbDoc.from_file(FIXTURE).save(out)
    assert _streams(out) == _streams(FIXTURE)


def test_source_library_edit_changes_only_that_component(tmp_path: Path) -> None:
    doc = AltiumPcbDoc.from_file(FIXTURE)
    target = doc.components[0]
    changed = target.set_source_library(
        library_identifier="ArenaDB.DbLib/Capacitor",
        footprint_library=r"C:\Libraries\Arena_Discretes.PcbLib",
    )
    assert changed == ["SOURCECOMPLIBRARYIDENTIFIER", "SOURCEFOOTPRINTLIBRARY"]
    assert target.set_source_library(library_identifier="ArenaDB.DbLib/Capacitor") == []
    out = tmp_path / "edited.PcbDoc"
    doc.save(out)

    before, after = _streams(FIXTURE), _streams(out)
    assert sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)) == [
        "Components6/Data"
    ]
    reloaded = AltiumPcbDoc.from_file(out)
    edited = reloaded.components[0]
    assert edited.source_component_library_identifier == "ArenaDB.DbLib/Capacitor"
    assert edited.source_footprint_library == r"C:\Libraries\Arena_Discretes.PcbLib"
    assert [c.to_frame() for c in reloaded.components[1:]] == [
        c._source_frame for c in AltiumPcbDoc.from_file(FIXTURE).components[1:]
    ]


@pytest.mark.parametrize("value", ["ArenaDB.DbLib/Capacitor"])
def test_edited_record_keeps_field_order(value: str) -> None:
    doc = AltiumPcbDoc.from_file(FIXTURE)
    comp = doc.components[0]
    keys_before = [p.split(b"=")[0] for p in comp._source_frame[4:].rstrip(b"\x00").split(b"|") if p]
    comp.set_source_library(library_identifier=value)
    keys_after = [p.split(b"=")[0] for p in comp.to_frame()[4:].rstrip(b"\x00").split(b"|") if p]
    assert keys_after[: len(keys_before)] == keys_before
