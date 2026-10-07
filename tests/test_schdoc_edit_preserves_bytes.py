"""Editing one SchDoc object must not re-encode untouched records."""

from pathlib import Path

from altium_monkey.altium_ole import AltiumOleFile
from altium_monkey.altium_schdoc import AltiumSchDoc
from altium_monkey.altium_schdoc_container import _record_frames

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "examples/assets/projects/simple_hierchical/parent.SchDoc"
)


def _fileheader_frames(path: Path) -> tuple[bytes, ...]:
    with AltiumOleFile(path) as ole:
        return _record_frames(ole.openstream("FileHeader"))


def test_edit_keeps_untouched_record_bytes(tmp_path: Path) -> None:
    original = _fileheader_frames(FIXTURE)
    # The fixture uses Altium's 0x8E list separator (in pins) and the UTF-8
    # broken bar (in %UTF8% fields); neither may be rewritten.
    assert any(b"\x8e" in frame for frame in original)
    assert any(b"\xc2\xa6" in frame for frame in original)

    doc = AltiumSchDoc(FIXTURE)
    component = doc.components[0]
    component.design_item_id = "EDITED-ITEM"
    out = tmp_path / "edited.SchDoc"
    doc.save(out)

    edited = _fileheader_frames(out)
    assert len(edited) == len(original)
    changed = [i for i, (a, b) in enumerate(zip(original, edited)) if a != b]
    assert len(changed) == 1
    assert b"DesignItemId=EDITED-ITEM" in edited[changed[0]]
    assert AltiumSchDoc(out).components[0].design_item_id == "EDITED-ITEM"


def test_untouched_save_is_byte_identical(tmp_path: Path) -> None:
    out = tmp_path / "copy.SchDoc"
    AltiumSchDoc(FIXTURE).save(out)
    assert _fileheader_frames(out) == _fileheader_frames(FIXTURE)


def test_new_footprint_link_uses_altium_field_order(tmp_path: Path) -> None:
    doc = AltiumSchDoc(FIXTURE)
    impl = next(
        o for o in doc.all_objects if type(o).__name__ == "AltiumSchImplementation"
    )
    impl.model_name = "FP_NEW"
    impl.model_datafiles = [("Lib.PcbLib", "FP_NEW", "PCBLib")]
    impl._sync_legacy_datafile_view()
    out = tmp_path / "relinked.SchDoc"
    doc.save(out)

    frame = next(f for f in _fileheader_frames(out) if b"ModelName=FP_NEW" in f)
    # Same order Altium Designer writes when the link is edited natively.
    assert (
        b"|ModelName=FP_NEW|ModelType=PCBLIB|DatafileCount=1|ModelDatafile0=Lib.PcbLib"
        b"|ModelDatafileEntity0=FP_NEW|ModelDatafileKind0=PCBLib|IsCurrent=T|"
    ) in frame


UTF8_DESCRIPTION_FIXTURE = (
    Path(__file__).resolve().parents[1] / "examples/assets/projects/loz-old-man/POWER.SchDoc"
)


def test_component_description_keeps_utf8_sidecar(tmp_path: Path) -> None:
    doc = AltiumSchDoc(UTF8_DESCRIPTION_FIXTURE)
    component = next(
        c for c in doc.components if "%UTF8%ComponentDescription" in c._source_record[0]
    )
    expected = component._source_record[0]["%UTF8%ComponentDescription"]
    assert component.component_description == expected

    # Edit a different component so the document is re-serialized.
    other = next(c for c in doc.components if c is not component)
    other.design_item_id = "EDITED-ITEM"
    out = tmp_path / "edited.SchDoc"
    doc.save(out)

    reloaded = AltiumSchDoc(out)
    match = next(
        c for c in reloaded.components if c.unique_id == component.unique_id
    )
    assert match.component_description == expected
    assert "%UTF8%ComponentDescription" in match._source_record[0]
