from altium_monkey import AltiumSchLib
from altium_monkey.altium_schlib_container import (
    _parse_section_keys,
    _SchLibBudget,
    _SchLibReadLimits,
)
from altium_monkey.altium_utilities import create_stream_from_records


def _section_keys(pairs: list[tuple[str, str]]) -> dict[str, str]:
    record = {"KeyCount": str(len(pairs))}
    for index, (libref, key) in enumerate(pairs):
        record[f"LibRef{index}"] = libref
        record[f"SectionKey{index}"] = key
    payload = create_stream_from_records([record])
    return _parse_section_keys(payload, _SchLibBudget(_SchLibReadLimits())).by_libref


def test_section_key_with_slash_maps_to_altium_storage_name() -> None:
    # Altium writes the key with the LibRef's characters and names the storage with '/' replaced by '_'
    # (Arena_Connectors.SchLib: "CON/ZIF, 22pin, CSI2, Molex, 50" -> storage "CON_ZIF, 22pin, CSI2, Molex, 50").
    keys = _section_keys([
        ("CON/ZIF, 22pin, CSI2, Molex, 5034802200", "CON/ZIF, 22pin, CSI2, Molex, 50"),
        ("XCVR_MICROCHIP_MCP2558FDT-H/MNY", "XCVR_MICROCHIP_MCP2558FDT-H/MNY"),
        ("PLAIN", "PLAIN_KEY"),
    ])
    assert keys == {
        "CON/ZIF, 22pin, CSI2, Molex, 5034802200": "CON_ZIF, 22pin, CSI2, Molex, 50",
        "XCVR_MICROCHIP_MCP2558FDT-H/MNY": "XCVR_MICROCHIP_MCP2558FDT-H_MNY",
        "PLAIN": "PLAIN_KEY",
    }


def test_get_symbol_by_libreference() -> None:
    library = AltiumSchLib()
    symbol = library.add_symbol("CON_ZIF", original_name="CON/ZIF")
    assert library.get_symbol("CON_ZIF") is symbol
    assert library.get_symbol("CON/ZIF") is symbol
    assert library.get_symbol("missing") is None


def test_symbol_svg_reports_where_the_origin_lands() -> None:
    import re

    library = AltiumSchLib()
    symbol = library.add_symbol("R")
    symbol.add_line(0, 0, 300, -100)            # mils; the render is in 10-mil units
    origin: dict = {}
    svg = library.symbol_to_svg("R", origin_out=origin)
    assert set(origin) == {"width", "height", "x", "y"}
    ends = [tuple(float(v) for v in m) for m in re.findall(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg)]
    assert (origin["x"], origin["y"], origin["x"] + 30, origin["y"] + 10) in ends
    assert library.symbol_to_svg("R") == svg
