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
