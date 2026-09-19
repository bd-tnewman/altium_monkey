from pathlib import Path

import pytest

from altium_monkey import AltiumPcbLib, AltiumSchLib


def test_schlib_owner_rename_roundtrip(tmp_path: Path) -> None:
    library = AltiumSchLib()
    symbol = library.add_symbol("OLD", original_name="Old Semantic")

    assert library.rename_symbol(symbol, "NEW", original_name="New Semantic") is symbol
    output = tmp_path / "renamed.SchLib"
    library.save(output)

    reopened = AltiumSchLib(output)
    assert reopened.symbols[0].name == "NEW"
    assert reopened.symbols[0].original_name == "New Semantic"


def test_pcblib_owner_rename_roundtrip_and_validation(tmp_path: Path) -> None:
    library = AltiumPcbLib()
    footprint = library.add_footprint("OLD")

    with pytest.raises(ValueError, match="printable ASCII"):
        library.rename_footprint(footprint, "P\N{LATIN SMALL LETTER A WITH DIAERESIS}D")
    assert library.rename_footprint(footprint, "NEW") is footprint
    output = tmp_path / "renamed.PcbLib"
    library.save(output)

    reopened = AltiumPcbLib(output)
    assert reopened.footprint_names() == ["NEW"]
